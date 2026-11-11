"""Receiver-only canonical playlist callbacks; no sender installer or generation."""
import math
import re


def guard():
    name = str(project.name)
    match = re.fullmatch(r"podcast\.5090\.(\d+)\.toe", name, re.I)
    if not match or int(match[1]) < 25 or str(app.build) != "2025.32820":
        raise RuntimeError("The canonical playlist requires a new 5090 revision in TD2025.32820")
    owner = op("/project1/podcast_visualizer")
    control = owner.op("show_control")
    if control.par.Livevariations.eval() or str(control.par.Runtimeprofile.eval()) != "3080_safe":
        raise RuntimeError("Canonical cached playback requires live generation off")
    for name in ("StreamDiffusionTD", "StreamDiffusionTD2"):
        renderer = owner.op(name)
        if renderer.par.Serveractive.eval() or renderer.par.Streamactive.eval():
            raise RuntimeError("Stop renderer servers before canonical playlist maintenance")
    return owner, control


def controller():
    return op("/project1/podcast_visualizer/execute_callbacks").module.get_controller()


def jump_story(number):
    owner, control = guard()
    stories = controller().sequencer.stories
    number = int(number)
    if not 1 <= number <= len(stories):
        raise ValueError("Story selection is outside the approved playlist")
    story = stories[number - 1]
    op("/project1").time.frame = math.ceil(story["start_ms"] / 1000 * project.cookRate) + 1
    op("/local/time").par.play = bool(control.par.Play.eval())
    controller().update(float(owner.par.Playheadsec.eval()))
    return story


def navigate(delta):
    owner, control = guard()
    seq = controller().sequencer
    position = seq.navigate(owner.par.Playheadsec.eval() * 1000, delta,
                            loop=bool(control.par.Loopplaylist.eval()))
    return jump_story(seq.story_at(position)["number"])


def configure_loop():
    _, control = guard()
    op("/local/time").par.rangelimit = "loop" if control.par.Loopplaylist.eval() else "hold"


def onValueChange(par, prev):
    if par.name == "Storychoice":
        jump_story(int(str(par.eval()).removeprefix("story")))
    elif par.name == "Loopplaylist":
        configure_loop()


def onPulse(par):
    if par.name == "Nextstory":
        navigate(1)
    elif par.name == "Previousstory":
        navigate(-1)
    elif par.name == "Restartplaylist":
        _, control = guard()
        control.par.Play = False
        controller().advance_seed_loop()
        jump_story(1)
