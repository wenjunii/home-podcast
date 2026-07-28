"""Build the adjustable show-control COMP without touching paid operators."""

from pathlib import Path
import re


SHOW_CONTROL_MARKER = "Recovered Homes show control"
COLOR_PIPELINE_MARKER = "Recovered Homes color pipeline"
AUDIO_PIPELINE_MARKER = "Recovered Homes audio source pipeline"
SPOUT_OUTPUT_MARKER = "Recovered Homes 5090 Spout output"
DEFAULT_CROSSFADE_SECONDS = 8.0
MAX_CROSSFADE_SECONDS = 30.0
NORMALIZED_CROSSFADE_SECONDS = 15.0
AUDIO_SOURCE_NAMES = ("voices", "soundscape")
AUDIO_SOURCE_LABELS = ("Human Voices Only", "Soundscape Only")
SPOUT_OUTPUT_SPECS = (
    (
        "syphonspoutout1",
        "null1",
        "TDSyphonSpoutOut",
        1175,
        400,
    ),
    (
        "syphonspoutout2",
        "null2",
        "TDSyphonSpoutOut2",
        1625,
        -275,
    ),
)
COLOR_DEFAULTS = {
    "Colorenabled": True,
    # TouchDesigner's Level TOP uses 1.0 as neutral brightness. A value of
    # 0.0 multiplies the image to black.
    "Brightness": 1.0,
    "Contrast": 1.0,
    "Gamma": 1.0,
    "Blacklevel": 0.0,
    "Opacity": 1.0,
    "Hue": 0.0,
    "Saturation": 1.0,
    "Value": 1.0,
}


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
    audio_source_value = _normalize_audio_source(
        getattr(connector.par, "Audiosource", None)
    )
    crossfade_value = float(default_fade)
    random_seeds_value = False
    color_values = dict(COLOR_DEFAULTS)
    existing = connector.op("show_control")
    if existing is not None:
        if SHOW_CONTROL_MARKER not in str(existing.comment):
            raise RuntimeError(
                "A non-Recovered-Homes operator already uses the name "
                f"{existing.path}; rename it before installing show control."
            )
        play_par = getattr(existing.par, "Play", None)
        audio_par = getattr(existing.par, "Audioenabled", None)
        audio_source_par = getattr(existing.par, "Audiosource", None)
        crossfade_par = getattr(existing.par, "Crossfadesec", None)
        random_seeds_par = getattr(existing.par, "Randomseeds", None)
        if play_par is not None:
            play_value = bool(play_par.eval())
        if audio_par is not None:
            audio_value = bool(audio_par.eval())
        if audio_source_par is not None:
            audio_source_value = _normalize_audio_source(audio_source_par)
        if crossfade_par is not None:
            crossfade_value = float(crossfade_par.eval())
        if random_seeds_par is not None:
            random_seeds_value = bool(random_seeds_par.eval())
        brightness_par = getattr(existing.par, "Brightness", None)
        legacy_brightness_range = _has_range(
            brightness_par,
            -1.0,
            1.0,
        )
        for name, default in COLOR_DEFAULTS.items():
            parameter = getattr(existing.par, name, None)
            if parameter is not None:
                converter = bool if isinstance(default, bool) else float
                color_values[name] = converter(parameter.eval())
        # Releases before this fix exposed Level TOP brightness as -1..1 and
        # documented 0 as neutral. Migrate that saved legacy-neutral value to
        # the actual Level TOP neutral value.
        if (
            legacy_brightness_range
            and color_values["Brightness"] == 0.0
        ):
            color_values["Brightness"] = COLOR_DEFAULTS["Brightness"]
        existing.destroy()

    _install_audio_source_pipeline(
        connector,
        project_root,
        operator_types,
        audio_source=audio_source_value,
    )
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
    audio_source = page.appendMenu(
        "Audiosource",
        label="Audio Source",
    )[0]
    audio_source.menuNames = list(AUDIO_SOURCE_NAMES)
    audio_source.menuLabels = list(AUDIO_SOURCE_LABELS)
    page.appendToggle(
        "Randomseeds",
        label="Random Seeds Each Loop",
    )
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
    page.appendPulse("Newseeds", label="New Random Seeds")
    page.appendPulse("Restart", label="Restart")
    page.appendPulse("Reload", label="Reload Scene JSON")

    color_page = control.appendCustomPage("Color")
    color_page.appendToggle(
        "Colorenabled",
        label="Color Adjustments Enabled",
    )
    brightness = color_page.appendFloat(
        "Brightness",
        label="Brightness",
    )[0]
    _configure_float(brightness, 0.0, 2.0)
    contrast = color_page.appendFloat("Contrast", label="Contrast")[0]
    _configure_float(contrast, 0.0, 4.0, norm_max=2.0)
    gamma = color_page.appendFloat("Gamma", label="Gamma")[0]
    _configure_float(gamma, 0.1, 4.0, norm_max=2.0)
    black_level = color_page.appendFloat(
        "Blacklevel",
        label="Black Level",
    )[0]
    _configure_float(black_level, 0.0, 1.0)
    opacity = color_page.appendFloat("Opacity", label="Opacity")[0]
    _configure_float(opacity, 0.0, 1.0)
    hue = color_page.appendFloat("Hue", label="Hue Shift")[0]
    _configure_float(hue, -180.0, 180.0)
    saturation = color_page.appendFloat(
        "Saturation",
        label="Saturation",
    )[0]
    _configure_float(saturation, 0.0, 4.0, norm_max=2.0)
    value = color_page.appendFloat("Value", label="Color Value")[0]
    _configure_float(value, 0.0, 4.0, norm_max=2.0)
    color_page.appendPulse("Resetcolor", label="Reset Color")

    control.par.Play = play_value
    control.par.Audioenabled = audio_value
    control.par.Audiosource = audio_source_value
    control.par.Randomseeds = random_seeds_value
    control.par.Crossfadesec = crossfade_value
    for name, value in color_values.items():
        getattr(control.par, name).val = value

    help_table = control.create(table_dat, "controls")
    help_table.nodeX = 0
    help_table.nodeY = 0
    help_table.appendRow(["control", "description"])
    help_table.appendRow(["Play", "Play or pause the TouchDesigner timeline"])
    help_table.appendRow(
        ["Audio Enabled", "Send the selected audio source to the device"]
    )
    help_table.appendRow(
        [
            "Audio Source",
            "Choose Human Voices Only or Soundscape Only; no combined mix",
        ]
    )
    help_table.appendRow(
        [
            "Random Seeds Each Loop",
            "Off repeats stable images; on selects a new seed bank each loop",
        ]
    )
    help_table.appendRow(
        [
            "Crossfade Seconds",
            "Live 0-30 second fade; capped at half the active scene duration",
        ]
    )
    help_table.appendRow(
        [
            "New Random Seeds",
            "Choose a fresh random seed bank without waiting for the next loop",
        ]
    )
    help_table.appendRow(["Restart", "Pause and return to episode start"])
    help_table.appendRow(["Reload Scene JSON", "Reload prompts and timing from disk"])
    help_table.appendRow(
        [
            "Color",
            "Live Level and HSV controls applied after each generator",
        ]
    )

    callbacks = control.create(parameter_execute_dat, "control_callbacks")
    callbacks.nodeX = 240
    callbacks.nodeY = 0
    callbacks.par.op = control.path
    callbacks.par.pars = (
        "Play Audioenabled Audiosource Randomseeds Crossfadesec "
        "Newseeds Restart Reload "
        "Colorenabled Brightness Contrast Gamma Blacklevel Opacity Hue "
        "Saturation Value Resetcolor"
    )
    callbacks.par.valuechange = True
    callbacks.par.valueschanged = False
    callbacks.par.onpulse = True
    callbacks.text = (
        project_root / "touchdesigner" / "show_control_callbacks.py"
    ).read_text(encoding="utf-8")
    _install_color_pipelines(connector, operator_types)
    _install_spout_outputs(connector, operator_types)
    return control


