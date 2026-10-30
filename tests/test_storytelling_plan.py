import json
import unittest
from pathlib import Path

from home_podcast.config import ProjectConfig


ROOT = Path(__file__).resolve().parents[1]


class StorytellingPlanTests(unittest.TestCase):
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
