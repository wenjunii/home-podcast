from __future__ import annotations

import hashlib
import json
import re
import shutil
import wave
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import ProjectConfig
from .storytelling_duration import (
    require_story_audio_frames, story_duration_preflight,
)
from .audio import render_soundscape_audio
from .ambient_mastering import load_settings as load_ambient_settings, master_ambient, sha as ambient_sha
from .providers.qwen_tts import Qwen3TTSLocalRenderer
from .providers.stable_audio import StableAudio3LocalRenderer
from .sound_design import validate_sound_design
from .speech_mastering import load_settings as load_mastering_settings, master_speech
from .storytelling_quality import (
    content_digest, personal_story_findings, require_current_speech_jobs,
)


DEFAULT_LOCAL_AUDIO_CONFIG = "config/local_audio_production.json"
DEFAULT_NEGATIVE_AUDIO_PROMPT = (
    "speech, voice, narration, dialogue, singing, lyrics, human vocalization, "
    "podcast, radio announcer, melody, beat, musical score, sudden loud impact"
)


def load_local_audio_config(
    config: ProjectConfig,
    path: Path | None = None,
    *,
    profile_name: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any], str]:
    config_path = (path or config.project_root / DEFAULT_LOCAL_AUDIO_CONFIG).resolve()
    value = json.loads(config_path.read_text(encoding="utf-8"))
    if value.get("contract_version") != 1:
        raise ValueError("Local audio config contract_version must be 1")
    profiles = value.get("profiles")
    if not isinstance(profiles, dict) or not profiles:
        raise ValueError("Local audio config needs at least one profile")
    selected = profile_name or str(value.get("default_profile") or "")
    if selected not in profiles:
        raise ValueError(f"Unknown local audio profile: {selected}")
    profile = _resolve_profile(profiles, selected)
    if profile.get("execution_mode") != "offline_sequential":
        raise ValueError("Local audio profile must use offline_sequential execution")
    if int(profile.get("concurrent_gpu_models", 0)) != 1:
        raise ValueError("Local audio profile must permit exactly one GPU model at a time")
    return value, profile, selected


def _resolve_profile(
    profiles: dict[str, Any], name: str, ancestry: tuple[str, ...] = ()
) -> dict[str, Any]:
    if name in ancestry:
        raise ValueError("Circular local audio profile inheritance")
    value = profiles[name]
    if not isinstance(value, dict):
        raise ValueError(f"Local audio profile {name!r} must be an object")
    parent_name = value.get("extends_profile")
    if not parent_name:
        return dict(value)
    if parent_name not in profiles:
        raise ValueError(f"Local audio profile {name!r} extends an unknown profile")
    parent = _resolve_profile(profiles, str(parent_name), ancestry + (name,))
    override = {
        key: item for key, item in value.items() if key != "extends_profile"
    }
    return _deep_merge(parent, override)


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def local_audio_doctor(
    config: ProjectConfig,
    *,
    profile_name: str | None = None,
    local_config_path: Path | None = None,
    component: str = "all",
) -> dict[str, Any]:
    _, profile, selected = load_local_audio_config(
        config, local_config_path, profile_name=profile_name
    )
    narration = profile["narration"]
    ambient = profile["ambient"]
    if component not in {"all", "qwen", "ambient"}:
        raise ValueError("Local audio doctor component must be all, qwen, or ambient")
    report: dict[str, Any] = {
        "profile": selected,
        "component": component,
        "hardware_target": profile.get("hardware_target"),
        "execution_mode": profile["execution_mode"],
        "concurrent_gpu_models": profile["concurrent_gpu_models"],
        "streamdiffusion_must_be_stopped": bool(
            profile.get("streamdiffusion_must_be_stopped", True)
        ),
        "ffmpeg_available": shutil.which("ffmpeg") is not None,
        "ffprobe_available": shutil.which("ffprobe") is not None,
        "models_loaded": 0,
        "model_servers_started": False,
        "network_calls": 0,
        "paid_calls": 0,
    }
    if component in {"all", "qwen"}:
        report["qwen_tts"] = {
            "model": narration["production_model"],
            **Qwen3TTSLocalRenderer.dependency_status(),
        }
    if component in {"all", "ambient"}:
        report["stable_audio_3"] = {
            "model": ambient["model"],
            **StableAudio3LocalRenderer.dependency_status(),
        }
    return report


def prepare_local_voice_audition(
    config: ProjectConfig,
    production_index_path: Path,
    output_path: Path,
    *,
    profile_name: str | None = None,
    local_config_path: Path | None = None,
    voice_limit: int | None = None,
) -> dict[str, Any]:
    root, profile, selected = load_local_audio_config(
        config, local_config_path, profile_name=profile_name
    )
    production = _read_json(production_index_path)
    narrations = [
        item
        for item in production.get("narrations", [])
        if item.get("readiness") == "ready_for_voice_audition"
        and not item.get("identity_constraints")
        and not personal_story_findings(config.episodes_dir / str(item["narration_id"]))
    ]
    designs = root.get("audition_voice_designs")
    if not isinstance(designs, list) or not designs:
        raise ValueError("Local audio config has no audition_voice_designs")
    if voice_limit is not None:
        designs = designs[: max(0, int(voice_limit))]
    if len(narrations) < len(designs):
        raise ValueError("Not enough unconstrained narrations for the audition plan")

    narration_config = profile["narration"]
    audition_root = config.audio_dir / "local-auditions"
    jobs = []
    selected_narrations: set[str] = set()
    for position, design in enumerate(designs):
        narration = _choose_diverse_narration(narrations, selected_narrations, position)
        narration_id = str(narration["narration_id"])
        selected_narrations.add(narration_id)
        adaptation_path = config.episodes_dir / narration_id / "adaptation.json"
        adaptation = _read_json(adaptation_path)
        section = _choose_audition_section(adaptation["sections"])
        sample_text = _audition_excerpt(
            str(section["text"]),
            int(narration_config.get("audition_max_characters", 520)),
        )
        voice_id = str(design["voice_id"])
        tts_instruction = _audition_instruction(
            str(design["tts_instruction"]), section.get("delivery", {})
        )
        fingerprint = _sha256_json(
            {
                "model": narration_config["audition_model"],
                "voice_id": voice_id,
                "instruction": tts_instruction,
                "text": sample_text,
                "language": adaptation.get("adaptation_language", "en"),
                "seed": int(design["seed"]),
            }
        )
        output_audio = audition_root / voice_id / f"{fingerprint}.wav"
        jobs.append(
            {
                "job_id": f"audition-{voice_id}-{fingerprint[:12]}",
                "voice_id": voice_id,
                "display_name": design["display_name"],
                "model": narration_config["audition_model"],
                "mode": "voice_design",
                "seed": int(design["seed"]),
                "language": adaptation.get("adaptation_language", "en"),
                "reference_text": sample_text,
                "tts_instruction": tts_instruction,
                "source_delivery": section.get("delivery", {}),
                "artistic_casting": {
                    "gender_presentation": design["gender_presentation"],
                    "age_presentation": design["age_presentation"],
                    "accent_profile": design["accent_profile"],
                    "personality_tags": design["personality_tags"],
                },
                "source_narration_id": narration_id,
                "source_section_id": section["section_id"],
                "adaptation_sha256": content_digest(adaptation),
                "identity_disclaimer": (
                    "This is an internal artistic voice audition. The voice traits "
                    "are not claims about the archived writer or witness."
                ),
                "cache_key": fingerprint,
                "output_audio": str(output_audio.resolve()),
                "cached": _valid_wav(output_audio),
            }
        )
    plan = {
        "contract_version": 1,
        "kind": "local_voice_design_audition",
        "profile": selected,
        "hardware_target": profile.get("hardware_target"),
        "model": narration_config["audition_model"],
        "purpose": "Create reviewable synthetic reference voices before production casting.",
        "jobs": jobs,
    }
    _write_json(output_path, plan)
    pending = sum(not job["cached"] for job in jobs)
    return {
        "output": str(output_path.resolve()),
        "jobs": len(jobs),
        "cached": len(jobs) - pending,
        "local_model_calls_pending": pending,
        "spoken_characters_pending": sum(
            len(job["reference_text"]) for job in jobs if not job["cached"]
        ),
        "execution_requested": False,
        "network_calls": 0,
        "paid_calls": 0,
        "models_loaded": 0,
    }