def _normalize_audio_source(value):
    if hasattr(value, "eval"):
        value = value.eval()
    if isinstance(value, (int, float)):
        return AUDIO_SOURCE_NAMES[1 if int(value) == 1 else 0]
    normalized = str(value or "").strip().casefold().replace(" ", "")
    if normalized in {
        "1",
        "soundscape",
        "soundscapeonly",
        "nonhuman",
        "nonhumanonly",
    }:
        return "soundscape"
    return "voices"


def _audio_source_index(value):
    return 1 if _normalize_audio_source(value) == "soundscape" else 0


def _install_audio_source_pipeline(
    connector,
    project_root,
    operator_types,
    *,
    audio_source="voices",
):
    required_types = (
        "audiofileinCHOP",
        "switchCHOP",
        "audiodeviceoutCHOP",
    )
    if any(name not in operator_types for name in required_types):
        return None

    podcast_page = next(
        (
            page
            for page in getattr(connector, "customPages", ())
            if page.name == "Podcast"
        ),
        None,
    )
    if podcast_page is None:
        podcast_page = connector.appendCustomPage("Podcast")
    connector_source = getattr(connector.par, "Audiosource", None)
    if connector_source is None:
        source_par = podcast_page.appendMenu(
            "Audiosource",
            label="Audio Source",
        )[0]
    else:
        source_par = connector_source
    source_par.menuNames = list(AUDIO_SOURCE_NAMES)
    source_par.menuLabels = list(AUDIO_SOURCE_LABELS)
    if getattr(connector.par, "Soundscapeaudiofile", None) is None:
        podcast_page.appendFile(
            "Soundscapeaudiofile",
            label="Soundscape-only Audio",
        )

    audio_source = _normalize_audio_source(audio_source)
    audio_dir = (
        project_root
        / "episodes"
        / "2013-12.01"
        / "audio"
    )
    voices_path = audio_dir / "2013-12.01-voices-only.mp3"
    soundscape_path = audio_dir / "2013-12.01-soundscape-only.mp3"
    connector.par.Audiosource = audio_source
    connector.par.Soundscapeaudiofile = str(soundscape_path)

    voices = connector.op("voices_only_audio")
    if voices is None:
        voices = connector.create(
            operator_types["audiofileinCHOP"],
            "voices_only_audio",
        )
    soundscape = connector.op("soundscape_audio")
    if soundscape is None:
        soundscape = connector.create(
            operator_types["audiofileinCHOP"],
            "soundscape_audio",
        )
    source_switch = connector.op("audiosource_switch")
    if source_switch is None:
        source_switch = connector.create(
            operator_types["switchCHOP"],
            "audiosource_switch",
        )
    elif AUDIO_PIPELINE_MARKER not in str(source_switch.comment):
        raise RuntimeError(
            f"{source_switch.path} is not a Recovered Homes audio switch."
        )
    audio_out = connector.op("audio_out")
    if audio_out is None:
        audio_out = connector.create(
            operator_types["audiodeviceoutCHOP"],
            "audio_out",
        )

    voices.comment = AUDIO_PIPELINE_MARKER
    soundscape.comment = AUDIO_PIPELINE_MARKER
    source_switch.comment = AUDIO_PIPELINE_MARKER
    voices.nodeX = 0
    voices.nodeY = -160
    soundscape.nodeX = 0
    soundscape.nodeY = -280
    source_switch.nodeX = 220
    source_switch.nodeY = -220
    audio_out.nodeX = 440
    audio_out.nodeY = -220

    voices.par.file = str(
        connector.par.Audiofile.eval()
        if str(connector.par.Audiofile.eval()).strip()
        else voices_path
    )
    soundscape.par.file = str(soundscape_path)
    for audio in (voices, soundscape):
        audio.par.playmode = "locked"
        audio.par.play = True
        audio.par.repeat = False

    for input_connector in source_switch.inputConnectors[:2]:
        input_connector.disconnect()
    audio_out.inputConnectors[0].disconnect()
    voices.outputConnectors[0].connect(source_switch.inputConnectors[0])
    soundscape.outputConnectors[0].connect(source_switch.inputConnectors[1])
    source_switch.outputConnectors[0].connect(audio_out.inputConnectors[0])
    source_switch.par.index.val = _audio_source_index(audio_source)
    audio_out.par.active.expr = "parent().par.Audioenabled"
    return source_switch


