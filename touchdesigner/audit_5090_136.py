"""Run audit(), then event_audit() in the TD Textport; never save/start models.

All writes are temporary Show Control interactions or local audit reports.
The tests restore the canonical paused state and never pulse generation controls.
"""
from pathlib import Path
import json
import math
import sys

FIELDS = ("Play", "Audioenabled", "Audiosource", "Visualpath", "Crossfadesec", "Storyfadesec",
          "Randomseeds", "Colorenabled", "Brightness", "Contrast", "Gamma", "Blacklevel",
          "Opacity", "Hue", "Saturation", "Value", "Loopplaylist", "Storychoice")
REPORT = "work/5090-136"


def guard():
    if str(project.name) != "podcast.5090.25.toe" or str(app.build) != "2025.32820":
        raise RuntimeError("Audit only the new 5090 .25 in TD2025.32820")
    owner = op("/project1/podcast_visualizer")
    control = owner.op("show_control")
    if control.par.Livevariations.eval() or str(control.par.Runtimeprofile.eval()) != "3080_safe":
        raise RuntimeError("Live generation must remain off")
    if any(owner.op(n).par.Serveractive.eval() or owner.op(n).par.Streamactive.eval()
           for n in ("StreamDiffusionTD", "StreamDiffusionTD2")):
        raise RuntimeError("Both model servers must remain stopped")
    return owner, control


def write_report(name, report):
    path = Path(project.folder) / REPORT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("AUDIT_5090_136", name, {k: v for k, v in report.items() if k not in ("details", "fixture")})
    return report


def current():
    return op("/project1/podcast_visualizer/execute_callbacks").module.get_controller()


def restore(owner, control, before):
    for name, value in before.items():
        getattr(control.par, name).val = value
    owner.par.Visualpath = control.par.Visualpath.eval()
    op("/project1").time.frame = 1
    owner.op("execute_callbacks").module._CONTROLLER = None
    current().update(0)
    owner.op("execute_callbacks").module._synchronize_show_control(reset_paused_start=True)
    control.op("control_callbacks").module._write_live_control()


