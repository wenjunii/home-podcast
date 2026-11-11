"""Refresh paths/callbacks for the approved canonical 136-story 5090 edition.

Run in TD2025.32820 with podcast.5090.25.toe (or a later numbered copy).
Never saves, starts servers, installs components or invokes a sender installer.
"""
from pathlib import Path
import json
import re

EDITION = "work/storytelling-real-december/continuous-image-hold-136-3080-2026-10-30"


def rebind_5090_136():
    match = re.fullmatch(r"podcast\.5090\.(\d+)\.toe", str(project.name), re.I)
    if not match or int(match[1]) < 25 or str(app.build) != "2025.32820":
        raise RuntimeError("Only new 5090 canonical revisions in TD2025.32820 may be rebound")
    root = Path(project.folder).resolve()
    owner = op("/project1/podcast_visualizer")
    control = owner.op("show_control")
    renderers = [owner.op(n) for n in ("StreamDiffusionTD", "StreamDiffusionTD2")]
    if any(n is None or n.par.Serveractive.eval() or n.par.Streamactive.eval() for n in renderers):
        raise RuntimeError("Both existing receiver renderer servers must be stopped")
    protected = [{k: getattr(n.par, k).eval() for k in ("Basefolder", "Txversion", "Modelid", "Acceleration", "Width", "Height", "Oscinport", "Oscoutport")} for n in renderers]
    manifest_path = root / EDITION / "playlist.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest["story_count"] != 136 or len(manifest["stories"]) != 136:
        raise RuntimeError("Unexpected approved show scope")
    plan = json.loads((root / manifest["plans"]["balanced"]["path"]).read_text(encoding="utf-8"))
    bindings = {
        "Playlistmanifest": manifest_path,
        "Scenejson": root / manifest["plans"]["original"]["path"],
        "Canonicalvisuals": root / manifest["plans"]["original"]["path"],
        "Humanfigurejson": root / manifest["plans"]["human_figures"]["path"],
        "Canonicalhumanvisuals": root / manifest["plans"]["human_figures"]["path"],
        "Balancedjson": root / manifest["plans"]["balanced"]["path"],
        "Sequencermodule": root / plan["sequencer_module"],
        "Controllermodule": root / plan["controller_module"],
        "Audiofile": root / manifest["audio"]["voices_only"],
        "Soundscapeaudiofile": root / manifest["audio"]["soundscape_only"],
        "Combinedaudiofile": root / manifest["audio"]["combined"],
    }
    if any(not path.is_file() or getattr(owner.par, name, None) is None for name, path in bindings.items()):
        raise RuntimeError("Incomplete 5090 edition or required approved assets")
    callbacks = {
        "show_control/playlist_callbacks": root / "touchdesigner/playlist_5090_callbacks.py",
        "show_control/control_callbacks": root / "touchdesigner/canonical_5090_callbacks.py",
    }
    if any(owner.op(name) is None or not path.is_file() for name, path in callbacks.items()):
        raise RuntimeError("Missing receiver callbacks")
    for name, path in bindings.items():
        getattr(owner.par, name).val = str(path)
    for name, filename in (("Livecontroljson", "control.json"), ("Livestatusjson", "status.json"), ("Livecurrentjson", "current.json")):
        getattr(owner.par, name).val = str(root / "work/5090-136/runtime" / filename)
    control.par.Play = False
    op("/local/time").par.play = False
    control.par.Runtimeprofile = owner.par.Runtimeprofile = "3080_safe"
    control.par.Livevariations = False
    for name, path in callbacks.items():
        owner.op(name).text = path.read_text(encoding="utf-8")
    owner.op("execute_callbacks").module._CONTROLLER = None
    op("/project1").time.frame = 1
    current = owner.op("execute_callbacks").module.get_controller()
    current.update(0)
    owner.op("execute_callbacks").module._synchronize_show_control(reset_paused_start=True)
    control.op("control_callbacks").module._write_live_control()
    after = [{k: getattr(n.par, k).eval() for k in before} for n, before in zip(renderers, protected)]
    if after != protected or len(current.sequencer.stories) != 136 or len(current.sequencer.scenes) != 619:
        raise RuntimeError("Receiver rig or approved scope changed unexpectedly")
    return dict(project=str(project.name), stories=136, scenes=619, live_generation=False,
                receiver_settings_preserved=True, saved=False, servers_started=False)


if "project" in globals():
    print("REBOUND_5090_136", rebind_5090_136())
