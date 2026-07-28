"""Inspect current 5090 StreamDiffusionTD output without starting servers.

Start exactly one configured StreamDiffusionTD server, wait for it to report
active, then run this script from the TouchDesigner Textport. Saved status
tables can contain telemetry from another machine, so readiness requires a
current output timestamp and non-black local TOP pixels.
"""

from pathlib import Path
import re
import time


PROJECT_NAME_PATTERN = re.compile(
    r"podcast\.5090(?:\.\d+)?\.toe",
    re.IGNORECASE,
)
OUTPUT_TIMESTAMP_PATTERN = re.compile(r"_out_(\d{10})(?:\D|$)")


def _target_paths(connector):
    value = str(connector.par.Streamdiffusionpath.eval()).strip()
    return [
        path.strip()
        for path in re.split(r"[;,\n]+", value)
        if path.strip()
    ] or ["StreamDiffusionTD"]


def _table_values(table):
    if table is None:
        return {}
    values = {}
    for row in range(1, table.numRows):
        key = str(table[row, 0]).strip()
        value = str(table[row, 1]).strip()
        values[key] = value
        values.setdefault(key.replace("-", "_"), value)
    return values


def _output_age_seconds(output_name):
    match = OUTPUT_TIMESTAMP_PATTERN.search(str(output_name))
    if match is None:
        return None
    return max(0.0, time.time() - int(match.group(1)))


def _connection_is_active(local_status, stream_status):
    local_state = str(
        local_status.get("connection_state")
        or local_status.get("stream_state")
        or ""
    ).strip().replace("-", "_").replace(" ", "_").upper()
    legacy_state = str(
        stream_status.get("stream_state", "")
    ).strip().replace("-", "_").replace(" ", "_").upper()
    return (
        local_state in {"STREAM_ACTIVE", "LOCAL_STREAMING", "ONLINE"}
        or legacy_state == "ONLINE"
    ), local_state, legacy_state


def _force_output_cook(target, connector, index):
    """Pull one current frame through out-of-band shared memory."""
    for path in (
        "shmem/output",
        "shmem/select1",
        "shmem/out1",
        "flip_y",
    ):
        operator = target.op(path)
        if operator is not None:
            operator.cook(force=True)
    for path in (f"color_out_{index}", f"null{index}"):
        operator = connector.op(path)
        if operator is not None:
            operator.cook(force=True)


def _pixel_stats(top):
    if top is None:
        return {
            "present": False,
            "shape": None,
            "mean": None,
            "standard_deviation": None,
            "minimum": None,
            "maximum": None,
            "non_black": False,
        }
    pixels = top.numpyArray()
    standard_deviation = float(pixels.std())
    maximum = float(pixels.max())
    return {
        "present": True,
        "shape": tuple(int(value) for value in pixels.shape),
        "mean": float(pixels.mean()),
        "standard_deviation": standard_deviation,
        "minimum": float(pixels.min()),
        "maximum": maximum,
        "non_black": maximum > 0.001 and standard_deviation > 0.0001,
    }


def audit_5090_visuals():
    project_name = Path(str(project.name)).name
    if PROJECT_NAME_PATTERN.fullmatch(project_name) is None:
        raise RuntimeError(
            "Refusing to audit visuals in a non-5090 project. Open "
            "podcast.5090.toe or a numbered podcast.5090 revision first. "
            "The 3080 projects are reference files and must remain untouched."
        )

    connector = op("/project1/podcast_visualizer")
    if connector is None:
        raise RuntimeError(
            "Missing /project1/podcast_visualizer in the 5090 project."
        )

    target_reports = []
    for index, target_name in enumerate(
        _target_paths(connector),
        start=1,
    ):
        target = connector.op(target_name)
        if target is None:
            target_reports.append(
                {
                    "target": target_name,
                    "present": False,
                    "ready": False,
                    "reason": "missing target",
                }
            )
            continue

        local_status = _table_values(target.op("local_backend_status"))
        stream_status = _table_values(target.op("stream_osc_data"))
        output_name = (
            stream_status.get("output_name")
            or local_status.get("output_name")
            or ""
        )
        output_age_seconds = _output_age_seconds(output_name)
        reported_gpu = local_status.get("gpu_name", "")
        current_status = (
            output_age_seconds is not None
            and re.search(r"\bRTX\s*5090\b", reported_gpu, re.IGNORECASE)
            is not None
        )
        _force_output_cook(target, connector, index)
        color_stats = _pixel_stats(connector.op(f"color_out_{index}"))
        spout_source_stats = _pixel_stats(connector.op(f"null{index}"))
        server_active = bool(target.par.Serveractive.eval())
        stream_active = bool(target.par.Streamactive.eval())
        (
            connection_active,
            local_connection_state,
            legacy_stream_state,
        ) = _connection_is_active(local_status, stream_status)
        operator_errors = str(target.errors()).strip()
        ready = (
            server_active
            and stream_active
            and current_status
            and connection_active
            and color_stats["non_black"]
            and spout_source_stats["non_black"]
            and not operator_errors
        )
        reasons = []
        if not server_active:
            reasons.append("Serveractive is off")
        if not stream_active:
            reasons.append("Streamactive is off")
        if not current_status:
            reasons.append(
                "backend status lacks a current output name or RTX 5090"
            )
        if not connection_active:
            reasons.append(
                "connection state is "
                f"{local_connection_state or legacy_stream_state or 'missing'}"
            )
        if not color_stats["non_black"]:
            reasons.append("color output is black")
        if not spout_source_stats["non_black"]:
            reasons.append("Spout source is black")
        if operator_errors:
            reasons.append(f"operator errors: {operator_errors}")

        target_reports.append(
            {
                "target": target_name,
                "present": True,
                "server_active": server_active,
                "stream_active": stream_active,
                "osc_receive_port": int(target.par.Oscinport.eval()),
                "osc_transmit_port": int(target.par.Oscoutport.eval()),
                "connection_state": local_connection_state,
                "legacy_stream_state": legacy_stream_state,
                "output_name": output_name,
                "output_session_age_seconds": output_age_seconds,
                "current_status": current_status,
                "reported_gpu": reported_gpu,
                "reported_fps": local_status.get("fps", ""),
                "last_error": (
                    local_status.get("last_error")
                    or ""
                ),
                "legacy_last_error": stream_status.get("last_error", ""),
                "operator_errors": operator_errors,
                "color_output": color_stats,
                "spout_source": spout_source_stats,
                "ready": ready,
                "reasons": reasons,
            }
        )

    ready_targets = [
        report["target"]
        for report in target_reports
        if report.get("ready")
    ]
    report = {
        "project": project_name,
        "ready_targets": ready_targets,
        "targets": target_reports,
        "saved": False,
        "model_servers_started": False,
        "model_servers_stopped": False,
    }
    print("AUDIT_5090_VISUALS", report)
    if not ready_targets:
        raise RuntimeError(
            "No configured 5090 visual target has current, non-black output. "
            f"Details: {target_reports}"
        )
    return report


audit_5090_visual_report = audit_5090_visuals()