def _configure_float(parameter, minimum, maximum, *, norm_max=None):
    parameter.min = minimum
    parameter.max = maximum
    parameter.clampMin = True
    parameter.clampMax = True
    parameter.normMin = minimum
    parameter.normMax = maximum if norm_max is None else norm_max


def _install_spout_outputs(connector, operator_types):
    """Recreate the two 5090 Spout senders when their output nulls exist."""

    operator_type = operator_types.get("syphonspoutoutTOP")
    if operator_type is None:
        return []

    outputs = []
    for name, source_name, sender_name, node_x, node_y in SPOUT_OUTPUT_SPECS:
        source = connector.op(source_name)
        if source is None:
            continue
        output = connector.op(name)
        if output is None:
            output = connector.create(operator_type, name)
        elif output.type != "syphonspoutout":
            raise RuntimeError(
                f"{output.path} exists but is not a Syphon Spout Out TOP."
            )

        output.comment = SPOUT_OUTPUT_MARKER
        output.nodeX = node_x
        output.nodeY = node_y
        output.par.active = True
        output.par.sendername = sender_name
        output.par.outputresolution = "useinput"
        output.inputConnectors[0].disconnect()
        source.outputConnectors[0].connect(output.inputConnectors[0])
        outputs.append(output)
    return outputs


