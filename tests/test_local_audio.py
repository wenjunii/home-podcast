from __future__ import annotations

import json
import tempfile
import unittest
import wave
from unittest.mock import patch
from pathlib import Path

from home_podcast.config import ProjectConfig
from home_podcast.local_audio import (
    assemble_local_speech,
    assemble_local_soundscape_collection,
    generate_local_ambient,
    generate_local_speech,
    prepare_local_ambient,
    prepare_local_speech_jobs,
    prepare_local_voice_audition,
)
from home_podcast.ambient_mastering import DEFAULTS as AMBIENT_DEFAULTS
from home_podcast.providers.qwen_tts import Qwen3TTSLocalRenderer
from home_podcast.storytelling_quality import content_digest
from tests.storytelling_test_support import write_review


class LocalAudioTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / "config").mkdir()
        (self.root / "narrations").mkdir()
        (self.root / "audio").mkdir()
        self.project_path = self.root / "storytelling.json"
        _write_json(
            self.project_path,
            {
                "project_name": "test",
                "primary_language": "en",
                "exports_dir": "exports",
                "catalog_path": "catalog.sqlite3",
                "themes_path": "themes.json",
                "show_bible_path": "show.json",
                "voice_roster_path": "voices.json",
                "episodes_dir": "narrations",
                "work_dir": "work",
                "audio_dir": "audio",
            },
        )
        self.config = ProjectConfig.load(self.project_path)
        self.local_config_path = self.root / "config" / "local.json"
        _write_json(
            self.local_config_path,
            {
                "contract_version": 1,
                "default_profile": "test",
                "profiles": {
                    "test": {
                        "execution_mode": "offline_sequential",
                        "concurrent_gpu_models": 1,
                        "hardware_target": "test",
                        "narration": {
                            "audition_model": "Qwen/audition",
                            "production_model": "Qwen/base",
                            "audition_max_characters": 180,
                        },
                        "ambient": {
                            "model": "medium",
                            "minimum_specific_span_ms": 15000,
                        },
                    }
                },
                "audition_voice_designs": [
                    {
                        "voice_id": "voice-a",
                        "display_name": "A",
                        "gender_presentation": "feminine",
                        "age_presentation": "adult",
                        "accent_profile": "Accent A",
                        "personality_tags": ["warm"],
                        "tts_instruction": "Warm and natural.",
                        "seed": 10,
                    },
                    {
                        "voice_id": "voice-b",
                        "display_name": "B",
                        "gender_presentation": "masculine",
                        "age_presentation": "adult",
                        "accent_profile": "Accent B",
                        "personality_tags": ["curious"],
                        "tts_instruction": "Curious and natural.",
                        "seed": 20,
                    },
                ],
            },
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_audition_plan_is_diverse_and_dry_run_only(self) -> None:
        index_path = self._make_narrations(2)
        plan_path = self.root / "work" / "audition.json"
        report = prepare_local_voice_audition(
            self.config,
            index_path,
            plan_path,
            profile_name="test",
            local_config_path=self.local_config_path,
        )
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        self.assertEqual(report["local_model_calls_pending"], 2)
        self.assertEqual(len({job["source_narration_id"] for job in plan["jobs"]}), 2)
        self.assertEqual(report["network_calls"], 0)

    def test_speech_jobs_are_cached_by_section_and_voice(self) -> None:
        index_path = self._make_narrations(1)
        reference = self.root / "audio" / "reference.wav"
        _write_wav(reference, frames=100)
        roster_path = self.root / "config" / "roster.json"
        _write_json(
            roster_path,
            {
                "contract_version": 1,
                "manual_assignments": {},
                "candidates": [
                    {
                        "voice_id": "voice-a",
                        "display_name": "A",
                        "reference_audio": "audio/reference.wav",
                        "reference_text": "Reference line.",
                        "gender_presentation": "feminine",
                        "age_presentation": "adult",
                        "accent_profile": "Accent A",
                        "personality_tags": ["warm"],
                        "supported_languages": ["en"],
                        "audition_status": "approved",
                    }
                ],
            },
        )
        jobs_path = self.root / "work" / "speech.jsonl"
        report = prepare_local_speech_jobs(
            self.config,
            index_path,
            roster_path,
            jobs_path,
            profile_name="test",
            local_config_path=self.local_config_path,
        )
        jobs = _read_jsonl(jobs_path)
        self.assertEqual(report["section_jobs"], 2)
        self.assertEqual(len({job["cache_key"] for job in jobs}), 2)
        dry_run = generate_local_speech(
            self.config,
            jobs_path,
            profile_name="test",
            local_config_path=self.local_config_path,
        )
        self.assertEqual(dry_run["local_model_calls_pending"], 2)
        self.assertEqual(dry_run["models_loaded"], 0)

    def test_assemble_writes_timeline_and_captions(self) -> None:
        narration_dir = self.root / "narrations" / "n-1"
        adaptation = {"narration_id": "n-1", "sections": [
            {"section_id": "001", "text": "I remember the first evening."},
            {"section_id": "002", "text": "Then I went home."},
        ]}
        _write_json(narration_dir / "adaptation.json", adaptation)
        write_review(narration_dir)
        audio_a = self.root / "audio" / "a.wav"
        audio_b = self.root / "audio" / "b.wav"
        _write_wav(audio_a, frames=1600)
        _write_wav(audio_b, frames=800)
        jobs_path = self.root / "jobs.jsonl"
        casting = {"voice": {"voice_id": "voice-a"}}
        _write_jsonl(
            jobs_path,
            [
                {
                    "narration_id": "n-1",
                    "section_id": "001",
                    "section_index": 0,
                    "text": "I remember the first evening.",
                    "adaptation_sha256": content_digest(adaptation),
                    "pause_after_ms": 100,
                    "casting_card": casting,
                    "output_audio": str(audio_a),
                },
                {
                    "narration_id": "n-1",
                    "section_id": "002",
                    "section_index": 1,
                    "text": "Then I went home.",
                    "adaptation_sha256": content_digest(adaptation),
                    "pause_after_ms": 0,
                    "casting_card": casting,
                    "output_audio": str(audio_b),
                },
            ],
        )
        report = assemble_local_speech(self.config, jobs_path, "n-1")
        timeline = json.loads(Path(report["timeline"]).read_text(encoding="utf-8"))
        self.assertEqual(len(timeline["segments"]), 2)
        self.assertTrue(Path(report["captions_vtt"]).is_file())

        # Final playback uses the shared mastering result, while the raw
        # assembled take and timeline/caption duration remain available.
        playback = self.root / "audio" / "leveled.wav"
        _write_wav(playback, frames=4000)
        with patch("home_podcast.local_audio.master_speech", return_value={
            "audio_path": str(playback), "cache_key": "master-key", "status": "ready",
        }) as mastering:
            mastered_report = assemble_local_speech(self.config, jobs_path, "n-1")
        mastering.assert_called_once()
        self.assertEqual(mastered_report["voices_audio"], str(playback))
        self.assertNotEqual(mastered_report["raw_voices_audio"], str(playback))
        self.assertEqual(mastered_report["duration_ms"], report["duration_ms"])
        mastered_timeline = json.loads(Path(mastered_report["timeline"]).read_text())
        self.assertEqual(mastered_timeline["voices_audio"], str(playback))
        self.assertEqual(mastered_timeline["speech_mastering_cache_key"], "master-key")

    def test_ambient_plan_is_continuous_and_skips_short_sections(self) -> None:
        narration_dir = self.root / "narrations" / "n-1"
        narration_dir.mkdir(parents=True)
        adaptation_path = narration_dir / "adaptation.json"
        _write_json(
            adaptation_path,
            {
                "narration_id": "n-1",
                "adaptation_notes": [],
                "sections": [
                    {"section_id": "001", "text": "Rain on the garden."},
                    {"section_id": "002", "text": "A brief thought."},
                ],
            },
        )
        timeline_path = self.root / "timeline.json"
        _write_json(
            timeline_path,
            {
                "episode_id": "n-1",
                "narration_id": "n-1",
                "duration_ms": 25000,
                "segments": [
                    {
                        "section_id": "001",
                        "segment_id": "001",
                        "start_ms": 0,
                        "end_ms": 20000,
                    },
                    {
                        "section_id": "002",
                        "segment_id": "002",
                        "start_ms": 20000,
                        "end_ms": 25000,
                    },
                ],
            },
        )
        sound_path = self.root / "sound.json"
        jobs_path = self.root / "ambient.jsonl"
        report = prepare_local_ambient(
            self.config,
            timeline_path,
            adaptation_path,
            sound_path,
            jobs_path,
            profile_name="test",
            local_config_path=self.local_config_path,
        )
        sound = json.loads(sound_path.read_text(encoding="utf-8"))
        self.assertTrue(sound["continuous_background"]["enabled"])
        self.assertEqual(report["specific_layers"], 1)
        self.assertEqual(len(_read_jsonl(jobs_path)), 2)

    def test_qwen_clone_prompt_is_reused_for_same_reference(self) -> None:
        reference = self.root / "reference.wav"
        _write_wav(reference, frames=100)

        class FakeModel:
            def __init__(self) -> None:
                self.prompt_calls = 0

            def create_voice_clone_prompt(self, **kwargs):
                self.prompt_calls += 1
                return ["cached-prompt"]

            def generate_voice_clone(self, **kwargs):
                return [[0.0]], 16000

        renderer = Qwen3TTSLocalRenderer(model_name="test", mode="voice_clone")
        model = FakeModel()
        cast = {
            "language": "en",
            "voice": {
                "reference_audio": str(reference),
                "reference_text": "Reference.",
            },
        }
        renderer._generate(model, {"text": "One."}, cast)
        renderer._generate(model, {"text": "Two."}, cast)
        self.assertEqual(model.prompt_calls, 1)

    def _ambient_fixture(self):
        index = self._make_narrations(1)
        jobs_path = self.root / "work/local-audio/ambient/n-0-jobs.jsonl"
        timeline = self.root / "audio/n-0/timeline.json"
        _write_json(timeline, {"narration_id": "n-0", "episode_id": "n-0", "duration_ms": 25000,
                              "segments": [{"section_id": "001", "segment_id": "001", "start_ms": 0, "end_ms": 20000},
                                           {"section_id": "002", "segment_id": "002", "start_ms": 20000, "end_ms": 25000}]})
        prepare_local_ambient(self.config, timeline, self.root / "narrations/n-0/adaptation.json",
                              self.root / "narrations/n-0/sound-design.json", jobs_path,
                              profile_name="test", local_config_path=self.local_config_path)
        _write_json(self.root / "config/ambient_mastering.json", AMBIENT_DEFAULTS)
        return index, jobs_path

    def test_ambient_dry_run_never_loads_model_or_masters_audio(self):
        _, jobs_path = self._ambient_fixture()
        with patch("home_podcast.local_audio.StableAudio3LocalRenderer.__init__") as model, \
                patch("home_podcast.local_audio.master_ambient") as mastering:
            report = generate_local_ambient(self.config, jobs_path, profile_name="test",
                                             local_config_path=self.local_config_path)
        self.assertEqual(report["local_model_calls_pending"], 2)
        self.assertTrue(report["ambient_mastering"]["enabled"])
        model.assert_not_called()
        mastering.assert_not_called()

    def test_cached_ambient_can_be_leveled_without_loading_model(self):
        _, jobs_path = self._ambient_fixture()
        jobs = _read_jsonl(jobs_path)
        for job in jobs:
            _write_wav(Path(job["output_audio"]), frames=100)
        with patch("home_podcast.local_audio.StableAudio3LocalRenderer.__init__") as model, \
                patch("home_podcast.local_audio.master_ambient", return_value={"audio_path": "finished.wav"}) as mastering:
            report = generate_local_ambient(self.config, jobs_path, execute=True, profile_name="test",
                                             local_config_path=self.local_config_path)
        self.assertEqual(report["local_model_calls_pending"], 0)
        self.assertEqual(report["mastered_assets"], 2)
        self.assertEqual(mastering.call_count, 2)
        model.assert_not_called()

    def test_ambient_assembly_uses_finished_copies_not_raw_jobs(self):
        index, jobs_path = self._ambient_fixture()
        jobs = _read_jsonl(jobs_path)
        original = jobs_path.read_bytes()
        _write_wav(self.root / "audio/n-0/voices-only.wav", frames=100)
        for job in jobs:
            _write_wav(Path(job["output_audio"]), frames=100)
        with patch("home_podcast.local_audio.master_ambient", side_effect=lambda source, *a, **kw: {
                "audio_path": str(source.with_name("finished-" + source.name)), "cache_key": "finished"}), \
                patch("home_podcast.local_audio.render_soundscape_audio", return_value={
                    "duration_ms": 25000, "tracks": {}}) as renderer:
            report = assemble_local_soundscape_collection(self.config, index)
        self.assertEqual(report["rendered"], 1)
        derived_path = renderer.call_args.kwargs["sfx_jobs_path"]
        self.assertNotEqual(derived_path, jobs_path)
        derived = _read_jsonl(derived_path)
        self.assertTrue(all(Path(j["output_audio"]).name.startswith("finished-") for j in derived))
        self.assertEqual(renderer.call_args.kwargs["ambient_mastering_settings"]["stem_target_lufs"], -30)
        self.assertIn("ambient-editions", str(renderer.call_args.args[3]))
        self.assertEqual(jobs_path.read_bytes(), original)

    def _make_narrations(self, count: int) -> Path:
        records = []
        for number in range(count):
            narration_id = f"n-{number}"
            records.append(
                {
                    "narration_id": narration_id,
                    "source_language": "en",
                    "adaptation_language": "en",
                    "primary_theme": f"theme-{number}",
                    "spoken_character_count": 400 + number,
                    "readiness": "ready_for_voice_audition",
                    "identity_constraints": [],
                }
            )
            narration_dir = self.root / "narrations" / narration_id
            narration_dir.mkdir(parents=True)
            _write_json(
                narration_dir / "adaptation.json",
                {
                    "narration_id": narration_id,
                    "adaptation_language": "en",
                    "narrator_profile": {"personality_tags": ["warm"]},
                    "sections": [
                        {
                            "section_id": "001",
                            "text": "I remember the road home. " * 12,
                            "delivery": {"emotion": "warm"},
                            "pause_after_ms": 100,
                        },
                        {
                            "section_id": "002",
                            "text": "Then the rain arrived. " * 10,
                            "delivery": {"emotion": "quiet"},
                            "pause_after_ms": 0,
                        },
                    ],
                },
            )
            write_review(narration_dir)
        index_path = self.root / "index.json"
        _write_json(index_path, {"narrations": records})
        return index_path


def _write_wav(path: Path, *, frames: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16000)
        handle.writeframes(b"\x00\x00" * frames)


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _write_jsonl(path: Path, values: list[dict[str, object]]) -> None:
    path.write_text("".join(json.dumps(value) + "\n" for value in values), encoding="utf-8")


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


if __name__ == "__main__":
    unittest.main()
