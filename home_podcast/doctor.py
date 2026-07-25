from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from .config import ProjectConfig
from .parser import discover_story_files


def run_doctor(config: ProjectConfig) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def add(name: str, ok: bool, detail: str, required: bool = True) -> None:
        checks.append({"name": name, "ok": ok, "required": required, "detail": detail})

    files = discover_story_files(config.exports_dir) if config.exports_dir.is_dir() else []
    add(
        "story_exports",
        bool(files),
        f"{len(files)} story Markdown files in {config.exports_dir}"
        if files
        else f"No stories_*.md files found in {config.exports_dir}",
    )
    add(
        "themes",
        config.themes_path.is_file(),
        str(config.themes_path),
    )
    add(
        "show_bible",
        config.show_bible_path.is_file(),
        str(config.show_bible_path),
    )
    add(
        "catalog",
        config.catalog_path.is_file(),
        str(config.catalog_path)
        if config.catalog_path.is_file()
        else "Not created yet; run ingest",
        required=False,
    )
    add(
        "ffmpeg",
        shutil.which("ffmpeg") is not None,
        shutil.which("ffmpeg") or "Not found on PATH",
    )
    add(
        "ffprobe",
        shutil.which("ffprobe") is not None,
        shutil.which("ffprobe") or "Not found on PATH",
    )
    for provider_name in (
        "analysis_provider",
        "script_provider",
        "speech_provider",
        "sound_effects_provider",
    ):
        value = getattr(config, provider_name)
        add(
            provider_name,
            bool(value),
            str(value) if value else "Not selected; required before the pilot stage",
            required=False,
        )
    voices: list[str] = []
    if config.show_bible_path.is_file():
        voices = [
            host["id"]
            for host in config.load_show_bible().get("hosts", [])
            if not host.get("voice_id")
        ]
    add(
        "host_voice_ids",
        not voices,
        "All recurring hosts are cast"
        if not voices
        else f"Uncast hosts: {', '.join(voices)}",
        required=False,
    )
    ingest_check_names = {"story_exports", "themes", "show_bible"}
    return {
        "ready_for_ingest": all(
            check["ok"] for check in checks if check["name"] in ingest_check_names
        ),
        "ready_for_audio_render": all(
            check["ok"]
            for check in checks
            if check["name"] in {"ffmpeg", "ffprobe", "host_voice_ids"}
        ),
        "checks": checks,
    }
