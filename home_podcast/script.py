from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return value


def validate_script(
    script_path: Path,
    evidence_packet_path: Path,
    show_bible_path: Path,
) -> dict[str, Any]:
    script = load_json(script_path)
    packet = load_json(evidence_packet_path)
    show_bible = load_json(show_bible_path)
    errors: list[str] = []
    warnings: list[str] = []
    episode_id = packet["episode"]["episode_id"]
    if script.get("contract_version") != 1:
        errors.append("contract_version must be 1")
    if script.get("episode_id") != episode_id:
        errors.append(f"episode_id must be {episode_id!r}")
    if not isinstance(script.get("title"), str) or not script["title"].strip():
        errors.append("title must be a non-empty string")
    allowed_speakers = {host["id"] for host in show_bible["hosts"]}
    evidence_by_id = {item["story_id"]: item for item in packet["evidence"]}
    used_story_ids: set[str] = set()
    segment_ids: set[str] = set()
    segments = script.get("segments")
    if not isinstance(segments, list) or not segments:
        errors.append("segments must be a non-empty array")
        segments = []
    for index, segment in enumerate(segments, start=1):
        label = f"segment {index}"
        if not isinstance(segment, dict):
            errors.append(f"{label} must be an object")
            continue
        segment_id = segment.get("segment_id")
        if not isinstance(segment_id, str) or not segment_id:
            errors.append(f"{label} has no segment_id")
        elif segment_id in segment_ids:
            errors.append(f"duplicate segment_id {segment_id!r}")
        else:
            segment_ids.add(segment_id)
        if segment.get("speaker") not in allowed_speakers:
            errors.append(f"{label} has unknown speaker {segment.get('speaker')!r}")
        text = segment.get("text")
        if not isinstance(text, str) or not text.strip():
            errors.append(f"{label} has empty text")
        source_ids = segment.get("source_story_ids", [])
        if not isinstance(source_ids, list):
            errors.append(f"{label}.source_story_ids must be an array")
            source_ids = []
        for story_id in source_ids:
            if story_id not in evidence_by_id:
                errors.append(f"{label} cites story outside the evidence packet: {story_id}")
            else:
                used_story_ids.add(story_id)
        kind = segment.get("kind", "host_dialogue")
        if kind == "quote":
            if len(source_ids) != 1:
                errors.append(f"{label} quote must cite exactly one story")
            elif isinstance(text, str) and source_ids[0] in evidence_by_id:
                source_text = evidence_by_id[source_ids[0]]["story_text"]
                if _normalize_quote(text) not in _normalize_quote(source_text):
                    errors.append(f"{label} quote is not verbatim in its source story")
        if kind not in {"host_dialogue", "quote", "transition"}:
            errors.append(f"{label} has unsupported kind {kind!r}")
        if (
            kind != "quote"
            and isinstance(text, str)
            and re.search(
                r"\b(?:AI hosts?|synthetic (?:hosts?|voices?)|"
                r"artificial intelligence hosts?)\b",
                text,
                flags=re.IGNORECASE,
            )
        ):
            errors.append(f"{label} discusses host generation technology on air")
        pause = segment.get("pause_after_ms", 0)
        if not isinstance(pause, int) or pause < 0 or pause > 10000:
            errors.append(f"{label}.pause_after_ms must be an integer from 0 to 10000")

    uncovered = sorted(set(evidence_by_id) - used_story_ids)
    if uncovered:
        errors.append(
            f"{len(uncovered)} evidence stories are unused: {', '.join(uncovered[:10])}"
            + ("…" if len(uncovered) > 10 else "")
        )
    return {
        "valid": not errors,
        "episode_id": episode_id,
        "segments": len(segments),
        "evidence_stories": len(evidence_by_id),
        "used_stories": len(used_story_ids),
        "errors": errors,
        "warnings": warnings,
    }


