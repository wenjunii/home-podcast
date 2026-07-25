from __future__ import annotations

import json
import os
import shutil
import subprocess
import wave
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import ProjectConfig
from .providers import ElevenLabsSoundEffectsClient


def generate_sound_effect_jobs(
    config: ProjectConfig,
    jobs_path: Path,
    *,
    execute: bool = False,
    max_credits: float | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    provider = config.sound_effects_provider
    if not provider:
        raise ValueError("sound_effects_provider is not configured")
    client = ElevenLabsSoundEffectsClient.from_config(provider)
    jobs = _read_jsonl(jobs_path)
    if limit is not None:
        jobs = jobs[: max(0, limit)]
    _validate_jobs(jobs, client.model)

    cached_jobs = [job for job in jobs if _valid_wav(Path(job["output_audio"]))]
    pending_jobs = [job for job in jobs if job not in cached_jobs]
    recoverable_jobs = [job for job in pending_jobs if _raw_path(job).is_file()]
    paid_jobs = [job for job in pending_jobs if job not in recoverable_jobs]
    credits_per_second = float(provider.get("credits_per_second", 11))
    pending_seconds = sum(
        float(job["generation_duration_ms"]) / 1000 for job in paid_jobs
    )
    estimated_credits = round(pending_seconds * credits_per_second, 2)
    report: dict[str, Any] = {
        "jobs": len(jobs),
        "cached": len(cached_jobs),
        "pending": len(pending_jobs),
        "recoverable_from_raw_cache": len(recoverable_jobs),
        "api_calls_pending": len(paid_jobs),
        "pending_generation_seconds": round(pending_seconds, 3),
        "estimated_credits": estimated_credits,
        "credits_per_second": credits_per_second,
        "execution_requested": execute,
        "generated": 0,
        "recovered_from_raw_cache": 0,
        "failed": 0,
        "remaining": len(pending_jobs),
        "failures": [],
    }
    if not execute or not pending_jobs:
        return report
    if paid_jobs and max_credits is None:
        raise ValueError("Paid generation requires --max-credits")
    if paid_jobs and max_credits is not None and max_credits < estimated_credits:
        raise ValueError(
            f"Pending jobs estimate {estimated_credits:g} credits, exceeding "
            f"--max-credits {max_credits:g}"
        )
    if paid_jobs and not os.environ.get(client.api_key_env):
        raise RuntimeError(
            f"Missing {client.api_key_env}; provide it as an environment variable"
        )
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg must be installed and available on PATH")

    failure_path = jobs_path.with_name(f"{jobs_path.stem}-failures.jsonl")
    completed_pending = 0
    for job in pending_jobs:
        cue_id = str(job["cue_id"])
        output_path = Path(job["output_audio"]).expanduser().resolve()
        raw_path = _raw_path(job)
        metadata_path = output_path.with_suffix(".generation.json")
        try:
            if raw_path.is_file():
                _normalize_to_wav(ffmpeg, raw_path, output_path)
                report["recovered_from_raw_cache"] += 1
            else:
                response = client.generate(
                    str(job["prompt"]),
                    duration_seconds=float(job["generation_duration_ms"]) / 1000,
                    loop=bool(job["loop"]),
                )
                _write_bytes_atomic(raw_path, response.audio)
                _normalize_to_wav(ffmpeg, raw_path, output_path)
                _write_json_atomic(
                    metadata_path,
                    {
                        "contract_version": 1,
                        "episode_id": job["episode_id"],
                        "cue_id": cue_id,
                        "provider": job["provider"],
                        "model": job["model"],
                        "cache_key": job["cache_key"],
                        "generation_duration_ms": job["generation_duration_ms"],
                        "loop": job["loop"],
                        "content_type": response.content_type,
                        "request_id": response.request_id,
                        "character_cost": response.character_cost,
                        "generated_at": datetime.now(timezone.utc).isoformat(),
                    },
                )
                report["generated"] += 1
            completed_pending += 1
            print(
                f"[{completed_pending}/{len(pending_jobs)}] generated SFX {cue_id}",
                flush=True,
            )
        except Exception as error:
            report["failed"] = 1
            report["failures"] = [
                {
                    "cue_id": cue_id,
                    "error": f"{type(error).__name__}: {error}",
                }
            ]
            print(
                f"[{completed_pending + 1}/{len(pending_jobs)}] "
                f"FAILED SFX {cue_id}: {error}",
                flush=True,
            )
            break

    report["remaining"] = len(pending_jobs) - completed_pending
    with failure_path.open("w", encoding="utf-8", newline="\n") as handle:
        for failure in report["failures"]:
            handle.write(json.dumps(failure, ensure_ascii=False) + "\n")
    report["failure_log"] = str(failure_path)
    report["completed"] = report["failed"] == 0 and report["remaining"] == 0
    return report


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    with path.open(encoding="utf-8-sig") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"Line {line_number}: expected a JSON object")
            jobs.append(value)
    return jobs


def _validate_jobs(jobs: list[dict[str, Any]], configured_model: str) -> None:
    cue_ids: set[str] = set()
    for index, job in enumerate(jobs, start=1):
        label = f"SFX job {index}"
        for field in (
            "episode_id",
            "cue_id",
            "provider",
            "model",
            "prompt",
            "cache_key",
            "output_audio",
        ):
            if not isinstance(job.get(field), str) or not job[field].strip():
                raise ValueError(f"{label}.{field} must be a non-empty string")
        cue_id = job["cue_id"]
        if cue_id in cue_ids:
            raise ValueError(f"Duplicate SFX cue_id {cue_id!r}")
        cue_ids.add(cue_id)
        if job["provider"] not in {"elevenlabs", "elevenlabs_sound_effects"}:
            raise ValueError(f"{label} is not an ElevenLabs job")
        if job["model"] != configured_model:
            raise ValueError(
                f"{label} uses model {job['model']!r}; configured model is "
                f"{configured_model!r}"
            )
        duration_ms = job.get("generation_duration_ms")
        if not isinstance(duration_ms, int) or not 500 <= duration_ms <= 30000:
            raise ValueError(
                f"{label}.generation_duration_ms must be from 500 to 30000"
            )
        if not isinstance(job.get("loop"), bool):
            raise ValueError(f"{label}.loop must be true or false")


def _raw_path(job: dict[str, Any]) -> Path:
    return Path(job["output_audio"]).expanduser().resolve().with_suffix(
        ".response.mp3"
    )


def _normalize_to_wav(ffmpeg: str, raw_path: Path, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(".tmp.wav")
    try:
        subprocess.run(
            [
                ffmpeg,
                "-y",
                "-loglevel",
                "error",
                "-i",
                str(raw_path),
                "-ar",
                "48000",
                "-ac",
                "2",
                "-c:a",
                "pcm_s16le",
                "-f",
                "wav",
                str(temporary),
            ],
            check=True,
        )
        if not _valid_wav(temporary):
            raise RuntimeError("Normalized ElevenLabs response is not a valid WAV file")
        temporary.replace(output_path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _valid_wav(path: Path) -> bool:
    if not path.is_file():
        return False
    try:
        with wave.open(str(path), "rb") as audio:
            return (
                audio.getnframes() > 0
                and audio.getframerate() == 48000
                and audio.getnchannels() == 2
                and audio.getsampwidth() == 2
            )
    except (EOFError, wave.Error):
        return False


def _write_bytes_atomic(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(value)
    temporary.replace(path)


def _write_json_atomic(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
