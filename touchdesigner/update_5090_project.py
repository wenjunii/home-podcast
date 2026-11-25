"""Maintain the connector in a local 5090 TouchDesigner project.

The .26 audio-overlay edition is verified in place, never rebound. Legacy
5090 editions retain their own update paths. No saves or model-server starts.
"""

from pathlib import Path
import re
from runpy import run_path


PROJECT_NAME_PATTERN = re.compile(
    r"podcast\.5090(?:\.([1-9]\d*))?\.toe",
    re.IGNORECASE,
)
LEGACY_PLAYLIST = "work/storytelling-real-december/continuous-image-hold-136-3080-2026-10-30/playlist.json"
MCP_TEST_FOLDER = "home-podcast-5090-mcp-test"
MCP_TEST_MARKER = "/rh_podcast_5090_27_mcp_guard"


def update_5090_project():
    project_name = Path(str(project.name)).name
    match = PROJECT_NAME_PATTERN.fullmatch(project_name)
    if match is None:
        raise RuntimeError(
            "Refusing to update a non-5090 project. Open podcast.5090.toe "
            "or a numbered podcast.5090 revision first. The 3080 projects "
            "are reference files and must remain untouched."
        )

    revision = int(match[1]) if match[1] else 0
    project_root = Path(project.folder).resolve()
    if project_root.name.casefold() == MCP_TEST_FOLDER or op(MCP_TEST_MARKER) is not None:
        raise RuntimeError(
            "Refusing to update the isolated MCP test copy. Use "
            "touchdesigner.verify_5090_mcp from the production checkout instead."
        )
    connector = op("/project1/podcast_visualizer")
    if connector is None:
        raise RuntimeError(
            "Missing /project1/podcast_visualizer in the 5090 project."
        )
    if revision >= 26:
        # Never run legacy writers on .26 or later, even when the manifest
        # parameter is missing, stale or already points back at .40.
        helper = project_root / "touchdesigner/verify_5090_audio_overlay.py"
        if not helper.is_file():
            raise RuntimeError("Missing 5090 audio-overlay verifier; sync the scripts before continuing")
        report = run_path(str(helper))["verify_native_overlay"](
            project_root, project_name, str(app.build), connector,
        )
        print("VERIFIED_5090_AUDIO_OVERLAY", report)
        return report

    playlist = getattr(connector.par, "Playlistmanifest", None)
    saved_playlist = (
        str(playlist.eval()).strip().replace("\\", "/").casefold()
        if playlist is not None else ""
    )
    if revision == 25:
        if not (saved_playlist == LEGACY_PLAYLIST or saved_playlist.endswith("/" + LEGACY_PLAYLIST)):
            raise RuntimeError(
                "The .25 receiver must be bound to its original canonical playlist; "
                "no fallback updater will run"
            )
        # TD exposes these context objects implicitly; they need not appear
        # in globals(). Pass them explicitly into the isolated helper scope.
        namespace = dict(globals(), project=project, app=app, op=op)
        exec((project_root / "touchdesigner/rebind_5090_136.py").read_text(encoding="utf-8"), namespace)
        return {"project": project_name, "edition": "canonical-136", "saved": False,
                "model_servers_started": False, "live_generation": False}
    if saved_playlist:
        raise RuntimeError("This legacy 5090 project has an edition playlist; refusing to run the pilot updater")
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
    control.par.Runtimeprofile = "5090_live"
    # Model processes remain opt-in. Selecting the capable profile does not
    # enable generation or start Ollama/Qwen3-TTS during project maintenance.
    control.par.Livevariations = False
    connector.par.Runtimeprofile = "5090_live"
    control.op("control_callbacks").module._write_live_control()
    report = {
        "project": project_name,
        "project_root": str(project_root),
        "audio_source_menu": list(control.par.Audiosource.menuNames),
        "audio_source": str(control.par.Audiosource.eval()),
        "visual_path_menu": list(control.par.Visualpath.menuNames),
        "visual_path": str(control.par.Visualpath.eval()),
        "runtime_profile": str(control.par.Runtimeprofile.eval()),
        "live_variations": bool(control.par.Livevariations.eval()),
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
