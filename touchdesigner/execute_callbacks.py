import importlib.util
import sys

_CONTROLLER = None


def _audio_source_index(value):
    if hasattr(value, "eval"):
        value = value.eval()
    if isinstance(value, (int, float)):
        return int(value) if int(value) in (1, 2) else 0
    normalized = str(value or "").strip().casefold().replace(" ", "")
    if normalized in {"2", "combined", "both", "mix", "narration+ambient"}:
        return 2
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
        return {1: "human_figures", 2: "balanced"}.get(int(value), "original")
    normalized = str(value or "").strip().casefold().replace(" ", "_")
    if normalized in {
        "1",
        "human",
        "human_figure",
        "human_figures",
        "humanfigures",
    }:
        return "human_figures"
    if normalized in {"2", "balanced", "balanced_memories"}:
        return "balanced"
    return "original"


def _runtime_profile_name(value):
    if hasattr(value, "eval"):
        value = value.eval()
    if isinstance(value, (int, float)):
        return "5090_live" if int(value) == 1 else "3080_safe"
    normalized = str(value or "").strip().casefold().replace(" ", "_")
    return "5090_live" if normalized in {"1", "5090", "5090_live"} else "3080_safe"


def _synchronize_show_control(*, reset_paused_start=False):
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
        # Apply the saved-paused startup guard only at load/create. Applying
        # it every application frame prevents paused seeking and rewinds both
        # synchronized audio stems while a visual cue is being inspected.
        if not desired_play and reset_paused_start:
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
                ("voices", "soundscape", "combined")[source_index]
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

    runtime_parameter = getattr(control.par, "Runtimeprofile", None)
    connector_runtime = getattr(owner.par, "Runtimeprofile", None)
    if runtime_parameter is not None:
        profile = _runtime_profile_name(runtime_parameter)
        if connector_runtime is not None:
            connector_runtime.val = profile
        live_parameter = getattr(control.par, "Livevariations", None)
        if (
            profile == "3080_safe"
            and live_parameter is not None
            and bool(live_parameter.eval())
        ):
            live_parameter.val = False


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


def _synchronize_live_control_file():
    control = parent().op("show_control")
    callbacks = (
        control.op("control_callbacks")
        if control is not None and hasattr(control, "op")
        else None
    )
    try:
        callbacks.module._write_live_control()
    except Exception:
        return


def onFrameStart(frame):
    _synchronize_show_control()
    controller = get_controller()
    if bool(parent().par.Enabled.eval()):
        controller.update(float(parent().par.Playheadsec.eval()))
    return


def onStart():
    _synchronize_show_control(reset_paused_start=True)
    _synchronize_live_control_file()
    controller = get_controller()
    if bool(parent().par.Enabled.eval()):
        controller.update(float(parent().par.Playheadsec.eval()))
    return


def onCreate():
    _synchronize_show_control(reset_paused_start=True)
    _synchronize_live_control_file()
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
