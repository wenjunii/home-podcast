"""Run inside TouchDesigner after moving the repository or a local .toe file.

This updates only the existing Recovered Homes connector's portable file paths
and tracked callback source. It does not destroy, recreate, or start either
paid StreamDiffusionTD component.
"""

from pathlib import Path


def rebind_project_paths():
    project_root = Path(project.folder).resolve()
    connector = op("/project1/podcast_visualizer")
    if connector is None:
        raise RuntimeError(
            "Missing /project1/podcast_visualizer; run the connector installer "
            "in a fresh project first."
        )

    paths = {
        "scene": (
            project_root
            / "episodes"
            / "2013-12.01"
            / "visuals"
            / "2013-12.01-visual-scenes.json"
        ),
        "human_scene": (
            project_root
            / "episodes"
            / "2013-12.01"
            / "visuals"
            / "2013-12.01-visual-scenes-human-figures.json"
        ),
        "voices_audio": (
            project_root
            / "episodes"
            / "2013-12.01"
            / "audio"
            / "2013-12.01-voices-only.mp3"
        ),
        "soundscape_audio": (
            project_root
            / "episodes"
            / "2013-12.01"
            / "audio"
            / "2013-12.01-soundscape-only.mp3"
        ),
        "sequencer": project_root / "touchdesigner" / "podcast_sequencer.py",
        "controller": project_root / "touchdesigner" / "podcast_td_controller.py",
        "execute_callbacks": (
            project_root / "touchdesigner" / "execute_callbacks.py"
        ),
        "parameter_callbacks": (
            project_root / "touchdesigner" / "parameter_callbacks.py"
        ),
        "show_control_callbacks": (
            project_root / "touchdesigner" / "show_control_callbacks.py"
        ),
    }
    missing = [str(path) for path in paths.values() if not path.is_file()]
    if missing:
        raise FileNotFoundError(
            "Save the .toe in the cloned repository root before rebinding. "
            "Missing tracked files: " + ", ".join(missing)
        )

    connector.par.Scenejson = str(paths["scene"])
    human_scene_parameter = getattr(connector.par, "Humanfigurejson", None)
    if human_scene_parameter is None:
        raise RuntimeError(
            "Missing Humanfigurejson parameter; run install_show_control.py "
            "before rebinding project paths."
        )
    human_scene_parameter.val = str(paths["human_scene"])
    connector.par.Audiofile = str(paths["voices_audio"])
    soundscape_parameter = getattr(
        connector.par,
        "Soundscapeaudiofile",
        None,
    )
    if soundscape_parameter is not None:
        soundscape_parameter.val = str(paths["soundscape_audio"])
    connector.par.Sequencermodule = str(paths["sequencer"])
    connector.par.Controllermodule = str(paths["controller"])

    audio = connector.op("voices_only_audio")
    soundscape_audio = connector.op("soundscape_audio")
    execute_callbacks = connector.op("execute_callbacks")
    parameter_callbacks = connector.op("parameter_callbacks")
    show_callbacks = connector.op("show_control/control_callbacks")
    required_ops = {
        "voices_only_audio": audio,
        "soundscape_audio": soundscape_audio,
        "execute_callbacks": execute_callbacks,
        "parameter_callbacks": parameter_callbacks,
        "show_control/control_callbacks": show_callbacks,
    }
    missing_ops = [name for name, operator in required_ops.items() if operator is None]
    if missing_ops:
        raise RuntimeError(
            "Existing connector is incomplete; missing operators: "
            + ", ".join(missing_ops)
        )

    audio.par.file = str(paths["voices_audio"])
    soundscape_audio.par.file = str(paths["soundscape_audio"])
    execute_callbacks.text = paths["execute_callbacks"].read_text(encoding="utf-8")
    parameter_callbacks.text = paths["parameter_callbacks"].read_text(
        encoding="utf-8"
    )
    show_callbacks.text = paths["show_control_callbacks"].read_text(
        encoding="utf-8"
    )

    controller = execute_callbacks.module.get_controller()
    controller.reload()
    connector.current = True
    return {
        "project_root": str(project_root),
        "scene_json": str(paths["scene"]),
        "human_figure_scene_json": str(paths["human_scene"]),
        "visual_path": str(connector.par.Visualpath.eval()),
        "voices_audio_file": str(paths["voices_audio"]),
        "soundscape_audio_file": str(paths["soundscape_audio"]),
        "streamdiffusion_paths_unchanged": str(
            connector.par.Streamdiffusionpath.eval()
        ),
    }


rebound_project_paths = rebind_project_paths()
