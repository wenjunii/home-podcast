from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from home_podcast.analysis import export_analysis_packets
from home_podcast.config import ProjectConfig
from home_podcast.database import connect
from home_podcast.ingest import ingest_exports
from home_podcast.planning import snapshot_crawl_month

from test_incremental import SECOND, fixture


class AnalysisExportTests(unittest.TestCase):
    def test_frozen_cohort_excludes_later_stories_and_detects_disappearance(self) -> None:
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
            source = exports / "stories_en.md"
            source.write_text(fixture("First frozen story."), encoding="utf-8")
            ingest_exports(config.catalog_path, config.exports_dir)
            cohort_path = root / "cohort.json"
            cohort, _ = snapshot_crawl_month(
                config, "2013-05", "pilot", cohort_path
            )

            source.write_text(
                fixture("First frozen story.", SECOND), encoding="utf-8"
            )
            ingest_exports(config.catalog_path, config.exports_dir)
            output_path = root / "jobs.jsonl"
            exported = export_analysis_packets(
                config, output_path, cohort_path=cohort_path
            )
            jobs = [
                json.loads(line)
                for line in output_path.read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(exported, 1)
            self.assertEqual(jobs[0]["story_id"], cohort["stories"][0]["story_id"])

            connection = connect(config.catalog_path)
            connection.execute(
                "UPDATE stories SET is_present = 0 WHERE id = ?",
                (cohort["stories"][0]["story_id"],),
            )
            connection.commit()
            connection.close()
            with self.assertRaisesRegex(ValueError, "changed or disappeared"):
                export_analysis_packets(
                    config, root / "missing.jsonl", cohort_path=cohort_path
                )


if __name__ == "__main__":
    unittest.main()
