"""CPU-only regression checks for bass-heavy backgrounds and faded loop joins."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import wave

from home_podcast.ambient_audibility import (
    DEFAULTS, check_loop_floor, inspect_file, inspect_samples, load_policy,
    loop_material, validate_policy,
)
from home_podcast.ambient_batch import fit_ambient

NUMERICS = all(importlib.util.find_spec(name) for name in ("numpy", "scipy"))


class AmbientAudibilityPolicyTests(unittest.TestCase):
    def test_unknown_invalid_nonfinite_and_boolean_numbers_are_rejected(self):
        for value in ([], {"unknown": 1}, {"enabled": "yes"}, {"contract_version": True},
                      {"minimum_midrange_energy_fraction": float("nan")},
                      {"maximum_mono_loss_db": float("inf")}, {"loop_edge_drop_db": True},
                      {"maximum_loop_edge_trim_fraction": .9}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_policy(value)

    def test_legacy_projects_without_policy_remain_disabled(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertFalse(load_policy(Path(directory))["enabled"])
        self.assertTrue(validate_policy({})["enabled"])

    def test_import_is_model_free_and_does_not_load_numerical_stack(self):
        subprocess.run([sys.executable, "-c",
                        "import sys; import home_podcast.ambient_audibility; "
                        "assert not {'torch','onnxruntime','qwen_tts','numpy','scipy'} & set(sys.modules)"],
                       check=True, capture_output=True)


@unittest.skipUnless(NUMERICS, "NumPy and SciPy unavailable")
class AmbientAudibilityTests(unittest.TestCase):
    @staticmethod
    def tone(frequency, rate=16000):
        import numpy as np
        x = .1 * np.sin(2 * np.pi * frequency * np.arange(rate * 4) / rate)
        return np.column_stack((x, x))

    def test_bass_heavy_background_is_held_even_with_appreciable_rms(self):
        low = inspect_samples(self.tone(200), 16000, DEFAULTS)
        audible = inspect_samples(self.tone(500), 16000, DEFAULTS)
        self.assertIn("insufficient_small_speaker_midrange", low["quality_findings"])
        self.assertLess(low["midrange_energy_fraction"], .001)
        self.assertGreater(audible["midrange_energy_fraction"], .99)
        self.assertFalse(audible["quality_findings"])

    def test_stereo_cancellation_is_held_without_downmixing_original(self):
        import numpy as np
        x = self.tone(500)
        x[:, 1] *= -1
        original = x.copy()
        checked = inspect_samples(x, 16000, DEFAULTS)
        self.assertIn("excessive_mono_cancellation", checked["quality_findings"])
        np.testing.assert_array_equal(x, original)

    def test_silence_and_malformed_audio_are_not_accepted(self):
        import numpy as np
        checked = inspect_samples(np.zeros((16000, 2)), 16000, DEFAULTS)
        self.assertIn("insufficient_small_speaker_midrange", checked["quality_findings"])
        for x, rate in ((np.zeros(20), 16000), (np.zeros((0, 2)), 16000),
                        (np.full((20, 2), float("nan")), 16000), (np.ones((20, 2)), 100)):
            with self.subTest(rate=rate, shape=x.shape), self.assertRaises(ValueError):
                inspect_samples(x, rate, DEFAULTS)

    def test_finished_pcm16_file_is_screened(self):
        import numpy as np
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ambient.wav"
            with wave.open(str(path), "wb") as stream:
                stream.setparams((2, 2, 16000, 0, "NONE", "not compressed"))
                stream.writeframes(np.rint(self.tone(500) * 32767).astype("<i2").tobytes())
            self.assertFalse(inspect_file(path, DEFAULTS)["quality_findings"])

    def test_generated_edge_fades_do_not_create_quiet_loop_join(self):
        import numpy as np
        rate = 8000
        source = np.full((rate * 120, 2), .1, np.float32)
        source[:rate * 2] *= (10 ** np.linspace(-60, 0, rate * 2))[:, None]
        source[-rate * 8:] *= (10 ** np.linspace(0, -60, rate * 8))[:, None]
        original = source.copy()
        frames = rate * 175
        legacy = fit_ambient(source, frames, rate * 4)
        self.assertIn("loop_or_body_level_dip", check_loop_floor(legacy, rate, DEFAULTS)["quality_findings"])
        checked = fit_ambient(source, frames, rate * 4, audibility_policy=DEFAULTS, sample_rate=rate)
        self.assertEqual(checked.shape, (frames, 2))
        self.assertFalse(check_loop_floor(checked, rate, DEFAULTS)["quality_findings"])
        np.testing.assert_array_equal(source, original)
        _, bounds = loop_material(source, rate, DEFAULTS)
        self.assertGreater(bounds["source_start_frame"], 0)
        self.assertLess(bounds["source_end_frame"], len(source))
        self.assertTrue(bounds["original_recording_unchanged"])

    def test_stable_short_and_non_looped_material_is_preserved(self):
        import numpy as np
        source = np.full((8000 * 10 + 13, 2), .1, np.float32)
        selected, bounds = loop_material(source, 8000, DEFAULTS)
        np.testing.assert_array_equal(selected, source)
        self.assertEqual(bounds["source_end_frame"], len(source))
        np.testing.assert_array_equal(fit_ambient(source, 1000, 500, audibility_policy=DEFAULTS,
                                                sample_rate=8000), source[:1000])
        short = source[:100]
        selected, _ = loop_material(short, 8000, DEFAULTS)
        np.testing.assert_array_equal(selected, short)

    def test_interior_hole_is_held_not_automatically_flattened(self):
        import numpy as np
        source = np.full((8000 * 30, 2), .1, np.float32)
        source[8000 * 12:8000 * 18] *= .001
        with self.assertRaisesRegex(ValueError, "quiet join or unstable body"):
            fit_ambient(source, 8000 * 65, 8000 * 4, audibility_policy=DEFAULTS, sample_rate=8000)


if __name__ == "__main__":
    unittest.main()
