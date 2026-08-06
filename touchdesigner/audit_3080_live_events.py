"""Frame-separated audit of RTX 3080 Parameter Execute callbacks.

TouchDesigner invokes Parameter Execute callbacks after the current script
returns. This audit schedules one control action and its assertion on separate
application frames, then restores the original state. It never saves the
project or starts a StreamDiffusionTD model server.
"""

from pathlib import Path
import re


PROJECT_VARIANT = "3080"
PROJECT_NAME_PATTERN = re.compile(
    r"podcast(?:\.3080)?(?:\.\d+)?\.toe",
    re.IGNORECASE,
)
CONNECTOR_PATH = "/project1/podcast_visualizer"
CONTROL_PATH = f"{CONNECTOR_PATH}/show_control"
CALLBACK_PATH = f"{CONTROL_PATH}/control_callbacks"
EXECUTE_PATH = f"{CONNECTOR_PATH}/execute_callbacks"
RESULTS_KEY = f"recovered_homes_{PROJECT_VARIANT}_live_audit_results"
SNAPSHOT_KEY = f"recovered_homes_{PROJECT_VARIANT}_live_audit_snapshot"
REPORT_KEY = f"recovered_homes_{PROJECT_VARIANT}_live_audit_report"
VALUE_CONTROLS = (
    "Play",
    "Audioenabled",
    "Audiosource",
    "Visualpath",
    "Randomseeds",
    "Crossfadesec",
    "Colorenabled",
    "Brightness",
    "Contrast",
    "Gamma",
    "Blacklevel",
    "Opacity",
    "Hue",
    "Saturation",
    "Value",
)


def _append_check_code(name, expression, detail_expression):
    return (
        f"_results=op({CONTROL_PATH!r}).fetch({RESULTS_KEY!r});"
        f"_passed=bool({expression});"
        "_results.append({"
        f"'check':{name!r},"
        "'passed':_passed,"
        f"'detail':str({detail_expression})"
        "})"
    )


