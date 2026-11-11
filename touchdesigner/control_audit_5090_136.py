"""Account for all 40 Show Control parameters without enabling generation.

Run inventory(), then start() inside TD2025.32820's Textport on the 5090 .25.
This script never saves a TOE, starts a process or loads a media model.
"""
from pathlib import Path
import json
import math
import time
import uuid
import sys

ACTIVE = {
    "Play", "Audioenabled", "Audiosource", "Visualpath", "Randomseeds", "Crossfadesec",
    "Newseeds", "Restart", "Reload", "Colorenabled", "Brightness", "Contrast", "Gamma",
    "Blacklevel", "Opacity", "Hue", "Saturation", "Value", "Resetcolor", "Storychoice",
    "Previousstory", "Nextstory", "Restartplaylist", "Loopplaylist", "Storyfadesec",
}
DORMANT = {"Narrationvariation", "Speechvariation", "Visualvariation", "Interpretivecasting", "Randomvariationseeds", "Variationseed"}
LOCKED = {"Runtimeprofile", "Livevariations", "Regeneratenext"}
DISPLAYS = {"Currentstory", "Storyelapsed", "Storyduration", "Playlistelapsed"}
DISABLED = {"Proofstory", "Abstractfadesec"}
EXPECTED = ACTIVE | DORMANT | LOCKED | DISPLAYS | DISABLED
PULSES = {"Newseeds", "Restart", "Reload", "Resetcolor", "Previousstory", "Nextstory", "Restartplaylist"}
COLOR = {"Brightness": ("color_level_", "brightness1"), "Contrast": ("color_level_", "contrast"),
         "Gamma": ("color_level_", "gamma1"), "Blacklevel": ("color_level_", "blacklevel"),
         "Opacity": ("color_level_", "opacity"), "Hue": ("color_hsv_", "hueoffset"),
         "Saturation": ("color_hsv_", "saturationmult"), "Value": ("color_hsv_", "valuemult")}
PROTOCOL = {"Narrationvariation": "narration_variation", "Speechvariation": "speech_variation", "Visualvariation": "visual_variation"}
KEY = "canonical_5090_full_control_audit"


def coverage(names):
    names = set(names)
    return dict(expected=len(EXPECTED), found=len(names), missing=sorted(EXPECTED - names), unknown=sorted(names - EXPECTED))


def downstream_value(name, value):
    # The signed UI is mapped to the HSV TOP's equivalent 0..360 rotation.
    return value % 360.0 if name == "Hue" else value


def guard():
    if str(project.name) != "podcast.5090.25.toe" or str(app.build) != "2025.32820":
        raise RuntimeError("Full control audit requires the 5090 .25 in TD2025.32820")
    owner = op("/project1/podcast_visualizer")
    control = owner.op("show_control")
    if control.par.Livevariations.eval() or str(control.par.Runtimeprofile.eval()) != "3080_safe":
        raise RuntimeError("Keep canonical cached playback and live generation off")
    for name in ("StreamDiffusionTD", "StreamDiffusionTD2"):
        renderer = owner.op(name)
        if renderer.par.Serveractive.eval() or renderer.par.Streamactive.eval():
            raise RuntimeError("Keep both model servers stopped")
    return owner, control


def report(name, value):
    path = Path(project.folder) / "work/5090-136" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    print("FULL_CONTROL_5090", name, {k: v for k, v in value.items() if k not in {"parameters", "details"}})
    return value


def inventory():
    _, control = guard()
    rows = []
    for p in control.customPars:
        group = next((label for label, names in (("playback", ACTIVE), ("dormant_settings", DORMANT),
            ("generation_locked", LOCKED), ("read_only_display", DISPLAYS), ("intentionally_disabled", DISABLED)) if p.name in names), "unknown")
        rows.append(dict(name=p.name, style=str(p.style), group=group, enabled=bool(p.enable), read_only=bool(p.readOnly),
                         minimum=p.min, maximum=p.max, clamp_min=bool(p.clampMin), clamp_max=bool(p.clampMax)))
    scope = coverage(p["name"] for p in rows)
    return report("full-control-inventory.json", dict(project=str(project.name), coverage=scope,
        passed=not scope["missing"] and not scope["unknown"], parameters=rows, live_generation=False))


