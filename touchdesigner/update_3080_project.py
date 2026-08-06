"""Refresh the tracked connector only in the active RTX 3080 project.

Run from the TouchDesigner Textport with ``podcast.toe``, a numbered
``podcast.<revision>.toe``, or an explicit ``podcast.3080`` revision open. It
does not save the .toe automatically or start model servers.
"""

from pathlib import Path
import re


PROJECT_VARIANT = "3080"
PROJECT_NAME_PATTERN = re.compile(
    r"podcast(?:\.3080)?(?:\.\d+)?\.toe",
    re.IGNORECASE,
)


def update_3080_project():
    project_name = Path(str(project.name)).name
    if PROJECT_NAME_PATTERN.fullmatch(project_name) is None:
        raise RuntimeError(
            f"Refusing to update a non-{PROJECT_VARIANT} project: "
            f"{project_name}. Open the matching project revision first."
        )

    project_root = Path(project.folder).resolve()
    connector = op("/project1/podcast_visualizer")
    if connector is None:
        raise RuntimeError(
            f"Missing /project1/podcast_visualizer in the {PROJECT_VARIANT} project."
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
            f"The {PROJECT_VARIANT} StreamDiffusion operator list changed unexpectedly."
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
                f"Missing required {PROJECT_VARIANT} connection "
                f"{source_name} -> {target_name}."
            )

    control = connector.op("show_control")
    report = {
        "project": project_name,
        "project_variant": PROJECT_VARIANT,
        "project_root": str(project_root),
        "audio_source_menu": list(control.par.Audiosource.menuNames),
        "audio_source": str(control.par.Audiosource.eval()),
        "visual_path_menu": list(control.par.Visualpath.menuNames),
        "visual_path": str(control.par.Visualpath.eval()),
        "original_scene_json": str(connector.par.Scenejson.eval()),
        "human_figure_scene_json": str(connector.par.Humanfigurejson.eval()),
        "streamdiffusion_paths": streamdiffusion_paths,
        "spout_outputs": [
            connector.op("syphonspoutout1").path,
            connector.op("syphonspoutout2").path,
        ],
        "saved": False,
        "model_servers_started": False,
    }
    connector.current = True
    print(f"UPDATED_{PROJECT_VARIANT}_PROJECT", report)
    return report


updated_3080_project = update_3080_project()
