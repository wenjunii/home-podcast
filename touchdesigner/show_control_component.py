"""Build the adjustable show-control COMP without touching paid operators."""

from pathlib import Path


SHOW_CONTROL_MARKER = "Recovered Homes show control"
DEFAULT_CROSSFADE_SECONDS = 8.0
MAX_CROSSFADE_SECONDS = 30.0
NORMALIZED_CROSSFADE_SECONDS = 15.0


def install_show_control(
    connector,
    project_root: Path,
    *,
    operator_types,
    default_fade=DEFAULT_CROSSFADE_SECONDS,
):
    base_comp = operator_types["baseCOMP"]
    table_dat = operator_types["tableDAT"]
    parameter_execute_dat = operator_types["parameterexecuteDAT"]
    operator_lookup = operator_types["op"]
    play_value = bool(operator_lookup("/local/time").par.play.eval())
    audio_value = bool(connector.par.Audioenabled.eval())
    crossfade_value = float(default_fade)
    existing = connector.op("show_control")
    if existing is not None:
        if SHOW_CONTROL_MARKER not in str(existing.comment):
            raise RuntimeError(
                "A non-Recovered-Homes operator already uses the name "
                f"{existing.path}; rename it before installing show control."
            )
        play_par = getattr(existing.par, "Play", None)
        audio_par = getattr(existing.par, "Audioenabled", None)
        crossfade_par = getattr(existing.par, "Crossfadesec", None)
        if play_par is not None:
            play_value = bool(play_par.eval())
        if audio_par is not None:
            audio_value = bool(audio_par.eval())
        if crossfade_par is not None:
            crossfade_value = float(crossfade_par.eval())
        existing.destroy()

    crossfade_value = min(
        MAX_CROSSFADE_SECONDS,
        max(0.0, crossfade_value),
    )

    control = connector.create(base_comp, "show_control")
    control.nodeX = 660
    control.nodeY = 0
    control.nodeWidth = 220
    control.nodeHeight = 140
    control.color = (0.18, 0.42, 0.64)
    control.comment = (
        f"{SHOW_CONTROL_MARKER}\n"
        "Adjust Crossfade Seconds live; effective fade is capped at half "
        "the current visual scene."
    )

    page = control.appendCustomPage("Show Control")
    page.appendToggle("Play", label="Play")
    page.appendToggle("Audioenabled", label="Audio Enabled")
    crossfade = page.appendFloat(
        "Crossfadesec",
        label="Crossfade Seconds",
    )[0]
    crossfade.min = 0
    crossfade.max = MAX_CROSSFADE_SECONDS
    crossfade.clampMin = True
    crossfade.clampMax = True
    crossfade.normMin = 0
    crossfade.normMax = NORMALIZED_CROSSFADE_SECONDS
    page.appendPulse("Restart", label="Restart")
    page.appendPulse("Reload", label="Reload Scene JSON")

    control.par.Play = play_value
    control.par.Audioenabled = audio_value
    control.par.Crossfadesec = crossfade_value

    help_table = control.create(table_dat, "controls")
    help_table.nodeX = 0
    help_table.nodeY = 0
    help_table.appendRow(["control", "description"])
    help_table.appendRow(["Play", "Play or pause the TouchDesigner timeline"])
    help_table.appendRow(["Audio Enabled", "Send voices-only audio to the device"])
    help_table.appendRow(
        [
            "Crossfade Seconds",
            "Live 0-30 second fade; capped at half the active scene duration",
        ]
    )
    help_table.appendRow(["Restart", "Pause and return to episode start"])
    help_table.appendRow(["Reload Scene JSON", "Reload prompts and timing from disk"])

    callbacks = control.create(parameter_execute_dat, "control_callbacks")
    callbacks.nodeX = 240
    callbacks.nodeY = 0
    callbacks.par.op = control.path
    callbacks.par.pars = (
        "Play Audioenabled Crossfadesec Restart Reload"
    )
    callbacks.par.valuechange = True
    callbacks.par.valueschanged = False
    callbacks.par.onpulse = True
    callbacks.text = (
        project_root / "touchdesigner" / "show_control_callbacks.py"
    ).read_text(encoding="utf-8")
    return control
