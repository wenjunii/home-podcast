from __future__ import annotations

from array import array
import math
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import wave
from unittest.mock import patch

from home_podcast.ambient_mastering import (
    DEFAULTS, AmbientQualityHold, find_ffmpeg, load_settings, master_ambient,
    measure_loudness, sha, validate_settings, PEAK_SAFE_VERSION,
)


class AmbientSettingsTests(unittest.TestCase):
    def test_invalid_settings_rejected(self):
        for value in ({"enabled": "yes"}, {"contract_version": True},
                      {"asset_target_lufs": float("nan")}, {"stem_true_peak_dbfs": 0},
                      {"highpass_hz": 1000}, {"unknown": 1}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_settings(value)

    def test_legacy_projects_unchanged(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertFalse(load_settings(Path(folder))["enabled"])

    def test_import_does_not_load_media_models_or_numerical_stack(self):
        subprocess.run([sys.executable, "-c", "import sys; import home_podcast.ambient_mastering; "
                        "assert not ({'torch','qwen_tts','ollama','numpy','scipy'} & set(sys.modules))"],
                       check=True, capture_output=True)

    def test_only_pre_execution_dll_failure_is_retried(self):
        from home_podcast.ambient_mastering import _spawn
        failure = subprocess.CompletedProcess(["ffprobe"], 3221225794, "", "")
        success = subprocess.CompletedProcess(["ffprobe"], 0, "ok", "")
        with patch("home_podcast.ambient_mastering.subprocess.run", side_effect=[failure, success]) as run:
            self.assertIs(_spawn(["ffprobe"]), success)
            self.assertEqual(run.call_count, 2)
        decode_error = subprocess.CompletedProcess(["ffmpeg"], 1, "", "bad audio")
        with patch("home_podcast.ambient_mastering.subprocess.run", return_value=decode_error) as run:
            self.assertIs(_spawn(["ffmpeg"]), decode_error)
            run.assert_called_once()


@unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg unavailable")
class AmbientMasteringTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.ffmpeg = find_ffmpeg(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def tone(self, name, amplitude=.1, frequency=500, transient=False):
        path = self.root / name
        rate, frames = 16000, 16000 * 5 + 123
        values = array("h")
        for index in range(frames):
            value = amplitude * math.sin(2 * math.pi * frequency * index / rate)
            if transient and rate < index < rate + 160:
                value = .9 * math.sin(2 * math.pi * 500 * index / rate)
            # Opposite-polarity stereo must never be collapsed to mono.
            sample = round(value * 32767)
            values.extend((sample, -sample))
        with wave.open(str(path), "wb") as stream:
            stream.setparams((2, 2, rate, frames, "NONE", "not compressed"))
            stream.writeframes(values.tobytes())
        return path

    def test_quiet_and_loud_assets_reach_same_lufs_preserving_frames_and_originals(self):
        results = []
        for name, amplitude in (("quiet.wav", .005), ("loud.wav", .2)):
            source = self.tone(name, amplitude)
            checksum = sha(source)
            receipt = master_ambient(source, DEFAULTS, root=self.root)
            self.assertEqual(sha(source), checksum)
            self.assertEqual(receipt["frames"], 16000 * 5 + 123)
            self.assertEqual(receipt["channels"], 2)
            self.assertFalse(receipt["quality_findings"])
            self.assertLessEqual(receipt["metrics"]["true_peak_dbfs"], -2.85)
            self.assertEqual(master_ambient(source, DEFAULTS, root=self.root), receipt)
            results.append(receipt["metrics"]["integrated_lufs"])
        self.assertLess(abs(results[0] - results[1]), .7)

    def test_subbass_only_asset_is_held_even_after_loudness_matching(self):
        source = self.tone("rumble.wav", frequency=30)
        checksum = sha(source)
        with self.assertRaises(AmbientQualityHold) as caught:
            master_ambient(source, DEFAULTS, root=self.root)
        self.assertIn("insufficient_audible_band_energy", caught.exception.receipt["quality_findings"])
        self.assertEqual(sha(source), checksum)
        with self.assertRaises(AmbientQualityHold):
            master_ambient(source, DEFAULTS, root=self.root)

    def test_transients_are_peak_limited_without_shortening_audio(self):
        source = self.tone("transient.wav", amplitude=.008, transient=True)
        receipt = master_ambient(source, DEFAULTS, root=self.root)
        self.assertAlmostEqual(receipt["metrics"]["integrated_lufs"], -24, delta=.7)
        self.assertLessEqual(receipt["metrics"]["true_peak_dbfs"], -2.85)
        self.assertEqual(receipt["frames"], 16000 * 5 + 123)

    def test_cache_corruption_is_not_repaired_by_overwriting(self):
        source = self.tone("cache.wav")
        receipt = master_ambient(source, DEFAULTS, root=self.root)
        output = Path(receipt["audio_path"])
        with output.open("ab") as stream:
            stream.write(b"corrupt")
        with self.assertRaisesRegex(ValueError, "cache changed"):
            master_ambient(source, DEFAULTS, root=self.root)

    def test_stem_and_solo_use_separate_central_targets(self):
        source = self.tone("stem.wav")
        stem = master_ambient(source, DEFAULTS, root=self.root, role="stem")
        solo = master_ambient(source, DEFAULTS, root=self.root, role="solo")
        self.assertNotEqual(stem["cache_key"], solo["cache_key"])
        self.assertAlmostEqual(stem["metrics"]["integrated_lufs"], -30, delta=.7)
        self.assertAlmostEqual(solo["metrics"]["integrated_lufs"], -23, delta=.7)

    def test_peak_only_overshoot_is_corrected_in_versioned_derivative(self):
        from home_podcast.ambient_mastering import _run
        source = self.tone("peak-only.wav")
        original = sha(source)
        legacy = master_ambient(source, DEFAULTS, root=self.root, role="solo")
        before = sha(Path(legacy["audio_path"]))
        readings = [{"integrated_lufs": -23.0, "true_peak_dbfs": -2.36, "loudness_range_lu": 5.3},
                    {"integrated_lufs": -23.02, "true_peak_dbfs": -3.3, "loudness_range_lu": 5.3}]
        with patch("home_podcast.ambient_mastering.measure_loudness", side_effect=readings) as measured, \
                patch("home_podcast.ambient_mastering._run", wraps=_run) as commands:
            result = master_ambient(source, DEFAULTS, root=self.root, role="solo", revision=PEAK_SAFE_VERSION)
        self.assertEqual(measured.call_count, 2)
        self.assertTrue(any("alimiter=" in " ".join(c.args[0]) for c in commands.call_args_list))
        self.assertFalse(result["quality_findings"])
        self.assertNotEqual(result["cache_key"], legacy["cache_key"])
        self.assertEqual(result["identity"]["version"], PEAK_SAFE_VERSION)
        self.assertEqual(sha(source), original)
        self.assertEqual(sha(Path(legacy["audio_path"])), before)
        self.assertEqual(master_ambient(source, DEFAULTS, root=self.root, role="solo"), legacy)

    def test_silence_is_not_amplified_into_an_accepted_asset(self):
        source = self.tone("silence.wav", amplitude=0)
        checksum = sha(source)
        with self.assertRaisesRegex(ValueError, "Silent or unmeasurable"):
            master_ambient(source, DEFAULTS, root=self.root)
        self.assertEqual(sha(source), checksum)


if __name__ == "__main__":
    unittest.main()
