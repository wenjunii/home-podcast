import importlib.util
import sys

_CONTROLLER = None


def _audio_source_index(value):
    if hasattr(value, "eval"):
        value = value.eval()
    if isinstance(value, (int, float)):
        return 1 if int(value) == 1 else 0
    normalized = str(value or "").strip().casefold().replace(" ", "")
    return (
        1
        if normalized
        in {"1", "soundscape", "soundscapeonly", "nonhuman", "nonhumanonly"}
        else 0
    )


def _visual_path_name(value):
    if hasattr(value, "eval"):
        value = value.eval()
    if isinstance(value, (int, float)):
        return "human_figures" if int(value) == 1 else "original"
    normalized = str(value or "").strip().casefold().replace(" ", "_")
    if normalized in {
        "1",
        "human",
        "human_figure",
        "human_figures",
        "humanfigures",
    }:
        return "human_figures"
    return "original"


def _synchronize_show_control():
    """Make saved show-control values authoritative after a project load."""
    owner = parent()
    control = owner.op("show_control")
    if control is None:
        return

    play_parameter = getattr(control.par, "Play", None)
    if play_parameter is not None:
        desired_play = bool(play_parameter.eval())
        timeline_play = op("/local/time").par.play
        if bool(timeline_play.eval()) != desired_play:
            timeline_play.val = desired_play
        # TouchDesigner may briefly cook frames while a .toe loads even when
        # /local/time already reports Play as off. Keep a saved paused show at
        # the episode start until the user explicitly enables Show Control.
        if not desired_play:
            project_root = op("/project1")
            if project_root is not None:
                project_root.time.frame = 1

    audio_parameter = getattr(control.par, "Audioenabled", None)
    if audio_parameter is not None:
        desired_audio = bool(audio_parameter.eval())
        if bool(owner.par.Audioenabled.eval()) != desired_audio:
            owner.par.Audioenabled.val = desired_audio
        audio_out = owner.op("audio_out")
        if (
            audio_out is not None
            and bool(audio_out.par.active.eval()) != desired_audio
        ):
            audio_out.par.active.val = desired_audio

    source_parameter = getattr(control.par, "Audiosource", None)
    if source_parameter is not None:
        source_index = _audio_source_index(source_parameter)
        connector_source = getattr(owner.par, "Audiosource", None)
        if connector_source is not None:
            connector_source.val = (
                "soundscape" if source_index == 1 else "voices"
            )
        source_switch = owner.op("audiosource_switch")
        if (
            source_switch is not None
            and int(source_switch.par.index.eval()) != source_index
        ):
            source_switch.par.index.val = source_index

    visual_parameter = getattr(control.par, "Visualpath", None)
    connector_visual_parameter = getattr(owner.par, "Visualpath", None)
    if visual_parameter is not None and connector_visual_parameter is not None:
        desired_visual_path = _visual_path_name(visual_parameter)
        if _visual_path_name(connector_visual_parameter) != desired_visual_path:
            connector_visual_parameter.val = desired_visual_path


def get_controller():
    global _CONTROLLER
    owner = parent()
    if _CONTROLLER is not None and _CONTROLLER.owner_comp == owner:
        return _CONTROLLER

    module_path = str(owner.par.Controllermodule.eval())
    module_name = "recovered_homes_podcast_td_controller"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    _CONTROLLER = module.PodcastVisualController(owner)
    return _CONTROLLER


def onFrameStart(frame):
    _synchronize_show_control()
    controller = get_controller()
    if bool(parent().par.Enabled.eval()):
        controller.update(float(parent().par.Playheadsec.eval()))
    return


def onStart():
    _synchronize_show_control()
    controller = get_controller()
    if bool(parent().par.Enabled.eval()):
        controller.update(float(parent().par.Playheadsec.eval()))
    return


def onCreate():
    _synchronize_show_control()
    controller = get_controller()
    if bool(parent().par.Enabled.eval()):
        controller.update(float(parent().par.Playheadsec.eval()))
    return


def onExit():
    return


def onFrameEnd(frame):
    return


def onPlayStateChange(state):
    return


def onDeviceChange():
    return


def onProjectPreSave():
    return


def onProjectPostSave():
    return


def onPostSave():
    return
