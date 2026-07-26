from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "touchdesigner" / "podcast_sequencer.py"
SPEC = importlib.util.spec_from_file_location("podcast_sequencer", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)
PodcastSequencer = MODULE.PodcastSequencer


class PodcastSequencerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.sequencer = PodcastSequencer(
            {
                "duration_ms": 30_000,
                "captions": [
                    {
                        "caption_id": "c1",
                        "start_ms": 0,
                        "end_ms": 12_000,
                        "speaker": "Lina",
                        "text": "First.",
                    },
                    {
                        "caption_id": "c2",
                        "start_ms": 12_000,
                        "end_ms": 30_000,
                        "speaker": "Maya",
                        "text": "Second.",
                    },
                ],
                "scenes": [
                    self._scene("v1", 0, 15_000, 0, "old prompt"),
                    self._scene("v2", 15_000, 30_000, 5_000, "new prompt"),
                ],
            }
        )

    def test_crossfade_emits_old_and_new_prompts(self) -> None:
        frame = self.sequencer.at(17_500)
        self.assertEqual(frame.scene_id, "v2")
        self.assertEqual(len(frame.prompt_layers), 2)
        self.assertAlmostEqual(frame.prompt_layers[0].weight, 0.5)
        self.assertAlmostEqual(frame.prompt_layers[1].weight, 0.5)
        self.assertEqual(frame.prompt_layers[0].seed, 11)
        self.assertEqual(frame.prompt_layers[1].seed, 22)
        self.assertEqual(frame.caption_id, "c2")

    def test_seek_recomputes_scene_without_state(self) -> None:
        self.assertEqual(self.sequencer.at(25_000).scene_id, "v2")
        self.assertEqual(self.sequencer.at(1_000).scene_id, "v1")

    def test_live_crossfade_override_is_smooth_and_capped(self) -> None:
        frame = self.sequencer.at(19_000, crossfade_ms=8_000)
        self.assertEqual(frame.crossfade_ms, 7_500)
        self.assertAlmostEqual(frame.crossfade_progress, 4_000 / 7_500)
        self.assertEqual(len(frame.prompt_layers), 2)
        self.assertAlmostEqual(
            frame.prompt_layers[1].weight,
            0.5499259259,
        )

    def test_zero_live_crossfade_switches_immediately(self) -> None:
        frame = self.sequencer.at(15_000, crossfade_ms=0)
        self.assertEqual(frame.crossfade_ms, 0)
        self.assertEqual(frame.crossfade_progress, 1.0)
        self.assertEqual(len(frame.prompt_layers), 1)
        self.assertEqual(frame.prompt_layers[0].scene_id, "v2")

    @staticmethod
    def _scene(
        scene_id: str,
        start_ms: int,
        end_ms: int,
        crossfade_ms: int,
        prompt: str,
    ) -> dict:
        return {
            "scene_id": scene_id,
            "start_ms": start_ms,
            "end_ms": end_ms,
            "crossfade_in_ms": crossfade_ms,
            "prompt": {
                "seed": 11 if scene_id == "v1" else 22,
                "chunks": [
                    {
                        "role": "narrative",
                        "text": prompt,
                        "weight": 1.0,
                    }
                ]
            },
        }


if __name__ == "__main__":
    unittest.main()
