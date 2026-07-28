"""Export, validate, or restore the pilot's paid SFX responses without a network call."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from home_podcast.config import ProjectConfig
from home_podcast.sfx_runner import generate_sound_effect_jobs
from home_podcast.sound_design import prepare_sfx_jobs


EPISODE_ID = "2013-12.01"
EPISODE_DIR = ROOT / "episodes" / EPISODE_ID
SOUND_DESIGN = EPISODE_DIR / "sound-design-scenes.json"
SCRIPT = EPISODE_DIR / "script.json"
JOBS = ROOT / "work" / "sfx" / f"{EPISODE_ID}-scene-jobs.jsonl"
PORTABLE_DIR = EPISODE_DIR / "audio" / "sfx-responses"
MANIFEST = PORTABLE_DIR / "manifest.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_jobs(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8-sig").splitlines()
        if line.strip()
    ]


def prepare_current_jobs() -> tuple[ProjectConfig, list[dict[str, Any]]]:
    config = ProjectConfig.load(ROOT / "podcast.json")
    provider = config.sound_effects_provider
    if not provider:
        raise ValueError("sound_effects_provider is not configured")
    model = str(provider.get("model", "")).strip()
    if not model:
        raise ValueError("sound_effects_provider.model is not configured")
    prepare_sfx_jobs(
        SOUND_DESIGN,
        SCRIPT,
        JOBS,
        config.audio_dir / "cache" / "sfx",
        provider="elevenlabs",
        model=model,
    )
    return config, read_jobs(JOBS)


def raw_cache_path(job: dict[str, Any]) -> Path:
    return Path(job["output_audio"]).with_suffix(".response.mp3")


def portable_path(job: dict[str, Any]) -> Path:
    return PORTABLE_DIR / f"{job['cache_key']}.response.mp3"


def atomic_copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    try:
        shutil.copy2(source, temporary)
        temporary.replace(destination)
    finally:
        if temporary.exists():
            temporary.unlink()


def export_cache(jobs: list[dict[str, Any]]) -> dict[str, Any]:
    missing = [raw_cache_path(job) for job in jobs if not raw_cache_path(job).is_file()]
    if missing:
        raise FileNotFoundError(
            f"{len(missing)} raw provider responses are missing; first: {missing[0]}"
        )

    PORTABLE_DIR.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    copied = 0
    for job in jobs:
        source = raw_cache_path(job)
        destination = portable_path(job)
        source_hash = sha256(source)
        if not destination.is_file() or sha256(destination) != source_hash:
            atomic_copy(source, destination)
            copied += 1
        records.append(
            {
                "cue_id": job["cue_id"],
                "cache_key": job["cache_key"],
                "filename": destination.name,
                "sha256": source_hash,
                "bytes": source.stat().st_size,
                "generation_duration_ms": job["generation_duration_ms"],
                "loop": job["loop"],
            }
        )

    manifest = {
        "contract_version": 1,
        "episode_id": EPISODE_ID,
        "asset_type": "raw_generated_sound_effect_responses",
        "provider": jobs[0]["provider"],
        "model": jobs[0]["model"],
        "files": records,
    }
    temporary = MANIFEST.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(MANIFEST)
    return {
        "mode": "export",
        "files": len(records),
        "copied": copied,
        "bytes": sum(record["bytes"] for record in records),
        "manifest": str(MANIFEST),
        "network_calls": 0,
    }


def validate_cache(jobs: list[dict[str, Any]]) -> dict[str, Any]:
    if not MANIFEST.is_file():
        raise FileNotFoundError(f"Portable SFX manifest does not exist: {MANIFEST}")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if manifest.get("contract_version") != 1:
        raise ValueError("Unsupported portable SFX manifest contract")
    if manifest.get("episode_id") != EPISODE_ID:
        raise ValueError("Portable SFX manifest belongs to another episode")

    records = manifest.get("files")
    if not isinstance(records, list):
        raise ValueError("Portable SFX manifest files must be an array")
    by_cue = {record.get("cue_id"): record for record in records}
    if len(by_cue) != len(records):
        raise ValueError("Portable SFX manifest contains duplicate cue IDs")
    if set(by_cue) != {job["cue_id"] for job in jobs}:
        raise ValueError("Portable SFX manifest does not match the current cue set")

    total_bytes = 0
    for job in jobs:
        record = by_cue[job["cue_id"]]
        expected = {
            "cache_key": job["cache_key"],
            "generation_duration_ms": job["generation_duration_ms"],
            "loop": job["loop"],
        }
        for field, value in expected.items():
            if record.get(field) != value:
                raise ValueError(
                    f"{job['cue_id']}: portable {field} does not match current job"
                )
        path = PORTABLE_DIR / str(record.get("filename", ""))
        if path.name != f"{job['cache_key']}.response.mp3" or not path.is_file():
            raise FileNotFoundError(f"{job['cue_id']}: portable response is missing")
        if path.stat().st_size != record.get("bytes"):
            raise ValueError(f"{job['cue_id']}: portable response size changed")
        if sha256(path) != record.get("sha256"):
            raise ValueError(f"{job['cue_id']}: portable response hash changed")
        total_bytes += path.stat().st_size

    return {
        "mode": "validate",
        "valid": True,
        "files": len(records),
        "bytes": total_bytes,
        "network_calls": 0,
    }


def restore_cache(
    config: ProjectConfig,
    jobs: list[dict[str, Any]],
) -> dict[str, Any]:
    validation = validate_cache(jobs)
    restored = 0
    for job in jobs:
        source = portable_path(job)
        destination = raw_cache_path(job)
        source_hash = sha256(source)
        if not destination.is_file() or sha256(destination) != source_hash:
            atomic_copy(source, destination)
            restored += 1

    generation = generate_sound_effect_jobs(
        config,
        JOBS,
        execute=True,
        max_credits=0,
    )
    if generation["api_calls_pending"] or generation["failed"] or generation["remaining"]:
        raise RuntimeError(
            "Portable restore did not reconstruct the complete local WAV cache"
        )
    return {
        "mode": "restore",
        "portable_files": validation["files"],
        "raw_responses_restored": restored,
        "normalized_wavs_cached": generation["cached"] + generation["recovered_from_raw_cache"],
        "paid_calls": generation["generated"],
        "network_calls": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Move the pilot's raw generated SFX responses between the ignored "
            "runtime cache and the tracked portable handoff."
        )
    )
    parser.add_argument("mode", choices=("export", "validate", "restore"))
    args = parser.parse_args()

    config, jobs = prepare_current_jobs()
    if not jobs:
        raise ValueError("No current SFX jobs were prepared")
    if args.mode == "export":
        report = export_cache(jobs)
    elif args.mode == "validate":
        report = validate_cache(jobs)
    else:
        report = restore_cache(config, jobs)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