def generate_local_voice_audition(
    config: ProjectConfig,
    plan_path: Path,
    *,
    execute: bool = False,
    max_calls: int | None = None,
    limit: int | None = None,
    allow_model_download: bool = False,
    local_config_path: Path | None = None,
) -> dict[str, Any]:
    plan = _read_json(plan_path)
    _, profile, selected = load_local_audio_config(
        config, local_config_path, profile_name=plan.get("profile")
    )
    jobs = list(plan.get("jobs", []))
    if limit is not None:
        jobs = jobs[: max(0, int(limit))]
    _validate_audition_jobs(jobs, str(plan.get("model")))
    require_current_speech_jobs(config, jobs, audition=True)
    pending = [job for job in jobs if not _valid_wav(Path(job["output_audio"]))]
    report = _execution_report(jobs, pending, execute=execute)
    report.update(
        {
            "profile": selected,
            "plan": str(plan_path.resolve()),
            "spoken_characters_pending": sum(
                len(job["reference_text"]) for job in pending
            ),
            "model_download_allowed": bool(allow_model_download),
        }
    )
    if not execute or not pending:
        return report
    _check_call_ceiling(len(pending), max_calls)
    narration_config = profile["narration"]
    model_source = _model_source(
        config,
        narration_config.get("audition_model_path"),
        narration_config["audition_model"],
        allow_model_download=allow_model_download,
    )
    renderer = Qwen3TTSLocalRenderer(
        model_name=model_source,
        mode="voice_design",
        device_map=narration_config.get("device_map", "cuda:0"),
        dtype=narration_config.get("dtype", "bfloat16"),
        attention=narration_config.get("attention", "sdpa"),
    )
    _execute_qwen_jobs(renderer, pending, report, audition=True)
    renderer.unload()
    return report


def approve_local_voice(
    config: ProjectConfig,
    plan_path: Path,
    voice_id: str,
    roster_path: Path,
    *,
    reviewer: str,
) -> dict[str, Any]:
    plan = _read_json(plan_path)
    _validate_audition_jobs(list(plan.get("jobs", [])), str(plan.get("model")))
    reviewer = str(reviewer).strip()
    if not reviewer:
        raise ValueError("Local voice approval requires a reviewer name")
    matches = [job for job in plan.get("jobs", []) if job.get("voice_id") == voice_id]
    if len(matches) != 1:
        raise ValueError(f"Audition plan does not contain exactly one voice {voice_id!r}")
    job = matches[0]
    require_current_speech_jobs(config, [job], audition=True)
    audio_path = Path(job["output_audio"]).expanduser().resolve()
    if not _valid_wav(audio_path):
        raise FileNotFoundError(f"Audition audio is missing or invalid: {audio_path}")
    roster = (
        _read_json(roster_path)
        if roster_path.is_file()
        else {
            "contract_version": 1,
            "kind": "local_synthetic_voice_roster",
            "status": "audition_in_progress",
            "manual_assignments": {},
            "candidates": [],
        }
    )
    candidates = roster.setdefault("candidates", [])
    candidates[:] = [item for item in candidates if item.get("voice_id") != voice_id]
    casting = job["artistic_casting"]
    candidates.append(
        {
            "voice_id": voice_id,
            "display_name": job["display_name"],
            "provider": "qwen3_tts_local",
            "production_model": "Qwen/Qwen3-TTS-12Hz-1.7B-Base",
            "reference_audio": _portable_path(config.project_root, audio_path),
            "reference_text": job["reference_text"],
            "gender_presentation": casting["gender_presentation"],
            "age_presentation": casting["age_presentation"],
            "accent_profile": casting["accent_profile"],
            "personality_tags": casting["personality_tags"],
            "supported_languages": [job["language"]],
            "audition_status": "approved",
            "reviewed_by": reviewer,
            "reviewed_at": datetime.now(timezone.utc).isoformat(),
            "identity_disclaimer": job["identity_disclaimer"],
        }
    )
    roster["status"] = "approved_voices_available"
    _write_json(roster_path, roster)
    return {
        "roster": str(roster_path.resolve()),
        "voice_id": voice_id,
        "approved_candidates": sum(
            item.get("audition_status") == "approved" for item in candidates
        ),
        "network_calls": 0,
        "paid_calls": 0,
    }


