from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .config import ProjectConfig
from .providers import CaprioleChatClient
from .script import render_tts_text, validate_script


def polish_episode_conversation(
    config: ProjectConfig,
    script_path: Path,
    evidence_path: Path,
    cast_path: Path,
    output_path: Path,
    *,
    target_words_min: int = 4400,
    target_words_max: int = 4600,
    max_new_calls: int | None = None,
) -> dict[str, Any]:
    if not config.script_provider:
        raise ValueError("script_provider is not configured")
    script = _load_object(script_path)
    episode_cast = _load_object(cast_path)
    if episode_cast.get("episode_id") != script.get("episode_id"):
        raise ValueError("Episode cast does not match the script")
    source_segments = [
        segment
        for segment in script.get("segments", [])
        if segment.get("kind") != "disclosure"
    ]
    if not source_segments:
        raise ValueError("Script has no polishable segments")

    instructions_path = config.project_root / "prompts" / "conversation_polisher.md"
    instructions = instructions_path.read_text(encoding="utf-8")
    client = CaprioleChatClient.from_config(config.script_provider)
    recipe_hash = hashlib.sha256(instructions.encode("utf-8")).hexdigest()[:12]
    source_hash = _canonical_hash({**script, "segments": source_segments})[:16]
    cache_dir = (
        config.work_dir
        / "scripts"
        / "conversation-polish"
        / _safe_component(client.model)
        / recipe_hash
        / f"{script['episode_id']}-{source_hash}"
    )
    cache_dir.mkdir(parents=True, exist_ok=True)

    groups = _segment_groups(source_segments)
    polished_segments: list[dict[str, Any]] = []
    completed_groups = 0
    generated_calls = 0
    cached_calls = 0
    total_usage: dict[str, int] = {}
    for group_index, (group_id, segments) in enumerate(groups, start=1):
        start_index = source_segments.index(segments[0])
        end_index = start_index + len(segments)
        previous_turn = (
            source_segments[start_index - 1]["text"] if start_index else None
        )
        next_turn = (
            source_segments[end_index]["text"]
            if end_index < len(source_segments)
            else None
        )
        prompt = _build_polish_prompt(
            instructions,
            episode_cast,
            segments,
            previous_turn=previous_turn,
            next_turn=next_turn,
        )
        prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16]
        cache_path = cache_dir / f"{group_index:02d}-{group_id}-{prompt_hash}.json"
        if cache_path.exists():
            cache_record = _load_object(cache_path)
            cached_calls += 1
            state = "cached"
        else:
            if max_new_calls is not None and generated_calls >= max(0, max_new_calls):
                break
            response = client.complete(prompt)
            cache_record = {
                "provider": "capriole",
                "model": response.model,
                "request_id": response.request_id,
                "usage": response.usage,
                "recipe_hash": recipe_hash,
                "source_hash": source_hash,
                "prompt_hash": prompt_hash,
                "text": response.text,
            }
            _write_json_atomic(cache_path, cache_record)
            generated_calls += 1
            state = "generated"
        for key, value in cache_record.get("usage", {}).items():
            total_usage[key] = total_usage.get(key, 0) + int(value)
        result = _parse_polish_output(
            str(cache_record["text"]),
            originals=segments,
        )
        polished = _validate_polished_group(segments, result["segments"])
        polished_segments.extend(polished)
        completed_groups += 1
        print(
            f"[polish {group_index}/{len(groups)}] {state}: {group_id}",
            flush=True,
        )

    if completed_groups < len(groups):
        return {
            "episode_id": script["episode_id"],
            "complete": False,
            "generated_calls": generated_calls,
            "cached_calls": cached_calls,
            "completed_groups": completed_groups,
            "total_groups": len(groups),
            "model": client.model,
            "usage": total_usage,
            "cache_dir": str(cache_dir),
        }

    candidate = {
        **script,
        "segments": polished_segments,
    }
    candidate_path = (
        config.work_dir
        / "scripts"
        / f"{script['episode_id']}-conversation-candidate.json"
    )
    _write_json_atomic(candidate_path, candidate)
    validation = validate_script(
        candidate_path,
        evidence_path,
        config.show_bible_path,
    )
    words = _spoken_words(candidate)
    if not target_words_min <= words <= target_words_max:
        validation["errors"].append(
            f"Polished script has {words} words; target is "
            f"{target_words_min}-{target_words_max}"
        )
        validation["valid"] = False
    if validation["valid"]:
        _write_json_atomic(output_path, candidate)
    return {
        "episode_id": script["episode_id"],
        "complete": True,
        "valid": validation["valid"],
        "generated_calls": generated_calls,
        "cached_calls": cached_calls,
        "model": client.model,
        "usage": total_usage,
        "removed_disclosure_segments": len(script["segments"]) - len(source_segments),
        "segments": len(polished_segments),
        "spoken_words": words,
        "estimated_minutes": round(words / 150, 1),
        "output": str(output_path) if validation["valid"] else None,
        "candidate": str(candidate_path),
        "cache_dir": str(cache_dir),
        "validation": validation,
    }


