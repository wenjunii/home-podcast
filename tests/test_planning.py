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
)

from test_incremental import fixture


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


if __name__ == "__main__":
    unittest.main()
