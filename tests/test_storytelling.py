from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from home_podcast.analysis import import_story_cards
from home_podcast.config import ProjectConfig
from home_podcast.database import connect
from home_podcast.ingest import ingest_exports
from home_podcast.storytelling import (
    create_storytelling_cast,
    create_storytelling_plan,
    export_storytelling_jobs,
    first_person_profile,
    import_storytelling_adaptations,
    validate_storytelling_adaptation_data,
)

from tests.test_incremental import fixture


SOURCE = (
    "I carried my old brass key for twenty years. When I finally came home, "
    "I opened the kitchen door and remembered my grandmother singing beside "
    "the blue stove."
)


def _setup(root: Path) -> tuple[ProjectConfig, dict, Path]:
    exports = root / "exports"
    exports.mkdir()
    (exports / "stories_en.md").write_text(fixture(SOURCE), encoding="utf-8")
    (root / "themes.json").write_text(
        json.dumps(
            {
                "themes": [
                    {
                        "slug": "memory-archive",
                        "name": "Memory and Archive",
                        "description": "Remembering home.",
                        "archaeology_questions": ["Why did this survive?"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (root / "bible.json").write_text(
        json.dumps({"format": {"production_mode": "self_narrated_storytelling"}}),
        encoding="utf-8",
    )
    policy_path = root / "voice-policy.json"
    policy_path.write_text(
        json.dumps(
            {
                "contract_version": 1,
                "provider": "test-tts",
                "selection_policy": "test deterministic rotation",
                "required_candidate_metadata": [
                    "person_id",
                    "display_name",
                    "voice_name",
                    "voice_id",
                    "provider",
                    "gender_presentation",
                    "verified_natural_accent",
                    "supported_languages",
                    "personality_tags",
                    "emotional_range_tags",
                    "audition_status",
                ],
                "candidates": [
                    {
                        "person_id": "narrator-a",
                        "display_name": "Narrator A",
                        "voice_name": "Voice A",
                        "voice_id": "voice-a",
                        "provider": "test-tts",
                        "gender_presentation": "feminine",
                        "verified_natural_accent": "verified test accent",
                        "supported_languages": ["en"],
                        "personality_tags": ["reflective", "warm"],
                        "emotional_range_tags": ["nostalgic", "tender"],
                        "audition_status": "approved",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    config_path = root / "storytelling.json"
    config_path.write_text(
        json.dumps(
            {
                "project_name": "Test Storytelling",
                "production_mode": "self_narrated_storytelling",
                "exports_dir": "exports",
                "catalog_path": "catalog.sqlite3",
                "themes_path": "themes.json",
                "show_bible_path": "bible.json",
                "voice_roster_path": "voice-policy.json",
                "episodes_dir": "narrations",
                "work_dir": "work",
                "audio_dir": "audio",
                "target_stories_per_installment": 1,
                "target_minutes_min": 0,
                "target_minutes_max": None,
            }
        ),
        encoding="utf-8",
    )
    config = ProjectConfig.load(config_path)
    ingest_exports(config.catalog_path, config.exports_dir)
    connection = connect(config.catalog_path)
    story = dict(
        connection.execute(
            "SELECT id, content_hash, story_text FROM stories"
        ).fetchone()
    )
    connection.close()
    cards = root / "cards.jsonl"
    cards.write_text(
        json.dumps(
            {
                "story_id": story["id"],
                "content_hash": story["content_hash"],
                "analysis": {
                    "eligible": True,
                    "summary": "A return home unlocks a memory of a grandmother.",
                    "narrative_beats": [
                        {
                            "label": "Key and return",
                            "summary": "The narrator keeps a key and returns home.",
                            "evidence_excerpt": (
                                "I carried my old brass key for twenty years."
                            ),
                        }
                    ],
                    "key_information": [
                        {
                            "claim": "The key was kept for twenty years.",
                            "evidence_excerpt": "When I finally came home",
                        }
                    ],
                    "people": [],
                    "locations": [],
                    "time_markers": [],
                    "sensory_details": [],
                    "unresolved_gaps": [],
                    "source_completeness": "likely_complete",
                    "primary_theme": "memory-archive",
                    "secondary_themes": [],
                    "theme_fit": 0.9,
                    "anchor_score": 0.8,
                    "emotional_tone": "nostalgic",
                    "digital_archaeology_angles": ["A remembered kitchen survives."],
                    "memorable_passages": [],
                    "sensitivity_notes": [],
                    "translation_needed": False,
                    "pronunciation_items": [],
                    "usage_recommendation": "featured",
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    imported, skipped = import_story_cards(
        config, cards, analyzer="test", analyzer_version="1"
    )
    if (imported, skipped) != (1, 0):
        raise AssertionError("test card did not import")
    return config, story, policy_path


def _adaptation(job: dict) -> dict:
    return {
        "contract_version": 1,
        "narration_id": job["narration_id"],
        "source_story_id": job["source_story_id"],
        "source_content_hash": job["source_content_hash"],
        "title": "The Brass Key",
        "source_language": "en",
        "adaptation_language": "en",
        "perspective_mode": "first_person_preserved",
        "identity_constraints": [],
        "narrator_profile": {
            "personality_tags": ["reflective", "warm"],
            "emotional_range_tags": ["nostalgic", "tender"],
            "energy": "low",
            "casting_notes": "Begin quietly and warm as the kitchen memory returns.",
        },
        "sections": [
            {
                "section_id": "001",
                "text": (
                    "I kept that old brass key with me for twenty years. When I "
                    "finally came home and opened the kitchen door, the room brought "
                    "back my grandmother and the sound of her singing beside the blue "
                    "stove. The key had outlasted the wait, and the memory was still there."
                ),
                "source_evidence": [
                    {
                        "excerpt": "I carried my old brass key for twenty years.",
                        "usage": "paraphrase_support",
                    },
                    {
                        "excerpt": "When I finally came home",
                        "usage": "paraphrase_support",
                    },
                ],
                "delivery": {
                    "emotion": "nostalgic warmth",
                    "intensity": 0.45,
                    "pace": "measured",
                    "nonverbal": ["breath"],
                    "direction": "Let the kitchen memory brighten the voice.",
                },
                "pause_after_ms": 700,
            }
        ],
        "unresolved_gaps": [],
        "adaptation_notes": ["First person is explicitly sustained by the source."],
    }


class StorytellingPipelineTests(unittest.TestCase):
    def test_first_person_detection_does_not_treat_lowercase_variable_as_i(self) -> None:
        profile = first_person_profile(
            "The variable i appears in this third-person technical note.",
            "en",
        )

        self.assertEqual(profile["preferred_perspective"], "unsupported_first_person")

    def test_editorial_split_creates_distinct_jobs_for_one_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config, story, _ = _setup(root)
            decisions_dir = root / "series" / "2013-05"
            decisions_dir.mkdir(parents=True)
            (decisions_dir / "storytelling-editorial-decisions.json").write_text(
                json.dumps(
                    {
                        "contract_version": 1,
                        "archive_volume": "2013-05",
                        "exclusions": [],
                        "splits": [
                            {
                                "source_story_id": story["id"],
                                "reason": "Test source contains two first-person parts.",
                                "parts": [
                                    {
                                        "part_id": "key",
                                        "attributed_narrator": "key keeper",
                                        "source_language": "en",
                                        "start_marker": "I carried my old brass key",
                                        "end_marker": "twenty years.",
                                    },
                                    {
                                        "part_id": "return",
                                        "attributed_narrator": "returning resident",
                                        "source_language": "en",
                                        "start_marker": "When I finally came home",
                                        "end_marker": "blue stove.",
                                    },
                                ],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            plan_path = root / "plan.json"
            plan = create_storytelling_plan(config, "2013-05", plan_path)

            self.assertEqual(plan["coverage"]["planned_eligible_narrations"], 2)
            self.assertEqual(plan["coverage"]["split_narration_units"], 2)
            jobs_path = root / "jobs.jsonl"
            export_storytelling_jobs(config, plan_path, jobs_path)
            jobs = [json.loads(line) for line in jobs_path.read_text().splitlines()]
            self.assertEqual(len(jobs), 2)
            self.assertEqual({job["source_story_id"] for job in jobs}, {story["id"]})
            self.assertNotEqual(jobs[0]["narration_id"], jobs[1]["narration_id"])
            self.assertTrue(all(job.get("source_partition") for job in jobs))

    def test_editorial_false_positive_is_excluded_from_plan(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config, story, _ = _setup(root)
            decisions_dir = root / "series" / "2013-05"
            decisions_dir.mkdir(parents=True)
            (decisions_dir / "storytelling-editorial-decisions.json").write_text(
                json.dumps(
                    {
                        "contract_version": 1,
                        "archive_volume": "2013-05",
                        "exclusions": [
                            {
                                "source_story_id": story["id"],
                                "classification": "test_false_positive",
                                "reason": "Not a single story.",
                            }
                        ],
                        "splits": [],
                    }
                ),
                encoding="utf-8",
            )
            plan = create_storytelling_plan(config, "2013-05", root / "plan.json")

            self.assertEqual(plan["coverage"]["planned_eligible_narrations"], 0)
            self.assertEqual(len(plan["coverage"]["editorially_excluded"]), 1)

    def test_plan_export_validate_import_and_resume(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config, story, _ = _setup(root)
            plan_path = root / "plan.json"
            plan = create_storytelling_plan(config, "2013-05", plan_path)

            self.assertEqual(plan["coverage"]["planned_eligible_narrations"], 1)
            self.assertEqual(
                plan["coverage"]["preferred_perspectives"][
                    "first_person_preserved"
                ],
                1,
            )
            jobs_path = root / "jobs.jsonl"
            result = export_storytelling_jobs(config, plan_path, jobs_path)
            self.assertEqual(result["exported"], 1)
            job = json.loads(jobs_path.read_text(encoding="utf-8").strip())
            self.assertEqual(
                job["perspective"]["preferred_perspective"],
                "first_person_preserved",
            )
            self.assertEqual(
                job["required_evidence_excerpts"],
                [
                    "I carried my old brass key for twenty years.",
                    "When I finally came home",
                ],
            )

            adaptation = _adaptation(job)
            validation = validate_storytelling_adaptation_data(adaptation, job)
            self.assertTrue(validation["valid"], validation["errors"])
            results_path = root / "results.jsonl"
            results_path.write_text(json.dumps(adaptation) + "\n", encoding="utf-8")
            imported = import_storytelling_adaptations(
                config,
                results_path,
                jobs_path,
                root / "import-report.json",
            )
            self.assertEqual(imported["imported"], 1)
            self.assertEqual(imported["rejected"], 0)
            narration_id = plan["narrations"][0]["narration_id"]
            self.assertTrue(
                (config.episodes_dir / narration_id / "manifest.json").is_file()
            )
            self.assertTrue(
                (config.episodes_dir / narration_id / "source-job.json").is_file()
            )
            self.assertEqual(story["content_hash"], job["source_content_hash"])

            resumed = export_storytelling_jobs(config, plan_path, root / "pending.jsonl")
            self.assertEqual(resumed["exported"], 0)
            self.assertEqual(resumed["skipped_existing"], 1)

    def test_third_person_is_rejected_by_first_person_only_collection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config, _, _ = _setup(root)
            plan_path = root / "plan.json"
            create_storytelling_plan(config, "2013-05", plan_path)
            jobs_path = root / "jobs.jsonl"
            export_storytelling_jobs(config, plan_path, jobs_path)
            job = json.loads(jobs_path.read_text(encoding="utf-8").strip())
            adaptation = _adaptation(job)
            adaptation["perspective_mode"] = "third_person_storyteller"
            adaptation["adaptation_notes"] = []

            report = validate_storytelling_adaptation_data(adaptation, job)

            self.assertFalse(report["valid"])
            self.assertTrue(
                any("perspective_mode is invalid" in error for error in report["errors"])
            )

    def test_documented_editorial_omission_can_account_for_required_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config, _, _ = _setup(root)
            plan_path = root / "plan.json"
            create_storytelling_plan(config, "2013-05", plan_path)
            jobs_path = root / "jobs.jsonl"
            export_storytelling_jobs(config, plan_path, jobs_path)
            job = json.loads(jobs_path.read_text(encoding="utf-8").strip())
            adaptation = _adaptation(job)
            omitted = adaptation["sections"][0]["source_evidence"].pop()
            adaptation["editorial_omissions"] = [
                {
                    "excerpt": omitted["excerpt"],
                    "classification": "other_non_narrative_artifact",
                    "reason": "Test-only source residue excluded from speech.",
                }
            ]

            report = validate_storytelling_adaptation_data(adaptation, job)

            self.assertTrue(report["valid"], report["errors"])
            self.assertEqual(report["omitted_evidence_excerpts"], 1)

    def test_cast_uses_auditioned_language_compatible_voice(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config, _, _ = _setup(root)
            plan_path = root / "plan.json"
            create_storytelling_plan(config, "2013-05", plan_path)
            jobs_path = root / "jobs.jsonl"
            export_storytelling_jobs(config, plan_path, jobs_path)
            job = json.loads(jobs_path.read_text(encoding="utf-8").strip())
            adaptation = _adaptation(job)
            adaptation_path = root / "adaptation.json"
            adaptation_path.write_text(json.dumps(adaptation), encoding="utf-8")
            cast_path = root / "cast.json"

            cast, created, reason = create_storytelling_cast(
                config,
                job["narration_id"],
                adaptation_path,
                cast_path,
            )

            self.assertTrue(created)
            self.assertIsNone(reason)
            self.assertEqual(cast["narrator"]["voice_id"], "voice-a")
            self.assertFalse(cast["identity_claim"])


if __name__ == "__main__":
    unittest.main()
