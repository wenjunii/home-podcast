"""Exercise every Recovered Homes control in a live 5090 project.

Run this script from the TouchDesigner Textport. It refuses non-5090 project
names, never saves the project, does not start model servers, and restores the
show-control, timeline, audio, seed, and color state before returning.
"""

from pathlib import Path
import re


PROJECT_NAME_PATTERN = re.compile(
    r"podcast\.5090(?:\.\d+)?\.toe",
    re.IGNORECASE,
)
CONTROL_STYLES = {
    "Play": "Toggle",
    "Audioenabled": "Toggle",
    "Audiosource": "Menu",
    "Randomseeds": "Toggle",
    "Crossfadesec": "Float",
    "Newseeds": "Pulse",
    "Restart": "Pulse",
    "Reload": "Pulse",
    "Colorenabled": "Toggle",
    "Brightness": "Float",
    "Contrast": "Float",
    "Gamma": "Float",
    "Blacklevel": "Float",
    "Opacity": "Float",
    "Hue": "Float",
    "Saturation": "Float",
    "Value": "Float",
    "Resetcolor": "Pulse",
}
FLOAT_SPECS = {
    "Crossfadesec": (0.0, 30.0, 0.0, 15.0),
    "Brightness": (0.0, 2.0, 0.0, 2.0),
    "Contrast": (0.0, 4.0, 0.0, 2.0),
    "Gamma": (0.1, 4.0, 0.1, 2.0),
    "Blacklevel": (0.0, 1.0, 0.0, 1.0),
    "Opacity": (0.0, 1.0, 0.0, 1.0),
    "Hue": (-180.0, 180.0, -180.0, 180.0),
    "Saturation": (0.0, 4.0, 0.0, 2.0),
    "Value": (0.0, 4.0, 0.0, 2.0),
}
COLOR_TESTS = {
    "Brightness": ("brightness1", 1.25, 1.25),
    "Contrast": ("contrast", 1.5, 1.5),
    "Gamma": ("gamma1", 1.2, 1.2),
    "Blacklevel": ("blacklevel", 0.1, 0.1),
    "Opacity": ("opacity", 0.75, 0.75),
    "Hue": ("hueoffset", -30.0, 330.0),
    "Saturation": ("saturationmult", 1.4, 1.4),
    "Value": ("valuemult", 1.3, 1.3),
}
COLOR_DEFAULTS = {
    "Colorenabled": True,
    "Brightness": 1.0,
    "Contrast": 1.0,
    "Gamma": 1.0,
    "Blacklevel": 0.0,
    "Opacity": 1.0,
    "Hue": 0.0,
    "Saturation": 1.0,
    "Value": 1.0,
}
SPOUT_SPECS = (
    ("null1", "syphonspoutout1", "TDSyphonSpoutOut"),
    ("null2", "syphonspoutout2", "TDSyphonSpoutOut2"),
)


def _target_paths(connector):
    value = str(connector.par.Streamdiffusionpath.eval()).strip()
    return [
        path.strip()
        for path in re.split(r"[;,\n]+", value)
        if path.strip()
    ] or ["StreamDiffusionTD"]


def _table_values(table):
    return {
        str(table[row, 0]): str(table[row, 1])
        for row in range(1, table.numRows)
    }


def _close_enough(actual, expected):
    return abs(float(actual) - float(expected)) <= 0.000001


