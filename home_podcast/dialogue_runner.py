from __future__ import annotations

import hashlib
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .casting import load_episode_cast
from .config import ProjectConfig
from .providers import ElevenLabsDialogueClient
from .script import render_tts_text
from .tts_runner import (
    _normalize_to_wav,
    _parse_character_cost,
    _valid_wav,
    _write_bytes_atomic,
    _write_json_atomic,
)

EPISODE_DIALOGUE_CHARACTER_LIMIT = 1900


def prepare_dialogue_audition_jobs(
    config: ProjectConfig,
    audition_path: Path,
    cast_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    provider = config.dialogue_provider
    if not provider:
        raise ValueError("dialogue_provider is not configured")
    if provider.get("type") != "elevenlabs_dialogue":
        raise ValueError("dialogue_provider must use elevenlabs_dialogue")
    model = str(provider.get("model", "eleven_v3"))
    if model != "eleven_v3":
        raise ValueError("Text to Dialogue requires the eleven_v3 model")

    audition = _load_object(audition_path)
    audition_id = _required_string(audition, "episode_id")
    cast_episode_id = _required_string(audition, "cast_episode_id")
    episode_cast = load_episode_cast(cast_path, episode_id=cast_episode_id)
    voices = {
        host["id"]: {
            "voice_id": host["voice_id"],
            "display_name": host["display_name"],
            "accent": host["accent"],
        }
        for host in episode_cast["hosts"]
    }
    segments = audition.get("segments")
    if not isinstance(segments, list) or len(segments) < 2:
        raise ValueError("Dialogue audition needs at least two segments")

    dialogue_inputs = []
    segment_ids: set[str] = set()
    for index, segment in enumerate(segments, start=1):
        if not isinstance(segment, dict):
            raise ValueError(f"Dialogue segment {index} must be an object")
        segment_id = _required_string(segment, "segment_id")
        if segment_id in segment_ids:
            raise ValueError(f"Duplicate dialogue segment_id {segment_id!r}")
        segment_ids.add(segment_id)
        speaker = _required_string(segment, "speaker")
        if speaker not in voices:
            raise ValueError(f"Unknown dialogue speaker {speaker!r}")
        text = render_tts_text(
            _required_string(segment, "text"),
            segment.get("pronunciation", {}),
            segment.get("delivery", {}),
            supports_audio_tags=True,
        )
        dialogue_inputs.append(
            {
                "segment_id": segment_id,
                "speaker": speaker,
                "display_name": voices[speaker]["display_name"],
                "voice_id": voices[speaker]["voice_id"],
                "accent": voices[speaker]["accent"],
                "text": text,
            }
        )
    total_characters = sum(len(item["text"]) for item in dialogue_inputs)
    if total_characters > 2000:
        raise ValueError(
            "Dialogue audition exceeds the reliable 2000-character request limit"
        )

    variants = audition.get("variants")
    if not isinstance(variants, list) or not variants:
        raise ValueError("Dialogue audition needs at least one settings variant")
    jobs = []
    variant_ids: set[str] = set()
    for variant in variants:
        if not isinstance(variant, dict):
            raise ValueError("Dialogue audition variants must be objects")
        variant_id = _required_string(variant, "id")
        if variant_id in variant_ids:
            raise ValueError(f"Duplicate dialogue variant {variant_id!r}")
        variant_ids.add(variant_id)
        settings = variant.get("settings", {})
        _validate_settings(settings)
        cache_payload = {
            "contract_version": 1,
            "audition_id": audition_id,
            "variant": variant_id,
            "provider": provider["type"],
            "model": model,
            "language_code": provider.get("language_code"),
            "output_format": provider.get("output_format"),
            "settings": settings,
            "inputs": dialogue_inputs,
        }
        cache_key = hashlib.sha256(
            json.dumps(
                cache_payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        output_audio = config.audio_dir / "cache" / "dialogue" / f"{cache_key}.wav"
        preview_mp3 = (
            config.work_dir
            / "tts"
            / audition_id
            / f"{audition_id}-{variant_id}.mp3"
        )
        jobs.append(
            {
                **cache_payload,
                "seed": int(cache_key[:8], 16),
                "cache_key": cache_key,
                "total_characters": total_characters,
                "output_audio": str(output_audio),
                "preview_mp3": str(preview_mp3),
                "cached": _valid_wav(output_audio),
            }
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        for job in jobs:
            handle.write(json.dumps(job, ensure_ascii=False) + "\n")
    return {
        "output": str(output_path),
        "audition_id": audition_id,
        "segments": len(dialogue_inputs),
        "variants": len(jobs),
        "characters_per_variant": total_characters,
        "total_characters": total_characters * len(jobs),
    }


def generate_dialogue_audition_jobs(
    config: ProjectConfig,
    jobs_path: Path,
    *,
    execute: bool = False,
    max_credits: float | None = None,
    variant: str | None = None,
) -> dict[str, Any]:
    provider = config.dialogue_provider
    if not provider:
        raise ValueError("dialogue_provider is not configured")
    client = ElevenLabsDialogueClient.from_config(provider)
    jobs = _read_jsonl(jobs_path)
    if variant is not None:
        jobs = [job for job in jobs if job.get("variant") == variant]
        if not jobs:
            raise ValueError(f"No dialogue job found for variant {variant!r}")
    _validate_jobs(jobs, client.model)

    cached_jobs = [job for job in jobs if _valid_wav(Path(job["output_audio"]))]
    pending_jobs = [job for job in jobs if job not in cached_jobs]
    recoverable_jobs = [job for job in pending_jobs if _raw_path(job).is_file()]
    paid_jobs = [job for job in pending_jobs if job not in recoverable_jobs]
    pending_characters = sum(int(job["total_characters"]) for job in paid_jobs)
    credits_per_character = float(provider.get("credits_per_character", 1))
    usd_per_thousand_characters = float(
        provider.get("usd_per_thousand_characters", 0.10)
    )
    estimated_credits = round(pending_characters * credits_per_character, 2)
    report: dict[str, Any] = {
        "jobs": len(jobs),
        "variants": [job["variant"] for job in jobs],
        "cached": len(cached_jobs),
        "pending": len(pending_jobs),
        "recoverable_from_raw_cache": len(recoverable_jobs),
        "api_calls_pending": len(paid_jobs),
        "pending_characters": pending_characters,
        "estimated_credits": estimated_credits,
        "estimated_usd": round(
            pending_characters / 1000 * usd_per_thousand_characters,
            4,
        ),
        "execution_requested": execute,
        "generated": 0,
        "recovered_from_raw_cache": 0,
        "actual_character_cost": 0,
        "failed": 0,
        "remaining": len(pending_jobs),
        "failures": [],
        "previews": [str(job["preview_mp3"]) for job in jobs],
    }
    if not execute or not pending_jobs:
        return report
    if paid_jobs and max_credits is None:
        raise ValueError("Paid dialogue generation requires --max-credits")
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

    completed_pending = 0
    for job in pending_jobs:
        output_audio = Path(job["output_audio"]).resolve()
        raw_path = _raw_path(job)
        preview_path = Path(job["preview_mp3"]).resolve()
        metadata_path = output_audio.with_suffix(".generation.json")
        try:
            if raw_path.is_file():
                _normalize_to_wav(ffmpeg, raw_path, output_audio)
                report["recovered_from_raw_cache"] += 1
            else:
                response = client.generate(
                    [
                        {
                            "text": item["text"],
                            "voice_id": item["voice_id"],
                        }
                        for item in job["inputs"]
                    ],
                    settings=job["settings"],
                    seed=int(job["seed"]),
                )
                _write_bytes_atomic(raw_path, response.audio)
                _normalize_to_wav(ffmpeg, raw_path, output_audio)
                report["actual_character_cost"] += _parse_character_cost(
                    response.character_cost
                )
                _write_json_atomic(
                    metadata_path,
                    {
                        "contract_version": 1,
                        "audition_id": job["audition_id"],
                        "variant": job["variant"],
                        "provider": job["provider"],
                        "model": job["model"],
                        "settings": job["settings"],
                        "cache_key": job["cache_key"],
                        "input_characters": job["total_characters"],
                        "content_type": response.content_type,
                        "request_id": response.request_id,
                        "character_cost": response.character_cost,
                        "generated_at": datetime.now(timezone.utc).isoformat(),
                    },
                )
                report["generated"] += 1
            preview_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(raw_path, preview_path)
            completed_pending += 1
            print(
                f"[{completed_pending}/{len(pending_jobs)}] generated dialogue "
                f"{job['variant']}",
                flush=True,
            )
        except Exception as error:
            report["failed"] = 1
            report["failures"] = [
                {
                    "variant": job["variant"],
                    "error": f"{type(error).__name__}: {error}",
                }
            ]
            break

    report["actual_character_cost"] = round(report["actual_character_cost"], 2)
    report["remaining"] = len(pending_jobs) - completed_pending
    report["completed"] = report["failed"] == 0 and report["remaining"] == 0
    return report


def prepare_dialogue_episode_jobs(
    config: ProjectConfig,
    script_path: Path,
    cast_path: Path,
    performance_path: Path,
    output_path: Path,
    *,
    variant: str,
) -> dict[str, Any]:
    provider = config.dialogue_provider
    if not provider:
        raise ValueError("dialogue_provider is not configured")
    if provider.get("type") != "elevenlabs_dialogue":
        raise ValueError("dialogue_provider must use elevenlabs_dialogue")
    model = str(provider.get("model", "eleven_v3"))
    if model != "eleven_v3":
        raise ValueError("Text to Dialogue requires the eleven_v3 model")

    script = _load_object(script_path)
    episode_id = _required_string(script, "episode_id")
    episode_cast = load_episode_cast(cast_path, episode_id=episode_id)
    voices = {
        host["id"]: {
            "voice_id": host["voice_id"],
            "display_name": host["display_name"],
            "accent": host["accent"],
        }
        for host in episode_cast["hosts"]
    }
    performance = _load_object(performance_path)
    variants = performance.get("variants")
    if not isinstance(variants, list):
        raise ValueError("Dialogue performance variants must be an array")
    selected = next(
        (
            item
            for item in variants
            if isinstance(item, dict) and item.get("id") == variant
        ),
        None,
    )
    if selected is None:
        raise ValueError(f"Dialogue performance has no variant {variant!r}")
    settings = selected.get("settings", {})
    _validate_settings(settings)

    segments = script.get("segments")
    if not isinstance(segments, list) or not segments:
        raise ValueError("Episode script needs at least one segment")
    inputs: list[dict[str, Any]] = []
    segment_ids: set[str] = set()
    for index, segment in enumerate(segments, start=1):
        if not isinstance(segment, dict):
            raise ValueError(f"Script segment {index} must be an object")
        segment_id = _required_string(segment, "segment_id")
        if segment_id in segment_ids:
            raise ValueError(f"Duplicate dialogue segment_id {segment_id!r}")
        segment_ids.add(segment_id)
        speaker = _required_string(segment, "speaker")
        if speaker not in voices:
            raise ValueError(f"Unknown dialogue speaker {speaker!r}")
        spoken_text = _required_string(segment, "text")
        tts_text = render_tts_text(
            spoken_text,
            segment.get("pronunciation", {}),
            segment.get("delivery", {}),
            supports_audio_tags=True,
        )
        if len(tts_text) > EPISODE_DIALOGUE_CHARACTER_LIMIT:
            raise ValueError(
                f"Dialogue segment {segment_id!r} alone exceeds "
                f"{EPISODE_DIALOGUE_CHARACTER_LIMIT} characters"
            )
        inputs.append(
            {
                "segment_id": segment_id,
                "speaker": speaker,
                "display_name": voices[speaker]["display_name"],
                "voice_id": voices[speaker]["voice_id"],
                "accent": voices[speaker]["accent"],
                "text": spoken_text,
                "tts_text": tts_text,
                "source_story_ids": segment.get("source_story_ids", []),
                "kind": segment.get("kind", "host_dialogue"),
            }
        )

    chunks = _chunk_episode_inputs(inputs, EPISODE_DIALOGUE_CHARACTER_LIMIT)
    jobs: list[dict[str, Any]] = []
    for chunk_number, chunk_inputs in enumerate(chunks, start=1):
        chunk_id = f"chunk-{chunk_number:03d}"
        total_characters = sum(len(item["tts_text"]) for item in chunk_inputs)
        cache_payload = {
            "contract_version": 1,
            "episode_id": episode_id,
            "chunk_id": chunk_id,
            "provider": provider["type"],
            "model": model,
            "language_code": provider.get("language_code"),
            "output_format": provider.get("output_format"),
            "performance_variant": variant,
            "settings": settings,
            "inputs": chunk_inputs,
        }
        cache_key = hashlib.sha256(
            json.dumps(
                cache_payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        output_audio = config.audio_dir / "cache" / "dialogue" / f"{cache_key}.wav"
        preview_audio = (
            config.work_dir
            / "tts"
            / episode_id
            / "dialogue-chunks"
            / f"{chunk_id}.mp3"
        )
        job = {
            **cache_payload,
            "seed": int(cache_key[:8], 16),
            "cache_key": cache_key,
            "total_characters": total_characters,
            "output_audio": str(output_audio),
            "timestamp_data": str(_timestamp_path_from_audio(output_audio)),
            "preview_audio": str(preview_audio),
        }
        job["cached"] = _complete_episode_dialogue_job(job)
        jobs.append(job)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        for job in jobs:
            handle.write(json.dumps(job, ensure_ascii=False) + "\n")
    total_characters = sum(job["total_characters"] for job in jobs)
    return {
        "output": str(output_path),
        "episode_id": episode_id,
        "segments": len(inputs),
        "chunks": len(jobs),
        "movements": len({_movement_id(item["segment_id"]) for item in inputs}),
        "performance_variant": variant,
        "total_characters": total_characters,
        "maximum_chunk_characters": max(job["total_characters"] for job in jobs),
        "character_limit": EPISODE_DIALOGUE_CHARACTER_LIMIT,
    }


def generate_dialogue_episode_jobs(
    config: ProjectConfig,
    jobs_path: Path,
    *,
    execute: bool = False,
    max_credits: float | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    provider = config.dialogue_provider
    if not provider:
        raise ValueError("dialogue_provider is not configured")
    client = ElevenLabsDialogueClient.from_config(provider)
    all_jobs = _read_jsonl(jobs_path)
    _validate_episode_jobs(all_jobs, client.model)
    jobs = all_jobs
    if limit is not None:
        if limit < 1:
            raise ValueError("limit must be at least 1")
        jobs = jobs[:limit]

    cached_jobs = [job for job in jobs if _complete_episode_dialogue_job(job)]
    pending_jobs = [job for job in jobs if job not in cached_jobs]
    recoverable_jobs = [
        job
        for job in pending_jobs
        if _raw_path(job).is_file() and _valid_timestamp_data(job)
    ]
    paid_jobs = [job for job in pending_jobs if job not in recoverable_jobs]
    pending_characters = sum(int(job["total_characters"]) for job in paid_jobs)
    credits_per_character = float(provider.get("credits_per_character", 1))
    usd_per_thousand_characters = float(
        provider.get("usd_per_thousand_characters", 0.10)
    )
    estimated_credits = round(pending_characters * credits_per_character, 2)
    report: dict[str, Any] = {
        "jobs": len(jobs),
        "episode_jobs": len(all_jobs),
        "episode_id": jobs[0]["episode_id"],
        "performance_variant": jobs[0]["performance_variant"],
        "cached": len(cached_jobs),
        "pending": len(pending_jobs),
        "recoverable_from_raw_cache": len(recoverable_jobs),
        "api_calls_pending": len(paid_jobs),
        "pending_characters": pending_characters,
        "estimated_credits": estimated_credits,
        "estimated_usd": round(
            pending_characters / 1000 * usd_per_thousand_characters,
            4,
        ),
        "execution_requested": execute,
        "generated": 0,
        "recovered_from_raw_cache": 0,
        "actual_character_cost": 0,
        "failed": 0,
        "remaining": len(pending_jobs),
        "failures": [],
        "render_ready": all(
            _complete_episode_dialogue_job(job) for job in all_jobs
        ),
    }
    if not execute or not pending_jobs:
        return report
    if paid_jobs and max_credits is None:
        raise ValueError("Paid dialogue generation requires --max-credits")
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

    completed_pending = 0
    for job in pending_jobs:
        output_audio = Path(job["output_audio"]).resolve()
        raw_path = _raw_path(job)
        timestamp_path = Path(job["timestamp_data"]).resolve()
        preview_path = Path(job["preview_audio"]).resolve()
        metadata_path = output_audio.with_suffix(".generation.json")
        try:
            if raw_path.is_file() and _valid_timestamp_data(job):
                _normalize_to_wav(ffmpeg, raw_path, output_audio)
                report["recovered_from_raw_cache"] += 1
            else:
                response = client.generate_with_timestamps(
                    [
                        {
                            "text": item["tts_text"],
                            "voice_id": item["voice_id"],
                        }
                        for item in job["inputs"]
                    ],
                    settings=job["settings"],
                    seed=int(job["seed"]),
                )
                timestamp_data = {
                    "contract_version": 1,
                    "episode_id": job["episode_id"],
                    "chunk_id": job["chunk_id"],
                    "cache_key": job["cache_key"],
                    "input_count": len(job["inputs"]),
                    "voice_segments": response.voice_segments,
                    "alignment": response.alignment,
                    "normalized_alignment": response.normalized_alignment,
                }
                _validate_timestamp_data(timestamp_data, len(job["inputs"]))
                _write_bytes_atomic(raw_path, response.audio)
                _write_json_atomic(timestamp_path, timestamp_data)
                _normalize_to_wav(ffmpeg, raw_path, output_audio)
                report["actual_character_cost"] += _parse_character_cost(
                    response.character_cost
                )
                _write_json_atomic(
                    metadata_path,
                    {
                        "contract_version": 1,
                        "episode_id": job["episode_id"],
                        "chunk_id": job["chunk_id"],
                        "provider": job["provider"],
                        "model": job["model"],
                        "performance_variant": job["performance_variant"],
                        "settings": job["settings"],
                        "cache_key": job["cache_key"],
                        "input_characters": job["total_characters"],
                        "content_type": response.content_type,
                        "request_id": response.request_id,
                        "character_cost": response.character_cost,
                        "generated_at": datetime.now(timezone.utc).isoformat(),
                    },
                )
                report["generated"] += 1
            preview_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(raw_path, preview_path)
            completed_pending += 1
            print(
                f"[{completed_pending}/{len(pending_jobs)}] generated dialogue "
                f"{job['chunk_id']}",
                flush=True,
            )
        except Exception as error:
            report["failed"] = 1
            report["failures"] = [
                {
                    "chunk_id": job["chunk_id"],
                    "error": f"{type(error).__name__}: {error}",
                }
            ]
            break

    report["actual_character_cost"] = round(report["actual_character_cost"], 2)
    report["remaining"] = len(pending_jobs) - completed_pending
    report["completed"] = report["failed"] == 0 and report["remaining"] == 0
    report["render_ready"] = all(
        _complete_episode_dialogue_job(job) for job in all_jobs
    )
    return report


def _validate_settings(settings: Any) -> None:
    if not isinstance(settings, dict):
        raise ValueError("Dialogue variant settings must be an object")
    allowed = {
        "stability",
        "similarity_boost",
        "style",
        "use_speaker_boost",
        "speed",
    }
    unknown = sorted(set(settings) - allowed)
    if unknown:
        raise ValueError(f"Unsupported dialogue settings: {', '.join(unknown)}")
    for field in ("stability", "similarity_boost", "style"):
        if field in settings and not 0 <= float(settings[field]) <= 1:
            raise ValueError(f"Dialogue setting {field} must be from 0 to 1")
    if "speed" in settings and not 0.7 <= float(settings["speed"]) <= 1.2:
        raise ValueError("Dialogue setting speed must be from 0.7 to 1.2")
    if "use_speaker_boost" in settings and not isinstance(
        settings["use_speaker_boost"], bool
    ):
        raise ValueError("Dialogue setting use_speaker_boost must be boolean")


def _validate_jobs(jobs: list[dict[str, Any]], model: str) -> None:
    if not jobs:
        raise ValueError("Dialogue jobs cannot be empty")
    variants: set[str] = set()
    for job in jobs:
        for field in (
            "audition_id",
            "variant",
            "provider",
            "model",
            "cache_key",
            "output_audio",
            "preview_mp3",
        ):
            _required_string(job, field)
        if job["variant"] in variants:
            raise ValueError(f"Duplicate dialogue variant {job['variant']!r}")
        variants.add(job["variant"])
        if job["provider"] != "elevenlabs_dialogue":
            raise ValueError("Dialogue job provider must be elevenlabs_dialogue")
        if job["model"] != model:
            raise ValueError(
                f"Dialogue job model {job['model']!r} does not match {model!r}"
            )
        inputs = job.get("inputs")
        if not isinstance(inputs, list) or len(inputs) < 2:
            raise ValueError("Dialogue job needs at least two inputs")
        total_characters = sum(len(_required_string(item, "text")) for item in inputs)
        if total_characters != job.get("total_characters"):
            raise ValueError("Dialogue job total_characters is stale")
        if total_characters > 2000:
            raise ValueError("Dialogue job exceeds 2000 characters")
        _validate_settings(job.get("settings"))


def _validate_episode_jobs(jobs: list[dict[str, Any]], model: str) -> None:
    if not jobs:
        raise ValueError("Episode dialogue jobs cannot be empty")
    episode_id = _required_string(jobs[0], "episode_id")
    chunk_ids: set[str] = set()
    segment_ids: set[str] = set()
    performance_variant = _required_string(jobs[0], "performance_variant")
    for job in jobs:
        for field in (
            "episode_id",
            "chunk_id",
            "provider",
            "model",
            "performance_variant",
            "cache_key",
            "output_audio",
            "timestamp_data",
            "preview_audio",
        ):
            _required_string(job, field)
        if job["episode_id"] != episode_id:
            raise ValueError("Episode dialogue jobs must share one episode_id")
        if job["performance_variant"] != performance_variant:
            raise ValueError("Episode dialogue jobs must share one performance variant")
        if job["chunk_id"] in chunk_ids:
            raise ValueError(f"Duplicate dialogue chunk_id {job['chunk_id']!r}")
        chunk_ids.add(job["chunk_id"])
        if job["provider"] != "elevenlabs_dialogue":
            raise ValueError("Dialogue job provider must be elevenlabs_dialogue")
        if job["model"] != model:
            raise ValueError(
                f"Dialogue job model {job['model']!r} does not match {model!r}"
            )
        inputs = job.get("inputs")
        if not isinstance(inputs, list) or not inputs:
            raise ValueError("Episode dialogue job needs at least one input")
        total_characters = 0
        for item in inputs:
            segment_id = _required_string(item, "segment_id")
            if segment_id in segment_ids:
                raise ValueError(f"Duplicate dialogue segment_id {segment_id!r}")
            segment_ids.add(segment_id)
            for field in (
                "speaker",
                "display_name",
                "voice_id",
                "accent",
                "text",
                "tts_text",
            ):
                _required_string(item, field)
            total_characters += len(item["tts_text"])
        if total_characters != job.get("total_characters"):
            raise ValueError("Episode dialogue job total_characters is stale")
        if total_characters > EPISODE_DIALOGUE_CHARACTER_LIMIT:
            raise ValueError(
                "Episode dialogue job exceeds the reliable character limit"
            )
        _validate_settings(job.get("settings"))


def _chunk_episode_inputs(
    inputs: list[dict[str, Any]],
    character_limit: int,
) -> list[list[dict[str, Any]]]:
    chunks: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    current_characters = 0
    current_movement: str | None = None
    for item in inputs:
        item_characters = len(item["tts_text"])
        movement = _movement_id(item["segment_id"])
        movement_changed = current and movement != current_movement
        limit_exceeded = (
            current and current_characters + item_characters > character_limit
        )
        if movement_changed or limit_exceeded:
            chunks.append(current)
            current = []
            current_characters = 0
        current.append(item)
        current_characters += item_characters
        current_movement = movement
    if current:
        chunks.append(current)
    return chunks


def _movement_id(segment_id: str) -> str:
    return segment_id.split("-", 1)[0]


def _timestamp_path_from_audio(output_audio: Path) -> Path:
    return output_audio.with_suffix(".timestamps.json")


def _valid_timestamp_data(job: dict[str, Any]) -> bool:
    try:
        value = json.loads(
            Path(job["timestamp_data"]).read_text(encoding="utf-8")
        )
        _validate_timestamp_data(value, len(job["inputs"]))
        return value.get("cache_key") == job.get("cache_key")
    except (FileNotFoundError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return False


def _validate_timestamp_data(value: Any, input_count: int) -> None:
    if not isinstance(value, dict):
        raise ValueError("Dialogue timestamp data must be an object")
    segments = value.get("voice_segments")
    if not isinstance(segments, list) or not segments:
        raise ValueError("Dialogue timestamp data needs voice segments")
    seen: set[int] = set()
    previous_start = -1.0
    for index, segment in enumerate(segments, start=1):
        if not isinstance(segment, dict):
            raise ValueError(f"Voice segment {index} must be an object")
        input_index = segment.get("dialogue_input_index")
        start = segment.get("start_time_seconds")
        end = segment.get("end_time_seconds")
        if not isinstance(input_index, int) or not 0 <= input_index < input_count:
            raise ValueError(f"Voice segment {index} has invalid dialogue_input_index")
        if not isinstance(start, (int, float)) or not isinstance(end, (int, float)):
            raise ValueError(f"Voice segment {index} needs numeric timestamps")
        if start < 0 or end <= start:
            raise ValueError(f"Voice segment {index} has invalid timestamp range")
        if start < previous_start:
            raise ValueError("Voice segments must be ordered by start time")
        previous_start = float(start)
        seen.add(input_index)
    missing = sorted(set(range(input_count)) - seen)
    if missing:
        raise ValueError(f"Dialogue timestamps omit input indexes: {missing}")


def _complete_episode_dialogue_job(job: dict[str, Any]) -> bool:
    return _valid_wav(Path(job["output_audio"])) and _valid_timestamp_data(job)


def _raw_path(job: dict[str, Any]) -> Path:
    return Path(job["output_audio"]).resolve().with_suffix(".response.mp3")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    values = []
    with path.open(encoding="utf-8-sig") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"Line {line_number}: expected a JSON object")
            values.append(value)
    return values


def _load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return value


def _required_string(value: dict[str, Any], field: str) -> str:
    result = value.get(field)
    if not isinstance(result, str) or not result.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return result
