"""Parameter callbacks for /project1/podcast_visualizer/show_control."""


def _connector():
    return parent().parent()


def _controller():
    return _connector().op("execute_callbacks").module.get_controller()


def _refresh():
    connector = _connector()
    if bool(connector.par.Enabled.eval()):
        _controller().update(float(connector.par.Playheadsec.eval()))


def onValueChange(par, prev):
    connector = _connector()
    if par.name == "Play":
        op("/local/time").par.play = bool(par.eval())
    elif par.name == "Audioenabled":
        connector.par.Audioenabled = bool(par.eval())
    elif par.name == "Crossfadesec":
        _refresh()
    return


def onValuesChanged(changes):
    return


def onPulse(par):
    if par.name == "Restart":
        op("/local/time").par.play = False
        op("/project1").time.frame = 1
        parent().par.Play = False
        _refresh()
    elif par.name == "Reload":
        _controller().reload()
    return


def onExpressionChange(par, val, prev):
    return


def onExportChange(par, val, prev):
    return


def onEnableChange(par, val, prev):
    return


def onModeChange(par, val, prev):
    return
