"""Portable CPU-only coverage for whole-story offline production safety."""
from __future__ import annotations

import copy
import json
import re
import struct
import subprocess
import sys
import tempfile
import unittest
import wave
from contextlib import nullcontext
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from home_podcast import single_take_audio as audio
from home_podcast.storytelling import create_storytelling_plan, export_storytelling_jobs
from tests.storytelling_test_support import write_review
from tests.test_storytelling import _adaptation, _setup


class SingleTakeAudioTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        config, _, _ = _setup(self.root)
        config = replace(config, target_minutes_max=5)
        create_storytelling_plan(config, "2013-05", self.root / "story-plan.json")
        export_storytelling_jobs(config, self.root / "story-plan.json", self.root / "jobs.jsonl")
        self.source = json.loads((self.root / "jobs.jsonl").read_text(encoding="utf-8"))
        self.adaptation = _adaptation(self.source)
        self.directory = config.episodes_dir / self.adaptation["narration_id"]
        audio.write_json(self.directory / "source-job.json", self.source)
        audio.write_json(self.directory / "adaptation.json", self.adaptation)
        write_review(self.directory)
        self.runner = audio.SingleTakeProduction(config, model_path=self.root / "cached-model")
        self.card = {
            "narration_id": self.adaptation["narration_id"], "speech_seed": 123,
            "voice_label": "Reflective performer", "voice_description": "A warm conversational voice.",
            "performance_direction": "Let the remembered kitchen brighten the voice.",
            "casting_note": "Performer choices, not assertions about the writer.",
            "casting": {key: {"value": value, "basis": "artistic_choice"} for key, value in (
                ("gender_presentation", "feminine"), ("accent", "General American English"),
                ("vocal_age", "adult"), ("personality", "reflective"))},
        }
        self.brief = {"contract_version": 1, "run_id": "test-production", "stories": [self.card]}

    def plan(self):
        self.runner.prepare(self.brief)
        return audio.read(self.runner.paths(self.brief)[0] / "plan.json")

    def take(self, job, *, seconds=2):
        directory = self.runner.job_dir(self.brief, job)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "voices-only.wav"
        with wave.open(str(path), "wb") as stream:
            stream.setparams((1, 2, 100, 0, "NONE", "not compressed"))
            stream.writeframes(struct.pack("<h", 1000) * (100 * seconds))
        audio.write_json(directory / "generation.json", {
            "status": "completed", "narration_id": job["narration_id"], "cache_key": job["cache_key"],
            "duration_ms": seconds * 1000, "wav_sha256": audio.sha(path),
        })
        return directory

    def test_import_does_not_load_models(self):
        result = subprocess.run([sys.executable, "-c", "import sys; import home_podcast.single_take_audio; "
                                 "assert not {'torch','qwen_tts','faster_whisper'} & set(sys.modules)"],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_one_call_covers_whole_story(self):
        job = self.runner.expected_jobs(self.brief)[0]
        model = Mock()
        audio.generate_once(model, job)
        model.generate_voice_design.assert_called_once()
        self.assertEqual(model.generate_voice_design.call_args.kwargs["text"], job["text"])
        self.assertEqual(job["text"], "\n\n".join(s["text"] for s in self.adaptation["sections"]))
        self.assertTrue(job["non_streaming_mode"])
        self.assertFalse(job["automatic_voice_approval"])

    def test_seed_is_part_of_cache_identity(self):
        first = self.runner.expected_jobs(self.brief)[0]["cache_key"]
        self.card["speech_seed"] += 1
        self.assertNotEqual(first, self.runner.expected_jobs(self.brief)[0]["cache_key"])

    def test_unsafe_and_duplicate_ids_rejected(self):
        for value in ("../escape", "C:/outside", "", "../test-run"):
            with self.assertRaises(ValueError):
                self.runner.paths({"run_id": value})
        self.brief["stories"].append(copy.deepcopy(self.card))
        with self.assertRaisesRegex(ValueError, "duplicate"):
            self.runner.expected_jobs(self.brief)
        self.assertTrue(re.fullmatch(audio.NARRATION_ID, self.card["narration_id"] + "--witness-a"))
        self.assertFalse(re.fullmatch(audio.NARRATION_ID, self.card["narration_id"] + "--../escape"))

    def test_profile_and_output_path_guards(self):
        for config in (replace(self.runner.project_config, target_minutes_max=30),
                       replace(self.runner.project_config, audio_dir=self.root.parent),
                       replace(self.runner.project_config, audio_dir=self.root)):
            with self.assertRaises(ValueError):
                audio.SingleTakeProduction(config)

    def test_casting_evidence_and_artistic_choice_required(self):
        for choice in ({"value": "French", "basis": "inferred_from_name"},
                       {"value": "French", "basis": "source_explicit", "evidence_excerpt": "not in source"}):
            self.card["casting"]["accent"] = choice
            with self.assertRaises(ValueError):
                self.runner.expected_jobs(self.brief)

    def test_all_explicit_voice_traits_locked(self):
        for trait, field in (("narrator_gender_presentation", "gender_presentation"),
                             ("narrator_accent", "accent"), ("narrator_age_presentation", "vocal_age")):
            adaptation = copy.deepcopy(self.adaptation)
            adaptation["identity_constraints"] = [{"trait": trait, "value": "locked value",
                                                     "evidence_excerpt": "I carried my old brass key for twenty years."}]
            with self.assertRaisesRegex(ValueError, field):
                audio.validate_casting(self.card, adaptation, self.source)
            card = copy.deepcopy(self.card)
            card["casting"][field] = {"value": "locked value", "basis": "source_explicit",
                                       "evidence_excerpt": adaptation["identity_constraints"][0]["evidence_excerpt"]}
            audio.validate_casting(card, adaptation, self.source)

    def test_current_editorial_review_is_required(self):
        (self.directory / "personal-story-review.json").unlink()
        with self.assertRaises(ValueError):
            self.runner.expected_jobs(self.brief)

    def test_stale_source_or_brief_blocks_plan(self):
        plan = self.plan()
        self.card["speech_seed"] += 1
        with self.assertRaisesRegex(ValueError, "Stale plan"):
            self.runner.validate_plan(self.brief, plan)

    def test_protected_inventory_and_files_are_checked(self):
        plan = self.plan()
        original = self.root / "podcast.json"
        audio.write_json(original, {})
        with self.assertRaisesRegex(ValueError, "inventory"):
            self.runner.validate_plan(self.brief, plan)
        self.runner.validate_plan(self.brief, plan, preservation=False)
        original.unlink()
        self.runner.project_config.config_path.write_text("changed", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "original changed"):
            self.runner.validate_plan(self.brief, plan)

    def test_dry_run_and_completed_run_load_no_model(self):
        plan = self.plan()
        with patch.object(audio, "hardware_guard") as guard:
            report = self.runner.render(self.brief, plan, execute=False, max_calls=None)
            self.assertEqual(report["local_generation_calls_pending"], 1)
            self.take(plan["jobs"][0])
            report = self.runner.render(self.brief, plan, execute=True, max_calls=0)
            self.assertEqual(report["local_generation_calls_pending"], 0)
            guard.assert_not_called()

    def test_wrong_ceiling_and_missing_model_stop_before_hardware(self):
        plan = self.plan()
        with patch.object(audio, "hardware_guard") as guard:
            for ceiling in (0, 2, None):
                with self.assertRaisesRegex(ValueError, "exact"):
                    self.runner.render(self.brief, plan, execute=True, max_calls=ceiling)
            with self.assertRaisesRegex(ValueError, "Pinned model missing"):
                self.runner.render(self.brief, plan, execute=True, max_calls=1)
            guard.assert_not_called()

    def test_held_attempt_is_not_pending_or_retried(self):
        plan = self.plan()
        directory = self.runner.job_dir(self.brief, plan["jobs"][0])
        audio.write_json(directory / "attempt.json", {"status": "held_quality"})
        with patch.object(audio, "hardware_guard") as guard:
            result = self.runner.render(self.brief, plan, execute=True, max_calls=0)
            self.assertEqual(result["blocked_attempts"], 1)
            self.assertEqual(result["local_generation_calls_pending"], 0)
            guard.assert_not_called()

    def test_duration_limit_preserves_but_rejects_long_audio(self):
        job = self.runner.expected_jobs(self.brief)[0]
        directory = self.take(job, seconds=301)
        self.assertFalse(self.runner.cached(self.brief, job))
        self.assertTrue((directory / "voices-only.wav").exists())

    def test_post_render_hold_does_not_retry_or_stop_later_jobs(self):
        plan = self.plan()
        second = copy.deepcopy(plan["jobs"][0])
        second.update(narration_id=second["narration_id"] + "--second", cache_key="b" * 64)
        plan["jobs"].append(second)
        self.runner.model_path.mkdir()
        (self.runner.model_path / "model.safetensors").touch()
        fake_torch = SimpleNamespace(cuda=Mock(), inference_mode=nullcontext)
        fake_torch.cuda.max_memory_allocated.return_value = 1000
        fake_model = Mock()
        fake_model.generate_voice_design.return_value = ([object()], 100)
        fake_renderer = Mock()
        fake_renderer._load_model.return_value = fake_model
        with patch.object(self.runner, "validate_plan"), patch.object(audio, "hardware_guard", return_value="RTX 3080"), \
                patch.object(audio, "offline"), patch.dict(sys.modules, {"torch": fake_torch}), \
                patch("home_podcast.providers.qwen_tts.Qwen3TTSLocalRenderer", return_value=fake_renderer), \
                patch("home_podcast.providers.qwen_tts._float_audio_to_pcm16", return_value=struct.pack("<h", 1000) * 200), \
                patch.object(audio, "require_story_audio_duration", side_effect=[ValueError("over length"), 2000]):
            result = self.runner.render(self.brief, plan, execute=True, max_calls=2)
        self.assertEqual(fake_model.generate_voice_design.call_count, 2)
        self.assertEqual(result["rendered"][0]["status"], "held_quality")
        self.assertEqual(result["rendered"][1]["duration_ms"], 2000)
        first_dir = self.runner.job_dir(self.brief, plan["jobs"][0])
        self.assertTrue((first_dir / "voices-only.wav").exists())
        self.assertFalse((first_dir / "generation.json").exists())
        self.assertEqual(audio.read(first_dir / "attempt.json")["status"], "held_quality")
        fake_renderer.unload.assert_called_once()

    def test_changed_audio_is_not_reused(self):
        plan = self.plan()
        job = plan["jobs"][0]
        directory = self.take(job)
        with (directory / "voices-only.wav").open("ab") as stream:
            stream.write(b"changed")
        self.assertFalse(self.runner.cached(self.brief, job))
        result = self.runner.quality(self.brief, plan)
        self.assertEqual(result["stories"][0]["status"], "held_invalid_cached_audio")
        self.assertEqual(result["held"], 1)

    def test_touchdesigner_and_5090_are_guarded(self):
        with patch.object(audio.subprocess, "run", return_value=SimpleNamespace(stdout="1")):
            with self.assertRaisesRegex(ValueError, "TouchDesigner"):
                audio.hardware_guard()
        with patch.object(audio.subprocess, "run", side_effect=[SimpleNamespace(stdout="0"),
                SimpleNamespace(stdout="NVIDIA GeForce RTX 5090, 30000")]):
            with self.assertRaisesRegex(ValueError, "3080"):
                audio.hardware_guard()

    def test_content_gate_holds_omissions_and_repetitions(self):
        report = audio.compare_text("I remember " + "home " * 40, "I remember home")
        self.assertIn("possible_missing_or_changed_passage", audio.content_findings(report))
        self.assertIn("possible_added_or_repeated_passage", audio.content_findings({
            "sequence_match_ratio": .97, "differences": [{"expected": "", "recognized": "again " * 12}]}))
        self.assertEqual(audio.content_findings({"sequence_match_ratio": .99, "differences": [
            {"expected": "blond", "recognized": "blonde"}]}), [])

    def test_caption_timing_is_audio_based_and_bounded(self):
        segments = [{"words": [{"word": "I remember.", "start_s": .1, "end_s": 1},
                               {"word": "Home.", "start_s": .9, "end_s": 2}]}]
        rows = audio.caption_rows(segments, 2000)
        self.assertEqual(rows[1]["start_ms"], 1000)
        self.assertEqual(rows[1]["speech_end_ms"], 2000)
        with self.assertRaises(ValueError):
            audio.caption_rows(segments, 500)

    def tail_fixture(self):
        text = "I remember the home where I grew up and the time we spent together in the kitchen telling stories while we made dinner."
        extra = "thank you so much for watching and please join us next time"
        job = {"text": text, "cache_key": "job"}
        kept = {"start_s": 1., "end_s": 11., "text": text,
                "words": [{"word": text, "start_s": 1., "end_s": 11.}]}
        suffix = {"start_s": 11., "end_s": 11.2, "text": extra,
                  "words": [{"word": word, "start_s": 11.2, "end_s": 11.2} for word in extra.split()]}
        original = {"recognized_text": text + " " + extra, "segments": [kept, suffix],
                    "audio_sha256": "audio", "cache_key": "job", "asr_model": "cached", "asr_revision": "pinned",
                    **audio.compare_text(text, text + " " + extra)}
        check = {"original_asr_sha256": "original", "audio_sha256": "audio", "cache_key": "job",
                 "asr_model": "cached", "asr_revision": "pinned", "start_s": .75,
                 "script_prompt_supplied": False, "recognized_text": text, "segments": [kept]}
        return job, original, check

    def test_tail_recheck_requires_complete_exact_script_and_impossible_suffix(self):
        job, original, _ = self.tail_fixture()
        self.assertIsNotNone(audio.asr_tail_candidate(job, original))
        changed = copy.deepcopy(original)
        changed["recognized_text"] = changed["recognized_text"].replace("kitchen", "garden")
        self.assertIsNone(audio.asr_tail_candidate(job, changed))
        changed = copy.deepcopy(original)
        changed["segments"][-1]["end_s"] = 15
        self.assertIsNone(audio.asr_tail_candidate(job, changed))
        changed = copy.deepcopy(original)
        for word in changed["segments"][-1]["words"]:
            word["end_s"] += .02
        self.assertIsNone(audio.asr_tail_candidate(job, changed))

    def test_tail_recheck_is_bound_to_unprompted_closing_audio_not_an_approval(self):
        job, original, check = self.tail_fixture()
        old = copy.deepcopy(original)
        result = audio.tail_checked_report(job, original, check, "original", "check")
        self.assertEqual(result["recognized_text"], job["text"])
        self.assertEqual(result["content_findings"], [])
        self.assertEqual(result["asr_tail_resolution"]["listening_approval"], "pending")
        self.assertEqual(original, old)
        for field, value in (("script_prompt_supplied", True), ("audio_sha256", "changed"),
                             ("recognized_text", "I said something different"), ("asr_revision", "other")):
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "Unresolved or stale"):
                audio.tail_checked_report(job, original, {**check, field: value}, "original", "check")

    def test_tail_resolution_rejects_changed_sidecar(self):
        job, original, check = self.tail_fixture()
        directory = self.root / "tail-check"
        directory.mkdir()
        (directory / "voices-only.wav").write_bytes(b"unchanged audio fixture")
        original["audio_sha256"] = check["audio_sha256"] = audio.sha(directory / "voices-only.wav")
        audio.write_json(directory / "asr-report.json", original)
        check["original_asr_sha256"] = audio.sha(directory / "asr-report.json")
        audio.write_json(directory / "asr-tail-check.json", check)
        result = audio.tail_checked_report(job, original, check, check["original_asr_sha256"],
                                           audio.sha(directory / "asr-tail-check.json"))
        audio.write_json(directory / "asr-report-tail-checked.json", result)
        self.assertEqual(audio.effective_asr_path(directory, job).name, "asr-report-tail-checked.json")
        check["recognized_text"] = "different audio"
        audio.write_json(directory / "asr-tail-check.json", check)
        with self.assertRaisesRegex(ValueError, "Unresolved or stale"):
            audio.effective_asr_path(directory, job)

    def test_quality_keeps_pending_held_and_asr_distinct(self):
        plan = self.plan()
        result = self.runner.quality(self.brief, plan)
        self.assertEqual(result["stories"][0]["status"], "pending_generation")
        directory = self.take(plan["jobs"][0])
        result = self.runner.quality(self.brief, plan)
        self.assertEqual(result["stories"][0]["status"], "pending_asr")
        audio.write_json(directory / "asr-report.json", {"cache_key": plan["jobs"][0]["cache_key"],
            "audio_sha256": audio.sha(directory / "voices-only.wav"), "sequence_match_ratio": .5, "differences": []})
        result = self.runner.quality(self.brief, plan)
        self.assertEqual(result["held"], 1)
        self.assertEqual(result["ready"], 0)

    def test_approval_is_explicit_immutable_and_does_not_approve_captions(self):
        plan = self.plan()
        job = plan["jobs"][0]
        directory = self.take(job)
        manifest_path = self.runner.paths(self.brief)[1] / "manifest.json"
        audio.write_json(manifest_path, {"stories": [{"audio_sha256": "raw", "listening_audio_sha256": "master",
            "listening_audio_path": str(directory / "voices-only.wav")} ]})
        old_hash = audio.sha(manifest_path)
        with self.assertRaises(ValueError):
            self.runner.approve(self.brief, plan, reviewer="user", note="")
        with patch.object(self.runner, "verify") as verify:
            result = self.runner.approve(self.brief, plan, reviewer="user", note="Sounds good")
            verify.assert_called_once_with(self.brief, plan, preservation=False, save=False)
            self.assertEqual(result["stories"][0]["caption_editorial_approval"], "pending")
            self.assertEqual(result, self.runner.approve(self.brief, plan, reviewer="user", note="Sounds good"))
            with self.assertRaisesRegex(ValueError, "differs"):
                self.runner.approve(self.brief, plan, reviewer="user", note="Changed decision")
        self.assertEqual(audio.sha(manifest_path), old_hash)

    def test_package_verify_roundtrip_and_caption_tampering(self):
        from home_podcast.speech_mastering import DEFAULTS
        audio.write_json(self.root / "config/speech_mastering.json", {**DEFAULTS, "enabled": False})
        plan = self.plan()
        job = plan["jobs"][0]
        directory = self.take(job)
        audio.write_json(directory / "asr-report.json", {
            "cache_key": job["cache_key"], "audio_sha256": audio.sha(directory / "voices-only.wav"),
            "sequence_match_ratio": 1., "differences": [], "recognized_text": job["text"],
            "segments": [{"words": [{"word": job["text"], "start_s": .1, "end_s": 1.9}]}],
        })
        self.runner.package(self.brief, plan)
        result = self.runner.verify(self.brief, plan)
        self.assertEqual(result["stories_verified"], 1)
        self.assertEqual(result["caption_editorial_review"], "pending")
        manifest_path = self.runner.paths(self.brief)[1] / "manifest.json"
        manifest = audio.read(manifest_path)
        tampered = copy.deepcopy(manifest)
        tampered["stories"][0]["duration_ms"] = 300001
        audio.write_json(manifest_path, tampered)
        with self.assertRaisesRegex(ValueError, "Package duration"):
            self.runner.verify(self.brief, plan)
        audio.write_json(manifest_path, manifest)
        (directory / "captions.srt").write_text("changed", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Caption file changed"):
            self.runner.verify(self.brief, plan)

    def test_queue_excludes_existing_and_duplicate_candidates(self):
        story_id = self.card["narration_id"]
        duplicate_id = story_id + "--another-witness"
        duplicate = self.runner.project_config.episodes_dir / duplicate_id
        adaptation = copy.deepcopy(self.adaptation)
        adaptation["narration_id"] = duplicate_id
        source = copy.deepcopy(self.source)
        source["narration_id"] = duplicate_id
        audio.write_json(duplicate / "source-job.json", source)
        audio.write_json(duplicate / "adaptation.json", adaptation)
        write_review(duplicate)
        index = self.root / "production-index.json"
        audio.write_json(index, {"narrations": [{"narration_id": identifier,
            "readiness": "ready_for_voice_audition", "source_url": "https://example.test/story"}
            for identifier in (story_id, duplicate_id)]})
        result = self.runner.queue(index)
        self.assertEqual(result["selected_count"], 1)
        self.assertEqual(result["deferred"][0]["reason"], "duplicate_candidate_review_separately")
        self.take(self.runner.expected_jobs(self.brief)[0])
        result = self.runner.queue(index)
        self.assertEqual(result["selected_count"], 0)
        self.assertEqual(result["deferred"][0]["reason"], "existing_take_preserved")


if __name__ == "__main__":
    unittest.main()
