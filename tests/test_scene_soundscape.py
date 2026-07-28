from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from home_podcast.scene_soundscape import (
    build_scene_soundscape,
    validate_scene_soundscape,
)
from home_podcast.sound_design import validate_sound_design


class SceneSoundscapeTests(unittest.TestCase):
    def test_builds_exact_continuous_scene_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            visuals_path = root / "visuals.json"
            timeline_path = root / "timeline.json"
            output_path = root / "sound-design.json"
            script_path = root / "script.json"
            visuals_path.write_text(
                json.dumps(
                    {
                        "episode_id": "episode-1",
                        "duration_ms": 35000,
                        "scenes": [
                            _scene("visual-001", 0, 15000, "s1", "paper and rain"),
                            _scene(
                                "visual-002",
                                15000,
                                35000,
                                "s2",
                                "open road at dusk",
                            ),
                        ],
                    }
                ),
                encoding="utf-8",
            )
            timeline_path.write_text(
                json.dumps(
                    {
                        "episode_id": "episode-1",
                        "duration_ms": 35000,
                        "segments": [
                            {"segment_id": "s1", "start_ms": 0, "end_ms": 15000},
                            {
                                "segment_id": "s2",
                                "start_ms": 15000,
                                "end_ms": 35000,
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )
            script_path.write_text(
                json.dumps(
                    {
                        "episode_id": "episode-1",
                        "segments": [{"segment_id": "s1"}, {"segment_id": "s2"}],
                    }
                ),
                encoding="utf-8",
            )
            prompts = {
                "visual-001": {
                    "sound_prompt": "Paper fibers, soft rain, no voices, seamless loop.",
                    "transcript_label": "paper and soft rain",
                },
                "visual-002": {
                    "sound_prompt": "Distant road air at dusk, no speech, seamless loop.",
                    "transcript_label": "distant road air",
                },
            }

            report = build_scene_soundscape(
                visuals_path,
                timeline_path,
                prompts,
                output_path,
            )
            self.assertTrue(report["valid"], report["errors"])
            self.assertEqual(report["scene_cues"], 2)
            self.assertEqual(report["continuous_base_cues"], 1)
            self.assertEqual(report["coverage_end_ms"], 35000)
            self.assertEqual(report["pending_generation_jobs"], 3)
            self.assertEqual(report["pending_generation_seconds_ceiling"], 65)
            standard = validate_sound_design(output_path, script_path)
            self.assertTrue(standard["valid"], standard["errors"])

    def test_rejects_stale_or_incomplete_scene_prompts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            visuals_path = root / "visuals.json"
            timeline_path = root / "timeline.json"
            output_path = root / "sound-design.json"
            visuals_path.write_text(
                json.dumps(
                    {
                        "episode_id": "episode-1",
                        "duration_ms": 15000,
                        "scenes": [
                            _scene("visual-001", 0, 15000, "s1", "paper and rain")
                        ],
                    }
                ),
                encoding="utf-8",
            )
            timeline_path.write_text(
                json.dumps(
                    {
                        "episode_id": "episode-1",
                        "duration_ms": 15000,
                        "segments": [
                            {"segment_id": "s1", "start_ms": 0, "end_ms": 15000}
                        ],
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "coverage mismatch"):
                build_scene_soundscape(
                    visuals_path, timeline_path, {}, output_path
                )
            with self.assertRaisesRegex(ValueError, "Visual plan changed"):
                build_scene_soundscape(
                    visuals_path,
                    timeline_path,
                    {
                        "visual-001": {
                            "sound_prompt": "Paper rain, no voices.",
                            "transcript_label": "paper rain",
                        }
                    },
                    output_path,
                    expected_visuals_sha256="not-the-current-hash",
                )

    def test_validator_detects_sound_that_precedes_visual(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            visuals_path = root / "visuals.json"
            timeline_path = root / "timeline.json"
            output_path = root / "sound-design.json"
            visuals_path.write_text(
                json.dumps(
                    {
                        "episode_id": "episode-1",
                        "duration_ms": 15000,
                        "scenes": [
                            _scene("visual-001", 0, 15000, "s1", "paper and rain")
                        ],
                    }
                ),
                encoding="utf-8",
            )
            timeline_path.write_text(
                json.dumps(
                    {
                        "episode_id": "episode-1",
                        "duration_ms": 15000,
                        "segments": [
                            {"segment_id": "s1", "start_ms": 0, "end_ms": 15000}
                        ],
                    }
                ),
                encoding="utf-8",
            )
            build_scene_soundscape(
                visuals_path,
                timeline_path,
                {
                    "visual-001": {
                        "sound_prompt": "Paper rain, no voices.",
                        "transcript_label": "paper rain",
                    }
                },
                output_path,
            )
            sound_design = json.loads(output_path.read_text(encoding="utf-8"))
            sound_design["cues"][1]["anchor"]["offset_ms"] = -1000
            output_path.write_text(json.dumps(sound_design), encoding="utf-8")
            report = validate_scene_soundscape(
                output_path, visuals_path, timeline_path
            )
            self.assertFalse(report["valid"])
            self.assertTrue(
                any("sound starts" in error for error in report["errors"])
            )


def _scene(
    scene_id: str,
    start_ms: int,
    end_ms: int,
    segment_id: str,
    prompt_text: str,
) -> dict:
    return {
        "scene_id": scene_id,
        "start_ms": start_ms,
        "end_ms": end_ms,
        "duration_ms": end_ms - start_ms,
        "segment_ids": [segment_id],
        "prompt": {
            "status": "generated_pending_editorial_review",
            "chunks": [{"role": "narrative", "text": prompt_text, "weight": 1.0}],
        },
    }


if __name__ == "__main__":
    unittest.main()