def prepare_tts_jobs(
    script_path: Path,
    show_bible_path: Path,
    output_path: Path,
    cache_dir: Path,
    *,
    provider: str,
    model: str,
) -> int:
    script = load_json(script_path)
    show_bible = load_json(show_bible_path)
    hosts = {host["id"]: host for host in show_bible["hosts"]}
    jobs = []
    segments = script["segments"]
    for index, segment in enumerate(segments):
        host = hosts.get(segment["speaker"])
        if host is None:
            raise ValueError(f"Unknown speaker {segment['speaker']!r}")
        voice_id = host.get("voice_id")
        if not voice_id:
            raise ValueError(
                f"Host {segment['speaker']!r} has no voice_id in the show bible"
            )
        render_text = render_tts_text(
            segment["text"],
            segment.get("pronunciation", {}),
            segment.get("delivery", {}),
            supports_audio_tags=model == "eleven_v3",
        )
        supports_context = model != "eleven_v3"
        previous_text = (
            segments[index - 1]["text"] if supports_context and index else None
        )
        next_text = (
            segments[index + 1]["text"]
            if supports_context and index + 1 < len(segments)
            else None
        )
        fingerprint = json.dumps(
            {
                "provider": provider,
                "model": model,
                "voice_id": voice_id,
                "render_text": render_text,
                "previous_text": previous_text,
                "next_text": next_text,
                "delivery": segment.get("delivery", {}),
                "pronunciation": segment.get("pronunciation", {}),
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        cache_key = hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()
        output_audio = (cache_dir / f"{cache_key}.wav").resolve()
        jobs.append(
            {
                "contract_version": 1,
                "episode_id": script["episode_id"],
                "segment_id": segment["segment_id"],
                "speaker": segment["speaker"],
                "display_name": host.get("display_name", segment["speaker"]),
                "accent": host.get("accent"),
                "provider": provider,
                "model": model,
                "voice_id": voice_id,
                "text": segment["text"],
                "render_text": render_text,
                "previous_text": previous_text,
                "next_text": next_text,
                "delivery": segment.get("delivery", {}),
                "pronunciation": segment.get("pronunciation", {}),
                "pause_after_ms": segment.get("pause_after_ms", 0),
                "source_story_ids": segment.get("source_story_ids", []),
                "cache_key": cache_key,
                "output_audio": str(output_audio),
                "cached": output_audio.exists(),
            }
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        for job in jobs:
            handle.write(json.dumps(job, ensure_ascii=False) + "\n")
    return len(jobs)


def render_tts_text(
    text: str,
    pronunciation: dict[str, Any],
    delivery: dict[str, Any] | None = None,
    *,
    supports_audio_tags: bool = True,
) -> str:
    if not isinstance(pronunciation, dict):
        raise ValueError("pronunciation must be an object")
    rendered = text
    for written, spoken in sorted(
        pronunciation.items(),
        key=lambda item: len(str(item[0])),
        reverse=True,
    ):
        if not isinstance(written, str) or not written:
            raise ValueError("pronunciation keys must be non-empty strings")
        if not isinstance(spoken, str) or not spoken:
            raise ValueError("pronunciation values must be non-empty strings")
        rendered = rendered.replace(written, spoken)
    if not supports_audio_tags:
        return rendered
    if delivery is None:
        delivery = {}
    if not isinstance(delivery, dict):
        raise ValueError("delivery must be an object")
    tags: list[str] = []
    tone = delivery.get("tone")
    if tone is not None:
        if not isinstance(tone, str) or not tone.strip():
            raise ValueError("delivery.tone must be a non-empty string")
        tags.append(tone.strip())
    audio_tags = delivery.get("audio_tags", [])
    if not isinstance(audio_tags, list):
        raise ValueError("delivery.audio_tags must be an array")
    for tag in audio_tags:
        if not isinstance(tag, str) or not tag.strip():
            raise ValueError("delivery.audio_tags entries must be non-empty strings")
        tags.append(tag.strip())
    normalized_tags = []
    for tag in tags:
        normalized = tag.removeprefix("[").removesuffix("]").strip()
        if normalized and normalized.casefold() not in {
            value.casefold() for value in normalized_tags
        }:
            normalized_tags.append(normalized)
    if not normalized_tags:
        return rendered
    return " ".join(f"[{tag}]" for tag in normalized_tags[:3]) + " " + rendered


def _normalize_quote(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()