def audit_3080_live_events():
    project_name = Path(str(project.name)).name
    if PROJECT_NAME_PATTERN.fullmatch(project_name) is None:
        raise RuntimeError(
            f"Refusing to audit live events in a non-{PROJECT_VARIANT} "
            f"project: {project_name}. Open the matching project revision first."
        )

    connector = op(CONNECTOR_PATH)
    control = op(CONTROL_PATH)
    callbacks = op(CALLBACK_PATH)
    execute_callbacks = op(EXECUTE_PATH)
    if any(
        operator is None
        for operator in (
            connector,
            control,
            callbacks,
            execute_callbacks,
        )
    ):
        raise RuntimeError(
            f"The {PROJECT_VARIANT} show-control callback network is incomplete."
        )
    if not bool(callbacks.par.active.eval()):
        raise RuntimeError(
            f"The {PROJECT_VARIANT} control callback DAT is inactive."
        )

    controller = execute_callbacks.module.get_controller()
    snapshot = {
        "controls": {
            name: getattr(control.par, name).eval()
            for name in VALUE_CONTROLS
        },
        "connector_enabled": bool(connector.par.Enabled.eval()),
        "timeline_play": bool(op("/local/time").par.play.eval()),
        "timeline_frame": int(op("/project1").time.frame),
        "seed_salt": controller.seed_salt,
        "seed_generation": controller.seed_generation,
    }
    control.store(SNAPSHOT_KEY, snapshot)
    control.store(RESULTS_KEY, [])
    control.store(REPORT_KEY, None)

    next_frame = 1

    def schedule(code, *, frames=1):
        nonlocal next_frame
        run(code, delayFrames=next_frame)
        next_frame += frames

    def action_and_check(
        action,
        name,
        expression,
        detail_expression,
    ):
        schedule(action, frames=2)
        schedule(
            _append_check_code(
                name,
                expression,
                detail_expression,
            ),
            frames=1,
        )

    action_and_check(
        f"op({CONTROL_PATH!r}).par.Play=True",
        "switch:Play:on",
        "op('/local/time').par.play.eval()",
        "op('/local/time').par.play.eval()",
    )
    action_and_check(
        f"op({CONTROL_PATH!r}).par.Play=False",
        "switch:Play:off",
        "not op('/local/time').par.play.eval()",
        "op('/local/time').par.play.eval()",
    )
    action_and_check(
        f"op({CONTROL_PATH!r}).par.Audioenabled=False",
        "switch:Audioenabled:off",
        (
            f"not op({CONNECTOR_PATH!r}).par.Audioenabled.eval() and "
            f"not op({CONNECTOR_PATH!r}).op('audio_out').par.active.eval()"
        ),
        (
            f"(op({CONNECTOR_PATH!r}).par.Audioenabled.eval(),"
            f"op({CONNECTOR_PATH!r}).op('audio_out').par.active.eval())"
        ),
    )
    action_and_check(
        f"op({CONTROL_PATH!r}).par.Audioenabled=True",
        "switch:Audioenabled:on",
        (
            f"op({CONNECTOR_PATH!r}).par.Audioenabled.eval() and "
            f"op({CONNECTOR_PATH!r}).op('audio_out').par.active.eval()"
        ),
        (
            f"(op({CONNECTOR_PATH!r}).par.Audioenabled.eval(),"
            f"op({CONNECTOR_PATH!r}).op('audio_out').par.active.eval())"
        ),
    )
    schedule(f"op({CONTROL_PATH!r}).par.Audioenabled=False", frames=2)
    for source_name, expected_index in (
        ("soundscape", 1),
        ("voices", 0),
    ):
        action_and_check(
            f"op({CONTROL_PATH!r}).par.Audiosource={source_name!r}",
            f"menu:Audiosource:{source_name}",
            (
                f"op({CONNECTOR_PATH!r}).par.Audiosource.eval()"
                f" == {source_name!r} and "
                f"int(op({CONNECTOR_PATH!r}).op("
                "'audiosource_switch').par.index.eval())"
                f" == {expected_index}"
            ),
            (
                f"(op({CONNECTOR_PATH!r}).par.Audiosource.eval(),"
                f"op({CONNECTOR_PATH!r}).op("
                "'audiosource_switch').par.index.eval())"
            ),
        )

    for visual_path, parameter_name in (
        ("human_figures", "Humanfigurejson"),
        ("original", "Scenejson"),
    ):
        action_and_check(
            f"op({CONTROL_PATH!r}).par.Visualpath={visual_path!r}",
            f"menu:Visualpath:{visual_path}",
            (
                f"op({CONNECTOR_PATH!r}).par.Visualpath.eval()"
                f" == {visual_path!r} and "
                f"op({EXECUTE_PATH!r}).module.get_controller().loaded_path"
                f" == op({EXECUTE_PATH!r}).module.get_controller()._resolve_path("
                f"str(getattr(op({CONNECTOR_PATH!r}).par,"
                f"{parameter_name!r}).eval()))"
            ),
            (
                f"(op({CONNECTOR_PATH!r}).par.Visualpath.eval(),"
                f"op({EXECUTE_PATH!r}).module.get_controller().loaded_path)"
            ),
        )

    for enabled, expected in ((False, False), (True, True)):
        action_and_check(
            f"op({CONTROL_PATH!r}).par.Randomseeds={enabled!r}",
            f"switch:Randomseeds:{'on' if enabled else 'off'}",
            (
                f"op({EXECUTE_PATH!r}).module.get_controller()"
                f"._random_seeds_enabled() is {expected!r}"
            ),
            (
                f"op({EXECUTE_PATH!r}).module.get_controller()"
                "._random_seeds_enabled()"
            ),
        )

    for value in (0.0, 30.0):
        action_and_check(
            f"op({CONTROL_PATH!r}).par.Crossfadesec={value!r}",
            f"slider:Crossfadesec:{value:g}",
            (
                f"op({EXECUTE_PATH!r}).module.get_controller()"
                f"._show_control_crossfade_ms()=={round(value * 1000)}"
            ),
            (
                f"op({EXECUTE_PATH!r}).module.get_controller()"
                "._show_control_crossfade_ms()"
            ),
        )

    for enabled, expected_index in ((False, 0), (True, 1)):
        action_and_check(
            f"op({CONTROL_PATH!r}).par.Colorenabled={enabled!r}",
            f"switch:Colorenabled:{'on' if enabled else 'off'}",
            (
                "all(int(op("
                f"{CONNECTOR_PATH!r}"
                ").op(f'color_switch_{_index}').par.index.eval())"
                f"=={expected_index} for _index in (1,2))"
            ),
            (
                "[op("
                f"{CONNECTOR_PATH!r}"
                ").op(f'color_switch_{_index}').par.index.eval()"
                " for _index in (1,2)]"
            ),
        )

    color_tests = (
        ("Brightness", "color_level", "brightness1", 1.25, 1.25),
        ("Contrast", "color_level", "contrast", 1.5, 1.5),
        ("Gamma", "color_level", "gamma1", 1.2, 1.2),
        ("Blacklevel", "color_level", "blacklevel", 0.1, 0.1),
        ("Opacity", "color_level", "opacity", 0.75, 0.75),
        ("Hue", "color_hsv", "hueoffset", -30.0, 330.0),
        (
            "Saturation",
            "color_hsv",
            "saturationmult",
            1.4,
            1.4,
        ),
        ("Value", "color_hsv", "valuemult", 1.3, 1.3),
    )
    for (
        control_name,
        operator_prefix,
        parameter_name,
        test_value,
        expected_value,
    ) in color_tests:
        action_and_check(
            (
                f"op({CONTROL_PATH!r}).par."
                f"{control_name}={test_value!r}"
            ),
            f"slider:{control_name}",
            (
                "all(abs(float(op("
                f"{CONNECTOR_PATH!r}"
                f").op(f'{operator_prefix}_{{_index}}').par."
                f"{parameter_name}.eval())-{expected_value!r})<0.000001 "
                "for _index in (1,2))"
            ),
            (
                "[op("
                f"{CONNECTOR_PATH!r}"
                f").op(f'{operator_prefix}_{{_index}}').par."
                f"{parameter_name}.eval() for _index in (1,2)]"
            ),
        )

    schedule(
        (
            f"op({CONTROL_PATH!r}).store("
            "'recovered_homes_generation_before',"
            f"op({EXECUTE_PATH!r}).module.get_controller().seed_generation"
            f");op({CONTROL_PATH!r}).par.Newseeds.pulse()"
        ),
        frames=2,
    )
    schedule(
        _append_check_code(
            "button:Newseeds",
            (
                f"op({EXECUTE_PATH!r}).module.get_controller()"
                ".seed_generation=="
                f"op({CONTROL_PATH!r}).fetch("
                "'recovered_homes_generation_before')+1"
            ),
            (
                f"op({EXECUTE_PATH!r}).module.get_controller()"
                ".seed_generation"
            ),
        ),
    )

    schedule(
        (
            f"op('/project1').time.frame=120;"
            f"op({CONTROL_PATH!r}).par.Play=True"
        ),
        frames=2,
    )
    action_and_check(
        f"op({CONTROL_PATH!r}).par.Restart.pulse()",
        "button:Restart",
        (
            f"not op({CONTROL_PATH!r}).par.Play.eval() and "
            "not op('/local/time').par.play.eval() and "
            "int(op('/project1').time.frame)==1"
        ),
        (
            f"(op({CONTROL_PATH!r}).par.Play.eval(),"
            "op('/local/time').par.play.eval(),"
            "op('/project1').time.frame)"
        ),
    )
    action_and_check(
        f"op({CONTROL_PATH!r}).par.Reload.pulse()",
        "button:Reload",
        (
            f"op({EXECUTE_PATH!r}).module.get_controller()"
            ".sequencer is not None"
        ),
        (
            f"op({EXECUTE_PATH!r}).module.get_controller()"
            ".loaded_path"
        ),
    )

    schedule(
        (
            f"_control=op({CONTROL_PATH!r});"
            "_control.par.Colorenabled=False;"
            "_control.par.Brightness=0.25;"
            "_control.par.Contrast=1.5;"
            "_control.par.Gamma=0.8;"
            "_control.par.Blacklevel=0.1;"
            "_control.par.Opacity=0.5;"
            "_control.par.Hue=45.0;"
            "_control.par.Saturation=0.5;"
            "_control.par.Value=1.5"
        ),
        frames=2,
    )
    action_and_check(
        f"op({CONTROL_PATH!r}).par.Resetcolor.pulse()",
        "button:Resetcolor",
        (
            f"op({CONTROL_PATH!r}).par.Colorenabled.eval() and "
            f"float(op({CONTROL_PATH!r}).par.Brightness.eval())==1.0 and "
            f"float(op({CONTROL_PATH!r}).par.Contrast.eval())==1.0 and "
            f"float(op({CONTROL_PATH!r}).par.Gamma.eval())==1.0 and "
            f"float(op({CONTROL_PATH!r}).par.Blacklevel.eval())==0.0 and "
            f"float(op({CONTROL_PATH!r}).par.Opacity.eval())==1.0 and "
            f"float(op({CONTROL_PATH!r}).par.Hue.eval())==0.0 and "
            f"float(op({CONTROL_PATH!r}).par.Saturation.eval())==1.0 and "
            f"float(op({CONTROL_PATH!r}).par.Value.eval())==1.0"
        ),
        (
            "[(p.name,p.eval()) for p in "
            f"op({CONTROL_PATH!r}).customPars]"
        ),
    )

    restore_values = (
        f"_control=op({CONTROL_PATH!r});"
        f"_snapshot=_control.fetch({SNAPSHOT_KEY!r});"
        "[(setattr(getattr(_control.par,_name),'val',_value)) "
        "for _name,_value in _snapshot['controls'].items()]"
    )
    schedule(restore_values, frames=3)
    schedule(
        (
            f"_control=op({CONTROL_PATH!r});"
            f"_snapshot=_control.fetch({SNAPSHOT_KEY!r});"
            f"_connector=op({CONNECTOR_PATH!r});"
            f"_controller=op({EXECUTE_PATH!r}).module.get_controller();"
            "_controller.seed_salt=_snapshot['seed_salt'];"
            "_controller.seed_generation=_snapshot['seed_generation'];"
            "_controller.last_streamdiffusion_signature=None;"
            "_controller.last_color_signature=None;"
            "op('/project1').time.frame=_snapshot['timeline_frame'];"
            "op('/local/time').par.play.val=_snapshot['timeline_play'];"
            "_connector.par.Enabled.val=_snapshot['connector_enabled'];"
            "_controller.update(float(_connector.par.Playheadsec.eval()))"
        ),
        frames=2,
    )
    schedule(
        _append_check_code(
            "state:restored",
            (
                f"all(op({CONTROL_PATH!r}).fetch({SNAPSHOT_KEY!r})"
                "['controls'][_name]==getattr("
                f"op({CONTROL_PATH!r}).par,_name).eval() "
                f"for _name in {VALUE_CONTROLS!r})"
            ),
            (
                "[(p.name,p.eval()) for p in "
                f"op({CONTROL_PATH!r}).customPars]"
            ),
        ),
    )
    schedule(
        (
            f"_control=op({CONTROL_PATH!r});"
            f"_results=_control.fetch({RESULTS_KEY!r});"
            "_failures=[_result for _result in _results "
            "if not _result['passed']];"
            "_report={"
            f"'project':{project_name!r},"
            f"'project_variant':{PROJECT_VARIANT!r},"
            f"'controls_exercised':{len(VALUE_CONTROLS) + 4},"
            "'event_checks_passed':len(_results)-len(_failures),"
            "'event_checks_failed':len(_failures),"
            "'failures':_failures,"
            "'state_restored':not any("
            "_failure['check']=='state:restored' "
            "for _failure in _failures),"
            "'saved':False,"
            "'model_servers_started':False"
            "};"
            f"_control.store({REPORT_KEY!r},_report);"
            f"print('AUDIT_{PROJECT_VARIANT}_LIVE_EVENTS',_report)"
        )
    )

    scheduled = {
        "project": project_name,
        "project_variant": PROJECT_VARIANT,
        "controls_scheduled": len(VALUE_CONTROLS) + 4,
        "completion_frame_delay": next_frame,
        "saved": False,
        "model_servers_started": False,
    }
    print(f"AUDIT_{PROJECT_VARIANT}_LIVE_EVENTS_SCHEDULED", scheduled)
    return scheduled


audit_3080_live_events_scheduled = audit_3080_live_events()
