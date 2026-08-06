from __future__ import annotations

import importlib.util
import sys
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

        module._synchronize_show_control()

        self.assertFalse(timeline.par.play.eval())
        self.assertEqual(project_root.time.frame, 1)
        self.assertFalse(connector.par.Audioenabled.eval())
        self.assertFalse(audio_out.par.active.eval())
        self.assertEqual(connector.par.Audiosource.eval(), "soundscape")
        self.assertEqual(source_switch.par.index.eval(), 1)
        self.assertEqual(connector.par.Visualpath.eval(), "human_figures")


if __name__ == "__main__":
    unittest.main()
