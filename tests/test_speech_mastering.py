from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
import wave
from pathlib import Path

from home_podcast.speech_mastering import (
    DEFAULTS, MasteringQualityHold, PEAK_RIDING_VERSION, level_samples, load_settings,
    master_speech, master_speech_for_playback, read_wave, sha256, validate_settings,
)

NUMERICS = all(importlib.util.find_spec(name) for name in ("numpy", "scipy"))


class MasteringSettingsTests(unittest.TestCase):
    def test_invalid_settings_rejected(self):
        for value in ({"enabled": "yes"}, {"peak_ceiling_dbfs": 0},
                      {"maximum_boost_db": 100}, {"target_speech_rms_dbfs": float("nan")},
                      {"unrecognized": 1}, {"contract_version": True}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_settings(value)

    def test_legacy_projects_do_not_enable_mastering_implicitly(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertFalse(load_settings(Path(folder))["enabled"])

    def test_import_is_lightweight(self):
        script = ("import sys; import home_podcast.speech_mastering; "
                  "assert not ({'numpy','scipy','torch','qwen_tts','ollama'} & set(sys.modules))")
        subprocess.run([sys.executable, "-c", script], check=True, capture_output=True)


@unittest.skipUnless(NUMERICS, "optional audio-mastering dependencies unavailable")
class SpeechMasteringTests(unittest.TestCase):
    def setUp(self):
        import numpy as np
        self.np = np
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.rate = 8000
        self.samples = self.tone(20)
        self.source = self.root / "raw.wav"
        self.write_wave(self.source, self.samples)

    def tearDown(self):
        self.temp.cleanup()

    def tone(self, seconds, amplitude=0.08):
        time = self.np.arange(int(seconds * self.rate)) / self.rate
        return amplitude * self.np.sin(2 * self.np.pi * 220 * time)

    def write_wave(self, path, samples):
        with wave.open(str(path), "wb") as stream:
            stream.setnchannels(1)
            stream.setsampwidth(2)
            stream.setframerate(self.rate)
            stream.writeframes(self.np.rint(samples * 32768).astype("<i2").tobytes())

    def test_corrects_twenty_db_drift_without_retiming(self):
        original = self.tone(50) * 10 ** (self.np.linspace(0, -20, 50 * self.rate) / 20)
        result, report = level_samples(original, self.rate, DEFAULTS)
        self.assertEqual(len(result), len(original))
        self.assertGreater(abs(report["before"]["end_minus_start_db"]), 12)
        self.assertLess(abs(report["after"]["end_minus_start_db"]), 1)
        self.assertEqual(report["quality_findings"], [])
        knots = [point["gain_db"] for point in report["gain_knots"]]
        self.assertLessEqual(max(abs(self.np.diff(knots))) / 0.25, 1.0001)

    def test_volume_drift_switch(self):
        original = self.tone(40) * 10 ** (self.np.linspace(0, -18, 40 * self.rate) / 20)
        _, report = level_samples(original, self.rate, {**DEFAULTS, "correct_volume_drift": False})
        self.assertIn("remaining_start_to_end_volume_difference", report["quality_findings"])
        self.assertAlmostEqual(report["gain_min_db"], report["gain_max_db"])

    def test_silence_does_not_drive_up_gain(self):
        original = self.np.concatenate((self.tone(10), self.np.zeros(self.rate * 12), self.tone(10)))
        result, report = level_samples(original, self.rate, DEFAULTS)
        self.assertTrue(self.np.all(result[self.rate * 10:self.rate * 22] == 0))
        self.assertLess(report["gain_max_db"] - report["gain_min_db"], 0.02)

    def test_all_silence_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "No measurable speech"):
            level_samples(self.np.zeros(self.rate * 2), self.rate, DEFAULTS)

    def test_peak_protection(self):
        signal = self.samples.copy()
        signal[self.rate * 5] = 0.97
        result, report = level_samples(signal, self.rate, DEFAULTS)
        self.assertLessEqual(report["four_times_oversampled_peak_dbfs"], -1.49)
        self.assertLess(self.np.max(self.np.abs(result)), 1)

    def test_slow_peak_riding_preserves_pauses_and_gain_speed(self):
        signal = self.tone(40)
        signal[self.rate * 15] = 0.97
        signal[self.rate * 24:self.rate * 26] = 0
        _, plain = level_samples(signal, self.rate, DEFAULTS)
        self.assertIn("speech_level_outside_target_tolerance", plain["quality_findings"])
        result, report = level_samples(signal, self.rate, DEFAULTS, peak_safe_riding=True)
        self.assertEqual(report["quality_findings"], [])
        self.assertEqual(len(result), len(signal))
        self.assertTrue(self.np.all(result[self.rate * 24:self.rate * 26] == 0))
        self.assertTrue(report["slow_peak_aware_gain"])
        self.assertFalse(report["fast_compression_or_limiting"])
        self.assertLessEqual(report["four_times_oversampled_peak_dbfs"], -1.49)
        knots = [point["gain_db"] for point in report["gain_knots"]]
        self.assertLessEqual(max(abs(self.np.diff(knots))) / 0.25, 1.0001)

    def test_peak_fallback_keeps_held_copy_and_reuses_successful_copy(self):
        signal = self.tone(40)
        signal[self.rate * 15] = 0.97
        self.write_wave(self.source, signal)
        original = sha256(self.source)
        with self.assertRaises(MasteringQualityHold) as held:
            master_speech(self.source, self.root / "mastered", DEFAULTS)
        held_path = Path(held.exception.receipt["audio_path"])
        held_hash = sha256(held_path)
        ready = master_speech_for_playback(self.source, self.root / "mastered", DEFAULTS)
        self.assertEqual(ready["identity"]["version"], PEAK_RIDING_VERSION)
        self.assertEqual(ready["status"], "ready")
        self.assertEqual(sha256(self.source), original)
        self.assertEqual(sha256(held_path), held_hash)
        self.assertNotEqual(str(held_path), ready["audio_path"])
        self.assertEqual(ready, master_speech_for_playback(self.source, self.root / "mastered", DEFAULTS))
        self.assertEqual(ready["tts_calls"], 0)

    def test_peak_fallback_does_not_bypass_other_holds_or_corruption(self):
        self.write_wave(self.source, self.tone(20, amplitude=0.0008))
        settings = {**DEFAULTS, "maximum_boost_db": 1}
        with self.assertRaises(MasteringQualityHold):
            master_speech_for_playback(self.source, self.root / "mastered", settings)
        self.assertEqual(len(list((self.root / "mastered").glob("*/mastering.json"))), 1)
        receipt_path = next((self.root / "mastered").glob("*/mastering.json"))
        output = receipt_path.parent / "voices-leveled.wav"
        output.write_bytes(b"preserve corruption for review")
        with self.assertRaisesRegex(ValueError, "Changed mastering cache"):
            master_speech_for_playback(self.source, self.root / "mastered", settings)
        self.assertEqual(output.read_bytes(), b"preserve corruption for review")

    def test_cache_preserves_raw_and_exact_frames(self):
        original = sha256(self.source)
        result = master_speech(self.source, self.root / "mastered", DEFAULTS)
        audio, rate = read_wave(Path(result["audio_path"]))
        self.assertEqual(len(audio), len(self.samples))
        self.assertEqual(rate, self.rate)
        self.assertEqual(sha256(self.source), original)
        self.assertEqual(result, master_speech(self.source, self.root / "mastered", DEFAULTS))
        self.assertEqual(result["tts_calls"], 0)

    def test_changed_setting_gets_new_copy_without_new_tts(self):
        first = master_speech(self.source, self.root / "mastered", DEFAULTS)
        second = master_speech(self.source, self.root / "mastered",
                               {**DEFAULTS, "target_speech_rms_dbfs": -24})
        self.assertNotEqual(first["audio_path"], second["audio_path"])
        self.assertTrue(Path(first["audio_path"]).exists())

    def test_tampered_cache_never_overwritten(self):
        result = master_speech(self.source, self.root / "mastered", DEFAULTS)
        output = Path(result["audio_path"])
        output.write_bytes(b"do not overwrite")
        with self.assertRaisesRegex(ValueError, "Changed mastering cache"):
            master_speech(self.source, self.root / "mastered", DEFAULTS)
        self.assertEqual(output.read_bytes(), b"do not overwrite")

    def test_asr_must_match_audio(self):
        report = self.root / "asr.json"
        report.write_text(json.dumps({"audio_sha256": "wrong", "segments": []}))
        with self.assertRaisesRegex(ValueError, "ASR report does not match"):
            master_speech(self.source, self.root / "mastered", DEFAULTS, asr_path=report)

    def test_audio_bound_asr_supported(self):
        report = self.root / "asr.json"
        report.write_text(json.dumps({"audio_sha256": sha256(self.source), "segments": [
            {"words": [{"start_s": 0, "end_s": 20}]}]}))
        result = master_speech(self.source, self.root / "mastered", DEFAULTS, asr_path=report)
        self.assertEqual(result["metrics"]["activity_basis"], "audio_bound_asr_words")

    def test_held_master_is_not_accepted_on_retry(self):
        self.write_wave(self.source, self.tone(20, amplitude=0.0008))
        settings = {**DEFAULTS, "maximum_boost_db": 1}
        for _ in range(2):
            with self.assertRaisesRegex(ValueError, "held"):
                master_speech(self.source, self.root / "mastered", settings)

    def test_disabled_returns_original_without_creating_files(self):
        result = master_speech(self.source, self.root / "mastered", {**DEFAULTS, "enabled": False})
        self.assertEqual(result["audio_path"], str(self.source))
        self.assertFalse((self.root / "mastered").exists())

    def test_over_five_minutes_rejected(self):
        with self.assertRaisesRegex(ValueError, "runtime"):
            level_samples(self.np.zeros(self.rate * 301), self.rate, DEFAULTS)


if __name__ == "__main__":
    unittest.main()
