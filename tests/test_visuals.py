from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from home_podcast.database import connect
from home_podcast.visuals import (
    expand_visual_scenes,
    prepare_visual_scenes,
    validate_visual_plan,
)


class VisualSceneTests(unittest.TestCase):
    def test_short_story_passage_is_merged_and_sound_cues_are_excluded(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            timeline_path = root / "timeline.json"
            catalog_path = root / "catalog.sqlite3"
            output_path = root / "visuals.json"
            jobs_path = root / "jobs.jsonl"
            timeline_path.write_text(
                json.dumps(
                    {
                        "episode_id": "pilot",
                        "duration_ms": 40_000,
                        "tracks": {
                            "voices_only": {
                                "distribution_audio": str(root / "voices.mp3")
                            }
                        },
                        "sound_cues": [
                            {
                                "start_ms": 0,
                                "end_ms": 1000,
                                "transcript_label": "paper",
                            }
                        ],
                        "segments": [
                            {
                                "segment_id": "s1",
                                "speaker": "a",
                                "display_name": "A",
                                "text": "Long first story.",
                                "source_story_ids": ["story-a"],
                                "start_ms": 0,
                                "end_ms": 20_000,
                            },
                            {
                                "segment_id": "s2",
                                "speaker": "b",
                                "display_name": "B",
                                "text": "Short bridge.",
                                "source_story_ids": ["story-b"],
                                "start_ms": 20_000,
                                "end_ms": 25_000,
                            },
                            {
                                "segment_id": "s3",
                                "speaker": "a",
                                "display_name": "A",
                                "text": "Long third story.",
                                "source_story_ids": ["story-c"],
                                "start_ms": 25_000,
                                "end_ms": 40_000,
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )
            connection = connect(catalog_path)
            try:
                connection.execute(
                    """
                    INSERT INTO ingest_runs(
                        source_root, started_at, completed_at
                    ) VALUES ('test', 'now', 'now')
                    """
                )
                run_id = connection.execute(
                    "SELECT MAX(id) FROM ingest_runs"
                ).fetchone()[0]
                for story_id in ("story-a", "story-b", "story-c"):
                    self._insert_story(connection, story_id, run_id)
                connection.commit()
            finally:
                connection.close()

            result = prepare_visual_scenes(
                timeline_path,
                catalog_path,
                output_path,
                jobs_path,
                min_scene_ms=10_000,
            )
            plan = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(result["visual_scenes"], 2)
            self.assertEqual(len(plan["captions"]), 3)
            self.assertNotIn("sound_cues", plan)
            self.assertEqual(plan["scenes"][0]["source_story_ids"], ["story-a", "story-b"])
            self.assertEqual(plan["scenes"][0]["end_ms"], 25_000)
            self.assertTrue(validate_visual_plan(output_path)["valid"])
            self.assertEqual(len(jobs_path.read_text(encoding="utf-8").splitlines()), 2)

    def test_expands_long_scene_and_only_jobs_complementary_prompts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            timeline_path = root / "timeline.json"
            catalog_path = root / "catalog.sqlite3"
            source_path = root / "visuals-36.json"
            output_path = root / "visuals-expanded.json"
            source_jobs_path = root / "source-jobs.jsonl"
            jobs_path = root / "expanded-jobs.jsonl"
            boundaries = [0, 20_000, 35_000, 55_000, 70_000, 90_000, 105_000]
            timeline_path.write_text(
                json.dumps(
                    {
                        "episode_id": "pilot",
                        "duration_ms": 105_000,
                        "tracks": {
                            "voices_only": {
                                "distribution_audio": str(root / "voices.mp3")
                            }
                        },
                        "segments": [
                            {
                                "segment_id": f"s{index + 1}",
                                "speaker": "host",
                                "display_name": "Host",
                                "text": f"Passage {index + 1} about a remembered garden.",
                                "source_story_ids": ["story-a"],
                                "start_ms": boundaries[index],
                                "end_ms": boundaries[index + 1],
                            }
                            for index in range(len(boundaries) - 1)
                        ],
                    }
                ),
                encoding="utf-8",
            )
            connection = connect(catalog_path)
            try:
                connection.execute(
                    """
                    INSERT INTO ingest_runs(
                        source_root, started_at, completed_at
                    ) VALUES ('test', 'now', 'now')
                    """
                )
                run_id = connection.execute(
                    "SELECT MAX(id) FROM ingest_runs"
                ).fetchone()[0]
                self._insert_story(connection, "story-a", run_id)
                connection.commit()
            finally:
                connection.close()

            prepare_visual_scenes(
                timeline_path,
                catalog_path,
                source_path,
                source_jobs_path,
                min_scene_ms=15_000,
            )
            source = json.loads(source_path.read_text(encoding="utf-8"))
            source["scenes"][0]["prompt"] = {
                "status": "generated_pending_editorial_review",
                "visual_intent": "A remembered garden.",
                "camera_policy": "Wide view.",
                "chunks": [
                    {
                        "role": "narrative",
                        "text": "A remembered garden in warm afternoon light.",
                        "weight": 1.0,
                        "content_token_count": 70,
                    }
                ],
                "seed": 42,
                "sensitivity_notes": [],
            }
            source_path.write_text(json.dumps(source), encoding="utf-8")

            result = expand_visual_scenes(
                source_path,
                timeline_path,
                catalog_path,
                output_path,
                jobs_path,
                min_scene_ms=15_000,
                max_scene_ms=35_000,
            )
            expanded = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(result["visual_scenes"], 3)
            self.assertEqual(result["preserved_prompts"], 1)
            self.assertEqual(result["prompts_pending_grounded_generation"], 2)
            self.assertEqual(
                [scene["duration_ms"] for scene in expanded["scenes"]],
                [35_000, 35_000, 35_000],
            )
            self.assertEqual(
                sum(
                    scene["origin_prompt_preserved"]
                    for scene in expanded["scenes"]
                ),
                1,
            )
            self.assertEqual(
                len(jobs_path.read_text(encoding="utf-8").splitlines()),
                2,
            )
            self.assertTrue(validate_visual_plan(output_path)["valid"])

    @staticmethod
    def _insert_story(
        connection: sqlite3.Connection,
        story_id: str,
        run_id: int,
    ) -> None:
        connection.execute(
            """
            INSERT INTO stories(
                id, language, heading, source_root, source_markdown,
                source_ordinal, source_url, source_file, crawl_dataset,
                crawl_timestamp, crawl_month, match_references_json,
                accepted_text, story_text, metadata_json, quality_flags_json,
                content_hash, record_hash, first_seen_at, last_seen_at,
                last_seen_run_id, is_present
            ) VALUES (
                ?, 'en', ?, 'root', 'stories_en.md', 1, 'https://example.test',
                'crawl.wet.gz', 'CC', '2013-12-01T00:00:00Z', '2013-12',
                '[]', 'accepted', ?, '{}', '[]', ?, ?, 'now', 'now', ?, 1
            )
            """,
            (
                story_id,
                story_id,
                f"Source text for {story_id}",
                f"hash-{story_id}",
                f"record-{story_id}",
                run_id,
            ),
        )


if __name__ == "__main__":
    unittest.main()