def audit_5090_controls():
    project_name = Path(str(project.name)).name
    if PROJECT_NAME_PATTERN.fullmatch(project_name) is None:
        raise RuntimeError(
            "Refusing to audit a non-5090 project. Open podcast.5090.toe "
            "or a numbered podcast.5090 revision first. The 3080 projects "
            "are reference files and must remain untouched."
        )

    connector = op("/project1/podcast_visualizer")
    if connector is None:
        raise RuntimeError(
            "Missing /project1/podcast_visualizer in the 5090 project."
        )
    control = connector.op("show_control")
    if control is None:
        raise RuntimeError("Missing the 5090 show_control component.")
    callbacks = control.op("control_callbacks")
    execute_callbacks = connector.op("execute_callbacks")
    if callbacks is None or execute_callbacks is None:
        raise RuntimeError("Missing a required 5090 callback DAT.")
    controller = execute_callbacks.module.get_controller()
    project_root = op("/project1")
    timeline = op("/local/time")

    passed = []
    failures = []

    def check(name, condition, detail=""):
        if condition:
            passed.append(name)
        else:
            failures.append(
                {
                    "check": name,
                    "detail": str(detail),
                }
            )

    control_values = {
        name: getattr(control.par, name).eval()
        for name in CONTROL_STYLES
        if CONTROL_STYLES[name] != "Pulse"
    }
    connector_enabled = bool(connector.par.Enabled.eval())
    timeline_play = bool(timeline.par.play.eval())
    timeline_frame = int(project_root.time.frame)
    callbacks_active = bool(callbacks.par.active.eval())
    seed_state = {
        "seed_salt": controller.seed_salt,
        "seed_generation": controller.seed_generation,
    }

    def set_control(name, value):
        parameter = getattr(control.par, name)
        previous = parameter.eval()
        parameter.val = value
        callbacks.module.onValueChange(parameter, previous)

    def pulse_control(name):
        callbacks.module.onPulse(getattr(control.par, name))

    callbacks.par.active.val = False
    try:
        connector.par.Enabled.val = True

        for name, expected_style in CONTROL_STYLES.items():
            parameter = getattr(control.par, name, None)
            actual_style = (
                str(parameter.style)
                if parameter is not None
                else "missing"
            )
            check(
                f"control:{name}:style",
                parameter is not None and actual_style == expected_style,
                actual_style,
            )

        for name, expected in FLOAT_SPECS.items():
            parameter = getattr(control.par, name)
            actual = (
                float(parameter.min),
                float(parameter.max),
                float(parameter.normMin),
                float(parameter.normMax),
            )
            check(
                f"control:{name}:range",
                all(
                    _close_enough(actual_value, expected_value)
                    for actual_value, expected_value in zip(
                        actual,
                        expected,
                    )
                )
                and bool(parameter.clampMin)
                and bool(parameter.clampMax),
                actual,
            )

        check(
            "control:Audiosource:menu",
            list(control.par.Audiosource.menuNames)
            == ["voices", "soundscape"]
            and list(control.par.Audiosource.menuLabels)
            == ["Human Voices Only", "Soundscape Only"],
            (
                list(control.par.Audiosource.menuNames),
                list(control.par.Audiosource.menuLabels),
            ),
        )
        callback_names = set(str(callbacks.par.pars.eval()).split())
        check(
            "callbacks:all_controls_registered",
            callback_names == set(CONTROL_STYLES),
            sorted(callback_names),
        )
        check(
            "callbacks:value_and_pulse_enabled",
            bool(callbacks.par.valuechange.eval())
            and bool(callbacks.par.onpulse.eval()),
            (
                callbacks.par.valuechange.eval(),
                callbacks.par.onpulse.eval(),
            ),
        )

        required_nodes = (
            "voices_only_audio",
            "soundscape_audio",
            "audiosource_switch",
            "audio_out",
            "prompt_out",
            "caption_out",
            "status_out",
            "syphonspoutout1",
            "syphonspoutout2",
        )
        for name in required_nodes:
            node = connector.op(name)
            check(
                f"node:{name}:present",
                node is not None,
            )
            if node is not None:
                check(
                    f"node:{name}:errors",
                    not str(node.errors()).strip(),
                    node.errors(),
                )

        for source_name, target_name in (
            ("voices_only_audio", "audiosource_switch"),
            ("soundscape_audio", "audiosource_switch"),
            ("audiosource_switch", "audio_out"),
        ):
            source = connector.op(source_name)
            target = connector.op(target_name)
            check(
                f"connection:{source_name}->{target_name}",
                source is not None
                and target is not None
                and target in source.outputs,
            )

        for source_name, output_name, sender_name in SPOUT_SPECS:
            source = connector.op(source_name)
            output = connector.op(output_name)
            check(
                f"connection:{source_name}->{output_name}",
                source is not None
                and output is not None
                and output in source.outputs,
            )
            if output is None:
                continue
            check(
                f"spout:{output_name}:type",
                output.type == "syphonspoutout",
                output.type,
            )
            check(
                f"spout:{output_name}:active",
                bool(output.par.active.eval()),
                output.par.active.eval(),
            )
            check(
                f"spout:{output_name}:sender",
                str(output.par.sendername.eval()) == sender_name,
                output.par.sendername.eval(),
            )
            check(
                f"spout:{output_name}:resolution",
                str(output.par.outputresolution.eval()) == "useinput",
                output.par.outputresolution.eval(),
            )

        targets = _target_paths(connector)
        check(
            "streamdiffusion:two_targets",
            len(targets) == 2,
            targets,
        )
        for index, target_name in enumerate(targets, start=1):
            target = connector.op(target_name)
            check(
                f"streamdiffusion:{target_name}:present",
                target is not None,
            )
            if target is not None:
                check(
                    f"streamdiffusion:{target_name}:errors",
                    not str(target.errors()).strip(),
                    target.errors(),
                )
            for node_name in (
                f"color_level_{index}",
                f"color_hsv_{index}",
                f"color_switch_{index}",
                f"color_out_{index}",
            ):
                node = connector.op(node_name)
                check(
                    f"node:{node_name}:present",
                    node is not None,
                )
                if node is not None:
                    check(
                        f"node:{node_name}:errors",
                        not str(node.errors()).strip(),
                        node.errors(),
                    )

        set_control("Play", True)
        check(
            "switch:Play:on",
            bool(timeline.par.play.eval()),
            timeline.par.play.eval(),
        )
        set_control("Play", False)
        check(
            "switch:Play:off",
            not bool(timeline.par.play.eval()),
            timeline.par.play.eval(),
        )

        set_control("Audioenabled", False)
        check(
            "switch:Audioenabled:off",
            not bool(connector.par.Audioenabled.eval())
            and not bool(connector.op("audio_out").par.active.eval()),
        )
        set_control("Audioenabled", True)
        check(
            "switch:Audioenabled:on",
            bool(connector.par.Audioenabled.eval())
            and bool(connector.op("audio_out").par.active.eval()),
        )
        set_control("Audioenabled", False)

        for source_name, expected_index in (
            ("voices", 0),
            ("soundscape", 1),
        ):
            set_control("Audiosource", source_name)
            check(
                f"switch:Audiosource:{source_name}",
                str(connector.par.Audiosource.eval()) == source_name
                and int(
                    connector.op("audiosource_switch").par.index.eval()
                )
                == expected_index,
                (
                    connector.par.Audiosource.eval(),
                    connector.op("audiosource_switch").par.index.eval(),
                ),
            )

        set_control("Randomseeds", False)
        status = _table_values(connector.op("status_out"))
        check(
            "switch:Randomseeds:off",
            status.get("seed_mode") == "stable",
            status.get("seed_mode"),
        )
        set_control("Randomseeds", True)
        status = _table_values(connector.op("status_out"))
        check(
            "switch:Randomseeds:on",
            status.get("seed_mode") == "random_per_loop",
            status.get("seed_mode"),
        )

        for value in (0.0, 30.0):
            set_control("Crossfadesec", value)
            check(
                f"slider:Crossfadesec:{value:g}",
                controller._show_control_crossfade_ms()
                == round(value * 1000),
                controller._show_control_crossfade_ms(),
            )

        generation = controller.seed_generation
        pulse_control("Newseeds")
        check(
            "button:Newseeds",
            controller.seed_generation == generation + 1,
            controller.seed_generation,
        )

        set_control("Play", False)
        project_root.time.frame = max(2, timeline_frame)
        pulse_control("Restart")
        check(
            "button:Restart",
            not bool(control.par.Play.eval())
            and not bool(timeline.par.play.eval())
            and int(project_root.time.frame) == 1,
            (
                control.par.Play.eval(),
                timeline.par.play.eval(),
                project_root.time.frame,
            ),
        )

        pulse_control("Reload")
        status = _table_values(connector.op("status_out"))
        check(
            "button:Reload",
            controller.sequencer is not None
            and status.get("state") == "ready",
            status,
        )

        set_control("Colorenabled", False)
        check(
            "switch:Colorenabled:off",
            all(
                int(connector.op(f"color_switch_{index}").par.index.eval())
                == 0
                for index in range(1, len(targets) + 1)
            ),
        )
        set_control("Colorenabled", True)
        check(
            "switch:Colorenabled:on",
            all(
                int(connector.op(f"color_switch_{index}").par.index.eval())
                == 1
                for index in range(1, len(targets) + 1)
            ),
        )

        for control_name, (
            output_parameter,
            test_value,
            expected_value,
        ) in COLOR_TESTS.items():
            set_control(control_name, test_value)
            output_family = (
                "color_hsv"
                if control_name in {"Hue", "Saturation", "Value"}
                else "color_level"
            )
            actual_values = [
                getattr(
                    connector.op(f"{output_family}_{index}").par,
                    output_parameter,
                ).eval()
                for index in range(1, len(targets) + 1)
            ]
            check(
                f"slider:{control_name}",
                all(
                    _close_enough(actual, expected_value)
                    for actual in actual_values
                ),
                actual_values,
            )

        for name, value in {
            "Colorenabled": False,
            "Brightness": 0.25,
            "Contrast": 1.5,
            "Gamma": 0.8,
            "Blacklevel": 0.1,
            "Opacity": 0.5,
            "Hue": 45.0,
            "Saturation": 0.5,
            "Value": 1.5,
        }.items():
            set_control(name, value)
        pulse_control("Resetcolor")
        reset_values = {
            name: getattr(control.par, name).eval()
            for name in COLOR_DEFAULTS
        }
        check(
            "button:Resetcolor",
            all(
                bool(reset_values[name]) == bool(expected)
                if isinstance(expected, bool)
                else _close_enough(reset_values[name], expected)
                for name, expected in COLOR_DEFAULTS.items()
            ),
            reset_values,
        )
    finally:
        set_control("Play", False)
        connector.par.Enabled.val = True
        for name, value in control_values.items():
            set_control(name, value)
        controller.seed_salt = seed_state["seed_salt"]
        controller.seed_generation = seed_state["seed_generation"]
        controller.last_streamdiffusion_signature = None
        controller.last_color_signature = None
        project_root.time.frame = timeline_frame
        timeline.par.play.val = timeline_play
        connector.par.Enabled.val = connector_enabled
        if connector_enabled:
            controller.update(float(connector.par.Playheadsec.eval()))
        callbacks.par.active.val = callbacks_active

    report = {
        "project": project_name,
        "controls_exercised": len(CONTROL_STYLES),
        "checks_passed": len(passed),
        "checks_failed": len(failures),
        "failures": failures,
        "state_restored": True,
        "saved": False,
        "model_servers_started": False,
    }
    print("AUDIT_5090_CONTROLS", report)
    if failures:
        raise RuntimeError(
            f"5090 control audit failed {len(failures)} checks: "
            f"{failures}"
        )
    return report


audit_5090_report = audit_5090_controls()
