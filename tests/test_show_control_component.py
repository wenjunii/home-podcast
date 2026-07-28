from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


MODULE_PATH = (
    Path(__file__).parents[1]
    / "touchdesigner"
    / "show_control_component.py"
)
SPEC = importlib.util.spec_from_file_location(
    "show_control_component",
    MODULE_PATH,
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class FakePar:
    def __init__(self, value) -> None:
        self.value = value

    def eval(self):
        return self.value


class FakeConnector:
    def __init__(self, owner, index, *, is_input) -> None:
        self.owner = owner
        self.index = index
        self.is_input = is_input
        self.connections = []

    def connect(self, target):
        if not self.is_input:
            input_connector = (
                target
                if isinstance(target, FakeConnector)
                else target.inputConnectors[0]
            )
            input_connector.connect(self)
            return
        self.disconnect()
        output = (
            target
            if isinstance(target, FakeConnector)
            else target.outputConnectors[0]
        )
        self.connections.append(output)
        output.connections.append(self)

    def disconnect(self):
        for connection in list(self.connections):
            if self in connection.connections:
                connection.connections.remove(self)
        self.connections.clear()


class FakeNode:
    def __init__(self, parent, name, *, inputs=1) -> None:
        self.parent = parent
        self.name = name
        self.path = f"/project1/podcast_visualizer/{name}"
        self.comment = ""
        self.valid = True
        self.nodeX = 0
        self.nodeY = 0
        self.nodeWidth = 100
        self.inputConnectors = [
            FakeConnector(self, index, is_input=True)
            for index in range(inputs)
        ]
        self.outputConnectors = [
            FakeConnector(self, 0, is_input=False)
        ]

    def destroy(self):
        for connector in self.inputConnectors + self.outputConnectors:
            connector.disconnect()
        self.valid = False
        self.parent.nodes.pop(self.name, None)


class FakeContainer:
    def __init__(self) -> None:
        self.nodes = {}
        self.par = SimpleNamespace(
            Streamdiffusionpath=FakePar("StreamDiffusionTD")
        )

    def add(self, name, *, inputs=1):
        node = FakeNode(self, name, inputs=inputs)
        self.nodes[name] = node
        return node

    def op(self, name):
        return self.nodes.get(name)

    def create(self, operator_type, name):
        inputs = 2 if operator_type == "switchTOP" else 1
        return self.add(name, inputs=inputs)


class ShowControlComponentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.container = FakeContainer()
        self.target = self.container.add("StreamDiffusionTD", inputs=0)
        self.display = self.container.add("display")
        self.display.inputConnectors[0].connect(self.target)
        self.operator_types = {
            "levelTOP": "levelTOP",
            "hsvadjustTOP": "hsvadjustTOP",
            "switchTOP": "switchTOP",
            "nullTOP": "nullTOP",
        }

    def test_color_pipeline_reroutes_existing_output(self) -> None:
        outputs = MODULE._install_color_pipelines(
            self.container,
            self.operator_types,
        )

        self.assertEqual([node.name for node in outputs], ["color_out_1"])
        self.assertEqual(
            self.display.inputConnectors[0].connections[0].owner.name,
            "color_out_1",
        )
        switch = self.container.op("color_switch_1")
        self.assertEqual(
            switch.inputConnectors[0].connections[0].owner.name,
            "StreamDiffusionTD",
        )
        self.assertEqual(
            switch.inputConnectors[1].connections[0].owner.name,
            "color_hsv_1",
        )

    def test_reinstall_preserves_downstream_routing(self) -> None:
        MODULE._install_color_pipelines(
            self.container,
            self.operator_types,
        )
        MODULE._install_color_pipelines(
            self.container,
            self.operator_types,
        )

        self.assertEqual(
            self.display.inputConnectors[0].connections[0].owner.name,
            "color_out_1",
        )
        self.assertEqual(
            sorted(
                name
                for name in self.container.nodes
                if name.startswith("color_")
            ),
            [
                "color_hsv_1",
                "color_level_1",
                "color_out_1",
                "color_switch_1",
            ],
        )

    def test_brightness_uses_level_top_neutral_default(self) -> None:
        self.assertEqual(MODULE.COLOR_DEFAULTS["Brightness"], 1.0)

    def test_detects_legacy_brightness_range_for_migration(self) -> None:
        parameter = SimpleNamespace(min=-1.0, max=1.0)

        self.assertTrue(MODULE._has_range(parameter, -1.0, 1.0))
        self.assertFalse(MODULE._has_range(parameter, 0.0, 2.0))

    def test_audio_source_normalization_excludes_combined_track(self) -> None:
        self.assertEqual(
            MODULE.AUDIO_SOURCE_NAMES,
            ("voices", "soundscape"),
        )
        self.assertEqual(
            MODULE._normalize_audio_source("Human Voices Only"),
            "voices",
        )
        self.assertEqual(
            MODULE._normalize_audio_source("Soundscape Only"),
            "soundscape",
        )
        self.assertEqual(
            MODULE._normalize_audio_source("combined"),
            "voices",
        )


if __name__ == "__main__":
    unittest.main()
