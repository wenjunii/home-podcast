"""CPU-only safety coverage; fake renderers never claim real GPU execution."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import wave

from home_podcast.ambient_batch import AmbientBatch, anchor_ms, fit_ambient
from home_podcast.ambient_audibility import DEFAULTS as AUDIBILITY_DEFAULTS
from home_podcast.ambient_mastering import DEFAULTS, sha
from home_podcast.ambient_mastering import PEAK_SAFE_VERSION
from home_podcast.cli import build_parser
from home_podcast.single_take_audio import read, write_json
from home_podcast.storytelling_quality import content_digest
from tests.storytelling_test_support import write_review

NUMERICS = all(importlib.util.find_spec(n) for n in ("numpy", "scipy", "soundfile"))


class AmbientBatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = SimpleNamespace(project_root=self.root, config_path=self.root / "project.json",
                                      work_dir=self.root / "work", audio_dir=self.root / "audio",
                                      episodes_dir=self.root / "narrations")
        sid = "2013-12--story-" + "a" * 24
        self.sid = sid
        self.directory = self.root / "narrations" / sid
        adaptation = {"narration_id": sid, "title": "A Home Remembered",
                      "sections": [{"section_id": "001", "text": "I remember my home."}]}
        write_json(self.directory / "adaptation.json", adaptation)
        write_json(self.directory / "source-job.json", {"story_text": "I remember my home."})
        write_review(self.directory)
        voice = self.root / "audio/approved/raw/voices-only.wav"
        voice.parent.mkdir(parents=True)
        with wave.open(str(voice), "wb") as out:
            out.setparams((1, 2, 24000, 0, "NONE", "not compressed"))
            out.writeframes(b"\0\0" * (24000 * 5))
        leveled = voice.parent / "mastered/voices-leveled.wav"
        leveled.parent.mkdir()
        shutil.copyfile(voice, leveled)
        write_json(leveled.parent / "mastering.json", {})
        write_json(voice.parent / "generation.json", {"cache_key": "fixture-voice"})
        write_json(voice.parent / "asr-report.json", {"segments": [{"words": [
            {"word": word, "start_s": i * .5, "end_s": (i + 1) * .5}
            for i, word in enumerate(("I", "remember", "my", "home."))]}]})
        manifest = {"stories": [{"narration_id": sid, "audio_path": str(voice), "audio_sha256": sha(voice),
                                  "listening_audio_path": str(leveled), "listening_audio_sha256": sha(leveled),
                                  "duration_ms": 5000}]}
        write_json(self.root / "audio/approved/manifest.json", manifest)
        write_json(self.root / "work/approval.json", {"manifest_sha256": sha(self.root / "audio/approved/manifest.json"),
            "stories": [{"narration_id": sid, "listening_approval": "approved_by_user",
                          "adaptation_sha256": content_digest(adaptation),
                          "source_job_sha256": content_digest(read(self.directory / "source-job.json")),
                          "editorial_review_sha256": content_digest(read(self.directory / "personal-story-review.json"))}]})
        write_json(self.root / "config/ambient_mastering.json", DEFAULTS)
        self.brief = {"contract_version": 1, "run_id": "ambient-test-batch",
                      "speech_manifest": "audio/approved/manifest.json", "speech_approval": "work/approval.json",
                      "steps": 8, "cfg": 1.5, "negative_prompt": "speech, voices, music",
                      "mix": {"speech_duck_db": 5, "fade_in_seconds": .2, "fade_out_seconds": .3, "cue_crossfade_seconds": .4},
                      "stories": [{"narration_id": sid, "location_note": "Unspecified place.", "direction": "Neutral air.",
                                   "cues": [{"cue_id": "home-air", "role": "base", "seed": 1,
                                             "source_evidence": "I remember my home.", "interpretation": "Artistic neutral air.",
                                             "start": "story_start", "end": "story_end", "prompt": "TrackType: SFX. Gentle airy background."},
                                            {"cue_id": "short-cue", "role": "specific", "seed": 2,
                                             "source_evidence": "my home", "interpretation": "Short artistic texture.",
                                             "start": {"phrase": "home", "edge": "end"}, "end": "story_end", "prompt": "Soft air."}]}]}
        self.brief_path = self.root / "work/brief.json"
        write_json(self.brief_path, self.brief)
        self.runner = AmbientBatch(self.config, self.brief_path)

    def test_prepare_and_dry_run_are_model_free_and_skip_short_cues(self):
        report = self.runner.prepare()
        self.assertEqual(report["pending_local_generation_calls"], 1)
        self.assertEqual(report["skipped_short_cues"], 1)
        self.assertEqual(report["models_loaded"], 0)
        self.assertEqual(report["network_calls"], 0)
        self.assertEqual(self.runner.prepare(), report)
        with patch("home_podcast.ambient_batch.hardware_guard") as gpu:
            self.runner.render()
        gpu.assert_not_called()

    def test_exact_call_ceiling_required_before_any_model_load(self):
        self.runner.prepare()
        with patch("home_podcast.ambient_batch.hardware_guard") as gpu:
            for count in (None, 0, 2, True):
                with self.subTest(count=count), self.assertRaisesRegex(ValueError, "exact"):
                    self.runner.render(execute=True, max_calls=count, worker=True)
        gpu.assert_not_called()

    def test_new_audibility_policy_is_frozen_not_silently_changed_on_resume(self):
        path = self.root / "config/ambient_audibility.json"
        write_json(path, AUDIBILITY_DEFAULTS)
        self.runner.prepare()
        self.assertEqual(self.runner.load()["audibility_policy"], AUDIBILITY_DEFAULTS)
        write_json(path, {**AUDIBILITY_DEFAULTS, "maximum_mono_loss_db": 7.0})
        with self.assertRaisesRegex(ValueError, "Protected input changed"):
            self.runner.load()

    def test_explicit_shorter_source_duration_can_reuse_loop_material(self):
        self.brief["stories"][0]["cues"][0]["asset_duration_ms"] = 3000
        write_json(self.brief_path, self.brief)
        self.runner = AmbientBatch(self.config, self.brief_path)
        self.runner.prepare()
        p = self.runner.load()
        self.assertEqual(p["assets"][0]["generation_duration_ms"], 3000)
        self.assertEqual(p["stories"][0]["cues"][0]["end_ms"], 5000)

    def test_invalid_explicit_source_duration_is_rejected(self):
        for duration in (True, 0, 121000, 5000.5):
            with self.subTest(duration=duration):
                self.brief["stories"][0]["cues"][0]["asset_duration_ms"] = duration
                write_json(self.brief_path, self.brief)
                with self.assertRaisesRegex(ValueError, "source duration"):
                    AmbientBatch(self.config, self.brief_path).prepare()

    def test_short_story_can_use_longer_base_without_extending_its_clock(self):
        self.brief["stories"][0]["cues"][0]["asset_duration_ms"] = 78000
        write_json(self.brief_path, self.brief)
        runner = AmbientBatch(self.config, self.brief_path)
        runner.prepare()
        plan = runner.load()
        self.assertEqual(plan["assets"][0]["generation_duration_ms"], 78000)
        self.assertEqual(plan["stories"][0]["duration_ms"], 5000)
        self.assertEqual(plan["stories"][0]["cues"][0]["end_ms"], 5000)

    def test_longer_source_does_not_broaden_specific_event_span(self):
        # Long enough to avoid the separate under-15-second skip gate.
        manifest_path = self.root / "audio/approved/manifest.json"
        manifest = read(manifest_path)
        manifest["stories"][0]["duration_ms"] = 20000
        write_json(manifest_path, manifest)
        approval = read(self.root / "work/approval.json")
        approval["manifest_sha256"] = sha(manifest_path)
        write_json(self.root / "work/approval.json", approval)
        cue = self.brief["stories"][0]["cues"][1]
        cue.update(start="story_start", end="story_end", asset_duration_ms=20001)
        write_json(self.brief_path, self.brief)
        with self.assertRaisesRegex(ValueError, "source duration"):
            AmbientBatch(self.config, self.brief_path).prepare()

    @unittest.skipUnless(NUMERICS, "optional audio environment required")
    def test_quality_holds_bass_only_base_before_packaging(self):
        import numpy as np
        write_json(self.root / "config/ambient_audibility.json", AUDIBILITY_DEFAULTS)
        self.runner.prepare()
        path = self.root / "bass-only.wav"
        tone = .1 * np.sin(2 * np.pi * 200 * np.arange(16000 * 4) / 16000)
        with wave.open(str(path), "wb") as stream:
            stream.setparams((2, 2, 16000, 0, "NONE", "not compressed"))
            stream.writeframes(np.rint(np.column_stack((tone, tone)) * 32767).astype("<i2").tobytes())
        with patch.object(self.runner, "cached", return_value=True), \
                patch("home_podcast.ambient_batch.master_ambient", return_value={"audio_path": str(path)}):
            quality = self.runner.quality()
        self.assertEqual(quality["accepted_assets"], 0)
        self.assertEqual(len(quality["held_assets"]), 1)
        self.assertIn("insufficient_small_speaker_midrange", quality["held_assets"][0]["findings"])
        with self.assertRaisesRegex(ValueError, "Resolve held ambient assets"):
            self.runner.package()

    def test_prior_attempt_is_held_without_retry(self):
        self.runner.prepare()
        asset = self.runner.load()["assets"][0]
        path = self.runner.inside(asset["output_audio"])
        write_json(path.with_suffix(".attempt.json"), {"status": "generating"})
        self.assertEqual(self.runner.dry_run()["blocked_prior_attempts"], 1)
        with self.assertRaisesRegex(ValueError, "no automatic retry"):
            self.runner.render(execute=True, max_calls=1)

    def test_changed_voice_and_source_review_block_resume(self):
        self.runner.prepare()
        review_path = self.directory / "personal-story-review.json"
        review = read(review_path)
        review["decision"] = "held"
        write_json(review_path, review)
        with self.assertRaisesRegex(ValueError, "Protected input changed"):
            self.runner.load()

    def test_unsupported_evidence_is_not_accepted(self):
        self.brief["stories"][0]["cues"][0]["source_evidence"] = "An invented house."
        write_json(self.brief_path, self.brief)
        with self.assertRaisesRegex(ValueError, "source evidence"):
            AmbientBatch(self.config, self.brief_path).prepare()

    def test_path_traversal_and_duplicate_ids_rejected(self):
        with self.assertRaisesRegex(ValueError, "inside"):
            self.runner.inside(self.root.parent / "escape")
        self.brief["stories"] *= 2
        write_json(self.brief_path, self.brief)
        with self.assertRaisesRegex(ValueError, "duplicate"):
            AmbientBatch(self.config, self.brief_path).prepare()

    def test_plan_tampering_rejected(self):
        self.runner.prepare()
        p = self.runner.load()
        p["stories"][0]["cues"][0]["start_ms"] = 42
        write_json(self.runner.plan_path, p)
        with self.assertRaisesRegex(ValueError, "Frozen ambient plan"):
            self.runner.load()

    def test_cli_exposes_supported_batch_stages(self):
        args = build_parser().parse_args(["ambient-batch", "render", "--brief", "work/brief.json"])
        self.assertFalse(args.execute)
        self.assertIsNone(args.max_calls)

    def test_listening_page_uses_its_actual_run_and_story_count(self):
        self.runner.prepare()
        p = self.runner.load()
        self.assertEqual(p["solo_mastering_revision"], PEAK_SAFE_VERSION)
        self.runner._page(p, p["stories"])
        page = (self.runner.out / "index.html").read_text(encoding="utf-8")
        self.assertIn("<title>ambient-test-batch</title>", page)
        self.assertIn("1 stories: ambient-test-batch", page)
        self.assertNotIn("batch 01", page)

    def test_anchor_is_exact_and_ambiguity_needs_explicit_occurrence(self):
        words = [{"word": "home", "start_s": 1, "end_s": 2}, {"word": "home", "start_s": 3, "end_s": 4}]
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            anchor_ms({"phrase": "home", "edge": "end"}, words, 5000)
        self.assertEqual(anchor_ms({"phrase": "home", "edge": "end", "occurrence": 2}, words, 5000), 4000)

    def test_import_has_no_media_model_side_effects(self):
        code = ("import sys; import home_podcast.ambient_batch; import home_podcast.providers.ambient_gpu; "
                "assert not {'torch','onnxruntime','qwen_tts','ollama','faster_whisper','numpy'} & set(sys.modules)")
        result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    @unittest.skipUnless(NUMERICS, "optional audio environment required")
    def test_render_resume_and_preserved_files_with_fake_engine(self):
        import numpy as np
        self.runner.prepare()
        engine = Mock()
        tone = .06 * np.sin(2 * np.pi * 500 * np.arange(5 * 44100) / 44100)
        engine.generate.return_value = (np.column_stack((tone, tone)).astype("float32"), {"wall_seconds": .1})
        engine.close.return_value = {"verified_cuda_matrix_operations": 1, "test_fixture_not_real_gpu": True}
        factory = Mock(return_value=engine)
        with patch("home_podcast.ambient_batch.hardware_guard", return_value="test 3080"), \
                patch("home_podcast.providers.ambient_gpu.verify_runtime", return_value={}):
            report = self.runner.render(execute=True, max_calls=1, worker=True, engine_factory=factory)
        self.assertEqual(report["generated"], 1)
        self.assertEqual(report["pending_local_generation_calls"], 0)
        result = self.runner.render(execute=True, max_calls=0, worker=True, engine_factory=factory)
        self.assertEqual(result["models_loaded"], 0)
        factory.assert_called_once()

    @unittest.skipUnless(NUMERICS and shutil.which("ffmpeg"), "optional audio environment and FFmpeg required")
    def test_package_and_verify_use_the_approved_voice_and_shared_level_targets(self):
        import numpy as np
        write_json(self.root / "config/ambient_audibility.json", AUDIBILITY_DEFAULTS)
        self.runner.prepare()
        engine = Mock()
        tone = .06 * np.sin(2 * np.pi * 500 * np.arange(5 * 44100) / 44100)
        engine.generate.return_value = (np.column_stack((tone, tone)).astype("float32"), {"wall_seconds": .1})
        engine.close.return_value = {"verified_cuda_matrix_operations": 1, "test_fixture_not_real_gpu": True}
        with patch("home_podcast.ambient_batch.hardware_guard", return_value="test 3080"), \
                patch("home_podcast.providers.ambient_gpu.verify_runtime", return_value={}):
            self.runner.render(execute=True, max_calls=1, worker=True, engine_factory=Mock(return_value=engine))
        quality = self.runner.quality()
        self.assertFalse(quality["assets"][0]["audibility"]["quality_findings"])
        write_json(self.runner.work / "speech-diagnostic.json", {
            "plan_digest": self.runner.load()["plan_digest"], "recognized_segments": 0,
            "test_fixture_not_real_asr": True, "assets": [{
                "asset_key": a["asset_key"], "audio_sha256": a["mastering"]["audio_sha256"],
                "recognized_segments": []} for a in quality["assets"]]})
        result = self.runner.package()
        self.assertEqual(result["stories"], 1)
        verified = self.runner.verify()
        self.assertFalse(read(self.runner.out / "manifest.json")["stories"][0]["audibility"]["quality_findings"])
        self.assertEqual(read(self.runner.out / "manifest.json")["stories"][0]["solo_mastering"]["identity"]["version"], PEAK_SAFE_VERSION)
        self.assertTrue(verified["original_voices_unchanged"])
        self.assertEqual(verified["page_audio_players"], 3)
        self.assertAlmostEqual(verified["stem_lufs_range"][0], -30, delta=.7)
        # Packaging is resumable without overwriting audio or regenerating.
        self.assertEqual(self.runner.package(), result)


@unittest.skipUnless(importlib.util.find_spec("numpy"), "NumPy unavailable")
class AmbientLoopTests(unittest.TestCase):
    def test_loop_is_full_length_without_holes_or_gain_spikes(self):
        import numpy as np
        source = np.ones((100, 2), np.float32) * .1
        output = fit_ambient(source, 358, 20)
        self.assertEqual(output.shape, (358, 2))
        np.testing.assert_allclose(output, .1)
        self.assertTrue(np.array_equal(fit_ambient(source, 31, 20), source[:31]))


if __name__ == "__main__":
    unittest.main()
