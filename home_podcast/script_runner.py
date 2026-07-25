from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .config import ProjectConfig
from .providers import CaprioleChatClient
from .script import validate_script


def generate_episode_script(
    config: ProjectConfig,
    evidence_path: Path,
    outline_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    if not config.script_provider:
        raise ValueError("script_provider is not configured")
    packet = _load_object(evidence_path)
    outline = _load_object(outline_path)
    episode_id = str(packet["episode"]["episode_id"])
    _validate_outline(outline, packet)

    prompt_path = config.project_root / "prompts" / "script_writer.md"
    prompt_text = prompt_path.read_text(encoding="utf-8")
    client = CaprioleChatClient.from_config(config.script_provider)
    recipe_hash = hashlib.sha256(
        (prompt_text + "\nchunked-story-card-script-v2").encode("utf-8")
    ).hexdigest()[:12]
    evidence_hash = hashlib.sha256(evidence_path.read_bytes()).hexdigest()[:16]
    cache_dir = (
        config.work_dir
        / "scripts"
        / "cache"
        / _safe_component(client.model)
        / recipe_hash
        / f"{episode_id}-{evidence_hash}"
    )
    cache_dir.mkdir(parents=True, exist_ok=True)

    evidence_by_id = {
        story["story_id"]: story for story in packet["evidence"]
    }
    all_segments: list[dict[str, Any]] = []
    total_usage: dict[str, int] = {}
    generated_calls = 0
    cached_calls = 0
    sections = [
        (movement, section)
        for movement in outline["movements"]
        for section in movement["sections"]
    ]
    for global_sequence, (movement, section) in enumerate(sections, start=1):
        section_evidence = [
            evidence_by_id[story_id] for story_id in section["story_ids"]
        ]
        request_text = _build_section_prompt(
            prompt_text,
            packet,
            outline,
            movement,
            section,
            global_sequence,
            len(sections),
            section_evidence,
        )
        request_hash = hashlib.sha256(request_text.encode("utf-8")).hexdigest()[:16]
        cache_path = cache_dir / (
            f"{global_sequence:02d}-{section['section_id']}-{request_hash}.json"
        )
        if cache_path.exists():
            cache_record = _load_object(cache_path)
            cached_calls += 1
            state = "cached"
        else:
            response = client.complete(request_text)
            cache_record = {
                "provider": "capriole",
                "model": response.model,
                "request_id": response.request_id,
                "usage": response.usage,
                "recipe_hash": recipe_hash,
                "evidence_hash": evidence_hash,
                "request_hash": request_hash,
                "text": response.text,
            }
            _write_json_atomic(cache_path, cache_record)
            generated_calls += 1
            state = "generated"
        for key, value in cache_record.get("usage", {}).items():
            total_usage[key] = total_usage.get(key, 0) + int(value)
        section_result = _parse_script_output(str(cache_record["text"]))
        section_segments = section_result.get("segments")
        if not isinstance(section_segments, list) or not section_segments:
            raise ValueError(f"Section {section['section_id']} returned no segments")
        all_segments.extend(
            _normalize_movement_segments(
                section_segments,
                global_sequence,
                evidence_by_id,
            )
        )
        print(
            f"[section {global_sequence}/{len(sections)}] "
            f"{state}: {movement['title']} / {section['section_id']}",
            flush=True,
        )

    script = {
        "contract_version": 1,
        "episode_id": episode_id,
        "title": str(packet["episode"]["title"]),
        "segments": all_segments,
    }
    candidate_path = config.work_dir / "scripts" / f"{episode_id}-candidate.json"
    _write_json_atomic(candidate_path, script)
    report = validate_script(
        candidate_path,
        evidence_path,
        config.show_bible_path,
    )
    report.update(_script_metrics(script))
    if report["valid"]:
        _write_json_atomic(output_path, script)
    return {
        "episode_id": episode_id,
        "valid": report["valid"],
        "generated_calls": generated_calls,
        "cached_calls": cached_calls,
        "model": client.model,
        "usage": total_usage,
        "outline": str(outline_path),
        "output": str(output_path) if report["valid"] else None,
        "candidate": str(candidate_path),
        "cache_dir": str(cache_dir),
        "validation": report,
    }


def _build_section_prompt(
    instructions: str,
    packet: dict[str, Any],
    outline: dict[str, Any],
    movement: dict[str, Any],
    section: dict[str, Any],
    global_sequence: int,
    section_count: int,
    evidence: list[dict[str, Any]],
) -> str:
    episode = packet["episode"]
    placement_rules = {
        1: (
            "This is the opening section. Start with a cold open, then introduce "
            "the show and include the disclosure that every host voice is synthetic. "
            "Explain once that December 2013 is capture time, not publication time."
        ),
        section_count: (
            "This is the final section. Do not reintroduce the show. End with an "
            "emotional callback and an honest statement about what the archive "
            "cannot tell us."
        ),
    }
    placement = placement_rules.get(
        global_sequence,
        "This is a middle section. Begin with a natural handoff and do not "
        "reintroduce the show.",
    )
    compact_evidence = [
        _compact_evidence_story(story) for story in evidence
    ]
    segment_contract = {
        "segments": [
            {
                "segment_id": "locally unique string",
                "speaker": "curious_guide | archive_nerd | connector",
                "kind": "host_dialogue | quote | disclosure | transition",
                "text": "spoken words only",
                "source_story_ids": ["story ID(s) supporting this turn"],
                "delivery": {},
                "pronunciation": {},
                "pause_after_ms": 0,
            }
        ]
    }
    return (
        f"{instructions.rstrip()}\n\n"
        "SECTION PRODUCTION BRIEF\n"
        f"- This is section {global_sequence} of {section_count} in one continuous episode.\n"
        f"- Episode: {episode['title']} ({episode['episode_id']}).\n"
        f"- Movement title: {movement['title']}.\n"
        f"- Section purpose: {section['purpose']}\n"
        f"- Target approximately {section['target_words']} spoken words and do not "
        f"exceed {int(section['target_words']) + 50} words.\n"
        f"- Ending handoff: {movement['ending_handoff']}\n"
        f"- Placement: {placement}\n"
        "- Use every supplied story and include each story ID in source_story_ids "
        "at least once. Do not speak IDs aloud.\n"
        "- Keep this a lively three-host conversation, not three essays. Use short "
        "responsive turns and let emotionally difficult material breathe.\n"
        "- Use kind=quote only when the entire text is copied verbatim from exactly "
        "one memorable_passages entry. Prefer grounded paraphrase if uncertain.\n"
        "- Treat each story_card summary as the boundary for factual claims. The "
        "full source was used to create the card and remains available for later "
        "validation, but is intentionally omitted here to fit the provider gateway.\n"
        "- Return one raw JSON object with only a segments array. No Markdown fences "
        "or outside commentary.\n\n"
        "SEGMENT CONTRACT EXAMPLE\n"
        f"{json.dumps(segment_contract, ensure_ascii=False, separators=(',', ':'))}\n\n"
        "EPISODE MAP\n"
        f"{json.dumps(_compact_episode_map(outline), ensure_ascii=False, separators=(',', ':'))}\n\n"
        "HOST ROLES\n"
        f"{json.dumps(_compact_show_bible(packet['show_bible']), ensure_ascii=False, separators=(',', ':'))}\n\n"
        "EVIDENCE FOR THIS SECTION\n"
        f"{json.dumps(compact_evidence, ensure_ascii=False, separators=(',', ':'))}"
    )


def _compact_evidence_story(story: dict[str, Any]) -> dict[str, Any]:
    card = story.get("story_card")
    if not isinstance(card, dict):
        raise ValueError(
            f"Story {story.get('story_id')} has no current story card"
        )
    card_fields = (
        "summary",
        "emotional_tone",
        "digital_archaeology_angles",
        "memorable_passages",
        "sensitivity_notes",
        "pronunciation_items",
    )
    return {
        "story_id": story["story_id"],
        "language": story.get("language"),
        "crawl_timestamp": story.get("crawl_timestamp"),
        "source_url": story.get("source_url"),
        "usage_type": story.get("usage_type"),
        "anchor_score": story.get("anchor_score"),
        "theme_fit": story.get("theme_fit"),
        "quality_flags": story.get("quality_flags", []),
        "story_card": {key: card[key] for key in card_fields if key in card},
    }


def _compact_episode_map(outline: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": outline["title"],
        "movements": [
            {
                "sequence": movement["sequence"],
                "title": movement["title"],
                "purpose": movement["purpose"],
                "ending_handoff": movement["ending_handoff"],
            }
            for movement in outline["movements"]
        ],
    }


def _compact_show_bible(show_bible: dict[str, Any]) -> dict[str, Any]:
    return {
        "promise": show_bible["promise"],
        "hosts": [
            {
                "id": host["id"],
                "display_name": host["display_name"],
                "role": host["role"],
                "writing_profile": host["writing_profile"],
            }
            for host in show_bible["hosts"]
        ],
    }


def _compact_evidence_packet(packet: dict[str, Any]) -> dict[str, Any]:
    return {
        "episode": packet["episode"],
        "show_bible": packet["show_bible"],
        "evidence": [
            _compact_evidence_story(story) for story in packet["evidence"]
        ],
        "writing_requirements": packet["writing_requirements"],
    }


def _validate_outline(
    outline: dict[str, Any],
    packet: dict[str, Any],
) -> None:
    episode_id = packet["episode"]["episode_id"]
    if outline.get("episode_id") != episode_id:
        raise ValueError(f"Outline episode_id must be {episode_id}")
    movements = outline.get("movements")
    if not isinstance(movements, list) or not movements:
        raise ValueError("Outline must contain at least one movement")
    sequences = [movement.get("sequence") for movement in movements]
    if sequences != list(range(1, len(movements) + 1)):
        raise ValueError("Outline movement sequences must be consecutive from 1")
    assigned = [
        story_id
        for movement in movements
        for section in movement.get("sections", [])
        for story_id in section.get("story_ids", [])
    ]
    expected = [story["story_id"] for story in packet["evidence"]]
    duplicates = sorted(
        story_id for story_id in set(assigned) if assigned.count(story_id) > 1
    )
    if duplicates:
        raise ValueError(f"Outline repeats stories: {', '.join(duplicates)}")
    missing = sorted(set(expected) - set(assigned))
    unknown = sorted(set(assigned) - set(expected))
    if missing or unknown:
        raise ValueError(
            f"Outline coverage mismatch; missing={missing}, unknown={unknown}"
        )
    for movement in movements:
        section_story_ids = [
            story_id
            for section in movement.get("sections", [])
            for story_id in section.get("story_ids", [])
        ]
        if section_story_ids != movement.get("story_ids"):
            raise ValueError(
                f"Movement {movement.get('movement_id')} section stories must "
                "match its story_ids in order"
            )


def _normalize_movement_segments(
    segments: list[Any],
    movement_sequence: int,
    evidence_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for index, original in enumerate(segments, start=1):
        if not isinstance(original, dict):
            raise ValueError(
                f"Movement {movement_sequence} segment {index} is not an object"
            )
        segment = dict(original)
        segment["segment_id"] = f"m{movement_sequence}-s{index:03d}"
        if segment.get("kind") == "quote":
            source_ids = segment.get("source_story_ids", [])
            text = segment.get("text")
            if (
                isinstance(text, str)
                and isinstance(source_ids, list)
                and len(source_ids) == 1
                and source_ids[0] in evidence_by_id
            ):
                source_text = str(evidence_by_id[source_ids[0]]["story_text"])
                stripped = text.strip().strip("\"'“”‘’")
                if (
                    _normalize_quote(text) not in _normalize_quote(source_text)
                    and _normalize_quote(stripped) in _normalize_quote(source_text)
                ):
                    segment["text"] = stripped
        normalized.append(segment)
    return normalized


def _parse_script_output(text: str) -> dict[str, Any]:
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
            raise ValueError("Model output did not contain a JSON object")
        try:
            value = json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError as error:
            raise ValueError(f"Model output contained invalid JSON: {error}") from error
    if not isinstance(value, dict):
        raise ValueError("Model output must be a JSON object")
    return value


def _script_metrics(script: dict[str, Any]) -> dict[str, Any]:
    segments = script.get("segments")
    if not isinstance(segments, list):
        return {"spoken_words": 0, "spoken_characters": 0, "estimated_minutes": 0}
    texts = [
        str(segment.get("text", ""))
        for segment in segments
        if isinstance(segment, dict)
    ]
    words = sum(len(re.findall(r"\b[\w'-]+\b", text)) for text in texts)
    characters = sum(len(text) for text in texts)
    return {
        "spoken_words": words,
        "spoken_characters": characters,
        "estimated_minutes": round(words / 150, 1),
    }


def _normalize_quote(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def _load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return value


def _safe_component(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value)


def _write_json_atomic(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
