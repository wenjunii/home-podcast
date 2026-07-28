"""Refresh the tracked connector only in a local 5090 TouchDesigner project.

Run this script from the TouchDesigner Textport with ``podcast.5090.toe`` or
one of its numbered revisions open.  It refuses to run against a 3080 project,
does not save the .toe automatically, and does not start model servers.
"""

from pathlib import Path
import re


PROJECT_NAME_PATTERN = re.compile(
    r"podcast\.5090(?:\.\d+)?\.toe",
    re.IGNORECASE,
)


def update_5090_project():
    project_name = Path(str(project.name)).name
    if PROJECT_NAME_PATTERN.fullmatch(project_name) is None:
        raise RuntimeError(
            "Refusing to update a non-5090 project. Open podcast.5090.toe "
            "or a numbered podcast.5090 revision first. The 3080 projects "
            "are reference files and must remain untouched."
        )

    project_root = Path(project.folder).resolve()
    connector = op("/project1/podcast_visualizer")
    if connector is None:
        raise RuntimeError(
            "Missing /project1/podcast_visualizer in the 5090 project."
        )
    streamdiffusion_paths = str(connector.par.Streamdiffusionpath.eval())

    exec(
        (
            project_root
            / "touchdesigner"
            / "install_show_control.py"
        ).read_text(encoding="utf-8"),
        globals(),
    )
    exec(
        (
            project_root
            / "touchdesigner"
            / "rebind_project_paths.py"
        ).read_text(encoding="utf-8"),
        globals(),
    )

    connector = op("/project1/podcast_visualizer")
    if str(connector.par.Streamdiffusionpath.eval()) != streamdiffusion_paths:
        raise RuntimeError(
            "The 5090 StreamDiffusion operator list changed unexpectedly."
        )

    required_connections = (
        ("voices_only_audio", "audiosource_switch"),
        ("soundscape_audio", "audiosource_switch"),
        ("audiosource_switch", "audio_out"),
        ("null1", "syphonspoutout1"),
        ("null2", "syphonspoutout2"),
    )
    for source_name, target_name in required_connections:
        source = connector.op(source_name)
        target = connector.op(target_name)
        if source is None or target is None or target not in source.outputs:
            raise RuntimeError(
                f"Missing required 5090 connection "
                f"{source_name} -> {target_name}."
            )

    control = connector.op("show_control")
    report = {
        "project": project_name,
        "project_root": str(project_root),
        "audio_source_menu": list(control.par.Audiosource.menuNames),
        "audio_source": str(control.par.Audiosource.eval()),
        "streamdiffusion_paths": streamdiffusion_paths,
        "spout_outputs": [
            connector.op("syphonspoutout1").path,
            connector.op("syphonspoutout2").path,
        ],
        "saved": False,
        "model_servers_started": False,
    }
    connector.current = True
    print("UPDATED_5090_PROJECT", report)
    return report


updated_5090_project = update_5090_project()
