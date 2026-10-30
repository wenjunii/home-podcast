"""Rebind an imported .40 ONLY, inside TD's Python Textport; never save/start.

exec(open(r'D:\new-project\touchdesigner\rebind_private_handoff.py', encoding='utf-8').read())
rebind_private_handoff()

Do not use the older pilot-only rebind_project_paths.py for this edition.
"""
from pathlib import Path
import importlib.util
import json
import sys


def replace_root(text, old_root, new_root):
    """Rebase literal paths, Python-repr paths and forward-slash paths only."""
    pairs = {
        old_root.replace("\\", "\\\\"): str(new_root).replace("\\", "\\\\"),
        old_root.replace("\\", "/"): str(new_root).replace("\\", "/"),
        old_root: str(new_root),
    }
    # Replace in one pass: a nested destination must not get replaced again.
    import re
    pattern = re.compile("|".join(re.escape(key) for key in sorted(pairs, key=len, reverse=True)))
    return pattern.sub(lambda match: pairs[match.group()], str(text))


def old_root_from_manifest(saved, relative):
    normalized = str(saved).replace("\\", "/")
    suffix = "/" + relative
    if not normalized.casefold().endswith(suffix.casefold()):
        raise RuntimeError("The saved project does not point to the selected .40 playlist")
    return str(saved)[:-len(suffix)]


def rebind_private_handoff():
    root = Path(project.folder).resolve()
    if str(app.build) != "2025.32820" or str(project.name) != "podcast.40.toe":
        raise RuntimeError("Rebind only the imported 3080 podcast.40.toe in TD2025.32820; no 5090 project")
    owner = op("/project1/podcast_visualizer")
    control = owner.op("show_control") if owner is not None else None
    if control is None or str(control.par.Runtimeprofile.eval()) != "3080_safe" or control.par.Livevariations.eval():
        raise RuntimeError("Offline 3080_safe profile required")
    for name in ("StreamDiffusionTD", "StreamDiffusionTD2"):
        renderer = owner.op(name)
        if renderer is None or renderer.par.Serveractive.eval() or renderer.par.Streamactive.eval():
            raise RuntimeError("Both renderer servers/streams must be stopped; no automatic model-path changes")
    spec = importlib.util.spec_from_file_location("rh_private_handoff_verify", root / "home_podcast/private_handoff.py")
    module = importlib.util.module_from_spec(spec);sys.modules[spec.name] = module;spec.loader.exec_module(module)
    module.verify_target(root)  # Full preflight BEFORE changing a native parameter.
    receipt = json.loads((root / "private-handoff-receipt.json").read_text(encoding="utf-8"))
    meta = receipt["metadata"]
    if meta.get("toe") != str(project.name) or meta.get("profile") != "3080_safe" or meta.get("stories") != 136:
        raise RuntimeError("Wrong handoff scope/profile")
    manifest = json.loads((root / meta["playlist"]).read_text(encoding="utf-8"))
    old_root = old_root_from_manifest(owner.par.Playlistmanifest.eval(), meta["playlist"])
    visual = {mode: root / entry["path"] for mode, entry in manifest["plans"].items()}
    plan = json.loads(visual["balanced"].read_text(encoding="utf-8"))
    bindings = {"Playlistmanifest": root / meta["playlist"],
        "Controllermodule": root / plan["controller_module"], "Sequencermodule": root / plan["sequencer_module"],
        "Scenejson": visual["original"], "Humanfigurejson": visual["human_figures"], "Balancedjson": visual["balanced"],
        "Canonicalvisuals": visual["original"], "Canonicalhumanvisuals": visual["human_figures"],
        "Audiofile": root / manifest["audio"]["voices_only"],
        "Soundscapeaudiofile": root / manifest["audio"]["soundscape_only"],
        "Combinedaudiofile": root / manifest["audio"]["combined"]}
    for name, filename in (("Livecontroljson", "control.json"), ("Livestatusjson", "status.json"), ("Livecurrentjson", "current.json")):
        if getattr(owner.par, name, None) is not None:
            bindings[name] = root / Path(meta["playlist"]).parent / "runtime" / filename
    required_nodes = [owner.op(name) for name in ("execute_callbacks", "voices_only_audio", "soundscape_audio", "combined_audio")]
    if any(node is None for node in required_nodes) or any(getattr(owner.par, name, None) is None for name in bindings):
        raise RuntimeError("Imported native connector is incomplete")
    # Restrict rebasing to our connector + Show Control, never paid-component
    # descendants. Includes the embedded callback helper paths often missed by
    # a simple Scenejson/Audiofile update.
    nodes = [node for node in list(owner.children) + list(control.children) if getattr(node, "isDAT", False)]
    patches = [(node, replace_root(node.text, old_root, root)) for node in nodes if old_root in node.text or old_root.replace("\\", "/") in node.text or old_root.replace("\\", "\\\\") in node.text]
    active = [(node, node.par.active.eval()) for node in nodes if getattr(node.par, "active", None) is not None]
    owner.par.Enabled = False
    control.par.Play = False
    op("/local/time").par.play = False
    try:
        for node, _ in active:node.par.active = False
        for name, path in bindings.items():getattr(owner.par, name).val = str(path)
        for node, text in patches:node.text = text
        callback = owner.op("execute_callbacks")
        callback.module._CONTROLLER = None
        op("/project1").time.frame = 1
        current = callback.module.get_controller()
        current.update(0)
        if len(current.sequencer.stories) != 136 or len(current.sequencer.scenes) != 619 or current.sequencer.neutral_mix_at(0) != 0:
            raise RuntimeError("Rebound controller did not retain the .40 edition")
        for name, key in (("voices_only_audio", "Audiofile"), ("soundscape_audio", "Soundscapeaudiofile"), ("combined_audio", "Combinedaudiofile")):
            if Path(str(owner.op(name).par.file.eval())).resolve() != bindings[key].resolve():
                raise RuntimeError("Audio binding did not follow the new project root")
    except Exception:
        # A failed rebind remains paused/disabled. Do not play a partial state.
        raise
    else:
        for node, was_active in active:node.par.active = was_active
        owner.par.Enabled = True
        callback.module._synchronize_show_control()
    result = dict(project=str(project.name), stories=136, rebound_parameters=len(bindings), rebound_dats=len(patches),
        saved=False, servers_started=False, paid_component_paths_changed=False, changes_5090=0)
    print("PRIVATE_HANDOFF_REBOUND", result)
    return result