def _build_polish_prompt(
    instructions: str,
    episode_cast: dict[str, Any],
    segments: list[dict[str, Any]],
    *,
    previous_turn: str | None,
    next_turn: str | None,
) -> str:
    cast = [
        {
            "speaker": host["id"],
            "display_name": host["display_name"],
        }
        for host in episode_cast["hosts"]
    ]
    boundary_context = {
        "previous_turn": previous_turn,
        "next_turn": next_turn,
    }
    return (
        f"{instructions.rstrip()}\n\n"
        "CURRENT EPISODE CAST\n"
        f"{json.dumps(cast, ensure_ascii=False, separators=(',', ':'))}\n\n"
        "BOUNDARY CONTEXT — DO NOT RETURN OR REWRITE THESE TURNS\n"
        f"{json.dumps(boundary_context, ensure_ascii=False, separators=(',', ':'))}\n\n"
        f"ORIGINAL SECTION WORDS: {_spoken_words({'segments': segments})}\n\n"
        "SEGMENTS TO POLISH\n"
        f"{json.dumps({'segments': segments}, ensure_ascii=False, separators=(',', ':'))}"
    )


def _validate_polished_group(
    originals: list[dict[str, Any]],
    polished: Any,
) -> list[dict[str, Any]]:
    if not isinstance(polished, list) or len(polished) != len(originals):
        raise ValueError("Polisher must return every segment exactly once")
    protected_fields = (
        "segment_id",
        "speaker",
        "kind",
        "source_story_ids",
        "pronunciation",
        "pause_after_ms",
    )
    checked: list[dict[str, Any]] = []
    for original, candidate in zip(originals, polished):
        if not isinstance(candidate, dict):
            raise ValueError("Every polished segment must be an object")
        for field in protected_fields:
            if candidate.get(field, _missing()) != original.get(field, _missing()):
                raise ValueError(
                    f"Polisher changed protected field {field!r} in "
                    f"{original['segment_id']}"
                )
        text = candidate.get("text")
        if not isinstance(text, str) or not text.strip():
            raise ValueError(f"Polisher returned empty text for {original['segment_id']}")
        if original.get("kind") == "quote":
            text = str(original["text"])
        delivery = candidate.get("delivery", {})
        render_tts_text(
            text,
            candidate.get("pronunciation", {}),
            delivery,
            supports_audio_tags=True,
        )
        checked.append(
            {
                **original,
                "text": text,
                "delivery": delivery,
            }
        )
    original_words = _spoken_words({"segments": originals})
    polished_words = _spoken_words({"segments": checked})
    lower = max(1, round(original_words * 0.9))
    upper = round(original_words * 1.1)
    if not lower <= polished_words <= upper:
        raise ValueError(
            f"Polished group has {polished_words} words; expected {lower}-{upper}"
        )
    return checked


def _segment_groups(
    segments: list[dict[str, Any]],
) -> list[tuple[str, list[dict[str, Any]]]]:
    groups: list[tuple[str, list[dict[str, Any]]]] = []
    for segment in segments:
        group_id = str(segment["segment_id"]).split("-", 1)[0]
        if not groups or groups[-1][0] != group_id:
            groups.append((group_id, []))
        groups[-1][1].append(segment)
    return groups


def _parse_polish_output(
    text: str,
    *,
    originals: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    if originals:
        cleaned = _restore_protected_quote_fields(cleaned, originals)
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("Polisher output did not contain a JSON object")
        value = json.loads(cleaned[start : end + 1])
    if not isinstance(value, dict) or not isinstance(value.get("segments"), list):
        raise ValueError("Polisher output must contain a segments array")
    return value


def _restore_protected_quote_fields(
    value: str,
    originals: list[dict[str, Any]],
) -> str:
    repaired = value
    for segment in originals:
        if segment.get("kind") != "quote":
            continue
        segment_id = re.escape(str(segment["segment_id"]))
        segment_match = re.search(
            rf'"segment_id"\s*:\s*"{segment_id}"',
            repaired,
        )
        if segment_match is None:
            continue
        text_match = re.search(
            r'"text"\s*:\s*',
            repaired[segment_match.end() :],
        )
        if text_match is None:
            continue
        value_start = segment_match.end() + text_match.end()
        source_match = re.search(
            r',\s*"source_story_ids"\s*:',
            repaired[value_start:],
        )
        if source_match is None:
            continue
        value_end = value_start + source_match.start()
        repaired = (
            repaired[:value_start]
            + json.dumps(str(segment["text"]), ensure_ascii=False)
            + repaired[value_end:]
        )
    return repaired


def _spoken_words(script: dict[str, Any]) -> int:
    return sum(
        len(re.findall(r"\b[\w'-]+\b", str(segment.get("text", ""))))
        for segment in script.get("segments", [])
        if isinstance(segment, dict)
    )


def _canonical_hash(value: dict[str, Any]) -> str:
    serialized = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _missing() -> object:
    return _MISSING


_MISSING = object()


def _safe_component(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value)


def _load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return value


def _write_json_atomic(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
