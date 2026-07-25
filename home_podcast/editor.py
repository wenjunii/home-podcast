from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .config import ProjectConfig
from .providers import CaprioleChatClient
from .script import validate_script


def trim_episode_script(
    config: ProjectConfig,
    script_path: Path,
    evidence_path: Path,
    output_path: Path,
    *,
    target_words_min: int = 4400,
    target_words_max: int = 4600,
    plan_path: Path | None = None,
) -> dict[str, Any]:
    if target_words_min < 1 or target_words_max < target_words_min:
        raise ValueError("Invalid target word range")
    script = _load_object(script_path)
    evidence = _load_object(evidence_path)
    if plan_path is not None:
        plan = _load_object(plan_path)
        if plan.get("episode_id") != script.get("episode_id"):
            raise ValueError("Saved trim plan episode_id does not match the script")
        expected_hash = plan.get("source_script_sha256")
        actual_hash = _canonical_object_hash(script)
        if expected_hash and expected_hash != actual_hash:
            raise ValueError(
                "Saved trim plan source hash does not match the current script"
            )
        generated = False
        model = "saved-editorial-plan"
        usage: dict[str, int] = {}
        cache_value: str | None = None
    else:
        if not config.script_provider:
            raise ValueError("script_provider is not configured")
        instructions_path = config.project_root / "prompts" / "script_editor.md"
        instructions = instructions_path.read_text(encoding="utf-8")
        client = CaprioleChatClient.from_config(config.script_provider)
        prompt = _build_trim_prompt(
            instructions,
            script,
            evidence,
            target_words_min,
            target_words_max,
        )
        prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16]
        recipe_hash = hashlib.sha256(instructions.encode("utf-8")).hexdigest()[:12]
        cache_dir = (
            config.work_dir
            / "scripts"
            / "editing"
            / _safe_component(client.model)
            / recipe_hash
        )
        cache_path = cache_dir / f"{script['episode_id']}-{prompt_hash}.json"
        generated = not cache_path.exists()
        if generated:
            response = client.complete(prompt)
            cache_record = {
                "provider": "capriole",
                "model": response.model,
                "request_id": response.request_id,
                "usage": response.usage,
                "prompt_hash": prompt_hash,
                "text": response.text,
            }
            _write_json_atomic(cache_path, cache_record)
        else:
            cache_record = _load_object(cache_path)
        plan = _parse_trim_plan(str(cache_record["text"]))
        model = str(cache_record.get("model", client.model))
        usage = cache_record.get("usage", {})
        cache_value = str(cache_path)
    candidate, trim_metrics = _apply_deletion_plan(script, plan)
    candidate_path = (
        config.work_dir / "scripts" / f"{script['episode_id']}-trimmed-candidate.json"
    )
    _write_json_atomic(candidate_path, candidate)
    validation = validate_script(
        candidate_path,
        evidence_path,
        config.show_bible_path,
    )
    words = _spoken_words(candidate)
    if words < target_words_min or words > target_words_max:
        validation["errors"].append(
            f"Trimmed script has {words} words; target is "
            f"{target_words_min}-{target_words_max}"
        )
        validation["valid"] = False
    if validation["valid"]:
        _write_json_atomic(output_path, candidate)
    return {
        "episode_id": script["episode_id"],
        "valid": validation["valid"],
        "generated": generated,
        "model": model,
        "usage": usage,
        "output": str(output_path) if validation["valid"] else None,
        "candidate": str(candidate_path),
        "cache": cache_value,
        "plan": str(plan_path) if plan_path is not None else None,
        "editorial_note": plan.get("editorial_note", ""),
        **trim_metrics,
        "final_words": words,
        "estimated_minutes": round(words / 150, 1),
        "validation": validation,
    }