def cases(seed_max=2147480000):
    result = [("Audiosource", x) for x in ("voices", "soundscape", "combined")]
    result += [("Visualpath", x) for x in ("original", "human_figures", "balanced")]
    result += [(n, x) for n in ("Crossfadesec", "Storyfadesec") for x in (0, .1, 3, 30)]
    bounds = {"Brightness": (0, 1, 2), "Contrast": (0, 1, 4), "Gamma": (.1, 1, 4),
              "Blacklevel": (0, .5, 1), "Opacity": (0, .5, 1), "Hue": (-180, 0, 180),
              "Saturation": (0, 1, 4), "Value": (0, 1, 4)}
    result += [(n, x) for n, values in bounds.items() for x in values]
    result += [(n, x) for n in ("Randomseeds", "Colorenabled", "Loopplaylist") for x in (False, True)]
    result += [("Storychoice", "story" + str(n)) for n in (1, 2, 68, 136, 1)]
    result += [("pulse", n) for n in ("Nextstory", "Previousstory", "Restartplaylist", "Resetcolor", "Restart", "Newseeds", "Reload")]
    result += [(n, x) for n in sorted(DORMANT - {"Variationseed"}) for x in (False, True)]
    result += [("Variationseed", x) for x in (0, 201312, int(seed_max))]
    result += [("Play", True), ("Play", False), ("Audioenabled", True), ("Audioenabled", False)]
    return result


def terminal_result(expected, details, restored):
    ids = [d["id"] for d in details]
    complete = sorted(ids) == list(range(expected))
    failures = [d for d in details if not d["passed"]]
    if not complete:
        failures.append(dict(check="all scheduled cases completed exactly once", passed=False))
    if not restored:
        failures.append(dict(check="original state restored", passed=False))
    return dict(expected_cases=expected, completed_cases=len(details), complete=complete,
                passed=not failures, failures=failures, state_restored=restored)


def _controller(owner):
    return owner.op("execute_callbacks").module.get_controller()


def _protocol(owner):
    return json.loads(Path(str(owner.par.Livecontroljson.eval())).read_text(encoding="utf-8"))


def _display_checks(owner, control, controller):
    ms = float(owner.par.Playheadsec.eval()) * 1000
    story = controller.sequencer.story_at(ms)
    return (str(control.par.Currentstory.eval()).startswith(str(story["number"]) + " / 136")
        and abs(control.par.Storyelapsed.eval() - max(0, (ms - story["start_ms"]) / 1000)) < .02
        and abs(control.par.Storyduration.eval() - story["duration_ms"] / 1000) < .02
        and abs(control.par.Playlistelapsed.eval() - ms / 1000) < .02)


def _seeds(controller):
    frame = controller.sequencer.at(controller.sequencer.scenes[0]["end_ms"] - 1)
    return [layer.seed for layer in controller._controlled_prompt_layers(frame)]


