"""Parameter callbacks for /project1/podcast_visualizer/show_control."""


COLOR_PARAMETERS = {
    "Colorenabled",
    "Brightness",
    "Contrast",
    "Gamma",
    "Blacklevel",
    "Opacity",
    "Hue",
    "Saturation",
    "Value",
}
AUDIO_SOURCE_NAMES = ("voices", "soundscape")
VISUAL_PATH_NAMES = ("original", "human_figures")


def _connector():
    return parent().parent()


def _controller():
    return _connector().op("execute_callbacks").module.get_controller()


def _refresh():
    connector = _connector()
    if bool(connector.par.Enabled.eval()):
        _controller().update(float(connector.par.Playheadsec.eval()))


def _set_audio_enabled(enabled):
    connector = _connector()
    enabled = bool(enabled)
    connector.par.Audioenabled = enabled

    # Older project revisions stored the intended expression on Active while
    # leaving the parameter in Constant mode. Keep legacy projects safe even
    # before the repair installer changes that mode.
    audio_out = connector.op("audio_out")
    if audio_out is not None:
        audio_out.par.active.val = enabled


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


def _set_audio_source(value):
    connector = _connector()
    index = _audio_source_index(value)
    source_name = AUDIO_SOURCE_NAMES[index]
    source_parameter = getattr(connector.par, "Audiosource", None)
    if source_parameter is not None:
        source_parameter.val = source_name
    source_switch = connector.op("audiosource_switch")
    if source_switch is not None:
        source_switch.par.index.val = index


def _visual_path_index(value):
    if hasattr(value, "eval"):
        value = value.eval()
    if isinstance(value, (int, float)):
        return 1 if int(value) == 1 else 0
    normalized = str(value or "").strip().casefold().replace(" ", "_")
    return (
        1
        if normalized
        in {"1", "human", "human_figure", "human_figures", "humanfigures"}
        else 0
    )


def _set_visual_path(value):
    connector = _connector()
    path_name = VISUAL_PATH_NAMES[_visual_path_index(value)]
    path_parameter = getattr(connector.par, "Visualpath", None)
    if path_parameter is not None:
        path_parameter.val = path_name
    # Both plans share the exact scene boundaries, so reloading selects the
    # matching prompt at the current playhead without touching either audio.
    _controller().reload()


def onValueChange(par, prev):
    if par.name == "Play":
        op("/local/time").par.play = bool(par.eval())
    elif par.name == "Audioenabled":
        _set_audio_enabled(par.eval())
    elif par.name == "Audiosource":
        _set_audio_source(par.eval())
    elif par.name == "Visualpath":
        _set_visual_path(par.eval())
    elif par.name == "Randomseeds":
        _controller().randomize_seeds()
        _refresh()
    elif par.name == "Crossfadesec":
        _refresh()
    elif par.name in COLOR_PARAMETERS:
        _refresh()
    return


def onValuesChanged(changes):
    return


def onPulse(par):
    if par.name == "Restart":
        _controller().advance_seed_loop()
        op("/local/time").par.play = False
        op("/project1").time.frame = 1
        parent().par.Play = False
        _refresh()
    elif par.name == "Reload":
        _controller().reload()
    elif par.name == "Newseeds":
        _controller().randomize_seeds()
        _refresh()
    elif par.name == "Resetcolor":
        control = parent()
        control.par.Colorenabled = True
        control.par.Brightness = 1.0
        control.par.Contrast = 1.0
        control.par.Gamma = 1.0
        control.par.Blacklevel = 0.0
        control.par.Opacity = 1.0
        control.par.Hue = 0.0
        control.par.Saturation = 1.0
        control.par.Value = 1.0
        _refresh()
    return


def onExpressionChange(par, val, prev):
    return


def onExportChange(par, val, prev):
    return


def onEnableChange(par, val, prev):
    return


def onModeChange(par, val, prev):
    return
