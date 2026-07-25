from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from home_podcast.analysis import import_story_cards
from home_podcast.config import ProjectConfig
from home_podcast.database import connect
from home_podcast.ingest import ingest_exports
from home_podcast.planning import (
    create_month_proposal,
    lock_episode_manifest,
    prepare_script_packet,
    snapshot_crawl_month,
)

from test_incremental import SECOND, fixture


class PlanningTests(unittest.TestCase):
    def test_plan_assigns_every_eligible_story(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            exports = root / "exports"
            exports.mkdir()
            (exports / "stories_en.md").write_text(
                fixture("A story about carrying home in memory."), encoding="utf-8"
            )
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
                json.dumps({"hosts": []}), encoding="utf-8"
            )
            config_data = {
                "project_name": "Test",
                "exports_dir": "exports",
                "catalog_path": "catalog.sqlite3",
                "themes_path": "themes.json",
                "show_bible_path": "bible.json",
                "episodes_dir": "episodes",
                "work_dir": "work",
                "audio_dir": "audio",
                "target_stories_per_installment": 30,
            }
            config_path = root / "podcast.json"
            config_path.write_text(json.dumps(config_data), encoding="utf-8")
            config = ProjectConfig.load(config_path)
            ingest_exports(config.catalog_path, config.exports_dir)
            connection = connect(config.catalog_path)
            row = connection.execute(
                "SELECT id, content_hash FROM stories"
            ).fetchone()
            connection.close()
            card_path = root / "cards.jsonl"
            card_path.write_text(
                json.dumps(
                    {
                        "story_id": row["id"],
                        "content_hash": row["content_hash"],
                        "analysis": {
                            "eligible": True,
                            "summary": "A remembered home.",
                            "primary_theme": "memory-archive",
                            "secondary_themes": [],
                            "theme_fit": 0.9,
                            "anchor_score": 0.8,
                            "emotional_tone": "reflective",
                            "digital_archaeology_angles": [
                                "The capture preserves a remembered home."
                            ],
                            "memorable_passages": [
                                "A story about carrying home in memory."
                            ],
                            "sensitivity_notes": [],
                            "translation_needed": False,
                            "pronunciation_items": [],
                            "usage_recommendation": "anchor",
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            imported, skipped = import_story_cards(
                config, card_path, analyzer="test", analyzer_version="1"
            )
            self.assertEqual((imported, skipped), (1, 0))
            proposal_path = root / "proposal.json"
            proposal = create_month_proposal(config, "2013-05", proposal_path)
            self.assertEqual(proposal["coverage"]["assigned_eligible_stories"], 1)
            episode_id = proposal["installments"][0]["episode_id"]
            manifest_path, created = lock_episode_manifest(
                config, proposal_path, episode_id
            )
            self.assertTrue(created)
            same_path, created = lock_episode_manifest(config, proposal_path, episode_id)
            self.assertEqual(same_path, manifest_path)
            self.assertFalse(created)
            packet = prepare_script_packet(
                config, manifest_path, episode_id, root / "evidence.json"
            )
            self.assertEqual(len(packet["evidence"]), 1)

    def test_plan_can_be_restricted_to_frozen_cohort(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            exports = root / "exports"
            exports.mkdir()
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
                json.dumps({"hosts": []}), encoding="utf-8"
            )
            config_path = root / "podcast.json"
            config_path.write_text(
                json.dumps(
                    {
                        "project_name": "Test",
                        "exports_dir": "exports",
                        "catalog_path": "catalog.sqlite3",
                        "themes_path": "themes.json",
                        "show_bible_path": "bible.json",
                        "episodes_dir": "episodes",
                        "work_dir": "work",
                        "audio_dir": "audio",
                        "target_stories_per_installment": 30,
                    }
                ),
                encoding="utf-8",
            )
            config = ProjectConfig.load(config_path)

            (exports / "stories_en.md").write_text(
                fixture("First frozen story."), encoding="utf-8"
            )
            ingest_exports(config.catalog_path, config.exports_dir)
            cohort_path = root / "cohort.json"
            cohort, created = snapshot_crawl_month(
                config, "2013-05", "pilot", cohort_path
            )
            self.assertTrue(created)
            self.assertEqual(cohort["story_count"], 1)

            (exports / "stories_en.md").write_text(
                fixture("First frozen story.", SECOND),
                encoding="utf-8",
            )
            ingest_exports(config.catalog_path, config.exports_dir)
            connection = connect(config.catalog_path)
            for row in connection.execute(
                "SELECT id, content_hash FROM stories"
            ).fetchall():
                connection.execute(
                    """
                    INSERT INTO story_cards (
                        story_id, content_hash, analyzer, analyzer_version,
                        card_json, created_at
                    ) VALUES (?, ?, 'test', '1', ?, '2026-01-01T00:00:00Z')
                    """,
                    (
                        row["id"],
                        row["content_hash"],
                        json.dumps(
                            {
                                "eligible": True,
                                "summary": "A home story.",
                                "primary_theme": "memory-archive",
                                "theme_fit": 0.8,
                                "anchor_score": 0.7,
                            }
                        ),
                    ),
                )
            connection.commit()
            connection.close()

            proposal = create_month_proposal(
                config, "2013-05", root / "proposal.json", cohort_path=cohort_path
            )
            self.assertEqual(proposal["coverage"]["unique_present_stories"], 1)
            self.assertEqual(proposal["coverage"]["assigned_eligible_stories"], 1)
            self.assertEqual(proposal["cohort"]["label"], "pilot")

    def test_snapshot_can_select_only_analyzed_stories(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            exports = root / "exports"
            exports.mkdir()
            (exports / "stories_en.md").write_text(
                fixture("First story.", SECOND), encoding="utf-8"
            )
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
                json.dumps({"hosts": []}), encoding="utf-8"
            )
            config_path = root / "podcast.json"
            config_path.write_text(
                json.dumps(
                    {
                        "project_name": "Test",
                        "exports_dir": "exports",
                        "catalog_path": "catalog.sqlite3",
                        "themes_path": "themes.json",
                        "show_bible_path": "bible.json",
                        "episodes_dir": "episodes",
                        "work_dir": "work",
                        "audio_dir": "audio",
                    }
                ),
                encoding="utf-8",
            )
            config = ProjectConfig.load(config_path)
            ingest_exports(config.catalog_path, config.exports_dir)
            connection = connect(config.catalog_path)
            analyzed = connection.execute(
                "SELECT id, content_hash FROM stories ORDER BY id LIMIT 1"
            ).fetchone()
            connection.execute(
                """
                INSERT INTO story_cards (
                    story_id, content_hash, analyzer, analyzer_version,
                    card_json, created_at
                ) VALUES (
                    ?, ?, 'test', '1',
                    '{"eligible": true, "primary_theme": "memory-archive"}',
                    '2026-01-01T00:00:00Z'
                )
                """,
                (analyzed["id"], analyzed["content_hash"]),
            )
            connection.commit()
            connection.close()

            cohort, _ = snapshot_crawl_month(
                config,
                "2013-05",
                "wave-1",
                root / "wave-1.json",
                analyzed_only=True,
            )
            self.assertEqual(cohort["story_count"], 1)
            self.assertEqual(
                cohort["selection_policy"],
                "present unique stories with a current story card",
            )
            self.assertEqual(cohort["stories"][0]["story_id"], analyzed["id"])

            themed, _ = snapshot_crawl_month(
                config,
                "2013-05",
                "theme-pilot",
                root / "theme-pilot.json",
                primary_theme="memory-archive",
            )
            self.assertEqual(themed["story_count"], 1)
            self.assertEqual(themed["primary_theme"], "memory-archive")

    def test_single_episode_plan_combines_all_eligible_stories(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            exports = root / "exports"
            exports.mkdir()
            (exports / "stories_en.md").write_text(
                fixture("A story about carrying home in memory."),
                encoding="utf-8",
            )
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
                json.dumps({"hosts": []}), encoding="utf-8"
            )
            config_path = root / "podcast.json"
            config_path.write_text(
                json.dumps(
                    {
                        "project_name": "Test",
                        "exports_dir": "exports",
                        "catalog_path": "catalog.sqlite3",
                        "themes_path": "themes.json",
                        "show_bible_path": "bible.json",
                        "episodes_dir": "episodes",
                        "work_dir": "work",
                        "audio_dir": "audio",
                    }
                ),
                encoding="utf-8",
            )
            config = ProjectConfig.load(config_path)
            ingest_exports(config.catalog_path, config.exports_dir)
            connection = connect(config.catalog_path)
            story = connection.execute(
                "SELECT id, content_hash FROM stories"
            ).fetchone()
            connection.execute(
                """
                INSERT INTO story_cards (
                    story_id, content_hash, analyzer, analyzer_version,
                    card_json, created_at
                ) VALUES (?, ?, 'test', '1', ?, '2026-01-01T00:00:00Z')
                """,
                (
                    story["id"],
                    story["content_hash"],
                    json.dumps(
                        {
                            "eligible": True,
                            "summary": "A remembered home.",
                            "primary_theme": "memory-archive",
                            "secondary_themes": [],
                            "theme_fit": 0.9,
                            "anchor_score": 0.8,
                            "usage_recommendation": "anchor",
                        }
                    ),
                ),
            )
            connection.commit()
            connection.close()

            proposal = create_month_proposal(
                config,
                "2013-05",
                root / "single.json",
                single_episode=True,
                single_episode_title="91 Fragments of Home",
            )
            self.assertEqual(len(proposal["installments"]), 1)
            self.assertEqual(
                proposal["installments"][0]["title"], "91 Fragments of Home"
            )
            self.assertEqual(proposal["installments"][0]["story_count"], 1)
            self.assertEqual(
                proposal["installments"][0]["stories"][0]["primary_theme"],
                "memory-archive",
            )


if __name__ == "__main__":
    unittest.main()
