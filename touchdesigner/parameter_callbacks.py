def onValueChange(par, prev):
    connector = parent()
    if par.name == "Playheadsec":
        controller = connector.op("execute_callbacks").module.get_controller()
        if bool(connector.par.Enabled.eval()):
            controller.update(float(par.eval()))
    elif par.name in {
        "Currentnarrationid",
        "Canonicalvisuals",
        "Canonicalhumanvisuals",
    }:
        callbacks = connector.op("show_control/control_callbacks")
        if callbacks is not None:
            callbacks.module._write_live_control()
    return


def onValuesChanged(changes):
    return


def onPulse(par):
    return


def onExpressionChange(par, val, prev):
    return


def onExportChange(par, val, prev):
    return


def onEnableChange(par, val, prev):
    return


def onModeChange(par, val, prev):
    return
