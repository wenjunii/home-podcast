from __future__ import annotations

import io
import json
import os
import shutil
import tempfile
import unittest
import wave
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from home_podcast.providers import ElevenLabsSoundEffectResponse
from home_podcast.sfx_runner import generate_sound_effect_jobs


class SoundEffectRunnerTests(unittest.TestCase):
    def test_dry_run_reports_cost_without_credential_or_provider_call(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            jobs_path = _write_jobs(root, [500, 1000])
            with (
                patch.dict(os.environ, {}, clear=True),
                patch(
                    "home_podcast.sfx_runner."
                    "ElevenLabsSoundEffectsClient.generate"
                ) as generate,
            ):
                report = generate_sound_effect_jobs(
                    _config(),
                    jobs_path,
                )
            self.assertEqual(report["pending"], 2)
            self.assertEqual(report["estimated_credits"], 16.5)
            self.assertFalse(report["execution_requested"])
            generate.assert_not_called()

    def test_paid_run_requires_explicit_credit_ceiling(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            jobs_path = _write_jobs(root, [1000])
            with self.assertRaisesRegex(ValueError, "--max-credits"):
                generate_sound_effect_jobs(
                    _config(),
                    jobs_path,
                    execute=True,
                )

    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg is required")
    def test_generates_normalized_wav_then_uses_cache(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            jobs_path = _write_jobs(root, [1000])
            response = ElevenLabsSoundEffectResponse(
                audio=_wav_bytes(),
                content_type="audio/mpeg",
                request_id="request-test",
                character_cost="1",
            )
            with (
                patch.dict(os.environ, {"ELEVENLABS_API_KEY": "test-secret"}),
                patch(
                    "home_podcast.sfx_runner."
                    "ElevenLabsSoundEffectsClient.generate",
                    return_value=response,
                ) as generate,
            ):
                report = generate_sound_effect_jobs(
                    _config(),
                    jobs_path,
                    execute=True,
                    max_credits=11,
                )
                cached_report = generate_sound_effect_jobs(
                    _config(),
                    jobs_path,
                    execute=True,
                    max_credits=0,
                )

            output = Path(json.loads(jobs_path.read_text())["output_audio"])
            self.assertTrue(output.is_file())
            with wave.open(str(output), "rb") as audio:
                self.assertEqual(audio.getframerate(), 48000)
                self.assertEqual(audio.getnchannels(), 2)
            self.assertEqual(report["generated"], 1)
            self.assertTrue(report["completed"])
            self.assertEqual(cached_report["cached"], 1)
            self.assertEqual(cached_report["estimated_credits"], 0)
            generate.assert_called_once()
            all_local_metadata = "".join(
                path.read_text(encoding="utf-8", errors="ignore")
                for path in root.rglob("*.json")
            )
            self.assertNotIn("test-secret", all_local_metadata)

    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg is required")
    def test_recovers_raw_response_without_credential_or_credit_budget(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            jobs_path = _write_jobs(root, [1000])
            job = json.loads(jobs_path.read_text(encoding="utf-8"))
            output = Path(job["output_audio"])
            output.with_suffix(".response.mp3").write_bytes(_wav_bytes())
            with (
                patch.dict(os.environ, {"ELEVENLABS_API_KEY": ""}),
                patch(
                    "home_podcast.sfx_runner."
                    "ElevenLabsSoundEffectsClient.generate"
                ) as generate,
            ):
                report = generate_sound_effect_jobs(
                    _config(),
                    jobs_path,
                    execute=True,
                )
            self.assertTrue(output.is_file())
            self.assertEqual(report["recovered_from_raw_cache"], 1)
            self.assertEqual(report["estimated_credits"], 0)
            generate.assert_not_called()


def _config() -> SimpleNamespace:
    return SimpleNamespace(
        sound_effects_provider={
            "type": "elevenlabs_sound_effects",
            "endpoint": "https://api.example.test/v1/sound-generation",
            "model": "eleven_text_to_sound_v2",
            "api_key_env": "ELEVENLABS_API_KEY",
            "timeout_seconds": 1,
            "max_attempts": 1,
            "prompt_influence": 0.3,
            "credits_per_second": 11,
        }
    )


def _write_jobs(root: Path, durations_ms: list[int]) -> Path:
    jobs_path = root / "jobs.jsonl"
    lines = []
    for index, duration_ms in enumerate(durations_ms, start=1):
        lines.append(
            json.dumps(
                {
                    "contract_version": 1,
                    "episode_id": "test-episode",
                    "cue_id": f"cue-{index}",
                    "provider": "elevenlabs",
                    "model": "eleven_text_to_sound_v2",
                    "prompt": "Quiet paper movement.",
                    "generation_duration_ms": duration_ms,
                    "loop": False,
                    "cache_key": f"key-{index}",
                    "output_audio": str(root / f"cue-{index}.wav"),
                    "cached": False,
                }
            )
        )
    jobs_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return jobs_path


def _wav_bytes() -> bytes:
    stream = io.BytesIO()
    with wave.open(stream, "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(24000)
        output.writeframes(b"\x00\x00" * 24000)
    return stream.getvalue()


if __name__ == "__main__":
    unittest.main()
