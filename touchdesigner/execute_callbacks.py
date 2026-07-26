import importlib.util
import sys

_CONTROLLER = None


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
    controller = get_controller()
    if bool(parent().par.Enabled.eval()):
        controller.update(float(parent().par.Playheadsec.eval()))
    return


def onStart():
    get_controller()
    return


def onCreate():
    get_controller()
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
