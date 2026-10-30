"""Parameter callbacks for /project1/podcast_visualizer/show_control."""

import json
import os
from datetime import datetime, timezone
from pathlib import Path


COLOR_PARAMETERS = {
    "Colorenabled",
    "Brightness",
    "Contrast",
    "Gamma",
    "Blacklevel",
    "Opacity",
    "Hue",
    "Saturation",
    "Value",
}
AUDIO_SOURCE_NAMES = ("voices", "soundscape", "combined")
VISUAL_PATH_NAMES = ("original", "human_figures", "balanced")
LIVE_PARAMETERS = {
    "Runtimeprofile",
    "Livevariations",
    "Narrationvariation",
    "Speechvariation",
    "Visualvariation",
    "Interpretivecasting",
    "Randomvariationseeds",
    "Variationseed",
}


def _connector():
    return parent().parent()


def _controller():
    return _connector().op("execute_callbacks").module.get_controller()


def _refresh():
    connector = _connector()
    if bool(connector.par.Enabled.eval()):
        _controller().update(float(connector.par.Playheadsec.eval()))


def _set_audio_enabled(enabled):
    connector = _connector()
    enabled = bool(enabled)
    connector.par.Audioenabled = enabled

    # Older project revisions stored the intended expression on Active while
    # leaving the parameter in Constant mode. Keep legacy projects safe even
    # before the repair installer changes that mode.
    audio_out = connector.op("audio_out")
    if audio_out is not None:
        audio_out.par.active.val = enabled


def _audio_source_index(value):
    if hasattr(value, "eval"):
        value = value.eval()
    if isinstance(value, (int, float)):
        return int(value) if int(value) in (1, 2) else 0
    normalized = str(value or "").strip().casefold().replace(" ", "")
    if normalized in {"2", "combined", "both", "mix", "narration+ambient"}:
        return 2
    return (
        1
        if normalized
        in {"1", "soundscape", "soundscapeonly", "nonhuman", "nonhumanonly"}
        else 0
    )


def _set_audio_source(value):
    connector = _connector()
    index = _audio_source_index(value)
    source_name = AUDIO_SOURCE_NAMES[index]
    source_parameter = getattr(connector.par, "Audiosource", None)
    if source_parameter is not None:
        source_parameter.val = source_name
    source_switch = connector.op("audiosource_switch")
    if source_switch is not None:
        source_switch.par.index.val = index


def _visual_path_index(value):
    if hasattr(value, "eval"):
        value = value.eval()
    if isinstance(value, (int, float)):
        return int(value) if int(value) in (1, 2) else 0
    normalized = str(value or "").strip().casefold().replace(" ", "_")
    if normalized in {"2", "balanced", "balanced_memories"}:
        return 2
    return (
        1
        if normalized
        in {"1", "human", "human_figure", "human_figures", "humanfigures"}
        else 0
    )


def _set_visual_path(value):
    connector = _connector()
    path_name = VISUAL_PATH_NAMES[_visual_path_index(value)]
    path_parameter = getattr(connector.par, "Visualpath", None)
    if path_parameter is not None:
        path_parameter.val = path_name
    # Plans may have different scene boundaries. Reload against the same
    # playhead without restarting or rebinding either synchronized audio stem.
    _controller().reload()


def _runtime_profile(value):
    if hasattr(value, "eval"):
        value = value.eval()
    if isinstance(value, (int, float)):
        return "5090_live" if int(value) == 1 else "3080_safe"
    normalized = str(value or "").strip().casefold().replace(" ", "_")
    return "5090_live" if normalized in {"1", "5090", "5090_live"} else "3080_safe"


def _read_json_object(path):
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_live_control(*, regenerate=False):
    connector = _connector()
    control = parent()
    path_parameter = getattr(connector.par, "Livecontroljson", None)
    if path_parameter is None:
        return None
    path = Path(str(path_parameter.eval())).resolve()
    previous = _read_json_object(path) if path.is_file() else {}
    profile = _runtime_profile(control.par.Runtimeprofile)
    live_enabled = bool(control.par.Livevariations.eval()) and profile == "5090_live"
    if profile == "3080_safe" and bool(control.par.Livevariations.eval()):
        control.par.Livevariations = False
    connector_profile = getattr(connector.par, "Runtimeprofile", None)
    if connector_profile is not None:
        connector_profile.val = profile
    nonce = int(previous.get("regeneration_nonce") or 0)
    if regenerate:
        nonce += 1
    current_narration = getattr(connector.par, "Currentnarrationid", None)
    canonical_visuals = getattr(connector.par, "Canonicalvisuals", None)
    canonical_human_visuals = getattr(
        connector.par, "Canonicalhumanvisuals", None
    )
    value = {
        "enabled": live_enabled,
        "profile": profile,
        "narration_variation": bool(control.par.Narrationvariation.eval()),
        "speech_variation": bool(control.par.Speechvariation.eval()),
        "visual_variation": bool(control.par.Visualvariation.eval()),
        "casting_mode": (
            "interpretive"
            if bool(control.par.Interpretivecasting.eval())
            else "evidence_conservative"
        ),
        "seed_mode": (
            "random"
            if bool(control.par.Randomvariationseeds.eval())
            else "fixed"
        ),
        "fixed_seed": max(0, int(control.par.Variationseed.eval())),
        "current_narration_id": (
            str(current_narration.eval()) if current_narration is not None else ""
        ),
        "canonical_visuals": (
            str(canonical_visuals.eval()) if canonical_visuals is not None else ""
        ),
        "canonical_human_visuals": (
            str(canonical_human_visuals.eval())
            if canonical_human_visuals is not None
            else ""
        ),
        "regeneration_nonce": nonce,
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "writer": "touchdesigner_show_control",
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".td.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)
    return value


def onValueChange(par, prev):
    if par.name == "Play":
        op("/local/time").par.play = bool(par.eval())
    elif par.name == "Audioenabled":
        _set_audio_enabled(par.eval())
    elif par.name == "Audiosource":
        _set_audio_source(par.eval())
    elif par.name == "Visualpath":
        _set_visual_path(par.eval())
    elif par.name == "Randomseeds":
        _controller().randomize_seeds()
        _refresh()
    elif par.name == "Crossfadesec":
        _refresh()
    elif par.name in LIVE_PARAMETERS:
        _write_live_control()
    elif par.name in COLOR_PARAMETERS:
        _refresh()
    return


def onValuesChanged(changes):
    return


def onPulse(par):
    if par.name == "Restart":
        _controller().advance_seed_loop()
        op("/local/time").par.play = False
        op("/project1").time.frame = 1
        parent().par.Play = False
        _refresh()
    elif par.name == "Reload":
        _controller().reload()
    elif par.name == "Newseeds":
        _controller().randomize_seeds()
        _refresh()
    elif par.name == "Resetcolor":
        control = parent()
        control.par.Colorenabled = True
        control.par.Brightness = 1.0
        control.par.Contrast = 1.0
        control.par.Gamma = 1.0
        control.par.Blacklevel = 0.0
        control.par.Opacity = 1.0
        control.par.Hue = 0.0
        control.par.Saturation = 1.0
        control.par.Value = 1.0
        _refresh()
    elif par.name == "Regeneratenext":
        _write_live_control(regenerate=True)
    return


def onExpressionChange(par, val, prev):
    return


def onExportChange(par, val, prev):
    return


def onEnableChange(par, val, prev):
    return


def onModeChange(par, val, prev):
    return
