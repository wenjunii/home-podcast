from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).parents[1]


def load_module(name, relative_path):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class FakePar:
    def __init__(self, name, value):
        self.name = name
        self._value = value

    def eval(self):
        return self._value

    @property
    def val(self):
        return self._value

    @val.setter
    def val(self, value):
        self._value = value


class FakePars(SimpleNamespace):
    def __setattr__(self, name, value):
        existing = self.__dict__.get(name)
        if isinstance(existing, FakePar):
            existing.val = value
            return
        super().__setattr__(name, value)


class ShowControlCallbackTests(unittest.TestCase):
    def test_runtime_control_file_forces_live_off_in_3080_profile(self):
        module = load_module(
            "show_control_callbacks_runtime_test",
            "touchdesigner/show_control_callbacks.py",
        )
        with tempfile.TemporaryDirectory() as directory:
            control_path = Path(directory) / "control.json"
            connector = SimpleNamespace(
                par=FakePars(
                    Livecontroljson=FakePar("Livecontroljson", str(control_path)),
                    Runtimeprofile=FakePar("Runtimeprofile", "5090_live"),
                    Currentnarrationid=FakePar("Currentnarrationid", "story-one"),
                    Canonicalvisuals=FakePar("Canonicalvisuals", "visuals.json"),
                )
            )
            control = SimpleNamespace(
                par=FakePars(
                    Runtimeprofile=FakePar("Runtimeprofile", "3080_safe"),
                    Livevariations=FakePar("Livevariations", True),
                    Narrationvariation=FakePar("Narrationvariation", True),
                    Speechvariation=FakePar("Speechvariation", True),
                    Visualvariation=FakePar("Visualvariation", True),
                    Interpretivecasting=FakePar("Interpretivecasting", True),
                    Randomvariationseeds=FakePar("Randomvariationseeds", False),
                    Variationseed=FakePar("Variationseed", 77),
                )
            )
            control.parent = lambda: connector
            module.parent = lambda: control

            result = module._write_live_control(regenerate=True)

            stored = json.loads(control_path.read_text(encoding="utf-8"))
            self.assertFalse(control.par.Livevariations.eval())
            self.assertFalse(stored["enabled"])
            self.assertEqual(stored["profile"], "3080_safe")
            self.assertEqual(stored["regeneration_nonce"], 1)
            self.assertEqual(stored["fixed_seed"], 77)
            self.assertEqual(result, stored)

    def test_audio_toggle_updates_legacy_constant_audio_output(self):
        module = load_module(
            "show_control_callbacks_audio_test",
            "touchdesigner/show_control_callbacks.py",
        )
        connector = SimpleNamespace(
            par=FakePars(
                Audioenabled=FakePar("Audioenabled", False),
            )
        )
        audio_out = SimpleNamespace(
            par=FakePars(active=FakePar("active", False))
        )
        connector.op = lambda name: (
            audio_out if name == "audio_out" else None
        )
        control = SimpleNamespace()
        control.parent = lambda: connector
        module.parent = lambda: control

        changed = FakePar("Audioenabled", True)
        module.onValueChange(changed, False)

        self.assertTrue(connector.par.Audioenabled.eval())
        self.assertTrue(audio_out.par.active.eval())

    def test_audio_source_selection_is_exclusive(self):
        module = load_module(
            "show_control_callbacks_audio_source_test",
            "touchdesigner/show_control_callbacks.py",
        )
        source_switch = SimpleNamespace(
            par=FakePars(index=FakePar("index", 0))
        )
        connector = SimpleNamespace(
            par=FakePars(
                Audiosource=FakePar("Audiosource", "voices"),
            )
        )
        connector.op = lambda name: (
            source_switch if name == "audiosource_switch" else None
        )
        control = SimpleNamespace()
        control.parent = lambda: connector
        module.parent = lambda: control

        module.onValueChange(
            FakePar("Audiosource", "soundscape"),
            "voices",
        )

        self.assertEqual(connector.par.Audiosource.eval(), "soundscape")
        self.assertEqual(source_switch.par.index.eval(), 1)

    def test_visual_path_switch_reloads_without_changing_audio(self):
        module = load_module(
            "show_control_callbacks_visual_path_test",
            "touchdesigner/show_control_callbacks.py",
        )
        reloads = []
        controller = SimpleNamespace(reload=lambda: reloads.append(True))
        execute_callbacks = SimpleNamespace(
            module=SimpleNamespace(get_controller=lambda: controller)
        )
        connector = SimpleNamespace(
            par=FakePars(
                Visualpath=FakePar("Visualpath", "original"),
                Audiosource=FakePar("Audiosource", "soundscape"),
            ),
            op=lambda name: (
                execute_callbacks if name == "execute_callbacks" else None
            ),
        )
        control = SimpleNamespace()
        control.parent = lambda: connector
        module.parent = lambda: control

        module.onValueChange(
            FakePar("Visualpath", "human_figures"),
            "original",
        )

        self.assertEqual(connector.par.Visualpath.eval(), "human_figures")
        self.assertEqual(connector.par.Audiosource.eval(), "soundscape")
        self.assertEqual(len(reloads), 1)

        module.onValueChange(FakePar("Visualpath", "balanced"), "human_figures")
        self.assertEqual(connector.par.Visualpath.eval(), "balanced")
        self.assertEqual(connector.par.Audiosource.eval(), "soundscape")
        self.assertEqual(len(reloads), 2)
        self.assertEqual(module._visual_path_index(2), 2)
        self.assertEqual(module._visual_path_index("Balanced Memories"), 2)

    def test_play_toggle_updates_touchdesigner_timeline(self):
        module = load_module(
            "show_control_callbacks_play_test",
            "touchdesigner/show_control_callbacks.py",
        )
        timeline = SimpleNamespace(
            par=FakePars(play=FakePar("play", False))
        )
        module.op = lambda path: timeline

        module.onValueChange(FakePar("Play", True), False)

        self.assertTrue(timeline.par.play.eval())

    def test_reset_color_restores_level_top_neutral_values(self):
        module = load_module(
            "show_control_callbacks_reset_color_test",
            "touchdesigner/show_control_callbacks.py",
        )
        control = SimpleNamespace(
            par=FakePars(
                Colorenabled=FakePar("Colorenabled", False),
                Brightness=FakePar("Brightness", 0.25),
                Contrast=FakePar("Contrast", 1.5),
                Gamma=FakePar("Gamma", 0.8),
                Blacklevel=FakePar("Blacklevel", 0.1),
                Opacity=FakePar("Opacity", 0.5),
                Hue=FakePar("Hue", 45.0),
                Saturation=FakePar("Saturation", 0.5),
                Value=FakePar("Value", 1.5),
            )
        )
        controller = SimpleNamespace(update=lambda playhead: None)
        connector = SimpleNamespace(
            par=FakePars(
                Enabled=FakePar("Enabled", True),
                Playheadsec=FakePar("Playheadsec", 0.0),
            ),
            op=lambda name: (
                SimpleNamespace(
                    module=SimpleNamespace(
                        get_controller=lambda: controller,
                    )
                )
                if name == "execute_callbacks"
                else None
            ),
        )
        connector.parent = lambda: None
        control.parent = lambda: connector
        module.parent = lambda: control

        module.onPulse(FakePar("Resetcolor", None))

        self.assertTrue(control.par.Colorenabled.eval())
        self.assertEqual(control.par.Brightness.eval(), 1.0)
        self.assertEqual(control.par.Contrast.eval(), 1.0)
        self.assertEqual(control.par.Gamma.eval(), 1.0)
        self.assertEqual(control.par.Blacklevel.eval(), 0.0)
        self.assertEqual(control.par.Opacity.eval(), 1.0)
        self.assertEqual(control.par.Hue.eval(), 0.0)
        self.assertEqual(control.par.Saturation.eval(), 1.0)
        self.assertEqual(control.par.Value.eval(), 1.0)