def start():
    owner, control = guard()
    previous = control.fetch(KEY, None)
    if previous and previous.get("running"):
        raise RuntimeError("A full control audit is already running; preserve its snapshot")
    scope = inventory()
    if not scope["passed"]:
        raise RuntimeError("Unknown or missing controls must be reviewed before testing")
    metadata = {row["name"]: row for row in scope["parameters"]}
    if any(not metadata[n]["read_only"] for n in DISPLAYS) or any(
        metadata[n]["enabled"] and not metadata[n]["read_only"] for n in DISABLED):
        raise RuntimeError("Read-only displays or retired controls are unexpectedly editable")
    controller = _controller(owner)
    actions = cases(control.par.Variationseed.max)
    state = dict(token=uuid.uuid4().hex, running=True, started=time.monotonic(),
        parameters={n: getattr(control.par, n).eval() for n in (ACTIVE | DORMANT) - PULSES},
        frame=float(op("/project1").time.frame), timeline_play=bool(op("/local/time").par.play.eval()),
        owner_enabled=bool(owner.par.Enabled.eval()), details=[], expected=len(actions),
        seed_salt=controller.seed_salt, seed_generation=controller.seed_generation,
        initial_nonce=int(_protocol(owner).get("regeneration_nonce", 0)))
    control.store(KEY, state)
    control.par.Play = False
    control.par.Audioenabled = False
    owner.op("execute_callbacks").module._synchronize_show_control()
    source = str(Path(project.folder) / "touchdesigner/control_audit_5090_136.py")
    options = dict(delayRef=op.TDResources, wallTime=True, group="rh_full_control_5090")
    for i, (name, value) in enumerate(actions):
        for function, offset in (("act", 500), ("check", 750)):
            run("exec(compile(open(args[0],encoding='utf-8').read(),args[0],'exec'),globals()); " + function + "(*args[1:])",
                source, state["token"], i, name, value, delayMilliSeconds=offset + i * 400, **options)
    run("exec(compile(open(args[0],encoding='utf-8').read(),args[0],'exec'),globals()); finish(args[1])",
        source, state["token"], delayMilliSeconds=1000 + len(actions) * 400, **options)
    print("FULL_CONTROL_5090_SCHEDULED", len(actions), "cases; generation remains off")


def act(token, index, name, value):
    owner, control = guard()
    state = control.fetch(KEY)
    if state["token"] != token or not state["running"]:
        return
    try:
        controller = _controller(owner)
        state["before_case"] = dict(frame=float(op("/project1").time.frame),
            seeds=_seeds(controller), story=controller.sequencer.story_at(owner.par.Playheadsec.eval() * 1000)["number"],
            loop=bool(control.par.Loopplaylist.eval()))
        if name == "pulse":
            if value not in PULSES:
                raise ValueError("Unsupported pulse")
            control.store(KEY + "_sequencer", controller.sequencer)
            getattr(control.par, value).pulse()
        else:
            if name not in (ACTIVE | DORMANT) - PULSES:
                raise ValueError("Unsupported control; never toggle a generation master")
            getattr(control.par, name).val = value
    except Exception as error:
        state["action_error"] = type(error).__name__
    control.store(KEY, state)


def evaluate(owner, control, name, value, before, nonce):
    controller = _controller(owner)
    seq = controller.sequencer
    if name == "Audiosource":
        okay = owner.op("audiosource_switch").par.index.eval() == ("voices", "soundscape", "combined").index(value)
    elif name == "Visualpath":
        okay = seq.plan["visual_path"]["id"] == value
    elif name == "Crossfadesec":
        okay = controller._show_control_crossfade_ms() == round(value * 1000)
    elif name == "Storyfadesec":
        okay = seq.story_crossfade_override_ms == round(value * 1000)
    elif name in COLOR:
        prefix, parameter = COLOR[name]
        expected = downstream_value(name, value)
        okay = all(abs(getattr(owner.op(prefix + str(i)).par, parameter).eval() - expected) < 1e-5 for i in (1, 2))
    elif name == "Colorenabled":
        okay = all(owner.op("color_switch_" + str(i)).par.index.eval() == int(value) for i in (1, 2))
    elif name == "Randomseeds":
        okay = controller._random_seeds_enabled() == value
    elif name == "Loopplaylist":
        okay = str(op("/local/time").par.rangelimit.eval()) == ("loop" if value else "hold")
    elif name == "Storychoice":
        okay = seq.story_at(owner.par.Playheadsec.eval() * 1000)["number"] == int(value.removeprefix("story"))
    elif name == "Play":
        okay = bool(op("/local/time").par.play.eval()) == value
    elif name == "Audioenabled":
        okay = bool(owner.op("audio_out").par.active.eval()) == value
    elif name in DORMANT:
        data = _protocol(owner)
        if name in PROTOCOL:
            okay = data[PROTOCOL[name]] == value
        elif name == "Interpretivecasting":
            okay = data["casting_mode"] == ("interpretive" if value else "evidence_conservative")
        elif name == "Randomvariationseeds":
            okay = data["seed_mode"] == ("random" if value else "fixed")
        else:
            okay = data["fixed_seed"] == value
        okay = okay and data["enabled"] is False and data["profile"] == "3080_safe" and data["regeneration_nonce"] == nonce
    elif name == "pulse":
        number = seq.story_at(owner.par.Playheadsec.eval() * 1000)["number"]
        if value in {"Nextstory", "Previousstory"}:
            expected = before["story"] + (1 if value == "Nextstory" else -1)
            expected = (expected - 1) % 136 + 1 if before["loop"] else max(1, min(136, expected))
            okay = number == expected
        elif value in {"Restart", "Restartplaylist"}:
            okay = op("/project1").time.frame == 1 and not control.par.Play.eval()
        elif value == "Resetcolor":
            neutral = dict(Brightness=1, Contrast=1, Gamma=1, Blacklevel=0, Opacity=1, Hue=0, Saturation=1, Value=1)
            okay = all(getattr(control.par, n).eval() == v for n, v in neutral.items()) and bool(control.par.Colorenabled.eval())
        elif value == "Newseeds":
            okay = _seeds(controller) != before["seeds"]
        elif value == "Reload":
            okay = control.fetch(KEY + "_sequencer") is not seq and len(seq.stories) == 136
        else:
            raise ValueError("Unsupported pulse check")
    else:
        raise ValueError("Unsupported check; unknown controls must fail closed")
    if name in {"Audiosource", "Visualpath"}:
        okay = okay and op("/project1").time.frame == before["frame"]
    return bool(okay and _display_checks(owner, control, controller))


