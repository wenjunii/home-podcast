from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


MODULE_PATH = (
    Path(__file__).parents[1] / "touchdesigner" / "podcast_td_controller.py"
)
SPEC = importlib.util.spec_from_file_location("podcast_td_controller", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)
PodcastVisualController = MODULE.PodcastVisualController


class FakePar:
    def __init__(self, value=None) -> None:
        self._value = value
        self.assignments = 0
        self.sequence = None

    def eval(self):
        return self._value

    @property
    def val(self):
        return self._value

    @val.setter
    def val(self, value):
        self.assignments += 1
        self._value = value


class FakeTarget:
    def __init__(self) -> None:
        prompt_dict = FakePar(0)
        prompt_dict.sequence = FakeSequence(
            lambda: SimpleNamespace(
                par=SimpleNamespace(
                    Concept=FakePar(""),
                    Weight=FakePar(0.0),
                )
            )
        )
        seed_dict = FakePar(0)
        seed_dict.sequence = FakeSequence(
            lambda: SimpleNamespace(
                par=SimpleNamespace(
                    Seedval=FakePar(0),
                    Seedweight=FakePar(0.0),
                )
            )
        )
        self.par = SimpleNamespace(
            Promptdict=prompt_dict,
            Seeddict=seed_dict,
            Normpweights=FakePar(False),
            Setinterpolation=FakePar("lerp"),
        )


class FakeSequence:
    def __init__(self, factory) -> None:
        self.factory = factory
        self.blocks = []

    @property
    def numBlocks(self):
        return len(self.blocks)

    @numBlocks.setter
    def numBlocks(self, value):
        while len(self.blocks) < value:
            self.blocks.append(self.factory())
        del self.blocks[value:]

    def __getitem__(self, index):
        return self.blocks[index]


class FakeOwner:
    def __init__(self, target, backup=None, crossfade_seconds=None) -> None:
        self.targets = {
            "StreamDiffusionTD": target,
            "StreamDiffusionTD1": backup,
        }
        if crossfade_seconds is not None:
            self.targets["show_control"] = SimpleNamespace(
                par=SimpleNamespace(
                    Crossfadesec=FakePar(crossfade_seconds),
                )
            )
        self.par = SimpleNamespace(
            Streamdiffusionpath=FakePar("StreamDiffusionTD")
        )

    def op(self, path):
        return self.targets.get(path)


class PodcastTdControllerTests(unittest.TestCase):
    def test_reads_live_crossfade_from_show_control(self) -> None:
        controller = PodcastVisualController.__new__(PodcastVisualController)
        controller.owner_comp = FakeOwner(None, crossfade_seconds=8.25)

        self.assertEqual(controller._show_control_crossfade_ms(), 8_250)

    def test_missing_show_control_uses_scene_plan_fade(self) -> None:
        controller = PodcastVisualController.__new__(PodcastVisualController)
        controller.owner_comp = FakeOwner(None)

        self.assertIsNone(controller._show_control_crossfade_ms())

    def test_writes_two_prompt_and_seed_blocks_for_crossfade(self) -> None:
        target = FakeTarget()
        controller = PodcastVisualController.__new__(PodcastVisualController)
        controller.owner_comp = FakeOwner(target)
        controller.last_streamdiffusion_signature = None
        frame = SimpleNamespace(
            prompt_layers=[
                SimpleNamespace(
                    scene_id="old",
                    text="old prompt",
                    weight=0.25,
                    seed=11,
                ),
                SimpleNamespace(
                    scene_id="new",
                    text="new prompt",
                    weight=0.75,
                    seed=22,
                ),
            ]
        )

        state = controller._write_streamdiffusion(frame)

        self.assertEqual(state, "connected")
        self.assertEqual(target.par.Promptdict.sequence.numBlocks, 2)
        self.assertEqual(
            target.par.Promptdict.sequence[0].par.Concept.val,
            "old prompt",
        )
        self.assertEqual(
            target.par.Promptdict.sequence[1].par.Concept.val,
            "new prompt",
        )
        self.assertEqual(
            target.par.Promptdict.sequence[0].par.Weight.val,
            0.25,
        )
        self.assertEqual(
            target.par.Promptdict.sequence[1].par.Weight.val,
            0.75,
        )
        self.assertEqual(
            target.par.Seeddict.sequence[0].par.Seedval.val,
            11,
        )
        self.assertEqual(
            target.par.Seeddict.sequence[1].par.Seedval.val,
            22,
        )
        self.assertTrue(target.par.Normpweights.val)
        self.assertEqual(target.par.Setinterpolation.val, "slerp")

        assignments = (
            target.par.Promptdict.sequence[0].par.Concept.assignments
        )
        self.assertEqual(controller._write_streamdiffusion(frame), "connected")
        self.assertEqual(
            target.par.Promptdict.sequence[0].par.Concept.assignments,
            assignments,
        )

    def test_missing_operator_remains_provider_neutral(self) -> None:
        controller = PodcastVisualController.__new__(PodcastVisualController)
        controller.owner_comp = FakeOwner(None)
        controller.last_streamdiffusion_signature = ("stale",)
        frame = SimpleNamespace(
            prompt_layers=[
                SimpleNamespace(
                    scene_id="scene",
                    text="prompt",
                    weight=1.0,
                    seed=11,
                )
            ]
        )

        self.assertEqual(
            controller._write_streamdiffusion(frame),
            "adapter_pending",
        )
        self.assertIsNone(controller.last_streamdiffusion_signature)

    def test_mirrors_crossfade_to_primary_and_backup(self) -> None:
        primary = FakeTarget()
        backup = FakeTarget()
        owner = FakeOwner(primary, backup)
        owner.par.Streamdiffusionpath.val = (
            "StreamDiffusionTD;StreamDiffusionTD1"
        )
        controller = PodcastVisualController.__new__(PodcastVisualController)
        controller.owner_comp = owner
        controller.last_streamdiffusion_signature = None
        frame = SimpleNamespace(
            prompt_layers=[
                SimpleNamespace(
                    scene_id="old",
                    text="old prompt",
                    weight=0.4,
                    seed=11,
                ),
                SimpleNamespace(
                    scene_id="new",
                    text="new prompt",
                    weight=0.6,
                    seed=22,
                ),
            ]
        )

        self.assertEqual(
            controller._write_streamdiffusion(frame),
            "connected:2",
        )
        for target in (primary, backup):
            self.assertEqual(target.par.Promptdict.sequence.numBlocks, 2)
            self.assertEqual(
                target.par.Promptdict.sequence[0].par.Weight.val,
                0.4,
            )
            self.assertEqual(
                target.par.Promptdict.sequence[1].par.Weight.val,
                0.6,
            )
            self.assertEqual(target.par.Setinterpolation.val, "slerp")


if __name__ == "__main__":
    unittest.main()
