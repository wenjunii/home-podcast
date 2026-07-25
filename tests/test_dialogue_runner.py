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

from home_podcast.dialogue_runner import (
    generate_dialogue_audition_jobs,
    generate_dialogue_episode_jobs,
    prepare_dialogue_audition_jobs,
    prepare_dialogue_episode_jobs,
)
from home_podcast.providers import (
    ElevenLabsDialogueResponse,
    ElevenLabsDialogueTimestampResponse,
)


class DialogueRunnerTests(unittest.TestCase):
    def test_prepares_contextual_variants_and_reports_dry_run_cost(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = _config(root)
            audition_path, cast_path = _write_contracts(root)
            jobs_path = root / "work" / "dialogue-jobs.jsonl"

            prepared = prepare_dialogue_audition_jobs(
                config,
                audition_path,
                cast_path,
                jobs_path,
            )
            report = generate_dialogue_audition_jobs(config, jobs_path)

            self.assertEqual(prepared["segments"], 2)
            self.assertEqual(prepared["variants"], 2)
            self.assertEqual(report["api_calls_pending"], 2)
            self.assertEqual(
                report["estimated_credits"],
                prepared["total_characters"],
            )
            jobs = [
                json.loads(line)
                for line in jobs_path.read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(
                jobs[0]["inputs"][0]["text"],
                "[curious] A recovered home?",
            )
            self.assertEqual(jobs[1]["settings"]["stability"], 0)

    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg is required")
    def test_generates_normalized_cached_dialogue_without_saving_secret(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = _config(root)
            audition_path, cast_path = _write_contracts(root)
            jobs_path = root / "work" / "dialogue-jobs.jsonl"
            prepare_dialogue_audition_jobs(
                config,
                audition_path,
                cast_path,
                jobs_path,
            )
            response = ElevenLabsDialogueResponse(
                audio=_wav_bytes(),
                content_type="audio/mpeg",
                request_id="request-dialogue",
                character_cost="31",
            )
            with (
                patch.dict(os.environ, {"ELEVENLABS_API_KEY": "test-secret"}),
                patch(
                    "home_podcast.dialogue_runner.ElevenLabsDialogueClient.generate",
                    return_value=response,
                ) as generate,
            ):
                report = generate_dialogue_audition_jobs(
                    config,
                    jobs_path,
                    execute=True,
                    max_credits=1000,
                    variant="natural",
                )
                cached = generate_dialogue_audition_jobs(
                    config,
                    jobs_path,
                    execute=True,
                    max_credits=0,
                    variant="natural",
                )

            job = json.loads(jobs_path.read_text(encoding="utf-8").splitlines()[0])
            output_audio = Path(job["output_audio"])
            with wave.open(str(output_audio), "rb") as audio:
                self.assertEqual(audio.getframerate(), 48000)
                self.assertEqual(audio.getnchannels(), 2)
            self.assertTrue(Path(job["preview_mp3"]).is_file())
            self.assertEqual(report["actual_character_cost"], 31)
            self.assertEqual(cached["cached"], 1)
            generate.assert_called_once()
            metadata = "".join(
                path.read_text(encoding="utf-8", errors="ignore")
                for path in root.rglob("*.json")
            )
            self.assertNotIn("test-secret", metadata)

    def test_prepares_movement_aware_episode_chunks_and_cost(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = _config(root)
            script_path, cast_path, performance_path = _write_episode_contracts(root)
            jobs_path = root / "work" / "episode-dialogue-jobs.jsonl"

            prepared = prepare_dialogue_episode_jobs(
                config,
                script_path,
                cast_path,
                performance_path,
                jobs_path,
                variant="creative-plus",
            )
            report = generate_dialogue_episode_jobs(config, jobs_path)

            self.assertEqual(prepared["segments"], 4)
            self.assertEqual(prepared["movements"], 2)
            self.assertEqual(prepared["chunks"], 2)
            self.assertEqual(prepared["performance_variant"], "creative-plus")
            self.assertEqual(report["api_calls_pending"], 2)
            self.assertEqual(report["estimated_credits"], prepared["total_characters"])
            jobs = [
                json.loads(line)
                for line in jobs_path.read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(jobs[0]["inputs"][0]["text"], "A recovered home?")
            self.assertEqual(
                jobs[0]["inputs"][0]["tts_text"],
                "[curious] A recovered home?",
            )
            self.assertEqual(jobs[1]["chunk_id"], "chunk-002")

    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg is required")
    def test_generates_timestamped_episode_chunks_resumably(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = _config(root)
            script_path, cast_path, performance_path = _write_episode_contracts(root)
            jobs_path = root / "work" / "episode-dialogue-jobs.jsonl"
            prepare_dialogue_episode_jobs(
                config,
                script_path,
                cast_path,
                performance_path,
                jobs_path,
                variant="creative-plus",
            )
            response = ElevenLabsDialogueTimestampResponse(
                audio=_wav_bytes(),
                content_type="audio/mpeg",
                request_id="request-timestamped-dialogue",
                character_cost="40",
                voice_segments=[
                    {
                        "dialogue_input_index": 0,
                        "start_time_seconds": 0,
                        "end_time_seconds": 0.45,
                    },
                    {
                        "dialogue_input_index": 1,
                        "start_time_seconds": 0.5,
                        "end_time_seconds": 0.95,
                    },
                ],
                alignment={"characters": ["A"]},
                normalized_alignment=None,
            )
            with (
                patch.dict(os.environ, {"ELEVENLABS_API_KEY": "test-secret"}),
                patch(
                    "home_podcast.dialogue_runner."
                    "ElevenLabsDialogueClient.generate_with_timestamps",
                    return_value=response,
                ) as generate,
            ):
                report = generate_dialogue_episode_jobs(
                    config,
                    jobs_path,
                    execute=True,
                    max_credits=1000,
                )
                cached = generate_dialogue_episode_jobs(
                    config,
                    jobs_path,
                    execute=True,
                    max_credits=0,
                )

            self.assertEqual(report["generated"], 2)
            self.assertEqual(report["actual_character_cost"], 80)
            self.assertTrue(report["render_ready"])
            self.assertEqual(cached["cached"], 2)
            self.assertEqual(generate.call_count, 2)
            jobs = [
                json.loads(line)
                for line in jobs_path.read_text(encoding="utf-8").splitlines()
            ]
            for job in jobs:
                self.assertTrue(Path(job["output_audio"]).is_file())
                timing = json.loads(
                    Path(job["timestamp_data"]).read_text(encoding="utf-8")
                )
                self.assertNotIn("audio_base64", timing)
            metadata = "".join(
                path.read_text(encoding="utf-8", errors="ignore")
                for path in root.rglob("*.json")
            )
            self.assertNotIn("test-secret", metadata)


def _config(root: Path) -> SimpleNamespace:
    return SimpleNamespace(
        dialogue_provider={
            "type": "elevenlabs_dialogue",
            "endpoint": "https://api.example.test/v1/text-to-dialogue",
            "model": "eleven_v3",
            "api_key_env": "ELEVENLABS_API_KEY",
            "timeout_seconds": 1,
            "max_attempts": 1,
            "output_format": "mp3_44100_128",
            "language_code": "en",
            "credits_per_character": 1,
            "usd_per_thousand_characters": 0.1,
        },
        audio_dir=root / "audio",
        work_dir=root / "work",
    )


def _write_contracts(root: Path) -> tuple[Path, Path]:
    audition = {
        "contract_version": 2,
        "episode_id": "test-dialogue",
        "cast_episode_id": "test-episode",
        "variants": [
            {"id": "natural", "settings": {"stability": 0.5}},
            {"id": "creative", "settings": {"stability": 0}},
        ],
        "segments": [
            {
                "segment_id": "one",
                "speaker": "curious_guide",
                "text": "A recovered home?",
                "delivery": {"tone": "curious"},
                "pronunciation": {},
            },
            {
                "segment_id": "two",
                "speaker": "archive_nerd",
                "text": "Let's look closer.",
                "delivery": {"tone": "warmly"},
                "pronunciation": {},
            },
        ],
    }
    cast = {
        "contract_version": 1,
        "episode_id": "test-episode",
        "provider": "elevenlabs",
        "selection": "test",
        "status": "test",
        "hosts": [
            {
                "id": "curious_guide",
                "person_id": "maya",
                "display_name": "Maya",
                "voice_name": "Bella",
                "voice_id": "voice-1",
                "accent": "american",
            },
            {
                "id": "archive_nerd",
                "person_id": "theo",
                "display_name": "Theo",
                "voice_name": "Roger",
                "voice_id": "voice-2",
                "accent": "american",
            },
            {
                "id": "connector",
                "person_id": "lina",
                "display_name": "Lina",
                "voice_name": "Lily",
                "voice_id": "voice-3",
                "accent": "british",
            },
        ],
    }
    audition_path = root / "audition.json"
    cast_path = root / "cast.json"
    audition_path.write_text(json.dumps(audition), encoding="utf-8")
    cast_path.write_text(json.dumps(cast), encoding="utf-8")
    return audition_path, cast_path


def _write_episode_contracts(root: Path) -> tuple[Path, Path, Path]:
    _, cast_path = _write_contracts(root)
    cast = json.loads(cast_path.read_text(encoding="utf-8"))
    cast["episode_id"] = "test-episode"
    cast_path.write_text(json.dumps(cast), encoding="utf-8")
    script = {
        "contract_version": 1,
        "episode_id": "test-episode",
        "title": "Test episode",
        "segments": [
            {
                "segment_id": "m1-s001",
                "speaker": "curious_guide",
                "text": "A recovered home?",
                "delivery": {"tone": "curious"},
                "source_story_ids": ["story-1"],
            },
            {
                "segment_id": "m1-s002",
                "speaker": "archive_nerd",
                "text": "Let's look closer.",
                "delivery": {"tone": "warmly"},
                "source_story_ids": ["story-1"],
            },
            {
                "segment_id": "m2-s001",
                "speaker": "connector",
                "text": "Now the next movement.",
                "delivery": {"tone": "animated"},
                "source_story_ids": ["story-2"],
            },
            {
                "segment_id": "m2-s002",
                "speaker": "curious_guide",
                "text": "And one final thought.",
                "delivery": {"tone": "reflective"},
                "source_story_ids": ["story-2"],
            },
        ],
    }
    performance = {
        "contract_version": 2,
        "episode_id": "test-performance",
        "variants": [
            {
                "id": "creative-plus",
                "settings": {
                    "stability": 0,
                    "similarity_boost": 0.75,
                    "style": 0.35,
                    "use_speaker_boost": True,
                    "speed": 1,
                },
            }
        ],
    }
    script_path = root / "script.json"
    performance_path = root / "performance.json"
    script_path.write_text(json.dumps(script), encoding="utf-8")
    performance_path.write_text(json.dumps(performance), encoding="utf-8")
    return script_path, cast_path, performance_path


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