def audit():
    owner, control = guard()
    before = {n: getattr(control.par, n).eval() for n in FIELDS}
    callback_nodes = [owner.op("execute_callbacks"), owner.op("parameter_callbacks")]
    callback_nodes += [control.op(n) for n in ("control_callbacks", "playlist_callbacks", "continuous_crossfade_callbacks")]
    active = [(n, n.par.active.eval()) for n in callback_nodes if n and getattr(n.par, "active", None) is not None]
    checks = []
    def check(name, value):
        checks.append(dict(check=name, passed=bool(value)))
    try:
        # A Parameter Execute DAT cannot compile its module for the first time
        # while inactive. Compile before suspending deferred UI callbacks.
        playlist_module = control.op("playlist_callbacks").module
        control.op("control_callbacks").module
        for node, _ in active:
            node.par.active = False
        control.par.Play = False
        control.par.Audioenabled = False
        owner.op("execute_callbacks").module._synchronize_show_control()
        check("136 story menu entries", len(control.par.Storychoice.menuNames) == 136)
        check("three audio modes", list(control.par.Audiosource.menuNames) == ["voices", "soundscape", "combined"])
        check("three visual paths", list(control.par.Visualpath.menuNames) == ["original", "human_figures", "balanced"])
        check("receiver playlist callback independent of sender installer", "install.py" not in control.op("playlist_callbacks").text)
        check("gap colour disabled", not control.par.Abstractfadesec.enable and control.par.Abstractfadesec.eval() == 0)
        for name, version, ports in (("StreamDiffusionTD", "0.3.1", (8574, 8583)), ("StreamDiffusionTD2", "0.3.0", (8567, 8577))):
            renderer = owner.op(name)
            check(name + ":receiver version", str(renderer.par.Txversion.eval()) == version)
            check(name + ":receiver base", Path(str(renderer.par.Basefolder.eval())).resolve() == Path(project.folder).parent / "StreamDiffusionTD3.1/StreamDiffusion")
            check(name + ":receiver OSC", (renderer.par.Oscinport.eval(), renderer.par.Oscoutport.eval()) == ports)
            check(name + ":resolution", (renderer.par.Width.eval(), renderer.par.Height.eval()) == (1024, 576))
            check(name + ":model and acceleration", renderer.par.Modelid.eval() == "stabilityai/sdxl-turbo" and renderer.par.Acceleration.eval() == "tensorrt")
        for mode in ("original", "human_figures", "balanced"):
            op("/project1").time.frame = 1
            control.par.Visualpath = owner.par.Visualpath = mode
            owner.op("execute_callbacks").module._CONTROLLER = None
            controller = current()
            seq = controller.sequencer
            check(mode + ":scope", len(seq.stories) == 136 and len(seq.scenes) == 619 and len(seq.captions) == 2862)
            check(mode + ":clock", seq.duration_ms == 11938720)
            check(mode + ":minimum scene", all(s["duration_ms"] >= 5000 for s in seq.scenes))
            check(mode + ":cold start", len(seq.at(0, crossfade_ms=3000).prompt_layers) == 1)
            for index, scene in enumerate(seq.scenes[1:], 1):
                ms = scene["start_ms"]
                frame = seq.at(ms - 1, crossfade_ms=3000)
                check(f"{mode}:scene{index}:no early incoming", all(layer.scene_id != scene["scene_id"] for layer in frame.prompt_layers if layer.weight > 0))
                fade = seq._effective_crossfade_ms(index, scene["duration_ms"], 3000)
                op("/project1").time.frame = math.ceil((ms + fade // 2) / 1000 * project.cookRate) + 1
                actual = round(owner.par.Playheadsec.eval() * 1000)
                controller.update(actual / 1000)
                layers = controller._controlled_prompt_layers(seq.at(actual, crossfade_ms=3000))
                check(f"{mode}:join{index}:conditioning blend", fade > 0 and len(layers) == 2 and all(0 < layer.weight < 1 for layer in layers))
                for renderer_name in ("StreamDiffusionTD", "StreamDiffusionTD2"):
                    renderer = owner.op(renderer_name)
                    prompts = renderer.par.Promptdict.sequence
                    seeds = renderer.par.Seeddict.sequence
                    okay = prompts.numBlocks == seeds.numBlocks == len(layers) == 2
                    okay = okay and all(abs(prompts[j].par.Weight.eval() - layer.weight) < 1e-5 and
                        abs(seeds[j].par.Seedweight.eval() - layer.weight) < 1e-5 and
                        seeds[j].par.Seedval.eval() == layer.seed for j, layer in enumerate(layers))
                    check(f"{mode}:join{index}:{renderer_name}", okay)
            for index, scene in enumerate(seq.scenes[:-1]):
                upcoming = seq.scenes[index + 1]
                if scene["end_ms"] < upcoming["start_ms"]:
                    ms = (scene["end_ms"] + upcoming["start_ms"]) // 2
                    check(f"{mode}:gap{index}:hold", not seq.is_abstract_at(ms) and seq.neutral_mix_at(ms) == 0 and bool(seq.at(ms).prompt_layers))
            for story in seq.stories:
                check(f"{mode}:story{story['number']}:boundary", seq.story_at(story["start_ms"])["narration_id"] == story["narration_id"])
            op("/project1").time.frame = math.ceil((seq.duration_ms - 20) / 1000 * project.cookRate) + 1
            controller.update(float(owner.par.Playheadsec.eval()))
            op("/project1").time.frame = 1
            controller.update(0)
            fade = seq._join_fade(seq.scenes[0]["duration_ms"])
            op("/project1").time.frame = math.ceil(fade / 2000 * project.cookRate) + 1
            actual = round(owner.par.Playheadsec.eval() * 1000)
            controller.update(actual / 1000)
            loop_layers = seq.at(actual, crossfade_ms=3000).prompt_layers
            check(mode + ":loop conditioning blend", len(loop_layers) == 2 and all(0 < layer.weight < 1 for layer in loop_layers) and owner.par.Semanticneutralmix.eval() == 0)
            check(mode + ":caption table", owner.op("caption_out").numRows > 0)
        control.par.Visualpath = owner.par.Visualpath = "balanced"
        owner.op("execute_callbacks").module._CONTROLLER = None
        controller = current()
        callbacks = control.op("control_callbacks").module
        for source, index in (("voices", 0), ("soundscape", 1), ("combined", 2)):
            callbacks._set_audio_source(source)
            check(source + ":audio routing", owner.op("audiosource_switch").par.index.eval() == index)
        for name in ("voices_only_audio", "soundscape_audio", "combined_audio"):
            node = owner.op(name)
            for ms in (0, 5969000, 11937720):
                op("/project1").time.frame = math.ceil(ms / 1000 * project.cookRate) + 1
                node.cook(force=True)
                check(f"{name}:{ms}:decoded stereo 48k", not node.errors() and node.numChans == 2 and abs(node.rate - 48000) < .01)
        op("/project1").time.frame = 1
        for enabled in (True, False):
            callbacks._set_audio_enabled(enabled)
            check("audio enabled " + str(enabled), bool(owner.op("audio_out").par.active.eval()) == enabled)
        mapping = {"Brightness": ("color_level_", "brightness1", .8), "Contrast": ("color_level_", "contrast", 1.2),
                   "Gamma": ("color_level_", "gamma1", 1.1), "Blacklevel": ("color_level_", "blacklevel", .05),
                   "Opacity": ("color_level_", "opacity", .9), "Hue": ("color_hsv_", "hueoffset", 25),
                   "Saturation": ("color_hsv_", "saturationmult", .7), "Value": ("color_hsv_", "valuemult", .85)}
        for name, (prefix, parameter, value) in mapping.items():
            getattr(control.par, name).val = value
            controller.update(0)
            for index in (1, 2):
                check(f"{name}:output{index}", abs(getattr(owner.op(prefix + str(index)).par, parameter).eval() - value) < 1e-5)
            getattr(control.par, name).val = before[name]
        for enabled in (False, True):
            control.par.Colorenabled = enabled
            controller.update(0)
            check("color bypass " + str(enabled), all(owner.op("color_switch_" + str(i)).par.index.eval() == int(enabled) for i in (1, 2)))
        for value in (0, 1, 8, 30):
            control.par.Crossfadesec = control.par.Storyfadesec = value
            controller.update(0)
            check("scene interpolation " + str(value), controller._show_control_crossfade_ms() == value * 1000)
            check("story interpolation " + str(value), controller.sequencer.story_crossfade_override_ms == value * 1000)
        control.par.Randomseeds = False
        # Compare an identical frame, away from a loop blend. Loop advance can
        # legitimately change the transport's active layer count at t=0.
        seed_frame = controller.sequencer.at(controller.sequencer.scenes[0]["end_ms"] - 1)
        a = [x.seed for x in controller._controlled_prompt_layers(seed_frame)]
        controller.advance_seed_loop()
        check("fixed seeds repeat", a == [x.seed for x in controller._controlled_prompt_layers(seed_frame)])
        control.par.Randomseeds = True
        a = [x.seed for x in controller._controlled_prompt_layers(seed_frame)]
        controller.advance_seed_loop()
        check("random seeds change next loop", a != [x.seed for x in controller._controlled_prompt_layers(seed_frame)])
        playlist = playlist_module
        playlist.jump_story(136)
        check("jump to last story", controller.sequencer.story_at(owner.par.Playheadsec.eval() * 1000)["number"] == 136)
        control.par.Loopplaylist = True
        playlist.navigate(1)
        check("next wraps to first", controller.sequencer.story_at(owner.par.Playheadsec.eval() * 1000)["number"] == 1)
        playlist.navigate(-1)
        check("previous wraps to last", controller.sequencer.story_at(owner.par.Playheadsec.eval() * 1000)["number"] == 136)
        for enabled in (False, True):
            control.par.Loopplaylist = enabled
            playlist.configure_loop()
            check("loop switch " + str(enabled), str(op("/local/time").par.rangelimit.eval()) == ("loop" if enabled else "hold"))
        check("no generation modules imported", not {"qwen_tts", "ollama", "diffusers"}.intersection(sys.modules))
    except Exception as error:
        checks.append(dict(check="audit exception", passed=False, error_type=type(error).__name__, message=str(error)[:300]))
    finally:
        restore(owner, control, before)
        for node, enabled in active:
            node.par.active = enabled
    guard()
    report = dict(project=str(project.name), checks=len(checks), passed=sum(c["passed"] for c in checks),
                  failures=[c for c in checks if not c["passed"]], state_restored=True,
                  live_generation=False, servers_started=False, details=checks)
    return write_report("native-audit.json", report)


def pixel_audit():
    """Synthetic fixture through both final output routes, with renderers off."""
    import numpy as np
    owner, control = guard()
    before = {n: getattr(control.par, n).eval() for n in FIELDS}
    owner_enabled = owner.par.Enabled.eval()
    fixture = owner.op("semantic_test_image")
    fixture_names = ("colorr", "colorg", "colorb", "alpha", "outputresolution", "resolutionw", "resolutionh")
    fixture_before = {n: getattr(fixture.par, n).eval() for n in fixture_names}
    checks = []
    originals = []
    try:
        owner.par.Enabled = False
        control.par.Colorenabled = False
        fixture.par.colorr = .8
        fixture.par.colorg = .12
        fixture.par.colorb = .05
        fixture.par.alpha = 1
        fixture.par.outputresolution = "custom"
        fixture.par.resolutionw = fixture.par.resolutionh = 128
        current()._write_color_controls()
        for i in (1, 2):
            blend = owner.op("semantic_neutral_output_" + str(i))
            originals.append((blend, blend.inputs[0]))
            blend.inputConnectors[0].connect(fixture)
            owner.par.Semanticneutralmix = 0
            output = owner.op("null" + str(i))
            output.cook(force=True)
            pixels = output.numpyArray(delayed=False)
            checks.append(dict(check=f"output{i}:synthetic final pixels", passed=pixels is not None and float(np.mean(pixels[:, :, :3])) > .05 and not output.errors()))
            sender = owner.op("syphonspoutout" + str(i))
            sender.cook(force=True)
            checks.append(dict(check=f"output{i}:Spout input and errors", passed=sender.inputs[0] == output and not sender.errors()))
        # The HSV TOP uses 0..360: UI -180 and +180 must produce the same
        # half-turn, and that half-turn must actually change fixture pixels.
        hue_pixels = {}
        control.par.Colorenabled = True
        for hue in (0, -180, 180):
            control.par.Hue = hue
            current()._write_color_controls()
            for i in (1, 2):
                output = owner.op("null" + str(i))
                output.cook(force=True)
                hue_pixels[hue, i] = output.numpyArray(delayed=False).copy()
        for i in (1, 2):
            equivalent = np.max(np.abs(hue_pixels[-180, i] - hue_pixels[180, i])) < .015
            changed = np.max(np.abs(hue_pixels[0, i] - hue_pixels[180, i])) > .05
            checks.append(dict(check=f"output{i}:signed hue boundary pixels", passed=bool(equivalent and changed)))
    except Exception as error:
        checks.append(dict(check="pixel audit exception", passed=False, error_type=type(error).__name__, message=str(error)[:300]))
    finally:
        for blend, original in originals:
            blend.inputConnectors[0].connect(original)
        for name, value in fixture_before.items():
            getattr(fixture.par, name).val = value
        owner.par.Enabled = owner_enabled
        restore(owner, control, before)
    return write_report("native-pixel-audit.json", dict(project=str(project.name), checks=len(checks), passed=sum(c["passed"] for c in checks),
        failures=[c for c in checks if not c["passed"]], details=checks, fixture_restored=True, live_generation=False, servers_started=False, generated_image_test=False))


def event_audit():
    owner, control = guard()
    control.store("native25_before", {n: getattr(control.par, n).eval() for n in FIELDS})
    control.store("native25_checks", [])
    control.par.Play = False
    control.par.Audioenabled = False
    actions = [("Audiosource", v) for v in ("voices", "soundscape", "combined")]
    actions += [("Visualpath", v) for v in ("original", "human_figures", "balanced")]
    actions += [(n, v) for n in ("Crossfadesec", "Storyfadesec") for v in (0, 1, 3, 30)]
    actions += [("Storychoice", "story136"), ("Storychoice", "story1")]
    actions += [("pulse", v) for v in ("Nextstory", "Previousstory", "Restartplaylist")]
    actions += [(n, v) for n in ("Loopplaylist", "Randomseeds", "Colorenabled") for v in (False, True)]
    actions += [("Brightness", .7), ("Contrast", 1.2), ("Gamma", 1.1), ("Blacklevel", .05),
                ("Opacity", .9), ("Hue", 25), ("Saturation", .7), ("Value", .85)]
    actions += [("pulse", v) for v in ("Resetcolor", "Restart", "Newseeds", "Reload")]
    actions += [("Play", True), ("Play", False), ("Audioenabled", True), ("Audioenabled", False)]
    control.store("native25_expected_events", len(actions))
    source = str(Path(project.folder) / "touchdesigner/audit_5090_136.py")
    options = dict(delayRef=op.TDResources, wallTime=True, group="rh_5090_25_events")
    for i, (name, value) in enumerate(actions):
        run("exec(compile(open(args[0],encoding='utf-8').read(),args[0],'exec'),globals()); event_action(args[1],args[2])", source, name, value, delayMilliSeconds=500 + i * 400, **options)
        run("exec(compile(open(args[0],encoding='utf-8').read(),args[0],'exec'),globals()); event_check(args[1],args[2])", source, name, value, delayMilliSeconds=750 + i * 400, **options)
    run("exec(compile(open(args[0],encoding='utf-8').read(),args[0],'exec'),globals()); event_finish()", source, delayMilliSeconds=1000 + len(actions) * 400, **options)
    print("AUDIT_5090_136_EVENTS_SCHEDULED", len(actions))


def event_action(name, value):
    _, control = guard()
    if name == "pulse" and value == "Newseeds":
        control.store("native25_old_seeds", [x.seed for x in current()._controlled_prompt_layers(current().sequencer.at(0))])
    if name == "pulse" and value == "Reload":
        control.store("native25_old_sequencer", id(current().sequencer))
    if name == "pulse":
        getattr(control.par, value).pulse()
    else:
        getattr(control.par, name).val = value


def event_check(name, value):
    owner, control = guard()
    seq = current().sequencer
    if name == "Audiosource":
        okay = owner.op("audiosource_switch").par.index.eval() == ("voices", "soundscape", "combined").index(value)
    elif name == "Visualpath":
        okay = seq.plan["visual_path"]["id"] == value
    elif name == "Crossfadesec":
        okay = current()._show_control_crossfade_ms() == value * 1000
    elif name == "Storyfadesec":
        okay = seq.story_crossfade_override_ms == value * 1000
    elif name == "Storychoice":
        okay = seq.story_at(owner.par.Playheadsec.eval() * 1000)["number"] == int(value.removeprefix("story"))
    elif name == "Loopplaylist":
        okay = str(op("/local/time").par.rangelimit.eval()) == ("loop" if value else "hold")
    elif name == "Colorenabled":
        okay = all(owner.op("color_switch_" + str(i)).par.index.eval() == int(value) for i in (1, 2))
    elif name == "Randomseeds":
        okay = current()._random_seeds_enabled() == value
    elif name in {"Brightness", "Contrast", "Gamma", "Blacklevel", "Opacity", "Hue", "Saturation", "Value"}:
        mapping = {"Brightness": ("color_level_", "brightness1"), "Contrast": ("color_level_", "contrast"),
                   "Gamma": ("color_level_", "gamma1"), "Blacklevel": ("color_level_", "blacklevel"),
                   "Opacity": ("color_level_", "opacity"), "Hue": ("color_hsv_", "hueoffset"),
                   "Saturation": ("color_hsv_", "saturationmult"), "Value": ("color_hsv_", "valuemult")}
        prefix, parameter = mapping[name]
        okay = all(abs(getattr(owner.op(prefix + str(i)).par, parameter).eval() - value) < 1e-5 for i in (1, 2))
    elif name == "Play":
        okay = bool(op("/local/time").par.play.eval()) == value
    elif name == "Audioenabled":
        okay = bool(owner.op("audio_out").par.active.eval()) == value
    elif name == "pulse" and value in {"Nextstory", "Previousstory", "Restartplaylist"}:
        okay = seq.story_at(owner.par.Playheadsec.eval() * 1000)["number"] == (2 if value == "Nextstory" else 1)
    elif name == "pulse" and value == "Resetcolor":
        okay = control.par.Brightness.eval() == 1 and owner.op("color_level_1").par.brightness1.eval() == 1
    elif name == "pulse" and value == "Restart":
        okay = op("/project1").time.frame == 1
    elif name == "pulse" and value == "Newseeds":
        okay = control.fetch("native25_old_seeds") != [x.seed for x in current()._controlled_prompt_layers(seq.at(0))]
    elif name == "pulse" and value == "Reload":
        okay = control.fetch("native25_old_sequencer") != id(seq) and len(seq.stories) == 136
    else:
        raise ValueError("Unsupported event check must not pass silently")
    checks = control.fetch("native25_checks")
    checks.append(dict(control=name, value=value, passed=bool(okay)))
    control.store("native25_checks", checks)


def event_finish():
    owner, control = guard()
    checks = control.fetch("native25_checks")
    restore(owner, control, control.fetch("native25_before"))
    expected = control.fetch("native25_expected_events")
    complete = len(checks) == expected and len({(c["control"], str(c["value"])) for c in checks}) == expected
    if not complete:
        checks.append(dict(check="all scheduled events completed exactly once", passed=False))
    return write_report("native-event-audit.json", dict(project=str(project.name), checks=len(checks), passed=sum(c["passed"] for c in checks),
        failures=[c for c in checks if not c["passed"]], state_restored=True, live_generation=False, servers_started=False, details=checks))