def prepare_local_speech_jobs(
    config: ProjectConfig,
    production_index_path: Path,
    roster_path: Path,
    output_path: Path,
    *,
    profile_name: str | None = None,
    local_config_path: Path | None = None,
    narration_limit: int | None = None,
    allow_conservative_editions: bool = False,
) -> dict[str, Any]:
    _, profile, selected = load_local_audio_config(
        config, local_config_path, profile_name=profile_name
    )
    if profile["narration"].get("production_mode") == "single_take_voice_design":
        raise ValueError("Use story-audio prepare --brief for whole-story production; section cloning requires the explicit 3080_legacy_voice_clone profile")
    production = _read_json(production_index_path)
    roster = _read_json(roster_path)
    candidates = [
        item
        for item in roster.get("candidates", [])
        if item.get("audition_status") == "approved"
    ]
    if not candidates:
        raise ValueError("No approved local voices; run and review the audition first")
    narrations = sorted(
        production.get("narrations", []),
        key=lambda item: (
            "conservative_spoken_edition" in item.get("editorial_warnings", []),
            str(item.get("narration_id")),
        ),
    )
    if narration_limit is not None:
        narrations = narrations[: max(0, int(narration_limit))]
    manual = roster.get("manual_assignments", {})
    narration_config = profile["narration"]
    jobs: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    cast_counts: dict[str, int] = {}
    for narration in narrations:
        narration_id = str(narration["narration_id"])
        quality_findings = personal_story_findings(config.episodes_dir / narration_id)
        if quality_findings or narration.get("readiness") != "ready_for_voice_audition":
            blocked.append({"narration_id": narration_id,
                            "reason": "personal_story_review_required",
                            "findings": quality_findings})
            continue
        adaptation_path = config.episodes_dir / narration_id / "adaptation.json"
        adaptation = _read_json(adaptation_path)
        duration_budget = story_duration_preflight(config, adaptation)
        if duration_budget["requires_condensation"]:
            blocked.append({"narration_id": narration_id,
                            "reason": "story_requires_condensation",
                            "duration_budget": duration_budget})
            continue
        if (
            "conservative_spoken_edition" in narration.get("editorial_warnings", [])
            and not allow_conservative_editions
        ):
            blocked.append(
                {
                    "narration_id": narration_id,
                    "reason": "conservative_spoken_edition_requires_editorial_approval",
                }
            )
            continue
        voice = _select_local_voice(narration, candidates, manual)
        if voice is None:
            blocked.append(
                {
                    "narration_id": narration_id,
                    "reason": "explicit_identity_constraints_require_manual_voice_assignment",
                }
            )
            continue
        reference_audio = _resolve_portable_path(
            config.project_root, str(voice["reference_audio"])
        )
        if not reference_audio.is_file():
            blocked.append(
                {
                    "narration_id": narration_id,
                    "reason": "approved_reference_audio_missing",
                    "voice_id": voice["voice_id"],
                }
            )
            continue
        cast_path = config.episodes_dir / narration_id / "local-cast.json"
        casting_card = {
            "contract_version": 1,
            "narration_id": narration_id,
            "language": adaptation.get("adaptation_language", "en"),
            "personality": adaptation.get("narrator_profile", {}).get(
                "personality_tags", []
            ),
            "voice": {
                "voice_id": voice["voice_id"],
                "display_name": voice["display_name"],
                "reference_audio": str(reference_audio.resolve()),
                "reference_text": voice["reference_text"],
                "gender_presentation": voice["gender_presentation"],
                "age_presentation": voice["age_presentation"],
                "accent_profile": voice["accent_profile"],
            },
            "identity_policy": (
                "Unsupported traits are artistic casting and are not claims about "
                "the archived writer or witness."
            ),
            "frozen": True,
        }
        narration_job_start = len(jobs)
        narration_blocked = False
        for index, section in enumerate(adaptation["sections"]):
            maximum_characters = int(
                narration_config.get("max_section_characters", 2200)
            )
            if len(str(section["text"])) > maximum_characters:
                blocked.append(
                    {
                        "narration_id": narration_id,
                        "reason": "section_exceeds_local_tts_character_limit",
                        "section_id": section["section_id"],
                        "characters": len(str(section["text"])),
                        "maximum": maximum_characters,
                    }
                )
                del jobs[narration_job_start:]
                narration_blocked = True
                break
            seed = _stable_seed(f"{narration_id}:{section['section_id']}:canonical")
            cache_key = _sha256_json(
                {
                    "provider": "qwen3_tts_local",
                    "model": narration_config["production_model"],
                    "mode": "voice_clone",
                    "text": section["text"],
                    "delivery": section.get("delivery", {}),
                    "voice_id": voice["voice_id"],
                    "reference_audio": str(reference_audio.resolve()),
                    "reference_text": voice["reference_text"],
                    "seed": seed,
                }
            )
            output_audio = config.audio_dir / "cache" / "local-qwen" / f"{cache_key}.wav"
            jobs.append(
                {
                    "job_id": f"{narration_id}-{section['section_id']}",
                    "narration_id": narration_id,
                    "section_id": section["section_id"],
                    "section_index": index,
                    "adaptation_sha256": content_digest(adaptation),
                    "provider": "qwen3_tts_local",
                    "model": narration_config["production_model"],
                    "mode": "voice_clone",
                    "text": section["text"],
                    "text_sha256": hashlib.sha256(
                        str(section["text"]).encode("utf-8")
                    ).hexdigest(),
                    "delivery": section.get("delivery", {}),
                    "pause_after_ms": int(section.get("pause_after_ms", 0)),
                    "seed": seed,
                    "casting_card": casting_card,
                    "cache_key": cache_key,
                    "output_audio": str(output_audio.resolve()),
                    "cached": _valid_wav(output_audio),
                }
            )
        if not narration_blocked:
            cast_counts[voice["voice_id"]] = (
                cast_counts.get(voice["voice_id"], 0) + 1
            )
            _write_json(cast_path, casting_card)
    _write_jsonl(output_path, jobs)
    pending = sum(not job["cached"] for job in jobs)
    return {
        "output": str(output_path.resolve()),
        "profile": selected,
        "narrations_requested": len(narrations),
        "narrations_prepared": len({job["narration_id"] for job in jobs}),
        "narrations_blocked": len(blocked),
        "blocking_details": blocked,
        "section_jobs": len(jobs),
        "cached": len(jobs) - pending,
        "local_model_calls_pending": pending,
        "spoken_characters_pending": sum(
            len(job["text"]) for job in jobs if not job["cached"]
        ),
        "cast_distribution": cast_counts,
        "execution_requested": False,
        "network_calls": 0,
        "paid_calls": 0,
        "models_loaded": 0,
    }


def generate_local_speech(
    config: ProjectConfig,
    jobs_path: Path,
    *,
    execute: bool = False,
    max_calls: int | None = None,
    limit: int | None = None,
    allow_model_download: bool = False,
    profile_name: str | None = None,
    local_config_path: Path | None = None,
) -> dict[str, Any]:
    jobs = _read_jsonl(jobs_path)
    if limit is not None:
        jobs = jobs[: max(0, int(limit))]
    _, profile, selected = load_local_audio_config(
        config, local_config_path, profile_name=profile_name
    )
    if profile["narration"].get("production_mode") == "single_take_voice_design":
        raise ValueError("Use story-audio render --brief for whole-story production; section cloning requires the explicit 3080_legacy_voice_clone profile")
    _validate_speech_jobs(jobs, str(profile["narration"]["production_model"]))
    require_current_speech_jobs(config, jobs, audition=False)
    pending = [job for job in jobs if not _valid_wav(Path(job["output_audio"]))]
    report = _execution_report(jobs, pending, execute=execute)
    report.update(
        {
            "profile": selected,
            "jobs_file": str(jobs_path.resolve()),
            "spoken_characters_pending": sum(len(job["text"]) for job in pending),
            "model_download_allowed": bool(allow_model_download),
        }
    )
    if not execute or not pending:
        return report
    _check_call_ceiling(len(pending), max_calls)
    narration_config = profile["narration"]
    model_source = _model_source(
        config,
        narration_config.get("production_model_path"),
        narration_config["production_model"],
        allow_model_download=allow_model_download,
    )
    renderer = Qwen3TTSLocalRenderer(
        model_name=model_source,
        mode="voice_clone",
        device_map=narration_config.get("device_map", "cuda:0"),
        dtype=narration_config.get("dtype", "bfloat16"),
        attention=narration_config.get("attention", "sdpa"),
    )
    _execute_qwen_jobs(renderer, pending, report, audition=False)
    renderer.unload()
    return report