class ExecuteCallbackTests(unittest.TestCase):
    def test_startup_sync_repairs_play_and_audio_state(self):
        module = load_module(
            "execute_callbacks_sync_test",
            "touchdesigner/execute_callbacks.py",
        )
        show_control = SimpleNamespace(
            par=FakePars(
                Play=FakePar("Play", False),
                Audioenabled=FakePar("Audioenabled", False),
                Audiosource=FakePar("Audiosource", "soundscape"),
                Visualpath=FakePar("Visualpath", "human_figures"),
            )
        )
        audio_out = SimpleNamespace(
            par=FakePars(active=FakePar("active", True))
        )
        connector = SimpleNamespace(
            par=FakePars(
                Audioenabled=FakePar("Audioenabled", True),
                Audiosource=FakePar("Audiosource", "voices"),
                Visualpath=FakePar("Visualpath", "original"),
            )
        )
        source_switch = SimpleNamespace(
            par=FakePars(index=FakePar("index", 0))
        )
        connector.op = lambda name: {
            "show_control": show_control,
            "audio_out": audio_out,
            "audiosource_switch": source_switch,
        }.get(name)
        timeline = SimpleNamespace(
            par=FakePars(play=FakePar("play", True))
        )
        project_root = SimpleNamespace(
            time=SimpleNamespace(frame=531)
        )
        module.parent = lambda: connector
        module.op = lambda path: (
            timeline if path == "/local/time" else project_root
        )

        module._synchronize_show_control(reset_paused_start=True)

        self.assertFalse(timeline.par.play.eval())
        self.assertEqual(project_root.time.frame, 1)
        self.assertFalse(connector.par.Audioenabled.eval())
        self.assertFalse(audio_out.par.active.eval())
        self.assertEqual(connector.par.Audiosource.eval(), "soundscape")
        self.assertEqual(source_switch.par.index.eval(), 1)
        self.assertEqual(connector.par.Visualpath.eval(), "human_figures")

    def test_regular_sync_preserves_paused_seek_position(self):
        module = load_module(
            "execute_callbacks_paused_seek_test",
            "touchdesigner/execute_callbacks.py",
        )
        show_control = SimpleNamespace(par=FakePars(Play=FakePar("Play", False)))
        connector = SimpleNamespace(par=FakePars(), op=lambda name: show_control if name == "show_control" else None)
        timeline = SimpleNamespace(par=FakePars(play=FakePar("play", False)))
        project_root = SimpleNamespace(time=SimpleNamespace(frame=901))
        module.parent = lambda: connector
        module.op = lambda path: timeline if path == "/local/time" else project_root

        module._synchronize_show_control()
        module._synchronize_show_control()

        self.assertEqual(project_root.time.frame, 901)
        self.assertFalse(timeline.par.play.eval())

    def test_load_events_request_startup_reset_but_frame_events_do_not(self):
        module = load_module(
            "execute_callbacks_reset_scope_test",
            "touchdesigner/execute_callbacks.py",
        )
        calls = []
        module._synchronize_show_control = lambda **kwargs: calls.append(kwargs)
        module._synchronize_live_control_file = lambda: None
        module.get_controller = lambda: SimpleNamespace(update=lambda seconds: None)
        module.parent = lambda: SimpleNamespace(par=FakePars(Enabled=FakePar("Enabled", False)))

        module.onStart()
        module.onCreate()
        module.onFrameStart(100)

        self.assertEqual(calls, [{"reset_paused_start": True}, {"reset_paused_start": True}, {}])


class ConnectorParameterCallbackTests(unittest.TestCase):
    def test_narration_change_updates_live_control_file(self):
        module = load_module(
            "parameter_callbacks_runtime_test",
            "touchdesigner/parameter_callbacks.py",
        )
        writes = []
        callbacks = SimpleNamespace(
            module=SimpleNamespace(
                _write_live_control=lambda: writes.append(True)
            )
        )
        connector = SimpleNamespace(
            op=lambda name: (
                callbacks if name == "show_control/control_callbacks" else None
            )
        )
        module.parent = lambda: connector

        module.onValueChange(FakePar("Currentnarrationid", "story-one"), "")

        self.assertEqual(writes, [True])


if __name__ == "__main__":
    unittest.main()
