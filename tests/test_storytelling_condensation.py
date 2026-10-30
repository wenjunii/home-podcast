from __future__ import annotations

import copy
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from home_podcast.storytelling import (
    create_storytelling_plan, export_storytelling_jobs,
    import_storytelling_adaptations, validate_storytelling_adaptation_data,
)
from home_podcast.storytelling_quality import content_digest, personal_story_findings
from scripts.audit_storytelling_duration import audit
from tests.storytelling_test_support import write_review
from tests.test_storytelling import _adaptation, _setup


class StorytellingCondensationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        config, _, _ = _setup(self.root)
        self.config = replace(config, target_minutes_max=5)
        create_storytelling_plan(self.config, "2013-05", self.root / "plan.json")
        self.jobs = self.root / "jobs.jsonl"
        export_storytelling_jobs(self.config, self.root / "plan.json", self.jobs)
        self.job = json.loads(self.jobs.read_text(encoding="utf-8"))
        self.original = _adaptation(self.job)
        self.assertEqual(self._import(self.original)["imported"], 1)
        self.directory = self.config.episodes_dir / self.job["narration_id"]
        write_review(self.directory)

    def tearDown(self):
        self.temporary.cleanup()

    def _import(self, value):
        path = self.root / "result.jsonl"
        path.write_text(json.dumps(value) + "\n", encoding="utf-8")
        return import_storytelling_adaptations(self.config, path, self.jobs, self.root / "report.json")

    def _short(self):
        result = copy.deepcopy(self.original)
        result["sections"][0]["text"] = "I kept the key for twenty years. Coming home, I remembered my grandmother singing."
        result["condensation"] = {
            "policy": "one_story_under_five_minutes",
            "full_adaptation_sha256": content_digest(self.original),
            "editorial_summary": "Test short edition preserves the central return-home memory.",
        }
        return result

    def test_import_preserves_full_edition_and_frozen_source_without_auto_review(self):
        protected = {name: (self.directory / name).read_bytes() for name in (
            "adaptation.json", "personal-story-review.json", "source-job.json", "manifest.json")}
        short = self._short()
        report = self._import(short)
        self.assertEqual((report["updated"], report["rejected"]), (1, 0))
        archive = self.directory / "full-editions" / content_digest(self.original)
        for name in ("adaptation.json", "personal-story-review.json"):
            self.assertEqual((archive / name).read_bytes(), protected[name])
        for name in ("source-job.json", "manifest.json"):
            self.assertEqual((self.directory / name).read_bytes(), protected[name])
        self.assertIn("stale_personal_story_review", personal_story_findings(self.directory))
        self.assertEqual(self._import(short)["rejected"], 0)

    def test_old_full_version_hash_is_checked_before_replacing_text(self):
        short = self._short()
        short["condensation"]["full_adaptation_sha256"] = "0" * 64
        original = (self.directory / "adaptation.json").read_bytes()
        self.assertEqual(self._import(short)["rejected"], 1)
        self.assertEqual((self.directory / "adaptation.json").read_bytes(), original)

    def test_published_story_cannot_be_overwritten_with_short_edition(self):
        manifest_path = self.directory / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["publication_status"] = "published"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        self.assertEqual(self._import(self._short())["rejected"], 1)
        self.assertFalse((self.directory / "full-editions").exists())

    def test_overlong_rewrite_is_not_imported_as_a_short_edition(self):
        short = self._short()
        short["sections"][0]["text"] = "I remember home. " * 250
        self.assertEqual(self._import(short)["rejected"], 1)
        self.assertFalse((self.directory / "full-editions").exists())

    def test_duration_omissions_need_explicit_condensation_provenance(self):
        short = self._short()
        omitted = short["sections"][0]["source_evidence"].pop()
        short["editorial_omissions"] = [{
            "excerpt": omitted["excerpt"], "classification": "duration_condensation",
            "reason": "Test metadata accounts for a secondary detail omitted for length.",
        }]
        self.assertTrue(validate_storytelling_adaptation_data(short, self.job)["valid"])
        short.pop("condensation")
        self.assertFalse(validate_storytelling_adaptation_data(short, self.job)["valid"])

    def test_condensation_cannot_claim_parts_or_invent_evidence(self):
        short = self._short()
        short["condensation"]["policy"] = "split_into_parts"
        self.assertFalse(validate_storytelling_adaptation_data(short, self.job)["valid"])
        short = self._short()
        short["editorial_omissions"] = [{
            "excerpt": "I remember an invented moon colony.", "classification": "duration_condensation",
            "reason": "Invalid evidence must be rejected.",
        }]
        self.assertFalse(validate_storytelling_adaptation_data(short, self.job)["valid"])

    def test_duration_audit_does_not_approve_drafts_or_include_archived_full_versions(self):
        self._import(self._short())
        report, jobs = audit(self.config)
        self.assertEqual(report["summary"]["drafts_audited"], 1)
        self.assertEqual(report["summary"]["within_text_budget"], 1)
        self.assertEqual(report["summary"]["approved_personal_stories"], 0)
        self.assertEqual(report["summary"]["pending_editorial_review_or_rewrite"], 1)
        self.assertEqual(jobs, [])

    def test_current_editorial_hold_preserves_overlong_original_without_requeue(self):
        path = self.directory / "adaptation.json"
        long_version = copy.deepcopy(self.original)
        long_version["sections"][0]["text"] = "I remember home. " * 250
        path.write_text(json.dumps(long_version), encoding="utf-8")
        write_review(self.directory)
        review_path = self.directory / "personal-story-review.json"
        review = json.loads(review_path.read_text(encoding="utf-8"))
        review["decision"] = "held_not_personal_story"
        review["reason"] = "Individual test review cannot establish a historical narrator."
        review_path.write_text(json.dumps(review), encoding="utf-8")
        original = path.read_bytes()
        report, jobs = audit(self.config)
        self.assertEqual(jobs, [])
        self.assertEqual(report["summary"]["needs_condensation"], 0)
        self.assertEqual(report["summary"]["held_originals_over_budget"], 1)
        self.assertEqual(report["summary"]["within_text_budget"], 0)
        self.assertEqual(report["summary"]["approved_personal_stories"], 0)
        self.assertEqual(report["summary"]["pending_editorial_review_or_rewrite"], 0)
        self.assertEqual(path.read_bytes(), original)
        self.assertIn("personal_story_held_by_editorial_review", personal_story_findings(self.directory))

        # A changed source revokes the hold's current status, not its safety gate.
        source_path = self.directory / "source-job.json"
        source = json.loads(source_path.read_text(encoding="utf-8"))
        source["story_text"] += " Newly recovered testimony."
        source_path.write_text(json.dumps(source), encoding="utf-8")
        report, jobs = audit(self.config)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(report["summary"]["held_originals_over_budget"], 0)
        self.assertEqual(report["summary"]["pending_editorial_review_or_rewrite"], 1)


if __name__ == "__main__":
    unittest.main()