def assemble_local_speech(
    config: ProjectConfig,
    jobs_path: Path,
    narration_id: str,
    *,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    jobs = [job for job in _read_jsonl(jobs_path) if job["narration_id"] == narration_id]
    jobs.sort(key=lambda item: int(item["section_index"]))
    if not jobs:
        raise ValueError(f"No speech jobs found for narration {narration_id}")
    require_current_speech_jobs(config, jobs, audition=False)
    missing = [job["output_audio"] for job in jobs if not _valid_wav(Path(job["output_audio"]))]
    if missing:
        raise FileNotFoundError(
            f"{len(missing)} speech sections are missing; first: {missing[0]}"
        )
    destination = (output_dir or config.audio_dir / narration_id).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    audio_path = destination / "voices-only.wav"
    timeline_sections: list[dict[str, Any]] = []
    chunks: list[bytes] = []
    sample_rate = 0
    cursor_frames = 0
    for job in jobs:
        with wave.open(str(job["output_audio"]), "rb") as handle:
            if handle.getnchannels() != 1 or handle.getsampwidth() != 2:
                raise ValueError("Local Qwen cache must be mono PCM16 WAV")
            current_rate = handle.getframerate()
            if sample_rate and current_rate != sample_rate:
                raise ValueError("Local Qwen sections use inconsistent sample rates")
            sample_rate = current_rate
            pcm = handle.readframes(handle.getnframes())
        start_ms = round(cursor_frames / sample_rate * 1000)
        chunks.append(pcm)
        cursor_frames += len(pcm) // 2
        speech_end_ms = round(cursor_frames / sample_rate * 1000)
        pause_ms = int(job.get("pause_after_ms", 0))
        if pause_ms:
            pause_frames = round(sample_rate * pause_ms / 1000)
            chunks.append(b"\x00\x00" * pause_frames)
            cursor_frames += pause_frames
        end_ms = round(cursor_frames / sample_rate * 1000)
        timeline_sections.append(
            {
                "section_id": job["section_id"],
                "segment_id": job["section_id"],
                "start_ms": start_ms,
                "speech_end_ms": speech_end_ms,
                "end_ms": end_ms,
                "text": job["text"],
                "voice_id": job["casting_card"]["voice"]["voice_id"],
                "source_story_ids": [],
            }
        )
    require_story_audio_frames(config, cursor_frames, sample_rate)
    temporary = audio_path.with_suffix(".tmp.wav")
    with wave.open(str(temporary), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(b"".join(chunks))
    temporary.replace(audio_path)
    duration_ms = round(cursor_frames / sample_rate * 1000)
    mastering = master_speech(
        audio_path, destination / "mastered", load_mastering_settings(config.project_root)
    )
    playback_path = Path(mastering["audio_path"])
    timeline = {
        "contract_version": 1,
        "kind": "self_narrated_story_timeline",
        "episode_id": narration_id,
        "narration_id": narration_id,
        "duration_ms": duration_ms,
        "sample_rate": sample_rate,
        "channels": 1,
        "voices_audio": str(playback_path.resolve()),
        "raw_voices_audio": str(audio_path.resolve()),
        "speech_mastering_cache_key": mastering.get("cache_key"),
        "sections": timeline_sections,
        "segments": timeline_sections,
    }
    timeline_path = destination / "timeline.json"
    _write_json(timeline_path, timeline)
    _write_captions(destination, timeline_sections)
    return {
        "narration_id": narration_id,
        "sections": len(jobs),
        "duration_ms": duration_ms,
        "voices_audio": str(playback_path.resolve()),
        "raw_voices_audio": str(audio_path.resolve()),
        "speech_mastering_status": mastering["status"],
        "timeline": str(timeline_path.resolve()),
        "captions_vtt": str((destination / "captions.vtt").resolve()),
        "captions_srt": str((destination / "captions.srt").resolve()),
        "network_calls": 0,
        "paid_calls": 0,
    }


def assemble_local_speech_collection(
    config: ProjectConfig,
    jobs_path: Path,
    *,
    narration_limit: int | None = None,
) -> dict[str, Any]:
    jobs = _read_jsonl(jobs_path)
    narration_ids = list(dict.fromkeys(str(job["narration_id"]) for job in jobs))
    if narration_limit is not None:
        narration_ids = narration_ids[: max(0, int(narration_limit))]
    assembled = []
    blocked = []
    for narration_id in narration_ids:
        narration_jobs = [job for job in jobs if job["narration_id"] == narration_id]
        missing = sum(
            not _valid_wav(Path(job["output_audio"])) for job in narration_jobs
        )
        if missing:
            blocked.append(
                {
                    "narration_id": narration_id,
                    "missing_sections": missing,
                }
            )
            continue
        assembled.append(assemble_local_speech(config, jobs_path, narration_id))
    return {
        "narrations_requested": len(narration_ids),
        "assembled": len(assembled),
        "blocked": len(blocked),
        "blocking_details": blocked,
        "outputs": assembled,
        "network_calls": 0,
        "paid_calls": 0,
    }


def prepare_local_ambient(
    config: ProjectConfig,
    timeline_path: Path,
    adaptation_path: Path,
    sound_design_path: Path,
    jobs_path: Path,
    *,
    profile_name: str | None = None,
    local_config_path: Path | None = None,
) -> dict[str, Any]:
    _, profile, selected = load_local_audio_config(
        config, local_config_path, profile_name=profile_name
    )
    timeline = _read_json(timeline_path)
    adaptation = _read_json(adaptation_path)
    if timeline.get("narration_id") != adaptation.get("narration_id"):
        raise ValueError("Timeline and adaptation narration_id do not match")
    ambient_config = profile["ambient"]
    minimum_span_ms = int(ambient_config.get("minimum_specific_span_ms", 15000))
    model = str(ambient_config["model"])
    model_max_ms = round(StableAudio3LocalRenderer.MODEL_MAX_SECONDS[model] * 1000)
    negative_prompt = str(
        ambient_config.get("negative_prompt") or DEFAULT_NEGATIVE_AUDIO_PROMPT
    )
    segments = timeline["segments"]
    first_segment_id = str(segments[0]["segment_id"])
    duration_ms = int(timeline["duration_ms"])
    base_prompt = _base_ambient_prompt(adaptation)
    cues: list[dict[str, Any]] = [
        _ambient_cue(
            cue_id="ambient-base",
            segment_id=first_segment_id,
            duration_ms=min(duration_ms, 300_000),
            generation_duration_ms=min(model_max_ms, max(60_000, min(duration_ms, 180_000))),
            prompt=base_prompt,
            coverage_role="base",
            gain_db=-31,
        )
    ]
    section_by_id = {str(item["section_id"]): item for item in adaptation["sections"]}
    for segment in segments:
        span_ms = int(segment["end_ms"]) - int(segment["start_ms"])
        if span_ms < minimum_span_ms:
            continue
        section = section_by_id.get(str(segment["section_id"]))
        if section is None:
            raise ValueError(f"Timeline section {segment['section_id']} is not in adaptation")
        prompt, evidence = _section_ambient_prompt(str(section["text"]), base_prompt)
        cues.append(
            _ambient_cue(
                cue_id=f"ambient-section-{section['section_id']}",
                segment_id=str(segment["segment_id"]),
                duration_ms=min(span_ms, 300_000),
                generation_duration_ms=min(model_max_ms, max(30_000, min(span_ms, 180_000))),
                prompt=prompt,
                coverage_role="section",
                gain_db=-27,
                editorial_note=(
                    "Acoustic keywords are mechanically grounded in this section: "
                    + (
                        ", ".join(evidence)
                        if evidence
                        else "no specific sound keyword; use base texture"
                    )
                ),
            )
        )
    sound_design = {
        "contract_version": 1,
        "episode_id": timeline["narration_id"],
        "sound_design_disclosure": (
            "All sounds are illustrative synthetic sound design, not archival recordings "
            "and not evidence of what occurred."
        ),
        "editorial_principles": [
            "No speech, voices, singing, or human vocalizations are generated.",
            "Locations and identities are never inferred from one another.",
            "The quiet base layer covers the complete narration.",
            "Specific layers shorter than the minimum span inherit the previous sound.",
        ],
        "continuous_background": {
            "enabled": True,
            "base_cue_id": "ambient-base",
            "minimum_specific_span_ms": minimum_span_ms,
            "short_span_policy": "inherit_previous",
        },
        "cues": cues,
    }
    _write_json(sound_design_path, sound_design)
    validation = validate_sound_design(sound_design_path, timeline_path)
    if not validation["valid"]:
        raise ValueError(
            "Generated local sound design is invalid: "
            + "; ".join(validation["errors"])
        )
    jobs: list[dict[str, Any]] = []
    for cue in cues:
        source = cue["source"]
        cache_key = _sha256_json(
            {
                "provider": "stable_audio_3_local",
                "model": model,
                "prompt": source["prompt"],
                "negative_prompt": negative_prompt,
                "duration_ms": source["generation_duration_ms"],
                "seed": _stable_seed(
                    f"{timeline['narration_id']}:{cue['cue_id']}:canonical"
                ),
            }
        )
        output_audio = config.audio_dir / "cache" / "stable-audio-3" / f"{cache_key}.wav"
        jobs.append(
            {
                "job_id": f"{timeline['narration_id']}-{cue['cue_id']}",
                "episode_id": timeline["narration_id"],
                "narration_id": timeline["narration_id"],
                "cue_id": cue["cue_id"],
                "provider": "stable_audio_3_local",
                "model": model,
                "prompt": source["prompt"],
                "negative_prompt": negative_prompt,
                "generation_duration_ms": source["generation_duration_ms"],
                "loop": True,
                "seed": _stable_seed(
                    f"{timeline['narration_id']}:{cue['cue_id']}:canonical"
                ),
                "cache_key": cache_key,
                "output_audio": str(output_audio.resolve()),
                "cached": _valid_audio_file(output_audio),
            }
        )
    _write_jsonl(jobs_path, jobs)
    pending = sum(not job["cached"] for job in jobs)
    return {
        "profile": selected,
        "narration_id": timeline["narration_id"],
        "sound_design": str(sound_design_path.resolve()),
        "jobs": str(jobs_path.resolve()),
        "continuous_base": True,
        "specific_layers": len(jobs) - 1,
        "short_sections_inherit_previous": len(segments) - (len(jobs) - 1),
        "local_model_calls_pending": pending,
        "pending_generation_seconds": round(
            sum(job["generation_duration_ms"] for job in jobs if not job["cached"])
            / 1000,
            3,
        ),
        "execution_requested": False,
        "network_calls": 0,
        "paid_calls": 0,
        "models_loaded": 0,
        "validation": validation,
    }


def prepare_local_ambient_collection(
    config: ProjectConfig,
    production_index_path: Path,
    aggregate_jobs_path: Path,
    *,
    profile_name: str | None = None,
    local_config_path: Path | None = None,
    narration_limit: int | None = None,
) -> dict[str, Any]:
    production = _read_json(production_index_path)
    narrations = list(production.get("narrations", []))
    if narration_limit is not None:
        narrations = narrations[: max(0, int(narration_limit))]
    all_jobs: list[dict[str, Any]] = []
    prepared = []
    blocked = []
    for item in narrations:
        narration_id = str(item["narration_id"])
        timeline_path = config.audio_dir / narration_id / "timeline.json"
        adaptation_path = config.episodes_dir / narration_id / "adaptation.json"
        if not timeline_path.is_file():
            blocked.append(
                {"narration_id": narration_id, "reason": "speech_timeline_missing"}
            )
            continue
        sound_design_path = config.episodes_dir / narration_id / "sound-design.json"
        per_story_jobs = (
            config.work_dir / "local-audio" / "ambient" / f"{narration_id}-jobs.jsonl"
        )
        report = prepare_local_ambient(
            config,
            timeline_path,
            adaptation_path,
            sound_design_path,
            per_story_jobs,
            profile_name=profile_name,
            local_config_path=local_config_path,
        )
        prepared.append(report)
        all_jobs.extend(_read_jsonl(per_story_jobs))
    _write_jsonl(aggregate_jobs_path, all_jobs)
    pending = sum(not job["cached"] for job in all_jobs)
    return {
        "aggregate_jobs": str(aggregate_jobs_path.resolve()),
        "narrations_requested": len(narrations),
        "narrations_prepared": len(prepared),
        "narrations_blocked": len(blocked),
        "blocking_details": blocked,
        "ambient_jobs": len(all_jobs),
        "local_model_calls_pending": pending,
        "pending_generation_seconds": round(
            sum(
                job["generation_duration_ms"]
                for job in all_jobs
                if not job["cached"]
            )
            / 1000,
            3,
        ),
        "execution_requested": False,
        "network_calls": 0,
        "paid_calls": 0,
        "models_loaded": 0,
    }


def assemble_local_soundscape_collection(
    config: ProjectConfig,
    production_index_path: Path,
    *,
    narration_limit: int | None = None,
) -> dict[str, Any]:
    production = _read_json(production_index_path)
    narrations = list(production.get("narrations", []))
    if narration_limit is not None:
        narrations = narrations[: max(0, int(narration_limit))]
    rendered = []
    blocked = []
    for item in narrations:
        narration_id = str(item["narration_id"])
        timeline_path = config.audio_dir / narration_id / "timeline.json"
        voices_path = config.audio_dir / narration_id / "voices-only.wav"
        if timeline_path.is_file():
            voices_path = Path(_read_json(timeline_path).get("voices_audio") or voices_path)
        sound_design_path = config.episodes_dir / narration_id / "sound-design.json"
        jobs_path = (
            config.work_dir / "local-audio" / "ambient" / f"{narration_id}-jobs.jsonl"
        )
        required = (timeline_path, voices_path, sound_design_path, jobs_path)
        missing = [str(path) for path in required if not path.is_file()]
        if not missing:
            ambient_jobs = _read_jsonl(jobs_path)
            missing.extend(
                job["output_audio"]
                for job in ambient_jobs
                if not _valid_audio_file(Path(job["output_audio"]))
            )
        if missing:
            blocked.append(
                {
                    "narration_id": narration_id,
                    "reason": "required_audio_or_plan_missing",
                    "missing_count": len(missing),
                    "first_missing": missing[0],
                }
            )
            continue
        # Raw generation jobs remain immutable. Resolve reviewed-level copies
        # only for this assembly; a quality hold blocks instead of falling back
        # to an inaudible or stale raw asset.
        settings = load_ambient_settings(config.project_root)
        render_options = {}
        soundscape_output = config.audio_dir / narration_id
        if settings["enabled"]:
            finished = []
            for job in ambient_jobs:
                receipt = master_ambient(Path(job["output_audio"]), settings,
                                         root=config.project_root)
                finished.append({**job, "raw_output_audio": job["output_audio"],
                                 "output_audio": receipt["audio_path"],
                                 "ambient_mastering_cache_key": receipt["cache_key"]})
            jobs_path = config.work_dir / "local-audio/ambient-mastered" / (
                narration_id + "-" + _sha256_json(finished)[:16] + ".jsonl")
            _write_jsonl(jobs_path, finished)
            # New level settings never replace an earlier listening edition.
            edition_key = _sha256_json({"jobs": finished, "settings": settings,
                                       "timeline": ambient_sha(timeline_path),
                                       "design": ambient_sha(sound_design_path),
                                       "voice": ambient_sha(voices_path)})[:16]
            soundscape_output = soundscape_output / "ambient-editions" / edition_key
            render_options = {"ambient_mastering_settings": settings,
                              "ambient_project_root": config.project_root}
        timeline = render_soundscape_audio(
            timeline_path,
            sound_design_path,
            config.work_dir / "local-audio" / "render",
            soundscape_output,
            sfx_jobs_path=jobs_path,
            voices_audio_path=voices_path,
            **render_options,
        )
        rendered.append(
            {
                "narration_id": narration_id,
                "duration_ms": timeline["duration_ms"],
                "tracks": timeline["tracks"],
            }
        )
    return {
        "narrations_requested": len(narrations),
        "rendered": len(rendered),
        "blocked": len(blocked),
        "blocking_details": blocked,
        "outputs": rendered,
        "network_calls": 0,
        "paid_calls": 0,
    }


def generate_local_ambient(
    config: ProjectConfig,
    jobs_path: Path,
    *,
    execute: bool = False,
    max_calls: int | None = None,
    limit: int | None = None,
    allow_model_download: bool = False,
    profile_name: str | None = None,
    local_config_path: Path | None = None,
) -> dict[str, Any]:
    jobs = _read_jsonl(jobs_path)
    if limit is not None:
        jobs = jobs[: max(0, int(limit))]
    _, profile, selected = load_local_audio_config(
        config, local_config_path, profile_name=profile_name
    )
    _validate_ambient_jobs(jobs, str(profile["ambient"]["model"]))
    pending = [job for job in jobs if not _valid_audio_file(Path(job["output_audio"]))]
    report = _execution_report(jobs, pending, execute=execute)
    report.update(
        {
            "profile": selected,
            "jobs_file": str(jobs_path.resolve()),
            "pending_generation_seconds": round(
                sum(job["generation_duration_ms"] for job in pending) / 1000, 3
            ),
            "model_download_allowed": bool(allow_model_download),
        }
    )
    settings = load_ambient_settings(config.project_root)
    report["ambient_mastering"] = {
        "enabled": settings["enabled"], "asset_target_lufs": settings["asset_target_lufs"],
        "quality_hold_on_inaudible_bass": True,
    }
    if not execute:
        return report
    if not pending:
        if settings["enabled"]:
            report["mastered_assets"] = len([
                master_ambient(Path(job["output_audio"]), settings, root=config.project_root)
                for job in jobs
            ])
        return report
    _check_call_ceiling(len(pending), max_calls)
    ambient_config = profile["ambient"]
    model_name = str(ambient_config["model"])
    renderer = StableAudio3LocalRenderer(
        model_name=model_name,
        device=ambient_config.get("device", "cuda"),
        model_half=bool(ambient_config.get("model_half", True)),
        steps=int(ambient_config.get("steps", 8)),
        cfg_scale=float(ambient_config.get("cfg_scale", 1.0)),
        chunked_decode=bool(ambient_config.get("chunked_decode", True)),
        allow_model_download=allow_model_download,
    )
    completed = 0
    failures = []
    for job in pending:
        try:
            render = renderer.render(
                prompt=job["prompt"],
                negative_prompt=job["negative_prompt"],
                duration_seconds=float(job["generation_duration_ms"]) / 1000,
                seed=int(job["seed"]),
                output_path=Path(job["output_audio"]),
            )
            _write_json(
                Path(job["output_audio"]).with_suffix(".generation.json"),
                {
                    "contract_version": 1,
                    "job_id": job["job_id"],
                    "cache_key": job["cache_key"],
                    "model": job["model"],
                    "seed": job["seed"],
                    "duration_ms": render.duration_ms,
                    "sample_rate": render.sample_rate,
                    "channels": render.channels,
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            if settings["enabled"]:
                master_ambient(render.audio_path, settings, root=config.project_root)
            completed += 1
            print(f"[{completed}/{len(pending)}] generated ambient {job['cue_id']}", flush=True)
        except Exception as error:
            failures.append(
                {"job_id": job["job_id"], "error": f"{type(error).__name__}: {error}"}
            )
            break
    renderer.unload()
    report.update(
        {
            "generated": completed,
            "failed": len(failures),
            "failures": failures,
            "remaining": len(pending) - completed,
            "completed": not failures and completed == len(pending),
            "models_loaded": 1,
            "network_calls": "model_download_only_if_cache_was_missing"
            if allow_model_download
            else 0,
        }
    )
    return report


def _execute_qwen_jobs(
    renderer: Qwen3TTSLocalRenderer,
    pending: list[dict[str, Any]],
    report: dict[str, Any],
    *,
    audition: bool,
) -> None:
    completed = 0
    failures = []
    for job in pending:
        section = {
            "section_id": job.get("source_section_id") or job.get("section_id") or "audition",
            "text": job.get("reference_text") if audition else job["text"],
            "delivery": job.get("delivery", {}),
        }
        if audition:
            casting = job["artistic_casting"]
            casting_card = {
                "language": job["language"],
                "personality": casting["personality_tags"],
                "voice": {
                    **casting,
                    "tts_instruction": job["tts_instruction"],
                },
            }
        else:
            casting_card = job["casting_card"]
        try:
            render = renderer.render_section(
                section,
                casting_card,
                Path(job["output_audio"]),
                speech_seed=int(job["seed"]),
            )
            _write_json(
                Path(job["output_audio"]).with_suffix(".generation.json"),
                {
                    "contract_version": 1,
                    "job_id": job["job_id"],
                    "cache_key": job["cache_key"],
                    "model": job["model"],
                    "seed": job["seed"],
                    "duration_ms": render.duration_ms,
                    "sample_rate": render.sample_rate,
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            completed += 1
            print(f"[{completed}/{len(pending)}] generated speech {job['job_id']}", flush=True)
        except Exception as error:
            failures.append(
                {"job_id": job["job_id"], "error": f"{type(error).__name__}: {error}"}
            )
            break
    report.update(
        {
            "generated": completed,
            "failed": len(failures),
            "failures": failures,
            "remaining": len(pending) - completed,
            "completed": not failures and completed == len(pending),
            "models_loaded": 1,
        }
    )


def _execution_report(
    jobs: list[dict[str, Any]], pending: list[dict[str, Any]], *, execute: bool
) -> dict[str, Any]:
    return {
        "jobs": len(jobs),
        "cached": len(jobs) - len(pending),
        "pending": len(pending),
        "local_model_calls_pending": len(pending),
        "execution_requested": bool(execute),
        "generated": 0,
        "failed": 0,
        "remaining": len(pending),
        "failures": [],
        "models_loaded": 0,
        "model_servers_started": False,
        "paid_calls": 0,
        "network_calls": 0,
    }


def _validate_audition_jobs(jobs: list[dict[str, Any]], expected_model: str) -> None:
    seen: set[str] = set()
    for job in jobs:
        job_id = str(job.get("job_id") or "")
        if not job_id or job_id in seen:
            raise ValueError(f"Invalid or duplicate local audition job_id: {job_id!r}")
        seen.add(job_id)
        if job.get("model") != expected_model or job.get("mode") != "voice_design":
            raise ValueError(f"Audition job {job_id} has unexpected model or mode")
        expected_cache = _sha256_json(
            {
                "model": job["model"],
                "voice_id": job["voice_id"],
                "instruction": job["tts_instruction"],
                "text": job["reference_text"],
                "language": job["language"],
                "seed": int(job["seed"]),
            }
        )
        _validate_job_cache(job, expected_cache)


def _validate_speech_jobs(jobs: list[dict[str, Any]], expected_model: str) -> None:
    seen: set[str] = set()
    for job in jobs:
        job_id = str(job.get("job_id") or "")
        if not job_id or job_id in seen:
            raise ValueError(f"Invalid or duplicate local speech job_id: {job_id!r}")
        seen.add(job_id)
        if (
            job.get("provider") != "qwen3_tts_local"
            or job.get("model") != expected_model
            or job.get("mode") != "voice_clone"
        ):
            raise ValueError(f"Speech job {job_id} has unexpected provider, model, or mode")
        text = str(job.get("text") or "")
        if hashlib.sha256(text.encode("utf-8")).hexdigest() != job.get("text_sha256"):
            raise ValueError(f"Speech job {job_id} text hash does not match")
        voice = job["casting_card"]["voice"]
        expected_cache = _sha256_json(
            {
                "provider": "qwen3_tts_local",
                "model": job["model"],
                "mode": "voice_clone",
                "text": text,
                "delivery": job.get("delivery", {}),
                "voice_id": voice["voice_id"],
                "reference_audio": str(Path(voice["reference_audio"]).resolve()),
                "reference_text": voice["reference_text"],
                "seed": int(job["seed"]),
            }
        )
        _validate_job_cache(job, expected_cache)


def _validate_ambient_jobs(jobs: list[dict[str, Any]], expected_model: str) -> None:
    seen: set[str] = set()
    maximum_ms = round(
        StableAudio3LocalRenderer.MODEL_MAX_SECONDS[expected_model] * 1000
    )
    for job in jobs:
        job_id = str(job.get("job_id") or "")
        if not job_id or job_id in seen:
            raise ValueError(f"Invalid or duplicate local ambient job_id: {job_id!r}")
        seen.add(job_id)
        if (
            job.get("provider") != "stable_audio_3_local"
            or job.get("model") != expected_model
        ):
            raise ValueError(f"Ambient job {job_id} has unexpected provider or model")
        duration_ms = int(job.get("generation_duration_ms", 0))
        if not 1000 <= duration_ms <= maximum_ms:
            raise ValueError(f"Ambient job {job_id} has invalid generation duration")
        expected_cache = _sha256_json(
            {
                "provider": "stable_audio_3_local",
                "model": job["model"],
                "prompt": job["prompt"],
                "negative_prompt": job["negative_prompt"],
                "duration_ms": duration_ms,
                "seed": int(job["seed"]),
            }
        )
        _validate_job_cache(job, expected_cache)


def _validate_job_cache(job: dict[str, Any], expected_cache: str) -> None:
    job_id = str(job["job_id"])
    if job.get("cache_key") != expected_cache:
        raise ValueError(f"Local audio job {job_id} cache key does not match content")
    if Path(str(job.get("output_audio"))).stem != expected_cache:
        raise ValueError(f"Local audio job {job_id} output filename is not its cache key")


def _check_call_ceiling(pending: int, maximum: int | None) -> None:
    if maximum is None:
        raise ValueError(
            f"Execution requires --max-calls; exact pending-call ceiling is {pending}"
        )
    if int(maximum) < pending:
        raise ValueError(
            f"Pending jobs require {pending} local model calls, exceeding --max-calls {maximum}"
        )


def _model_source(
    config: ProjectConfig,
    configured_path: str | None,
    model_name: str,
    *,
    allow_model_download: bool,
) -> str:
    if configured_path:
        path = _resolve_portable_path(config.project_root, configured_path)
        if not path.is_dir():
            raise FileNotFoundError(f"Configured local model directory does not exist: {path}")
        return str(path)
    if not allow_model_download:
        raise ValueError(
            f"Model {model_name!r} has no local path. Download it separately or rerun "
            "with --allow-model-download after reviewing its license and disk use."
        )
    return model_name


def _choose_diverse_narration(
    narrations: list[dict[str, Any]], selected: set[str], offset: int
) -> dict[str, Any]:
    ordered = sorted(
        narrations,
        key=lambda item: (
            str(item.get("source_language")),
            str(item.get("primary_theme")),
            int(item.get("spoken_character_count", 0)),
            str(item["narration_id"]),
        ),
    )
    available = [item for item in ordered if item["narration_id"] not in selected]
    return available[(offset * 37) % len(available)]


def _choose_audition_section(sections: list[dict[str, Any]]) -> dict[str, Any]:
    suitable = [item for item in sections if 180 <= len(str(item.get("text", ""))) <= 1200]
    candidates = suitable or sections
    return min(candidates, key=lambda item: abs(len(str(item.get("text", ""))) - 480))


def _audition_excerpt(text: str, maximum: int) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) <= maximum:
        return compact
    candidate = compact[:maximum]
    stop = max(candidate.rfind(". "), candidate.rfind("? "), candidate.rfind("! "))
    if stop >= max(120, maximum // 2):
        return candidate[: stop + 1]
    space = candidate.rfind(" ")
    # Do not invent a sentence ending; keep the audition a contiguous excerpt.
    return candidate[:space].rstrip() if space > 0 else candidate


def _audition_instruction(base: str, delivery: dict[str, Any]) -> str:
    emotion = str(delivery.get("emotion") or "emotionally responsive").strip()
    pace = str(delivery.get("pace") or "conversational").strip()
    nonverbal = [str(item).replace("_", " ") for item in delivery.get("nonverbal", [])]
    details = (
        " Where the meaning naturally supports it, include these subtle human "
        "behaviors without speaking their labels: "
        + ", ".join(nonverbal)
        + "."
        if nonverbal
        else ""
    )
    return (
        f"{base} For this excerpt, use a {pace} pace and a {emotion} emotional "
        f"arc.{details} Never read performance directions aloud."
    )


def _select_local_voice(
    narration: dict[str, Any],
    candidates: list[dict[str, Any]],
    manual: dict[str, str],
) -> dict[str, Any] | None:
    narration_id = str(narration["narration_id"])
    by_id = {str(item["voice_id"]): item for item in candidates}
    if narration_id in manual:
        selected = by_id.get(str(manual[narration_id]))
        if selected is None:
            raise ValueError(f"Manual voice assignment for {narration_id} is not approved")
        return selected
    if narration.get("identity_constraints"):
        return None
    language = str(narration.get("adaptation_language") or "en")
    compatible = [
        item for item in candidates if language in item.get("supported_languages", [])
    ]
    if not compatible:
        compatible = candidates
    ordered = sorted(compatible, key=lambda item: str(item["voice_id"]))
    return ordered[_stable_seed(narration_id) % len(ordered)]


def _base_ambient_prompt(adaptation: dict[str, Any]) -> str:
    notes = " ".join(adaptation.get("adaptation_notes", [])).casefold()
    archive_texture = (
        "very subtle paper and distant archive-room air, "
        if "archive" in notes
        else ""
    )
    return (
        "Continuous understated non-human environmental ambience for an intimate "
        f"spoken history: {archive_texture}soft room tone, diffuse air, gentle low-frequency "
        "movement, sparse natural detail, seamless loop, restrained documentary sound design, "
        "no dramatic events, no speech, no voices, no footsteps, no music."
    )


_ACOUSTIC_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("rain", "soft rain on distant surfaces"),
    ("storm", "distant weather and restrained wind"),
    ("wind", "light wind moving through nearby space"),
    ("sea", "distant shoreline wash"),
    ("ocean", "distant ocean wash"),
    ("river", "gentle moving water"),
    ("train", "far-off rail movement and low mechanical rhythm"),
    ("road", "very distant road ambience"),
    ("car", "restrained distant vehicle movement"),
    ("kitchen", "quiet kitchen room tone and subtle utensil movement"),
    ("door", "occasional soft wooden door movement"),
    ("fire", "quiet hearth crackle"),
    ("garden", "soft garden air and sparse leaves"),
    ("forest", "quiet woodland air and sparse leaves"),
    ("wood", "quiet woodland air and sparse leaves"),
    ("bird", "sparse distant birds"),
    ("school", "empty institutional room tone far from activity"),
    ("church", "large quiet reverberant interior"),
    ("market", "distant non-verbal market movement without discernible voices"),
    ("snow", "muted winter exterior air"),
)


def _section_ambient_prompt(text: str, base_prompt: str) -> tuple[str, list[str]]:
    folded = text.casefold()
    details = [
        description
        for keyword, description in _ACOUSTIC_KEYWORDS
        if re.search(rf"\b{re.escape(keyword)}\b", folded)
    ]
    details = list(dict.fromkeys(details))[:4]
    if not details:
        return base_prompt, []
    return (
        "Illustrative non-human environmental ambience, subtle and emotionally restrained: "
        + ", ".join(details)
        + ". Seamless loop, natural spatial depth, documentary realism, no intelligible speech, "
        "no voices, no singing, no music, no identity inference.",
        details,
    )


def _ambient_cue(
    *,
    cue_id: str,
    segment_id: str,
    duration_ms: int,
    generation_duration_ms: int,
    prompt: str,
    coverage_role: str,
    gain_db: float,
    editorial_note: str = "",
) -> dict[str, Any]:
    fade = min(15_000, max(2_000, duration_ms // 5))
    return {
        "cue_id": cue_id,
        "kind": "ambience",
        "coverage_role": coverage_role,
        "anchor": {"segment_id": segment_id, "point": "start", "offset_ms": 0},
        "duration_ms": duration_ms,
        "gain_db": gain_db,
        "mix_gain_db": 0,
        "fade_in_ms": fade,
        "fade_out_ms": fade,
        "loop": True,
        "duck_under_dialogue": True,
        "transcript_label": "illustrative ambient sound",
        "editorial_note": editorial_note,
        "provenance": {
            "presentation": "illustrative_sound_design",
            "disclosure": "Synthetic illustrative sound; not an archival recording.",
        },
        "source": {
            "type": "generated",
            "prompt": prompt,
            "generation_duration_ms": generation_duration_ms,
        },
    }


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    values = []
    with path.open(encoding="utf-8-sig") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number}: expected a JSON object")
            values.append(value)
    return values


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def _write_jsonl(path: Path, values: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        for value in values:
            handle.write(json.dumps(value, ensure_ascii=False) + "\n")
    temporary.replace(path)


def _sha256_json(value: dict[str, Any]) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _stable_seed(value: str) -> int:
    return int(hashlib.sha256(value.encode("utf-8")).hexdigest()[:8], 16)


def _valid_wav(path: Path) -> bool:
    if not path.is_file():
        return False
    try:
        with wave.open(str(path), "rb") as handle:
            return (
                handle.getnframes() > 0
                and handle.getframerate() > 0
                and handle.getnchannels() == 1
                and handle.getsampwidth() == 2
            )
    except (EOFError, wave.Error):
        return False


def _valid_audio_file(path: Path) -> bool:
    return path.is_file() and path.stat().st_size > 44


def _portable_path(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _resolve_portable_path(root: Path, value: str) -> Path:
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def _write_captions(output_dir: Path, sections: list[dict[str, Any]]) -> None:
    vtt = ["WEBVTT", ""]
    srt: list[str] = []
    for index, section in enumerate(sections, 1):
        text = re.sub(r"\s+", " ", str(section["text"])).strip()
        start_vtt = _timestamp(int(section["start_ms"]), vtt=True)
        end_vtt = _timestamp(int(section["speech_end_ms"]), vtt=True)
        vtt.extend([str(index), f"{start_vtt} --> {end_vtt}", text, ""])
        srt.extend(
            [
                str(index),
                f"{_timestamp(int(section['start_ms']), vtt=False)} --> "
                f"{_timestamp(int(section['speech_end_ms']), vtt=False)}",
                text,
                "",
            ]
        )
    (output_dir / "captions.vtt").write_text("\n".join(vtt), encoding="utf-8")
    (output_dir / "captions.srt").write_text("\n".join(srt), encoding="utf-8")


def _timestamp(milliseconds: int, *, vtt: bool) -> str:
    hours, remainder = divmod(max(0, milliseconds), 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, millis = divmod(remainder, 1_000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}{'.' if vtt else ','}{millis:03d}"
