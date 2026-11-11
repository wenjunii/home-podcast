"""Read-only native startup assertions; no parameter edits, saves or servers."""
from pathlib import Path
import json
import sys


def check_startup():
    owner = op("/project1/podcast_visualizer")
    control = owner.op("show_control")
    controller = owner.op("execute_callbacks").module.get_controller()
    seq = controller.sequencer
    checks = {
        "correct_project": str(project.name) == "podcast.5090.25.toe",
        "correct_build": str(app.build) == "2025.32820",
        "paused_frame_one": not control.par.Play.eval() and not op("/local/time").par.play.eval() and op("/project1").time.frame == 1,
        "canonical_live_off": str(control.par.Runtimeprofile.eval()) == "3080_safe" and not control.par.Livevariations.eval(),
        "approved_scope": len(seq.stories) == 136 and len(seq.scenes) == 619 and len(seq.captions) == 2862,
        "balanced_combined_defaults": str(control.par.Visualpath.eval()) == "balanced" and str(control.par.Audiosource.eval()) == "combined",
        "continuous_image_hold": seq.plan.get("hold_visual_gaps_edition") is True and seq.neutral_mix_at(0) == 0 and not control.par.Abstractfadesec.enable,
        "edition_interpolation_defaults": control.par.Crossfadesec.eval() == control.par.Storyfadesec.eval() == 3,
        "receiver_audio_enable": bool(control.par.Audioenabled.eval()),
        "no_generation_imports": not {"qwen_tts", "ollama", "diffusers"}.intersection(sys.modules),
        "own_playlist_callback": "install.py" not in control.op("playlist_callbacks").text,
    }
    for name, version, ports in (("StreamDiffusionTD", "0.3.1", (8574, 8583)), ("StreamDiffusionTD2", "0.3.0", (8567, 8577))):
        node = owner.op(name)
        checks[name + ":stopped"] = not node.par.Serveractive.eval() and not node.par.Streamactive.eval()
        checks[name + ":version"] = str(node.par.Txversion.eval()) == version
        checks[name + ":base"] = Path(str(node.par.Basefolder.eval())).resolve() == Path(project.folder).parent / "StreamDiffusionTD3.1/StreamDiffusion"
        checks[name + ":ports"] = (node.par.Oscinport.eval(), node.par.Oscoutport.eval()) == ports
    report = dict(project=str(project.name), passed=all(checks.values()), checks=checks, saved=False, live_generation=False, servers_started=False)
    path = Path(project.folder) / "work/5090-136/native-startup-check.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("STARTUP_5090_25", report)
    if not report["passed"]:
        raise RuntimeError("New native startup check failed")
    return report


if "project" in globals():
    check_startup()
