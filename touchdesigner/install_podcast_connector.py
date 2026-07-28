"""Run inside TouchDesigner 2025.32820 to install the connector COMP."""

from pathlib import Path
import importlib.util
import json
import math
import sys


def install():
    root = op("/project1")
    existing = root.op("podcast_visualizer")
    if existing is not None:
        existing.destroy()

    connector = root.create(baseCOMP, "podcast_visualizer")
    connector.nodeX = 300
    connector.nodeY = -150
    connector.nodeWidth = 220
    connector.nodeHeight = 160
    connector.comment = (
        "Recovered Homes scene sequencer\n"
        "StreamDiffusionTD prompt/seed adapter included."
    )

    page = connector.appendCustomPage("Podcast")
    page.appendToggle("Enabled", label="Enabled")
    page.appendToggle("Audioenabled", label="Audio Enabled")
    page.appendFloat("Playheadsec", label="Playhead Seconds")
    page.appendFile("Scenejson", label="Scene JSON")
    page.appendFile("Audiofile", label="Voices-only Audio")
    page.appendFile("Sequencermodule", label="Sequencer Module")
    page.appendFile("Controllermodule", label="Controller Module")
    page.appendStr("Targettd", label="Target TD")
    page.appendStr("Streamdiffusionpath", label="StreamDiffusion OP")

    project_root = Path(project.folder)
    scene_json = (
        project_root
        / "episodes"
        / "2013-12.01"
        / "visuals"
        / "2013-12.01-visual-scenes.json"
    )
    scene_plan = json.loads(scene_json.read_text(encoding="utf-8"))
    pilot_end_frame = (
        math.ceil(float(scene_plan["duration_ms"]) / 1000.0 * project.cookRate) + 1
    )
    time_component = op("/local/time")
    if int(time_component.par.end.eval()) < pilot_end_frame:
        time_component.par.end = pilot_end_frame
        time_component.par.rangeend = pilot_end_frame
    time_component.par.play = False
    root.time.frame = 1

    connector.par.Enabled = True
    connector.par.Audioenabled = False
    connector.par.Playheadsec = 0
    connector.par.Playheadsec.expr = "max(0, me.time.seconds)"
    connector.par.Scenejson = str(scene_json)
    connector.par.Audiofile = str(
        project_root
        / "episodes"
        / "2013-12.01"
        / "audio"
        / "2013-12.01-voices-only.mp3"
    )
    connector.par.Sequencermodule = str(
        project_root / "touchdesigner" / "podcast_sequencer.py"
    )
    connector.par.Controllermodule = str(
        project_root / "touchdesigner" / "podcast_td_controller.py"
    )
    connector.par.Targettd = "2025.32820"
    connector.par.Streamdiffusionpath = "StreamDiffusionTD"

    for name, x, y in (
        ("prompt_out", 0, 0),
        ("caption_out", 220, 0),
        ("status_out", 440, 0),
    ):
        table = connector.create(tableDAT, name)
        table.nodeX = x
        table.nodeY = y

    audio = connector.create(audiofileinCHOP, "voices_only_audio")
    audio.nodeX = 0
    audio.nodeY = -160
    audio.par.file = str(connector.par.Audiofile.eval())
    audio.par.playmode = "locked"
    audio.par.play = True
    audio.par.repeat = False

    audio_out = connector.create(audiodeviceoutCHOP, "audio_out")
    audio_out.nodeX = 220
    audio_out.nodeY = -160
    audio_out.inputConnectors[0].connect(audio)
    audio_out.par.active.expr = "parent().par.Audioenabled"

    callbacks = connector.create(executeDAT, "execute_callbacks")
    callbacks.nodeX = 440
    callbacks.nodeY = -160
    callbacks.par.framestart = True
    callbacks.par.start = True
    callbacks.par.create = True
    callbacks.text = (
        project_root / "touchdesigner" / "execute_callbacks.py"
    ).read_text(
        encoding="utf-8"
    )

    parameter_callbacks = connector.create(
        parameterexecuteDAT,
        "parameter_callbacks",
    )
    parameter_callbacks.nodeX = 660
    parameter_callbacks.nodeY = -160
    parameter_callbacks.par.op = connector.path
    parameter_callbacks.par.pars = "Playheadsec"
    parameter_callbacks.par.valuechange = True
    parameter_callbacks.par.valueschanged = False
    parameter_callbacks.text = (
        project_root / "touchdesigner" / "parameter_callbacks.py"
    ).read_text(encoding="utf-8")

    show_control_path = (
        project_root / "touchdesigner" / "show_control_component.py"
    )
    show_control_spec = importlib.util.spec_from_file_location(
        "recovered_homes_show_control_component",
        show_control_path,
    )
    show_control_module = importlib.util.module_from_spec(show_control_spec)
    sys.modules[show_control_spec.name] = show_control_module
    show_control_spec.loader.exec_module(show_control_module)
    show_control_module.install_show_control(
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

    controller = callbacks.module.get_controller()
    controller.update(float(connector.par.Playheadsec.eval()))
    connector.current = True
    return connector


installed_connector = install()
