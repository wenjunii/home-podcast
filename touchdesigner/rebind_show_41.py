"""Rebase the imported approved 3080 .41 in TD2025.32820, never save/start.

Use this for a fresh import of --edition 3080-41, not a 4090/5090 migration.
The local mirror made before this exporter has its own START-HERE instructions.
"""
import hashlib
import importlib.util
import json
from pathlib import Path, PureWindowsPath
import re
import sys


TOE = "podcast.41.toe"
EDITION = "work/storytelling-real-december/approved-ambient-136-3080-2026-11-24"
PLAYLIST = EDITION + "/playlist.json"


def saved_root(saved, relative=PLAYLIST):
    spelling = str(saved)
    suffix = "/" + relative
    if not spelling.replace("\\", "/").casefold().endswith(suffix.casefold()):
        raise RuntimeError("The loaded project is not bound to the approved .41 playlist")
    old = spelling[:-len(suffix)]
    if not Path(old).is_absolute() and not PureWindowsPath(old).is_absolute():
        raise RuntimeError("The saved .41 project path is not absolute")
    return old


def replace_root(text, old, new):
    """Rebase the owned DATs' plain, forward-slash and Python-repr paths."""
    a, b = str(old), str(new)
    plain, replacement = a.replace("/", "\\"), b.replace("/", "\\")
    pairs = {
        a.replace("\\", "/"): b.replace("\\", "/"),
        plain: replacement,
        plain.replace("\\", "\\\\"): replacement.replace("\\", "\\\\").replace("'", "\\'"),
    }
    pairs = {key.casefold(): value for key, value in pairs.items()}
    expression = "|".join(re.escape(key) for key in sorted(pairs, key=len, reverse=True))
    return re.sub(expression, lambda match: pairs[match.group().casefold()], text, flags=re.I)


