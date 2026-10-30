from __future__ import annotations

import json
import tempfile
import unittest
import wave
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from home_podcast.local_audio import assemble_local_speech
from home_podcast.storytelling_duration import (
    require_story_audio_duration, require_story_audio_frames,
    require_story_text_budget, story_duration_limit_ms, story_duration_preflight,
)
from home_podcast.storytelling_quality import content_digest, require_current_speech_jobs
from tests.storytelling_test_support import write_review


def _config(root: Path = Path(".")) -> SimpleNamespace:
    return SimpleNamespace(
        production_mode="self_narrated_storytelling", target_minutes_max=5,
        episodes_dir=root / "narrations", audio_dir=root / "audio",
    )


def _wav(path: Path, frames: int, rate: int = 10) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(rate)
        audio.writeframes(b"\x00\x00" * frames)


class StorytellingDurationTests(unittest.TestCase):
    def test_only_storytelling_receives_the_limit(self):
        self.assertEqual(story_duration_limit_ms(_config()), 300_000)
        config = _config()
        config.production_mode = "podcast"
        self.assertIsNone(story_duration_limit_ms(config))
        self.assertEqual(require_story_audio_frames(config, 6000, 10), 600_000)

    def test_bad_limits_are_rejected(self):
        for maximum in (0, -1, float("nan"), float("inf")):
            with self.subTest(maximum=maximum):
                config = _config()
                config.target_minutes_max = maximum
                with self.assertRaises(ValueError):
                    story_duration_limit_ms(config)

    def test_preflight_counts_pauses_and_performance_headroom(self):
        adaptation = {"sections": [{"text": "home " * 650, "pause_after_ms": 6000}]}
        report = story_duration_preflight(_config(), adaptation)
        self.assertEqual(report["spoken_words"], 650)
        self.assertEqual(report["explicit_pause_ms"], 6000)
        self.assertEqual(report["estimated_duration_ms"], 299572)
        self.assertFalse(report["requires_condensation"])
        adaptation["sections"][0]["pause_after_ms"] = 6500
        original = json.dumps(adaptation)
        with self.assertRaisesRegex(ValueError, "prepare one reviewed condensed version"):
            require_story_text_budget(_config(), adaptation)
        self.assertEqual(json.dumps(adaptation), original)

    def test_negative_pauses_are_not_a_duration_shortcut(self):
        with self.assertRaisesRegex(ValueError, "negative"):
            story_duration_preflight(_config(), {"sections": [{"pause_after_ms": -1}]})

    def test_exact_boundary_and_one_extra_sample(self):
        self.assertEqual(require_story_audio_frames(_config(), 300 * 24000, 24000), 300000)
        with self.assertRaisesRegex(ValueError, "300-second limit"):
            require_story_audio_frames(_config(), 300 * 24000 + 1, 24000)
        self.assertEqual(require_story_audio_frames(_config(), 24001, 24000), 1001)

    def test_wav_duration_uses_frames_without_ffprobe(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "take.wav"
            _wav(path, 3000)
            with patch("home_podcast.storytelling_duration.subprocess.run") as run:
                self.assertEqual(require_story_audio_duration(_config(), path), 300000)
                run.assert_not_called()
            _wav(path, 3001)
            with self.assertRaisesRegex(ValueError, "Not accepted or promoted"):
                require_story_audio_duration(_config(), path)
            self.assertTrue(path.is_file())

    def test_compressed_audio_is_measured_and_not_rounded_down(self):
        with patch("home_podcast.storytelling_duration.shutil.which", return_value="ffprobe"), \
             patch("home_podcast.storytelling_duration.subprocess.run") as run:
            run.return_value = SimpleNamespace(stdout="300.000000\n")
            self.assertEqual(require_story_audio_duration(_config(), Path("take.mp3")), 300000)
            run.return_value = SimpleNamespace(stdout="300.000001\n")
            with self.assertRaisesRegex(ValueError, "300-second limit"):
                require_story_audio_duration(_config(), Path("take.mp3"))
            for unknown in ("N/A", "NaN", "Infinity", "0"):
                run.return_value = SimpleNamespace(stdout=unknown)
                with self.assertRaises(ValueError):
                    require_story_audio_duration(_config(), Path("take.mp3"))

    def test_legacy_cached_jobs_cannot_bypass_limit_but_short_auditions_can(self):
        with tempfile.TemporaryDirectory() as temporary:
            config = _config(Path(temporary))
            directory = config.episodes_dir / "n-1"
            directory.mkdir(parents=True)
            text = "I remember the road home. " * 150
            adaptation = {"narration_id": "n-1", "sections": [{"section_id": "001", "text": text}]}
            path = directory / "adaptation.json"
            path.write_text(json.dumps(adaptation), encoding="utf-8")
            write_review(directory)
            original = path.read_bytes()
            production = [{"narration_id": "n-1", "section_id": "001", "text": text,
                           "adaptation_sha256": content_digest(adaptation)}]
            with self.assertRaisesRegex(ValueError, "Story duration budget exceeded"):
                require_current_speech_jobs(config, production, audition=False)
            audition = [{"source_narration_id": "n-1", "source_section_id": "001",
                         "reference_text": "I remember the road home.",
                         "adaptation_sha256": content_digest(adaptation)}]
            require_current_speech_jobs(config, audition, audition=True)
            self.assertEqual(path.read_bytes(), original)

    def test_overlong_assembly_keeps_master_and_cached_take(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = _config(root)
            directory = config.episodes_dir / "n-1"
            directory.mkdir(parents=True)
            adaptation = {"narration_id": "n-1", "sections": [{
                "section_id": "001", "text": "I remember the road home.", "pause_after_ms": 2000}]}
            (directory / "adaptation.json").write_text(json.dumps(adaptation), encoding="utf-8")
            write_review(directory)
            cached = root / "cached.wav"
            _wav(cached, 2990)
            master = config.audio_dir / "n-1" / "voices-only.wav"
            _wav(master, 100)
            original = master.read_bytes()
            jobs_path = root / "jobs.jsonl"
            jobs_path.write_text(json.dumps({
                "narration_id": "n-1", "section_id": "001", "section_index": 0,
                "text": adaptation["sections"][0]["text"],
                "adaptation_sha256": content_digest(adaptation), "pause_after_ms": 2000,
                "casting_card": {"voice": {"voice_id": "fixed"}}, "output_audio": str(cached),
            }) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "300-second limit"):
                assemble_local_speech(config, jobs_path, "n-1")
            self.assertEqual(master.read_bytes(), original)
            self.assertTrue(cached.is_file())
            self.assertFalse(master.with_suffix(".tmp.wav").exists())


if __name__ == "__main__":
    unittest.main()
