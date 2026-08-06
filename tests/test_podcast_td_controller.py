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


class FakeColorNode:
    def __init__(self, **parameters) -> None:
        self.par = SimpleNamespace(
            **{
                name: FakePar(value)
                for name, value in parameters.items()
            }
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
    def __init__(
        self,
        target,
        backup=None,
        crossfade_seconds=None,
        random_seeds=False,
    ) -> None:
        self.targets = {
            "StreamDiffusionTD": target,
            "StreamDiffusionTD1": backup,
        }
        if crossfade_seconds is not None or random_seeds:
            self.targets["show_control"] = SimpleNamespace(
                par=SimpleNamespace(
                    Crossfadesec=FakePar(
                        0.0
                        if crossfade_seconds is None
                        else crossfade_seconds
                    ),
                    Randomseeds=FakePar(random_seeds),
                )
            )
        self.par = SimpleNamespace(
            Streamdiffusionpath=FakePar("StreamDiffusionTD"),
            Scenejson=FakePar(str(Path(__file__).resolve())),
            Humanfigurejson=FakePar(str(MODULE_PATH.resolve())),
            Visualpath=FakePar("original"),
        )

    def op(self, path):
        return self.targets.get(path)


class PodcastTdControllerTests(unittest.TestCase):
    def test_selects_original_or_human_figure_scene_path(self) -> None:
        owner = FakeOwner(None)
        controller = PodcastVisualController.__new__(PodcastVisualController)
        controller.owner_comp = owner

        self.assertEqual(
            controller._selected_scene_path(),
            str(Path(__file__).resolve()),
        )
        owner.par.Visualpath.val = "human_figures"
        self.assertEqual(
            controller._selected_scene_path(),
            str(MODULE_PATH.resolve()),
        )

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

    def test_random_seed_bank_changes_by_loop_but_is_stable_within_loop(
        self,
    ) -> None:
        controller = PodcastVisualController.__new__(PodcastVisualController)
        controller.owner_comp = FakeOwner(
            None,
            crossfade_seconds=8,
            random_seeds=True,
        )
        controller.sequencer = SimpleNamespace(
            duration_ms=30_000,
            scenes=[
                {"scene_id": "first"},
                {"scene_id": "last"},
            ],
        )
        controller.seed_salt = 1234
        controller.seed_generation = 7
        frame = SimpleNamespace(
            scene_index=1,
            prompt_layers=[
                SimpleNamespace(
                    scene_id="last",
                    role="narrative",
                    text="last prompt",
                    weight=0.5,
                    seed=22,
                ),
                SimpleNamespace(
                    scene_id="first",
                    role="narrative",
                    text="first prompt",
                    weight=0.5,
                    seed=11,
                ),
            ],
        )

        first_pass = controller._controlled_prompt_layers(frame)
        second_pass = controller._controlled_prompt_layers(frame)
        controller.seed_generation += 1
        next_loop = controller._controlled_prompt_layers(frame)

        self.assertEqual(
            [layer.seed for layer in first_pass],
            [layer.seed for layer in second_pass],
        )
        self.assertNotEqual(
            [layer.seed for layer in first_pass],
            [layer.seed for layer in next_loop],
        )
        self.assertNotEqual(first_pass[0].seed, 22)
        self.assertNotEqual(first_pass[1].seed, 11)

    def test_random_seeds_remain_continuous_across_loop_crossfade(
        self,
    ) -> None:
        controller = PodcastVisualController.__new__(PodcastVisualController)
        controller.owner_comp = FakeOwner(
            None,
            crossfade_seconds=8,
            random_seeds=True,
        )
        controller.sequencer = SimpleNamespace(
            duration_ms=30_000,
            scenes=[
                {"scene_id": "first"},
                {"scene_id": "last"},
            ],
        )
        controller.seed_salt = 9876
        controller.seed_generation = 3
        layers = [
            SimpleNamespace(
                scene_id="last",
                role="narrative",
                text="last prompt",
                weight=0.5,
                seed=22,
            ),
            SimpleNamespace(
                scene_id="first",
                role="narrative",
                text="first prompt",
                weight=0.5,
                seed=11,
            ),
        ]
        end_frame = SimpleNamespace(scene_index=1, prompt_layers=layers)
        end_seeds = [
            layer.seed
            for layer in controller._controlled_prompt_layers(end_frame)
        ]

        controller.seed_generation = 4
        start_frame = SimpleNamespace(scene_index=0, prompt_layers=layers)
        start_seeds = [
            layer.seed
            for layer in controller._controlled_prompt_layers(start_frame)
        ]

        self.assertEqual(end_seeds, start_seeds)

    def test_detected_loop_advances_random_seed_bank(self) -> None:
        controller = PodcastVisualController.__new__(PodcastVisualController)
        controller.owner_comp = FakeOwner(
            None,
            crossfade_seconds=8,
            random_seeds=True,
        )
        controller.sequencer = SimpleNamespace(duration_ms=30_000)
        controller.last_playhead_ms = 29_900
        controller.last_streamdiffusion_signature = ("stale",)
        controller.seed_generation = 2

        controller._advance_loop_seed_if_needed(100)

        self.assertEqual(controller.seed_generation, 3)
        self.assertIsNone(controller.last_streamdiffusion_signature)

    def test_color_controls_drive_level_hsv_and_bypass_switch(self) -> None:
        owner = FakeOwner(None, crossfade_seconds=8)
        owner.targets["show_control"].par = SimpleNamespace(
            Colorenabled=FakePar(True),
            Brightness=FakePar(0.15),
            Contrast=FakePar(1.2),
            Gamma=FakePar(0.9),
            Blacklevel=FakePar(0.03),
            Opacity=FakePar(0.8),
            Hue=FakePar(-30),
            Saturation=FakePar(1.4),
            Value=FakePar(1.1),
        )
        level = FakeColorNode(
            brightness1=1.0,
            contrast=1.0,
            gamma1=1.0,
            blacklevel=0.0,
            opacity=1.0,
        )
        hsv = FakeColorNode(
            hueoffset=0.0,
            saturationmult=1.0,
            valuemult=1.0,
        )
        switch = FakeColorNode(index=0)
        owner.targets.update(
            {
                "color_level_1": level,
                "color_hsv_1": hsv,
                "color_switch_1": switch,
            }
        )
        controller = PodcastVisualController.__new__(PodcastVisualController)
        controller.owner_comp = owner
        controller.last_color_signature = None

        self.assertEqual(controller._write_color_controls(), "connected")
        self.assertEqual(level.par.brightness1.val, 0.15)
        self.assertEqual(level.par.contrast.val, 1.2)
        self.assertEqual(level.par.gamma1.val, 0.9)
        self.assertEqual(level.par.blacklevel.val, 0.03)
        self.assertEqual(level.par.opacity.val, 0.8)
        self.assertEqual(hsv.par.hueoffset.val, 330.0)
        self.assertEqual(hsv.par.saturationmult.val, 1.4)
        self.assertEqual(hsv.par.valuemult.val, 1.1)
        self.assertEqual(switch.par.index.val, 1)

    def test_missing_brightness_control_uses_level_top_neutral(self) -> None:
        owner = FakeOwner(None, crossfade_seconds=8)
        owner.targets["show_control"].par = SimpleNamespace(
            Colorenabled=FakePar(True),
        )
        level = FakeColorNode(
            brightness1=0.0,
            contrast=0.0,
            gamma1=0.0,
            blacklevel=1.0,
            opacity=0.0,
        )
        hsv = FakeColorNode(
            hueoffset=45.0,
            saturationmult=0.0,
            valuemult=0.0,
        )
        switch = FakeColorNode(index=0)
        owner.targets.update(
            {
                "color_level_1": level,
                "color_hsv_1": hsv,
                "color_switch_1": switch,
            }
        )
        controller = PodcastVisualController.__new__(PodcastVisualController)
        controller.owner_comp = owner
        controller.last_color_signature = None

        self.assertEqual(controller._write_color_controls(), "connected")
        self.assertEqual(level.par.brightness1.val, 1.0)
        self.assertEqual(level.par.contrast.val, 1.0)
        self.assertEqual(level.par.gamma1.val, 1.0)
        self.assertEqual(level.par.blacklevel.val, 0.0)
        self.assertEqual(level.par.opacity.val, 1.0)
        self.assertEqual(hsv.par.hueoffset.val, 0.0)
        self.assertEqual(hsv.par.saturationmult.val, 1.0)
        self.assertEqual(hsv.par.valuemult.val, 1.0)


if __name__ == "__main__":
    unittest.main()