def _verified_snapshot(root):
    receipt = json.loads((root / "private-handoff-receipt.json").read_text(encoding="utf-8"))
    meta = receipt["metadata"]
    if (meta.get("toe"), meta.get("playlist"), meta.get("profile"), meta.get("selection_mode")) != (
            TOE, PLAYLIST, "3080_safe", "approved-3080-41-playback"):
        raise RuntimeError("Use a fresh import of the dedicated .41 playback snapshot")
    body = dict(format=receipt["format"], metadata=meta, files=receipt["files"])
    raw = (json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    if hashlib.sha256(raw).hexdigest() != receipt["snapshot"]:
        raise RuntimeError("The imported .41 snapshot identity does not match its receipt")
    # Run only the project tool copied by the vetted snapshot, not an
    # arbitrary executable path provided by a playlist or global environment.
    logical = "home_podcast/private_handoff.py"
    binding = [row for row in receipt["files"] if row["path"] == logical]
    helper = root / logical
    if len(binding) != 1 or hashlib.sha256(helper.read_bytes()).hexdigest() != binding[0]["sha256"]:
        raise RuntimeError("Standalone verification code differs from the imported snapshot")
    spec = importlib.util.spec_from_file_location("rh_verify_3080_show_41", helper)
    tool = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = tool
    spec.loader.exec_module(tool)
    tool.verify_target(root)  # Full verification before any native mutation.
    return tool


def rebind_show_41():
    if str(project.name) != TOE or str(app.build) != "2025.32820":
        raise RuntimeError("Open the imported podcast.41.toe in TouchDesigner 2025.32820")
    owner = op("/project1/podcast_visualizer")
    control = owner.op("show_control") if owner is not None else None
    if control is None or str(control.par.Runtimeprofile.eval()) != "3080_safe" or control.par.Livevariations.eval():
        raise RuntimeError("Only the approved 3080_safe project is supported")
    for name in ("StreamDiffusionTD", "StreamDiffusionTD2"):
        target = owner.op(name)
        if target is None or target.par.Serveractive.eval() or target.par.Streamactive.eval():
            raise RuntimeError("Keep both renderer servers and streams stopped")
    root = Path(project.folder).resolve()
    tool = _verified_snapshot(root)
    old = saved_root(owner.par.Playlistmanifest.eval())
    manifest_path = tool.checked_path(root, PLAYLIST)
    manifest = tool.read(manifest_path)
    if manifest["story_count"] != 136 or manifest["profile"] != "3080_safe":
        raise RuntimeError("The approved .41 scope has changed")
    plans = {mode: tool.checked_path(root, row["path"]) for mode, row in manifest["plans"].items()}
    plan = tool.read(plans["balanced"])
    audio = {kind: tool.checked_path(root, name) for kind, name in manifest["audio"].items()}
    bindings = {
        "Playlistmanifest": manifest_path, "Scenejson": plans["original"],
        "Canonicalvisuals": plans["original"], "Humanfigurejson": plans["human_figures"],
        "Canonicalhumanvisuals": plans["human_figures"], "Balancedjson": plans["balanced"],
        "Controllermodule": tool.checked_path(root, plan["controller_module"]),
        "Sequencermodule": tool.checked_path(root, plan["sequencer_module"]),
        "Audiofile": audio["voices_only"], "Soundscapeaudiofile": audio["soundscape_only"],
        "Combinedaudiofile": audio["combined"],
    }
    if any(not path.is_file() or getattr(owner.par, name, None) is None for name, path in bindings.items()):
        raise RuntimeError("Missing verified .41 asset or playback parameter")
    runtime = tool.checked_path(root, EDITION + "/runtime")
    for name, path in (("Livecontroljson", "control.json"), ("Livestatusjson", "status.json"), ("Livecurrentjson", "current.json")):
        if getattr(owner.par, name, None) is not None:
            bindings[name] = tool.checked_path(root, f"{EDITION}/runtime/{path}")

    # Never traverse, inspect or mutate licensed renderer descendants.
    nodes = [node for node in (*owner.children, *control.children) if getattr(node, "isDAT", False)]
    patches = []
    for node in nodes:
        patched = replace_root(node.text, old, root)
        if patched != node.text:
            if node.name.endswith("_callbacks"):
                compile(patched, node.name, "exec")
            patches.append((node, patched))
    navigation = control.op("playlist_callbacks")
    if navigation is None:
        raise RuntimeError("The story navigation callback is missing")
    text = next((value for node, value in patches if node == navigation), navigation.text)
    helper = str(tool.checked_path(root, EDITION + "/playlist_controls.py")).replace("\\", "/")
    if helper.casefold() not in text.replace("\\\\", "\\").replace("\\", "/").casefold():
        raise RuntimeError("The story navigation callback did not rebase")
    runtime.mkdir(exist_ok=True)
    states = [(node, node.par.active.eval()) for node in nodes if getattr(node.par, "active", None) is not None]
    enabled = owner.par.Enabled.eval()
    control.par.Play = False
    op("/local/time").par.play = False
    owner.par.Enabled = False
    try:
        for node, _ in states:
            node.par.active = False
        for name, path in bindings.items():
            getattr(owner.par, name).val = str(path)
        for node, value in patches:
            node.text = value
        callbacks = owner.op("execute_callbacks").module
        callbacks._CONTROLLER = None
        op("/project1").time.frame = 1
        current = callbacks.get_controller()
        current.update(0)
        seq = current.sequencer
        if (len(seq.stories), len(seq.scenes), len(seq.captions), seq.neutral_mix_at(0)) != (136, 619, 2862, 0):
            raise RuntimeError("The restored playback timeline changed")
        for name, kind in (("voices_only_audio", "voices_only"), ("soundscape_audio", "soundscape_only"), ("combined_audio", "combined")):
            if Path(str(owner.op(name).par.file.eval())).resolve() != audio[kind].resolve():
                raise RuntimeError("A native audio operator did not follow the restored path")
        for node, active in states:
            node.par.active = active
        owner.par.Enabled = enabled
        callbacks._synchronize_show_control()
    except Exception:
        owner.par.Enabled = False
        control.par.Play = False
        raise  # Reopen the immutable imported TOE rather than save a partial rebind.
    return dict(stories=136, paused=True, toe_saved=False, models_started=False)
