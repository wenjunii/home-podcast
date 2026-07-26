def onValueChange(par, prev):
    controller = parent().op("execute_callbacks").module.get_controller()
    if bool(parent().par.Enabled.eval()):
        controller.update(float(par.eval()))
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