def _has_range(parameter, minimum, maximum):
    if parameter is None:
        return False
    try:
        return (
            float(parameter.min) == float(minimum)
            and float(parameter.max) == float(maximum)
        )
    except (AttributeError, TypeError, ValueError):
        return False


def _install_color_pipelines(connector, operator_types):
    required_types = (
        "levelTOP",
        "hsvadjustTOP",
        "switchTOP",
        "nullTOP",
    )
    if any(name not in operator_types for name in required_types):
        return []

    target_spec = str(connector.par.Streamdiffusionpath.eval()).strip()
    target_paths = [
        path.strip()
        for path in re.split(r"[;,\n]+", target_spec)
        if path.strip()
    ] or ["StreamDiffusionTD"]
    outputs = []
    for index, target_path in enumerate(target_paths, start=1):
        target = connector.op(target_path)
        if target is None or not target.outputConnectors:
            continue

        existing_output = connector.op(f"color_out_{index}")
        downstream_connectors = _downstream_connectors(existing_output)
        if not downstream_connectors:
            # A prior install may have stopped after creating the marked nodes
            # but before wiring the final output. In that case, recover the
            # target's original downstream connections instead.
            downstream_connectors = _downstream_connectors(target)
        for node_name in (
            f"color_out_{index}",
            f"color_switch_{index}",
            f"color_hsv_{index}",
            f"color_level_{index}",
        ):
            existing_node = connector.op(node_name)
            if existing_node is None:
                continue
            if COLOR_PIPELINE_MARKER not in str(existing_node.comment):
                raise RuntimeError(
                    f"{existing_node.path} is not a Recovered Homes color node."
                )
            existing_node.destroy()

        level = connector.create(
            operator_types["levelTOP"],
            f"color_level_{index}",
        )
        hsv = connector.create(
            operator_types["hsvadjustTOP"],
            f"color_hsv_{index}",
        )
        switch = connector.create(
            operator_types["switchTOP"],
            f"color_switch_{index}",
        )
        output = connector.create(
            operator_types["nullTOP"],
            f"color_out_{index}",
        )
        for node in (level, hsv, switch, output):
            node.comment = COLOR_PIPELINE_MARKER

        base_x = target.nodeX + target.nodeWidth + 140
        base_y = target.nodeY
        level.nodeX = base_x
        level.nodeY = base_y - 120
        hsv.nodeX = base_x + 160
        hsv.nodeY = base_y - 120
        switch.nodeX = base_x + 320
        switch.nodeY = base_y
        output.nodeX = base_x + 480
        output.nodeY = base_y

        # StreamDiffusionTD is a component whose regular output connector
        # exposes its TOP output. Connect from that connector explicitly;
        # passing the component itself into a TOP input is ambiguous in TD.
        target.outputConnectors[0].connect(level.inputConnectors[0])
        level.outputConnectors[0].connect(hsv.inputConnectors[0])
        target.outputConnectors[0].connect(switch.inputConnectors[0])
        hsv.outputConnectors[0].connect(switch.inputConnectors[1])
        switch.outputConnectors[0].connect(output.inputConnectors[0])
        for downstream in downstream_connectors:
            if downstream.owner.valid:
                output.outputConnectors[0].connect(downstream)
        outputs.append(output)
    return outputs


def _downstream_connectors(operator):
    if operator is None or not operator.outputConnectors:
        return []
    return list(operator.outputConnectors[0].connections)
