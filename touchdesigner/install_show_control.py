"""Upgrade an existing podcast_visualizer while preserving show-control values."""

import importlib.util
from pathlib import Path
import sys


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def install():
    connector = op("/project1/podcast_visualizer")
    if connector is None:
        raise RuntimeError(
            "/project1/podcast_visualizer was not found; run the full "
            "connector installer first."
        )

    project_root = Path(project.folder)
    touchdesigner_root = project_root / "touchdesigner"

    controller_path = touchdesigner_root / "podcast_td_controller.py"
    connector.par.Controllermodule = str(controller_path)
    connector.op("execute_callbacks").text = (
        touchdesigner_root / "execute_callbacks.py"
    ).read_text(encoding="utf-8")
    connector.op("parameter_callbacks").text = (
        touchdesigner_root / "parameter_callbacks.py"
    ).read_text(encoding="utf-8")

    component_module = _load_module(
        "recovered_homes_show_control_component",
        touchdesigner_root / "show_control_component.py",
    )
    control = component_module.install_show_control(
        connector,
        project_root,
        operator_types={
            "baseCOMP": baseCOMP,
            "tableDAT": tableDAT,
            "parameterexecuteDAT": parameterexecuteDAT,
            "levelTOP": levelTOP,
            "hsvadjustTOP": hsvadjustTOP,
            "switchTOP": switchTOP,
            "nullTOP": nullTOP,
            "audiofileinCHOP": audiofileinCHOP,
            "switchCHOP": switchCHOP,
            "audiodeviceoutCHOP": audiodeviceoutCHOP,
            "syphonspoutoutTOP": syphonspoutoutTOP,
            "op": op,
        },
    )

    callbacks = connector.op("execute_callbacks")
    callbacks.par.framestart = True
    callbacks.par.start = True
    callbacks.par.create = True
    audio_out = connector.op("audio_out")
    if audio_out is not None:
        audio_out.par.active.expr = "parent().par.Audioenabled"
    callbacks.module._CONTROLLER = None
    controller = callbacks.module.get_controller()
    callbacks.module._synchronize_show_control()
    controller.update(float(connector.par.Playheadsec.eval()))
    control.current = True
    return control


installed_show_control = install()