def check(token, index, name, value):
    owner, control = guard()
    state = control.fetch(KEY)
    if state["token"] != token or not state["running"]:
        return
    detail = dict(id=index, control=name, value=value, passed=False)
    try:
        if state.get("action_error"):
            detail["error_type"] = state.pop("action_error")
        else:
            detail["passed"] = evaluate(owner, control, name, value, state["before_case"], state["initial_nonce"])
    except Exception as error:
        detail["error_type"] = type(error).__name__
    state["details"].append(detail)
    control.store(KEY, state)


def finish(token):
    owner, control = guard()
    state = control.fetch(KEY)
    if state["token"] != token:
        return
    restored = False
    try:
        control.par.Play = False
        for name, value in state["parameters"].items():
            if name != "Play":
                getattr(control.par, name).val = value
        owner.par.Visualpath = control.par.Visualpath.eval()
        owner.par.Enabled = state["owner_enabled"]
        controller = _controller(owner)
        controller.seed_salt = state["seed_salt"]
        controller.seed_generation = state["seed_generation"]
        op("/project1").time.frame = state["frame"]
        controller.update(float(owner.par.Playheadsec.eval()))
        control.par.Play = state["parameters"]["Play"]
        owner.op("execute_callbacks").module._synchronize_show_control()
        control.op("control_callbacks").module._write_live_control()
        restored = all(getattr(control.par, n).eval() == v for n, v in state["parameters"].items())
        restored = restored and (state["parameters"]["Play"] or abs(op("/project1").time.frame - state["frame"]) < 1)
    except Exception as error:
        state["restore_error_type"] = type(error).__name__
    state["running"] = False
    control.store(KEY, state)
    control.store(KEY + "_sequencer", None)
    result = terminal_result(state["expected"], state["details"], restored)
    result.update(project=str(project.name), elapsed_seconds=round(time.monotonic() - state["started"], 2),
        run_token=state["token"],
        coverage=coverage(p.name for p in control.customPars), details=state["details"],
        locked_controls=sorted(LOCKED), retired_controls=sorted(DISABLED), displays=sorted(DISPLAYS),
        generation_modules_loaded=sorted({"qwen_tts", "ollama", "diffusers"}.intersection(sys.modules)),
        live_generation=False, saved=False, servers_started=False)
    return report("full-control-audit.json", result)
