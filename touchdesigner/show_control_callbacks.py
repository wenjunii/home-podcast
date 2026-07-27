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


def onValueChange(par, prev):
    if par.name == "Play":
        op("/local/time").par.play = bool(par.eval())
    elif par.name == "Audioenabled":
        _set_audio_enabled(par.eval())
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
