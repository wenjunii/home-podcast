import json
import tempfile
import unittest
from pathlib import Path

from home_podcast.config import ProjectConfig
from home_podcast.storytelling import (
    create_storytelling_plan, export_storytelling_jobs, import_storytelling_adaptations,
)
from scripts.build_storytelling_preflight import build_preflight
from tests.test_storytelling import SOURCE, _setup, _adaptation
from tests.storytelling_test_support import write_review


ROOT = Path(__file__).resolve().parents[1]


class StorytellingPlanTests(unittest.TestCase):
    def synthetic_collection(self, root):
        """One invented fixture story; never read or approve production records."""
        config, story, _ = _setup(root)
        plan_path, jobs_path = root / "plan.json", root / "jobs.jsonl"
        plan = create_storytelling_plan(config, "2013-05", plan_path)
        export_storytelling_jobs(config, plan_path, jobs_path)
        job = json.loads(jobs_path.read_text(encoding="utf-8"))
        adaptation = _adaptation(job)
        results = root / "results.jsonl"
        results.write_text(json.dumps(adaptation)+"\n", encoding="utf-8")
        imported = import_storytelling_adaptations(config, results, jobs_path, root / "report.json")
        self.assertEqual((imported["imported"], imported["rejected"]), (1, 0))
        return config, story, plan, job, jobs_path, adaptation

    def test_fixture_plan_freezes_full_source_and_preserves_other_projects(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pilot = root / "episodes/pilot/script.json"
            pilot.parent.mkdir(parents=True)
            pilot.write_bytes(b'{"preserved_podcast": true}\n')
            other_project = root / "podcast.5090.toe"
            other_project.write_bytes(b"synthetic existing project sentinel")
            before = (pilot.read_bytes(), other_project.read_bytes())
            config, story, plan, job, _, _ = self.synthetic_collection(root)
            directory = config.episodes_dir / job["narration_id"]
            frozen = json.loads((directory / "source-job.json").read_text(encoding="utf-8"))
            self.assertEqual(plan["coverage"]["planned_eligible_narrations"], 1)
            self.assertEqual(frozen["story_text"], SOURCE)
            self.assertEqual(frozen["source_content_hash"], story["content_hash"])
            self.assertEqual(job["perspective"]["preferred_perspective"], "first_person_preserved")
            self.assertEqual((pilot.read_bytes(), other_project.read_bytes()), before)

    def test_fixture_preflight_summary_requires_current_editorial_review(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config, _, _, job, jobs, adaptation = self.synthetic_collection(root)
            index, audit, inventory = build_preflight(config, jobs)
            self.assertEqual(index["summary"], audit["summary"])
            self.assertEqual(index["summary"]["planned_narrations"], 1)
            self.assertEqual(index["summary"]["readiness"]["blocked_before_voice_audition"], 1)
            self.assertFalse(audit["valid"])
            self.assertEqual(inventory, [])
            self.assertFalse(audit["model_servers_started"])
            # Explicit synthetic review, labelled test-fixture by the helper.
            directory = config.episodes_dir / job["narration_id"]
            write_review(directory)
            index, audit, inventory = build_preflight(config, jobs)
            self.assertTrue(audit["valid"], audit["blocked_narrations"])
            self.assertEqual(index["summary"], audit["summary"])
            self.assertEqual(index["summary"]["sections_ready_for_voice_audition"], len(inventory))
            self.assertEqual(len(inventory), len(adaptation["sections"]))
            self.assertTrue(all(row["cast_status"] == "pending_storytelling_voice_audition" for row in inventory))
            adaptation["sections"][0]["text"] += " A changed memory."
            (directory / "adaptation.json").write_text(json.dumps(adaptation), encoding="utf-8")
            _, stale_audit, stale_inventory = build_preflight(config, jobs)
            self.assertFalse(stale_audit["valid"])
            self.assertEqual(stale_inventory, [])

    def test_storytelling_uses_shared_evidence_and_separate_outputs(self):
        storytelling = ProjectConfig.load(ROOT / "storytelling.real-december.json")
        podcast = ProjectConfig.load(ROOT / "podcast.real-december.json")

        self.assertEqual(storytelling.catalog_path, podcast.catalog_path)
        self.assertEqual(storytelling.exports_dir, podcast.exports_dir)
        self.assertNotEqual(storytelling.episodes_dir, podcast.episodes_dir)
        self.assertNotEqual(storytelling.work_dir, podcast.work_dir)
        self.assertNotEqual(storytelling.audio_dir, podcast.audio_dir)
        self.assertEqual(storytelling.target_stories_per_installment, 1)
        self.assertEqual(storytelling.target_minutes_max, 5)
        self.assertIsNone(podcast.target_minutes_max)

    def test_storytelling_policy_keeps_voice_traits_separate_from_identity(self):
        policy = json.loads(
            (ROOT / "config" / "storytelling_voice_policy.json").read_text(
                encoding="utf-8"
            )
        )
        identity = policy["identity_policy"]

        self.assertFalse(identity["location_implies_accent"])
        self.assertFalse(identity["language_implies_ethnicity"])
        self.assertFalse(identity["name_implies_gender"])
        self.assertFalse(identity["performed_voice_claims_to_be_source_person"])
        self.assertTrue(identity["unsupported_voice_traits_are_artistic_casting"])

    @unittest.skipUnless(
        (ROOT / "series/2013-12/storytelling-collection.json").is_file(),
        "Private production snapshot is not included in a public code-only checkout",
    )
    def test_storytelling_collection_preserves_podcast_and_has_complete_sources(self):
        collection = json.loads(
            (ROOT / "series" / "2013-12" / "storytelling-collection.json").read_text(
                encoding="utf-8"
            )
        )

        self.assertEqual(collection["source_scope"]["recovered_captures"], 422)
        self.assertEqual(collection["source_scope"]["recovered_story_units"], 444)
        self.assertEqual(collection["source_scope"]["pending_recovery"], 0)
        self.assertEqual(collection["source_scope"]["pending_analysis"], 0)
        self.assertEqual(
            collection["narration_plan"]["planned_eligible_narrations"], 415
        )
        self.assertEqual(collection["narration_plan"]["source_stories_represented"], 412)
        self.assertEqual(collection["narration_plan"]["adaptations_imported"], 415)
        self.assertEqual(collection["narration_plan"]["adaptations_pending"], 0)
        self.assertEqual(
            collection["narration_plan"]["editorial_false_positive_exclusions"],
            15,
        )
        self.assertEqual(collection["narration_plan"]["split_narration_units"], 6)
        self.assertEqual(
            collection["narration_plan"]["held_without_supported_first_person"], 2
        )
        self.assertEqual(
            collection["podcast_path"]["status"],
            "preserved_for_possible_future_continuation",
        )
        self.assertTrue(
            collection["podcast_path"][
                "existing_pilot_and_touchdesigner_assets_unchanged"
            ]
        )

    def test_storytelling_script_contract_requires_grounded_sections(self):
        contract = json.loads(
            (ROOT / "contracts" / "storytelling-script.schema.json").read_text(
                encoding="utf-8"
            )
        )
        required = set(contract["required"])
        section = contract["properties"]["sections"]["items"]

        self.assertIn("source_story_id", required)
        self.assertIn("source_content_hash", required)
        self.assertIn("identity_constraints", required)
        self.assertIn("narrator_profile", required)
        self.assertIn("source_evidence", section["required"])
        self.assertIn("delivery", section["required"])

    def test_local_runtime_defaults_to_safe_profile(self):
        runtime = json.loads(
            (ROOT / "config" / "live_storytelling.json").read_text(
                encoding="utf-8"
            )
        )

        self.assertEqual(runtime["default_profile"], "3080_safe")
        self.assertFalse(runtime["profiles"]["3080_safe"]["local_generation_enabled"])
        self.assertTrue(runtime["profiles"]["5090_live"]["local_generation_enabled"])
        self.assertEqual(
            runtime["profiles"]["5090_live"]["ollama"]["model"],
            "gemma4:12b",
        )
        safeguards = runtime["interpretive_casting"]["safeguards"]
        self.assertFalse(safeguards["accent_implies_appearance"])
        self.assertTrue(safeguards["one_cast_per_complete_rendition"])

    @unittest.skipUnless(
        all((ROOT / "series/2013-12" / name).is_file() for name in
            ("pre-elevenlabs-handoff.json", "storytelling-production-index.json")),
        "Private production snapshots are not included in a public code-only checkout",
    )
    def test_pre_elevenlabs_handoff_matches_production_index(self):
        handoff = json.loads(
            (ROOT / "series" / "2013-12" / "pre-elevenlabs-handoff.json").read_text(
                encoding="utf-8"
            )
        )
        index = json.loads(
            (ROOT / "series" / "2013-12" / "storytelling-production-index.json").read_text(
                encoding="utf-8"
            )
        )
        summary = index["summary"]

        self.assertEqual(handoff["state"], "partial_personal_story_review_bulk_production_blocked")
        self.assertEqual(handoff["validation"]["blocked_narrations"],
                         summary["readiness"]["blocked_before_voice_audition"])
        self.assertEqual(
            handoff["collection"]["active_first_person_narrations"],
            summary["planned_narrations"],
        )
        self.assertEqual(
            handoff["validation"]["provider_neutral_sections"],
            summary["sections_ready_for_voice_audition"],
        )
        self.assertEqual(
            handoff["validation"]["spoken_characters"],
            summary["spoken_characters"],
        )
        self.assertTrue(
            handoff["editorial_review"]["bulk_tts_requires_explicit_editorial_approval"]
        )
        self.assertEqual(handoff["voice_gate"]["auditioned_candidates"], 0)


if __name__ == "__main__":
    unittest.main()
