from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .config import ProjectConfig
from .script import render_tts_text


def prepare_voice_candidate_audition_jobs(
    config: ProjectConfig,
    audition_path: Path,
    candidates_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    provider = config.speech_provider
    if not provider:
        raise ValueError("speech_provider is not configured")
    if provider.get("type") != "elevenlabs_tts":
        raise ValueError("speech_provider must use elevenlabs_tts")

    audition = _load_object(audition_path)
    candidates = _load_object(candidates_path)
    if audition.get("contract_version") != 1:
        raise ValueError("Voice audition contract_version must be 1")
    if candidates.get("contract_version") != 1:
        raise ValueError("Voice candidate contract_version must be 1")
    if candidates.get("provider") != "elevenlabs":
        raise ValueError("Voice candidates must use the ElevenLabs provider")

    audition_id = _required_string(audition, "audition_id")
    text = _required_string(audition, "text")
    pronunciation = audition.get("pronunciation", {})
    delivery = audition.get("delivery", {})
    model = str(provider.get("model", "eleven_v3"))
    render_text = render_tts_text(
        text,
        pronunciation,
        delivery,
        supports_audio_tags=model == "eleven_v3",
    )

    policy = candidates.get("screening_policy")
    if not isinstance(policy, dict):
        raise ValueError("Voice candidates need screening_policy")
    minimum_notice = int(policy.get("minimum_notice_period_days", 0))
    maximum_rate = float(policy.get("maximum_credit_rate", 1))
    candidate_items = candidates.get("candidates")
    if not isinstance(candidate_items, list) or not candidate_items:
        raise ValueError("Voice candidates need a non-empty candidates array")

    output_format = str(provider.get("output_format", "mp3_44100_128"))
    jobs: list[dict[str, Any]] = []
    candidate_ids: set[str] = set()
    voice_ids: set[str] = set()
    for index, candidate in enumerate(candidate_items, start=1):
        if not isinstance(candidate, dict):
            raise ValueError(f"Voice candidate {index} must be an object")
        candidate_id = _required_string(candidate, "candidate_id")
        voice_id = _required_string(candidate, "voice_id")
        if candidate_id in candidate_ids:
            raise ValueError(f"Duplicate voice candidate_id {candidate_id!r}")
        if voice_id in voice_ids:
            raise ValueError(f"Duplicate candidate voice_id {voice_id!r}")
        candidate_ids.add(candidate_id)
        voice_ids.add(voice_id)
        for field in ("display_name", "voice_name", "accent", "locale"):
            _required_string(candidate, field)
        if candidate.get("english_verified") is not True:
            raise ValueError(f"Voice candidate {candidate_id!r} is not English-verified")
        notice_days = int(candidate.get("notice_period_days", 0))
        if notice_days < minimum_notice:
            raise ValueError(
                f"Voice candidate {candidate_id!r} has only {notice_days} notice days"
            )
        credit_rate = float(candidate.get("credit_rate", maximum_rate + 1))
        if credit_rate > maximum_rate:
            raise ValueError(
                f"Voice candidate {candidate_id!r} credit rate {credit_rate:g} "
                f"exceeds {maximum_rate:g}"
            )
        roles = candidate.get("proposed_roles")
        if not isinstance(roles, list) or not roles:
            raise ValueError(f"Voice candidate {candidate_id!r} needs proposed_roles")

        fingerprint = json.dumps(
            {
                "contract_version": 1,
                "audition_id": audition_id,
                "candidate_id": candidate_id,
                "provider": provider["type"],
                "model": model,
                "voice_id": voice_id,
                "output_format": output_format,
                "language_code": provider.get("language_code"),
                "voice_settings": provider.get("voice_settings", {}),
                "render_text": render_text,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        cache_key = hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()
        output_audio = config.audio_dir / "cache" / "tts" / f"{cache_key}.wav"
        preview_mp3 = (
            config.work_dir
            / "tts"
            / audition_id
            / f"{candidate_id}-{output_format}.mp3"
        )
        jobs.append(
            {
                "contract_version": 1,
                "episode_id": audition_id,
                "segment_id": candidate_id,
                "speaker": candidate_id,
                "display_name": candidate["display_name"],
                "voice_name": candidate["voice_name"],
                "voice_id": voice_id,
                "accent": candidate["accent"],
                "locale": candidate["locale"],
                "proposed_roles": roles,
                "provider": provider["type"],
                "model": model,
                "output_format": output_format,
                "text": text,
                "render_text": render_text,
                "previous_text": None,
                "next_text": None,
                "delivery": delivery,
                "pronunciation": pronunciation,
                "pause_after_ms": 0,
                "source_story_ids": [],
                "cache_key": cache_key,
                "output_audio": str(output_audio.resolve()),
                "preview_mp3": str(preview_mp3.resolve()),
                "cached": output_audio.is_file(),
            }
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        for job in jobs:
            handle.write(json.dumps(job, ensure_ascii=False) + "\n")
    return {
        "output": str(output_path),
        "audition_id": audition_id,
        "candidates": len(jobs),
        "accents": sorted({job["accent"] for job in jobs}),
        "characters_per_candidate": len(render_text),
        "total_characters": len(render_text) * len(jobs),
        "output_format": output_format,
        "previews": [job["preview_mp3"] for job in jobs],
    }


def _required_string(value: dict[str, Any], field: str) -> str:
    result = value.get(field)
    if not isinstance(result, str) or not result.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return result


def _load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return value
