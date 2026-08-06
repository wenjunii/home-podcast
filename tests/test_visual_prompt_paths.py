from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path


MODULE_PATH = (
    Path(__file__).parents[1] / "scripts" / "validate_visual_prompt_paths.py"
)
SPEC = importlib.util.spec_from_file_location(
    "validate_visual_prompt_paths",
    MODULE_PATH,
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

PREPARER_PATH = (
    Path(__file__).parents[1] / "scripts" / "prepare_human_figure_visual_path.py"
)
PREPARER_SPEC = importlib.util.spec_from_file_location(
    "prepare_human_figure_visual_path",
    PREPARER_PATH,
)
PREPARER = importlib.util.module_from_spec(PREPARER_SPEC)
assert PREPARER_SPEC.loader is not None
sys.modules[PREPARER_SPEC.name] = PREPARER
PREPARER_SPEC.loader.exec_module(PREPARER)


class VisualPromptPathTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.original = {
            "episode_id": "test",
            "duration_ms": 20_000,
            "master_track": "voices_only",
            "captions": [{"caption_id": "caption-1", "start_ms": 0}],
            "scenes": [
                {
                    "scene_id": "visual-001",
                    "sequence": 1,
                    "start_ms": 0,
                    "end_ms": 20_000,
                    "duration_ms": 20_000,
                    "crossfade_in_ms": 0,
                    "crossfade_out_ms": 5_000,
                    "segment_ids": ["segment-1"],
                    "source_story_ids": ["story-1"],
                    "transcript": "A grounded story passage.",
                }
            ],
        }
        self.human = deepcopy(self.original)
        self.human["visual_path"] = {
            "id": "human_figures",
            "audio_compatibility": ["voices_only", "soundscape_only"],
            "front_portrait_scene_count": 1,
            "clear_face_scene_count": 0,
        }
        self.human["scenes"][0].update(
            {
                "human_figure_path": {"mode": "front_portrait_identity_safe"},
                "prompt": {
                    "chunks": [{"content_token_count": 72}],
                },
            }
        )
        self.sound_design = {
            "cues": [
                {
                    "visual_scene_id": "visual-001",
                    "coverage_role": "section",
                    "duration_ms": 20_000,
                }
            ]
        }

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _write(self, name: str, value: dict) -> Path:
        path = self.root / name
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def _validate(self):
        voices = self.root / "voices.mp3"
        soundscape = self.root / "soundscape.mp3"
        voices.write_bytes(b"voices")
        soundscape.write_bytes(b"soundscape")
        return MODULE.validate_paths(
            self._write("original.json", self.original),
            self._write("human.json", self.human),
            self._write("sound.json", self.sound_design),
            voices,
            soundscape,
        )

    def test_accepts_locked_paths_with_shared_audio(self) -> None:
        report = self._validate()

        self.assertTrue(report["valid"])
        self.assertEqual(report["human_primary_scenes"], 1)
        self.assertEqual(report["soundscape_scene_cues"], 1)

    def test_rejects_timing_drift(self) -> None:
        self.human["scenes"][0]["start_ms"] = 1_000

        report = self._validate()

        self.assertFalse(report["valid"])
        self.assertIn(
            "visual-001: locked field differs: start_ms",
            report["errors"],
        )


class FrontPortraitPreparationTests(unittest.TestCase):
    def test_human_back_view_becomes_identity_safe_front_portrait(self) -> None:
        scene = {"grounding": {"identity_claims": []}}

        result = PREPARER._front_portrait_body(
            "Anonymous student seen from behind entering a room, lane behind him.",
            scene,
        )

        self.assertIn("facing the camera in soft silhouette", result)
        self.assertIn("behind the figure", result)
        self.assertNotIn("behind him", result)

    def test_nonhuman_back_view_is_not_mislabeled_as_a_person(self) -> None:
        scene = {"grounding": {"identity_claims": []}}

        result = PREPARER._front_portrait_body(
            "A single car seen from behind on a mountain road.",
            scene,
        )

        self.assertEqual(
            result,
            "A single car seen from behind on a mountain road.",
        )
        self.assertFalse(
            PREPARER.FRONT_ORIENTATION.search(result)
            and PREPARER.HUMAN_SUBJECT.search(result)
        )

    def test_incomplete_token_trim_does_not_leave_sentence_fragment(self) -> None:
        self.assertEqual(
            PREPARER._clean_prompt_ending("Warm light spilling across"),
            "Warm light spilling.",
        )


if __name__ == "__main__":
    unittest.main()
