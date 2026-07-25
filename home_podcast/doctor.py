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
        "voice_roster",
        config.voice_roster_path.is_file(),
        str(config.voice_roster_path),
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
        "dialogue_provider",
        "sound_effects_provider",
    ):
        value = getattr(config, provider_name)
        add(
            provider_name,
            bool(value),
            str(value) if value else "Not selected; required before the pilot stage",
            required=False,
        )
    roster_roles: list[dict[str, Any]] = []
    if config.voice_roster_path.is_file():
        roster_roles = config.load_voice_roster().get("roles", [])
    uncast_roles = [
        str(role.get("id", "unknown"))
        for role in roster_roles
        if not isinstance(role.get("candidates"), list)
        or len(role["candidates"]) < 2
    ]
    add(
        "rotating_voice_roster",
        len(roster_roles) == 3 and not uncast_roles,
        "Three rotating host roles have at least two candidates each"
        if len(roster_roles) == 3 and not uncast_roles
        else f"Incomplete rotating roles: {', '.join(uncast_roles) or 'unknown'}",
        required=False,
    )
    role_accents = {
        str(role.get("id", "unknown")): {
            str(candidate.get("accent", "")).strip().casefold()
            for candidate in role.get("candidates", [])
            if isinstance(candidate, dict)
            and str(candidate.get("accent", "")).strip()
        }
        for role in roster_roles
        if isinstance(role, dict)
    }
    all_accents = set().union(*role_accents.values()) if role_accents else set()
    accent_ready = (
        len(role_accents) == 3
        and all(len(accents) >= 2 for accents in role_accents.values())
        and len(all_accents) >= 3
    )
    add(
        "accent_aware_voice_roster",
        accent_ready,
        (
            f"{len(all_accents)} verified accents; every host role can rotate "
            "across at least two"
        )
        if accent_ready
        else "Accent rotation needs three verified accents and two per host role",
        required=False,
    )
    ingest_check_names = {"story_exports", "themes", "show_bible", "voice_roster"}
    return {
        "ready_for_ingest": all(
            check["ok"] for check in checks if check["name"] in ingest_check_names
        ),
        "ready_for_audio_render": all(
            check["ok"]
            for check in checks
            if check["name"]
            in {
                "ffmpeg",
                "ffprobe",
                "rotating_voice_roster",
                "accent_aware_voice_roster",
            }
        ),
        "checks": checks,
    }