def _build_trim_prompt(
    instructions: str,
    script: dict[str, Any],
    evidence: dict[str, Any],
    target_words_min: int,
    target_words_max: int,
) -> str:
    story_ids = [story["story_id"] for story in evidence["evidence"]]
    compact_segments = [
        {
            "segment_id": segment["segment_id"],
            "speaker": segment["speaker"],
            "kind": segment["kind"],
            "text": segment["text"],
            "source_story_ids": segment.get("source_story_ids", []),
        }
        for segment in script["segments"]
    ]
    return (
        f"{instructions.rstrip()}\n\n"
        "EDIT TARGET\n"
        f"- Current words: {_spoken_words(script)}\n"
        f"- Required final range: {target_words_min}-{target_words_max} words\n"
        f"- Required story IDs: {json.dumps(story_ids, ensure_ascii=False)}\n\n"
        "SCRIPT SEGMENTS\n"
        f"{json.dumps(compact_segments, ensure_ascii=False, separators=(',', ':'))}"
    )


def _parse_trim_plan(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("Editor output did not contain a JSON object")
        value = json.loads(cleaned[start : end + 1])
    if not isinstance(value, dict):
        raise ValueError("Editor output must be a JSON object")
    delete_ids = value.get("delete_segment_ids")
    if not isinstance(delete_ids, list) or not all(
        isinstance(item, str) for item in delete_ids
    ):
        raise ValueError("delete_segment_ids must be an array of strings")
    if len(delete_ids) != len(set(delete_ids)):
        raise ValueError("delete_segment_ids contains duplicates")
    return value


def _apply_deletion_plan(
    script: dict[str, Any],
    plan: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, int]]:
    segments = script.get("segments")
    if not isinstance(segments, list):
        raise ValueError("Script segments must be an array")
    by_id = {segment["segment_id"]: segment for segment in segments}
    if len(by_id) != len(segments):
        raise ValueError("Script contains duplicate segment IDs")
    delete_ids = set(plan["delete_segment_ids"])
    unknown = sorted(delete_ids - set(by_id))
    if unknown:
        raise ValueError(f"Trim plan references unknown segments: {unknown}")
    protected = sorted(
        segment_id
        for segment_id in delete_ids
        if by_id[segment_id].get("kind") == "quote"
    )
    if protected:
        raise ValueError(
            f"Trim plan attempts to delete protected segments: {protected}"
        )
    replacements = plan.get("replace_segments", [])
    if not isinstance(replacements, list):
        raise ValueError("replace_segments must be an array")
    replacement_by_id: dict[str, str] = {}
    for replacement in replacements:
        if not isinstance(replacement, dict):
            raise ValueError("Each replace_segments item must be an object")
        segment_id = replacement.get("segment_id")
        text = replacement.get("text")
        if (
            not isinstance(segment_id, str)
            or segment_id not in by_id
            or not isinstance(text, str)
            or not text.strip()
        ):
            raise ValueError("Invalid transition replacement")
        if segment_id in replacement_by_id:
            raise ValueError(f"Duplicate transition replacement: {segment_id}")
        if by_id[segment_id].get("kind") != "transition":
            raise ValueError(
                f"Only transition segments may be replaced: {segment_id}"
            )
        if segment_id in delete_ids:
            raise ValueError(
                f"Segment cannot be both deleted and replaced: {segment_id}"
            )
        replacement_by_id[segment_id] = text
    original_sections = {
        segment["segment_id"].split("-", 1)[0] for segment in segments
    }
    kept = []
    for original in segments:
        if original["segment_id"] in delete_ids:
            continue
        segment = dict(original)
        replacement = replacement_by_id.get(segment["segment_id"])
        if replacement is not None:
            segment["text"] = replacement
        kept.append(segment)
    kept_sections = {
        segment["segment_id"].split("-", 1)[0] for segment in kept
    }
    if kept_sections != original_sections:
        raise ValueError("Trim plan removes an entire generation section")
    candidate = {**script, "segments": kept}
    original_words = _spoken_words(script)
    final_words = _spoken_words(candidate)
    return candidate, {
        "deleted_segments": len(delete_ids),
        "deleted_words": original_words - final_words,
        "original_words": original_words,
        "replaced_transitions": len(replacement_by_id),
    }


def _spoken_words(script: dict[str, Any]) -> int:
    segments = script.get("segments", [])
    return sum(
        len(re.findall(r"\b[\w'-]+\b", str(segment.get("text", ""))))
        for segment in segments
        if isinstance(segment, dict)
    )


def _load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return value


def _safe_component(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value)


def _canonical_object_hash(value: dict[str, Any]) -> str:
    serialized = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _write_json_atomic(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
