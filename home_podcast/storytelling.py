from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .config import ProjectConfig
from .database import connect
from .storytelling_duration import require_story_text_budget
from .storytelling_quality import content_digest


STORYTELLING_CONTRACT_VERSION = 1
_FIRST_PERSON_PATTERNS = {
    "en": re.compile(
        r"(?:\bI\b|(?i:\b(?:me|my|mine|myself|we|us|our|ours|ourselves)\b))",
    ),
    "fr": re.compile(
        r"\b(?:je|moi|mon|ma|mes|nous|notre|nos)\b|\bj['’]",
        re.IGNORECASE,
    ),
    "it": re.compile(r"\b(?:io|me|mio|mia|miei|mie|noi|nostro|nostra)\b", re.I),
    "pt": re.compile(r"\b(?:eu|meu|minha|meus|minhas|nós|nosso|nossa)\b", re.I),
    "no": re.compile(r"\b(?:jeg|meg|min|mitt|mine|vi|oss|vår|vårt|våre)\b", re.I),
    "sv": re.compile(r"\b(?:jag|mig|min|mitt|mina|vi|oss|vår|vårt|våra)\b", re.I),
}
_ALLOWED_PERSPECTIVES = {
    "first_person_preserved",
    "attributed_first_person",
}
_ALLOWED_PACES = {"very_slow", "slow", "measured", "conversational", "quick"}
_ALLOWED_NONVERBAL = {
    "breath",
    "soft_laugh",
    "chuckle",
    "sigh",
    "hesitation",
    "voice_catch",
    "whispered_emphasis",
}
_ALLOWED_ENERGY = {"very_low", "low", "medium", "high", "variable"}
_IDENTITY_TRAITS = {
    "narrator_gender_presentation",
    "narrator_accent",
    "narrator_language",
    "narrator_age_presentation",
    "narrator_role",
    "narrator_race",
    "narrator_ethnicity",
    "narrator_nationality",
    "narrator_religion",
    "narrator_disability",
    "narrator_class",
    "other",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return value


def _read_jsonl(path: Path) -> Iterable[tuple[int, dict[str, Any]]]:
    with path.open(encoding="utf-8-sig") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"Line {line_number}: expected a JSON object")
            yield line_number, value


def narration_id(month: str, story_id: str) -> str:
    if not re.fullmatch(r"\d{4}-\d{2}", month):
        raise ValueError("month must use YYYY-MM")
    if not re.fullmatch(r"story-[a-f0-9]{24}", story_id):
        raise ValueError(f"Invalid story ID: {story_id}")
    return f"{month}--{story_id}"


def _editorial_decisions(config: ProjectConfig, month: str) -> dict[str, Any]:
    path = (
        config.project_root
        / "series"
        / month
        / "storytelling-editorial-decisions.json"
    )
    if not path.exists():
        return {"exclusions": [], "splits": []}
    decisions = _read_json(path)
    if decisions.get("archive_volume") != month:
        raise ValueError(f"Editorial decisions do not match archive volume {month}")
    return decisions


def _partition_story_text(
    story_text: str,
    *,
    start_marker: str,
    end_marker: str,
) -> str:
    start = story_text.find(start_marker)
    if start < 0:
        raise ValueError(f"Split start marker is absent: {start_marker!r}")
    if story_text.find(start_marker, start + 1) >= 0:
        raise ValueError(f"Split start marker is not unique: {start_marker!r}")
    end_start = story_text.find(end_marker, start)
    if end_start < 0:
        raise ValueError(f"Split end marker is absent after its start: {end_marker!r}")
    if story_text.find(end_marker, end_start + 1) >= 0:
        raise ValueError(f"Split end marker is not unique: {end_marker!r}")
    return story_text[start : end_start + len(end_marker)].strip()


def _require_storytelling_mode(config: ProjectConfig) -> None:
    if config.production_mode != "self_narrated_storytelling":
        raise ValueError(
            "Storytelling commands require a config with "
            "production_mode=self_narrated_storytelling"
        )


def _context_excerpt(text: str, position: int, limit: int = 700) -> str:
    left_candidates = [
        text.rfind(value, 0, position) for value in (". ", "? ", "! ", "\n\n")
    ]
    left = max(left_candidates)
    left = 0 if left < 0 else left + (2 if text[left : left + 2] != "\n\n" else 2)
    right_candidates = [
        found
        for value in (". ", "? ", "! ", "\n\n")
        if (found := text.find(value, position)) >= 0
    ]
    right = min(right_candidates) + 1 if right_candidates else len(text)
    if right - left > limit:
        left = max(0, position - limit // 3)
        right = min(len(text), left + limit)
    return text[left:right].strip()


def first_person_profile(text: str, language: str) -> dict[str, Any]:
    pattern = _FIRST_PERSON_PATTERNS.get(language, _FIRST_PERSON_PATTERNS["en"])
    matches = list(pattern.finditer(text))
    paragraph_indexes: set[int] = set()
    evidence: list[str] = []
    for match in matches:
        paragraph_indexes.add(text.count("\n\n", 0, match.start()))
        excerpt = _context_excerpt(text, match.start())
        if excerpt and excerpt not in evidence:
            evidence.append(excerpt)
        if len(evidence) >= 6:
            break
    if not matches:
        preference = "unsupported_first_person"
        strength = "none"
    else:
        preference = "first_person_preserved"
        strength = (
            "strong"
            if len(matches) >= 3 and (len(paragraph_indexes) >= 2 or len(matches) >= 6)
            else "possible_requires_editorial_confirmation"
        )
    return {
        "preferred_perspective": preference,
        "preference_strength": strength,
        "first_person_marker_count": len(matches),
        "first_person_paragraph_count": len(paragraph_indexes),
        "first_person_evidence": evidence,
        "policy": (
            "Use supported first person only. Hold the story when the recovered "
            "source cannot safely establish a narrator who can say I."
        ),
    }


def _current_story_rows(config: ProjectConfig, month: str) -> list[Any]:
    connection = connect(config.catalog_path)
    rows = connection.execute(
        """
        SELECT s.*,
               (
                   SELECT c.card_json
                     FROM story_cards AS c
                    WHERE c.story_id = s.id
                      AND c.content_hash = s.content_hash
                    ORDER BY c.created_at DESC
                    LIMIT 1
               ) AS card_json
          FROM stories AS s
         WHERE s.is_present = 1
           AND s.duplicate_of IS NULL
           AND s.crawl_month = ?
         ORDER BY s.crawl_timestamp, s.language, s.id
        """,
        (month,),
    ).fetchall()
    connection.close()
    return rows


def create_storytelling_plan(
    config: ProjectConfig,
    month: str,
    output_path: Path,
) -> dict[str, Any]:
    _require_storytelling_mode(config)
    rows = _current_story_rows(config, month)
    if not rows:
        raise ValueError(f"No present, unique stories found for crawl month {month}")
    narrations = []
    unanalyzed = []
    ineligible = []
    held_no_first_person = []
    editorially_excluded = []
    split_source_stories = []
    perspective_counts: dict[str, int] = {}
    decisions = _editorial_decisions(config, month)
    exclusions = {
        value["source_story_id"]: value
        for value in decisions.get("exclusions", [])
    }
    splits = {
        value["source_story_id"]: value for value in decisions.get("splits", [])
    }
    for row in rows:
        if not row["card_json"]:
            unanalyzed.append(row["id"])
            continue
        card = json.loads(row["card_json"])
        if not card.get("eligible", False):
            ineligible.append(
                {
                    "story_id": row["id"],
                    "reason": str(card.get("exclusion_reason") or "Not eligible"),
                }
            )
            continue
        exclusion = exclusions.get(row["id"])
        if exclusion:
            editorially_excluded.append(
                {
                    "story_id": row["id"],
                    "reason": str(exclusion["reason"]),
                    "classification": str(exclusion["classification"]),
                }
            )
            continue
        split = splits.get(row["id"])
        if split:
            split_entries = []
            for part in split.get("parts", []):
                part_id = str(part["part_id"])
                if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", part_id):
                    raise ValueError(f"Invalid storytelling split part ID: {part_id!r}")
                part_text = _partition_story_text(
                    row["story_text"],
                    start_marker=str(part["start_marker"]),
                    end_marker=str(part["end_marker"]),
                )
                part_language = str(part.get("source_language") or row["language"])
                part_perspective = first_person_profile(part_text, part_language)
                if part_perspective["preferred_perspective"] == "unsupported_first_person":
                    raise ValueError(
                        f"Split part {row['id']}:{part_id} has no supported first person"
                    )
                child_id = f"{narration_id(month, row['id'])}--{part_id}"
                entry = {
                    "narration_id": child_id,
                    "source_story_id": row["id"],
                    "source_content_hash": row["content_hash"],
                    "source_language": part_language,
                    "crawl_timestamp": row["crawl_timestamp"],
                    "source_url": row["source_url"],
                    "primary_theme": card.get("primary_theme"),
                    "secondary_themes": card.get("secondary_themes", []),
                    "source_completeness": card.get("source_completeness", "unknown"),
                    "preferred_perspective": part_perspective["preferred_perspective"],
                    "perspective_strength": part_perspective["preference_strength"],
                    "status": "adaptation_pending",
                    "source_partition": {
                        "part_id": part_id,
                        "attributed_narrator": str(part["attributed_narrator"]),
                        "start_marker": str(part["start_marker"]),
                        "end_marker": str(part["end_marker"]),
                    },
                }
                narrations.append(entry)
                split_entries.append(child_id)
                preferred = part_perspective["preferred_perspective"]
                perspective_counts[preferred] = perspective_counts.get(preferred, 0) + 1
            if not split_entries:
                raise ValueError(f"Editorial split has no parts: {row['id']}")
            split_source_stories.append(
                {
                    "story_id": row["id"],
                    "reason": str(split["reason"]),
                    "narration_ids": split_entries,
                }
            )
            continue
        perspective = first_person_profile(row["story_text"], row["language"])
        preferred = perspective["preferred_perspective"]
        perspective_counts[preferred] = perspective_counts.get(preferred, 0) + 1
        if preferred == "unsupported_first_person":
            held_no_first_person.append(
                {
                    "story_id": row["id"],
                    "reason": (
                        "The recovered source does not establish a first-person "
                        "narrator; the first-person-only collection will not invent one."
                    ),
                }
            )
            continue
        narrations.append(
            {
                "narration_id": narration_id(month, row["id"]),
                "source_story_id": row["id"],
                "source_content_hash": row["content_hash"],
                "source_language": row["language"],
                "crawl_timestamp": row["crawl_timestamp"],
                "source_url": row["source_url"],
                "primary_theme": card.get("primary_theme"),
                "secondary_themes": card.get("secondary_themes", []),
                "source_completeness": card.get("source_completeness", "unknown"),
                "preferred_perspective": preferred,
                "perspective_strength": perspective["preference_strength"],
                "status": "adaptation_pending",
            }
        )
    plan = {
        "contract_version": STORYTELLING_CONTRACT_VERSION,
        "kind": "self_narrated_storytelling_plan",
        "project": config.project_name,
        "archive_volume": month,
        "created_at": _utc_now(),
        "capture_time_note": (
            "Archive volume is Common Crawl capture month, not writing or "
            "publication month."
        ),
        "policy": {
            "one_source_story_per_narration": True,
            "multi_narrator_sources_are_split": True,
            "fixed_runtime_minutes": None,
            "first_person_only": True,
            "unsupported_first_person_is_held": True,
            "voice_is_a_performed_adaptation_not_source_identity": True,
            "published_narrations_are_immutable": True,
        },
        "narrations": narrations,
        "coverage": {
            "unique_present_stories": len(rows),
            "planned_eligible_narrations": len(narrations),
            "unanalyzed_story_ids": unanalyzed,
            "ineligible_stories": ineligible,
            "held_no_supported_first_person": held_no_first_person,
            "editorially_excluded": editorially_excluded,
            "split_source_stories": split_source_stories,
            "split_narration_units": sum(
                len(value["narration_ids"]) for value in split_source_stories
            ),
            "analysis_complete": not unanalyzed,
            "ready_for_adaptation": not unanalyzed,
            "preferred_perspectives": perspective_counts,
        },
    }
    _write_json(output_path, plan)
    return plan


def _required_evidence(card: dict[str, Any], story_text: str) -> list[str]:
    excerpts = []
    evidence_groups = (
        "narrative_beats",
        "key_information",
        "people",
        "locations",
        "time_markers",
        "sensory_details",
    )
    for group in evidence_groups:
        for item in card.get(group, []):
            if not isinstance(item, dict):
                continue
            excerpt = item.get("evidence_excerpt")
            if isinstance(excerpt, str) and excerpt and excerpt in story_text:
                if excerpt not in excerpts:
                    excerpts.append(excerpt)
    for excerpt in card.get("memorable_passages", []):
        if isinstance(excerpt, str) and excerpt and excerpt in story_text:
            if excerpt not in excerpts:
                excerpts.append(excerpt)
    if excerpts:
        return [
            excerpt
            for index, excerpt in enumerate(excerpts)
            if not any(
                index != other_index and excerpt in other_excerpt
                for other_index, other_excerpt in enumerate(excerpts)
            )
        ]
    paragraphs = [value.strip() for value in re.split(r"\n\s*\n", story_text) if value.strip()]
    return paragraphs or [story_text]


def _required_gap_disclosures(completeness: str) -> list[str]:
    disclosures = []
    if completeness in {"start_missing", "both_missing"}:
        disclosures.append("The recovered source is missing its beginning.")
    if completeness in {"end_missing", "both_missing"}:
        disclosures.append("The recovered source is missing its ending.")
    if completeness == "gated_or_preview":
        disclosures.append("The recovered source is limited by an access gate or preview.")
    if completeness == "unknown":
        disclosures.append("The recovered source has uncertain narrative boundaries.")
    return disclosures


def _storytelling_job(entry: dict[str, Any], row: Any, config: ProjectConfig) -> dict[str, Any]:
    card = json.loads(row["card_json"])
    metadata = json.loads(row["metadata_json"])
    completeness = str(card.get("source_completeness", "unknown"))
    partition = entry.get("source_partition")
    story_text = row["story_text"]
    source_language = row["language"]
    if partition:
        story_text = _partition_story_text(
            story_text,
            start_marker=str(partition["start_marker"]),
            end_marker=str(partition["end_marker"]),
        )
        source_language = str(entry["source_language"])
    perspective = first_person_profile(story_text, source_language)
    job = {
        "contract_version": STORYTELLING_CONTRACT_VERSION,
        "narration_id": entry["narration_id"],
        "source_story_id": row["id"],
        "source_content_hash": row["content_hash"],
        "source_language": source_language,
        "adaptation_language": config.primary_language,
        "crawl_timestamp": row["crawl_timestamp"],
        "source_url": row["source_url"],
        "source_file": row["source_file"],
        "source_metadata": metadata,
        "quality_flags": json.loads(row["quality_flags_json"]),
        "source_completeness": completeness,
        "story_text": story_text,
        "story_card": card,
        "perspective": {
            **perspective,
            "allowed_modes": sorted(_ALLOWED_PERSPECTIVES),
            "third_person_override_requires_reason": (
                perspective["preferred_perspective"] == "first_person_preserved"
            ),
        },
        "required_evidence_excerpts": _required_evidence(card, story_text),
        "required_gap_disclosures": _required_gap_disclosures(completeness),
        "writing_requirements": {
            "conversational_spoken_adaptation": True,
            "word_for_word_reading_required": False,
            "retain_all_material_information": True,
            "all_enriched_evidence_must_be_accounted_for": True,
            "exact_direct_quotes": True,
            "identity_inference_forbidden": True,
            "voice_is_not_source_person": True,
            "delivery_directions_are_not_transcript_text": True,
            "output_contract": "contracts/storytelling-script.schema.json",
            "prompt": "prompts/storytelling_writer.md",
        },
    }
    if partition:
        job["source_partition"] = partition
    return job


def export_storytelling_jobs(
    config: ProjectConfig,
    plan_path: Path,
    output_path: Path,
    *,
    include_existing: bool = False,
    limit: int | None = None,
) -> dict[str, Any]:
    _require_storytelling_mode(config)
    if limit is not None and limit < 1:
        raise ValueError("limit must be a positive integer")
    plan = _read_json(plan_path)
    if plan.get("kind") != "self_narrated_storytelling_plan":
        raise ValueError(f"Not a storytelling plan: {plan_path}")
    entries = plan.get("narrations")
    if not isinstance(entries, list):
        raise ValueError("Storytelling plan requires narrations")
    narration_ids = [entry["narration_id"] for entry in entries]
    if len(set(narration_ids)) != len(narration_ids):
        raise ValueError("Storytelling plan contains duplicate narration IDs")
    rows = _current_story_rows(config, str(plan["archive_volume"]))
    row_by_id = {row["id"]: row for row in rows}
    jobs = []
    skipped_existing = 0
    for entry in entries:
        row = row_by_id.get(entry["source_story_id"])
        if row is None or row["content_hash"] != entry["source_content_hash"]:
            raise ValueError(
                f"Story changed or disappeared after planning: {entry['source_story_id']}"
            )
        job = _storytelling_job(entry, row, config)
        adaptation_path = config.episodes_dir / entry["narration_id"] / "adaptation.json"
        if adaptation_path.exists() and not include_existing:
            report = validate_storytelling_adaptation_data(
                _read_json(adaptation_path), job
            )
            if report["valid"]:
                skipped_existing += 1
                continue
        jobs.append(job)
        if limit is not None and len(jobs) >= limit:
            break
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        for job in jobs:
            handle.write(json.dumps(job, ensure_ascii=False) + "\n")
    return {
        "exported": len(jobs),
        "skipped_existing": skipped_existing,
        "planned_narrations": len(entries),
        "first_person_preferred": sum(
            job["perspective"]["preferred_perspective"]
            == "first_person_preserved"
            for job in jobs
        ),
        "output": str(output_path),
        "network_calls": 0,
    }


def validate_storytelling_adaptation_data(
    adaptation: dict[str, Any],
    job: dict[str, Any],
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []

    def require_equal(field: str) -> None:
        if adaptation.get(field) != job.get(field):
            errors.append(f"{field} does not match the source job")

    if adaptation.get("contract_version") != STORYTELLING_CONTRACT_VERSION:
        errors.append("contract_version must be 1")
    for field in ("narration_id", "source_story_id", "source_content_hash"):
        require_equal(field)
    for field in ("title", "source_language", "adaptation_language"):
        value = adaptation.get(field)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{field} must be a non-empty string")
    if adaptation.get("source_language") != job.get("source_language"):
        errors.append("source_language does not match the source job")
    if adaptation.get("adaptation_language") != job.get("adaptation_language"):
        errors.append("adaptation_language does not match the source job")

    perspective = adaptation.get("perspective_mode")
    if perspective not in _ALLOWED_PERSPECTIVES:
        errors.append("perspective_mode is invalid")
    source_text = str(job.get("story_text", ""))
    source_profile = job.get("perspective", {})
    if perspective in {"first_person_preserved", "attributed_first_person"}:
        if not source_profile.get("first_person_evidence"):
            errors.append("first-person perspective has no first-person source evidence")
        spoken = " ".join(
            str(section.get("text", ""))
            for section in adaptation.get("sections", [])
            if isinstance(section, dict)
        )
        spoken_language = str(adaptation.get("adaptation_language", "en"))
        spoken_pattern = _FIRST_PERSON_PATTERNS.get(
            spoken_language,
            _FIRST_PERSON_PATTERNS["en"],
        )
        if not spoken_pattern.search(spoken):
            errors.append("first-person adaptation contains no first-person language")
    preferred = source_profile.get("preferred_perspective")

    constraints = adaptation.get("identity_constraints")
    if not isinstance(constraints, list):
        errors.append("identity_constraints must be an array")
        constraints = []
    for index, constraint in enumerate(constraints, 1):
        if not isinstance(constraint, dict):
            errors.append(f"identity_constraints[{index}] must be an object")
            continue
        if constraint.get("trait") not in _IDENTITY_TRAITS:
            errors.append(f"identity_constraints[{index}].trait is invalid")
        value = constraint.get("value")
        excerpt = constraint.get("evidence_excerpt")
        if not isinstance(value, str) or not value.strip():
            errors.append(f"identity_constraints[{index}].value is required")
        if not isinstance(excerpt, str) or not excerpt or excerpt not in source_text:
            errors.append(
                f"identity_constraints[{index}] evidence is not verbatim source text"
            )

    profile = adaptation.get("narrator_profile")
    if not isinstance(profile, dict):
        errors.append("narrator_profile must be an object")
    else:
        for field in ("personality_tags", "emotional_range_tags"):
            values = profile.get(field)
            if not isinstance(values, list) or not values or any(
                not isinstance(value, str) or not value.strip() for value in values
            ):
                errors.append(f"narrator_profile.{field} must contain strings")
        if profile.get("energy") not in _ALLOWED_ENERGY:
            errors.append("narrator_profile.energy is invalid")
        if not isinstance(profile.get("casting_notes"), str):
            errors.append("narrator_profile.casting_notes must be a string")

    sections = adaptation.get("sections")
    cited_excerpts: list[str] = []
    spoken_words = 0
    if not isinstance(sections, list) or not sections:
        errors.append("sections must be a non-empty array")
        sections = []
    section_ids = set()
    for index, section in enumerate(sections, 1):
        if not isinstance(section, dict):
            errors.append(f"sections[{index}] must be an object")
            continue
        section_id = section.get("section_id")
        if not isinstance(section_id, str) or not section_id.strip():
            errors.append(f"sections[{index}].section_id is required")
        elif section_id in section_ids:
            errors.append(f"duplicate section_id {section_id!r}")
        section_ids.add(section_id)
        text = section.get("text")
        if not isinstance(text, str) or not text.strip():
            errors.append(f"sections[{index}].text is required")
            text = ""
        spoken_words += len(re.findall(r"\b\w+\b", text))
        if re.search(r"\[(?:sigh|laugh|breath|pause|hesitat|whisper)", text, re.I):
            errors.append(f"sections[{index}] contains a delivery tag in spoken text")
        evidence = section.get("source_evidence")
        if not isinstance(evidence, list) or not evidence:
            errors.append(f"sections[{index}].source_evidence is required")
            evidence = []
        for evidence_index, item in enumerate(evidence, 1):
            if not isinstance(item, dict):
                errors.append(
                    f"sections[{index}].source_evidence[{evidence_index}] is invalid"
                )
                continue
            excerpt = item.get("excerpt")
            usage = item.get("usage")
            if not isinstance(excerpt, str) or not excerpt or excerpt not in source_text:
                errors.append(
                    f"sections[{index}].source_evidence[{evidence_index}] is not "
                    "verbatim source text"
                )
                continue
            cited_excerpts.append(excerpt)
            if usage not in {"paraphrase_support", "direct_quote"}:
                errors.append(
                    f"sections[{index}].source_evidence[{evidence_index}].usage "
                    "is invalid"
                )
            if usage == "direct_quote" and excerpt not in text:
                errors.append(
                    f"sections[{index}] direct quotation is not exact in spoken text"
                )
        delivery = section.get("delivery")
        if not isinstance(delivery, dict):
            errors.append(f"sections[{index}].delivery must be an object")
        else:
            if not isinstance(delivery.get("emotion"), str) or not delivery["emotion"]:
                errors.append(f"sections[{index}].delivery.emotion is required")
            intensity = delivery.get("intensity")
            if (
                not isinstance(intensity, (int, float))
                or isinstance(intensity, bool)
                or not 0 <= intensity <= 1
            ):
                errors.append(f"sections[{index}].delivery.intensity is invalid")
            if delivery.get("pace") not in _ALLOWED_PACES:
                errors.append(f"sections[{index}].delivery.pace is invalid")
            nonverbal = delivery.get("nonverbal")
            if not isinstance(nonverbal, list) or any(
                value not in _ALLOWED_NONVERBAL for value in nonverbal
            ):
                errors.append(f"sections[{index}].delivery.nonverbal is invalid")
        pause = section.get("pause_after_ms")
        if not isinstance(pause, int) or isinstance(pause, bool) or not 0 <= pause <= 10000:
            errors.append(f"sections[{index}].pause_after_ms is invalid")

    omitted_excerpts: list[str] = []
    omissions = adaptation.get("editorial_omissions", [])
    if not isinstance(omissions, list):
        errors.append("editorial_omissions must be an array")
        omissions = []
    allowed_omission_classes = {
        "webpage_boilerplate",
        "navigation_or_contact_data",
        "duplicate_quoted_material",
        "non_narrative_taxonomy",
        "other_non_narrative_artifact",
        "duration_condensation",
    }
    condensation = adaptation.get("condensation")
    if condensation is not None:
        if (not isinstance(condensation, dict)
                or condensation.get("policy") != "one_story_under_five_minutes"
                or not re.fullmatch(r"[a-f0-9]{64}", str(condensation.get("full_adaptation_sha256", "")))
                or not isinstance(condensation.get("editorial_summary"), str)
                or not condensation.get("editorial_summary", "").strip()):
            errors.append("condensation requires the single-story policy, preserved adaptation hash and editorial summary")
    for index, omission in enumerate(omissions, 1):
        if not isinstance(omission, dict):
            errors.append(f"editorial_omissions[{index}] must be an object")
            continue
        excerpt = omission.get("excerpt")
        classification = omission.get("classification")
        reason = omission.get("reason")
        if not isinstance(excerpt, str) or not excerpt or excerpt not in source_text:
            errors.append(
                f"editorial_omissions[{index}].excerpt is not verbatim source text"
            )
        else:
            omitted_excerpts.append(excerpt)
        if classification not in allowed_omission_classes:
            errors.append(f"editorial_omissions[{index}].classification is invalid")
        if classification == "duration_condensation" and not isinstance(condensation, dict):
            errors.append("duration_condensation omissions require condensation metadata")
        if not isinstance(reason, str) or not reason.strip():
            errors.append(f"editorial_omissions[{index}].reason is required")
    for excerpt in job.get("required_evidence_excerpts", []):
        if excerpt not in cited_excerpts and excerpt not in omitted_excerpts:
            errors.append(
                "a required narrative evidence passage was neither cited nor "
                "documented as an editorial omission"
            )
    gaps = adaptation.get("unresolved_gaps")
    if not isinstance(gaps, list) or any(not isinstance(value, str) for value in gaps):
        errors.append("unresolved_gaps must be an array of strings")
        gaps = []
    for disclosure in job.get("required_gap_disclosures", []):
        if disclosure not in gaps:
            errors.append(f"missing required gap disclosure: {disclosure}")

    if spoken_words < 30:
        warnings.append("adaptation is unusually short")
    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "narration_id": adaptation.get("narration_id"),
        "sections": len(sections),
        "spoken_words": spoken_words,
        "cited_evidence_excerpts": len(cited_excerpts),
        "omitted_evidence_excerpts": len(omitted_excerpts),
        "required_evidence_excerpts": len(job.get("required_evidence_excerpts", [])),
        "perspective_mode": perspective,
        "preferred_perspective": preferred,
    }


def validate_storytelling_adaptation(
    adaptation_path: Path,
    job_path: Path,
) -> dict[str, Any]:
    adaptation = _read_json(adaptation_path)
    try:
        job = _read_json(job_path)
    except json.JSONDecodeError:
        narration_id_value = adaptation.get("narration_id")
        job = next(
            (
                value
                for _, value in _read_jsonl(job_path)
                if value.get("narration_id") == narration_id_value
            ),
            None,
        )
        if job is None:
            raise ValueError(
                f"No job for narration {narration_id_value!r} in {job_path}"
            )
    return validate_storytelling_adaptation_data(adaptation, job)


def import_storytelling_adaptations(
    config: ProjectConfig,
    input_path: Path,
    jobs_path: Path,
    report_path: Path,
) -> dict[str, Any]:
    _require_storytelling_mode(config)
    jobs = {job["narration_id"]: job for _, job in _read_jsonl(jobs_path)}
    imported = 0
    updated = 0
    rejected = []
    seen = set()
    for line_number, adaptation in _read_jsonl(input_path):
        current_id = adaptation.get("narration_id")
        if current_id in seen:
            rejected.append(
                {"line": line_number, "narration_id": current_id, "errors": ["duplicate result"]}
            )
            continue
        seen.add(current_id)
        job = jobs.get(current_id)
        if job is None:
            rejected.append(
                {
                    "line": line_number,
                    "narration_id": current_id,
                    "errors": ["no matching current narration job"],
                }
            )
            continue
        validation = validate_storytelling_adaptation_data(adaptation, job)
        if not validation["valid"]:
            rejected.append(
                {
                    "line": line_number,
                    "narration_id": current_id,
                    "errors": validation["errors"],
                    "warnings": validation["warnings"],
                }
            )
            continue
        narration_dir = config.episodes_dir / str(current_id)
        source_job_path = narration_dir / "source-job.json"
        manifest_path = narration_dir / "manifest.json"
        manifest = {
            "contract_version": STORYTELLING_CONTRACT_VERSION,
            "kind": "self_narrated_story_manifest",
            "manifest_status": "locked_source",
            "locked_at": _utc_now(),
            "narration_id": current_id,
            "source_story_id": job["source_story_id"],
            "source_content_hash": job["source_content_hash"],
            "source_language": job["source_language"],
            "crawl_timestamp": job["crawl_timestamp"],
            "source_url": job["source_url"],
            "preferred_perspective": job["perspective"]["preferred_perspective"],
            "source_job_sha256": hashlib.sha256(
                json.dumps(job, ensure_ascii=False, sort_keys=True).encode("utf-8")
            ).hexdigest(),
            "publication_status": "draft",
            "immutability": (
                "The source identity and hash are immutable. After publication, "
                "adaptation revisions require a new version or supplement."
            ),
        }
        if manifest_path.exists():
            existing_manifest = _read_json(manifest_path)
            same_source = all(
                existing_manifest.get(field) == manifest[field]
                for field in ("narration_id", "source_story_id", "source_content_hash")
            )
            if not same_source:
                rejected.append(
                    {
                        "line": line_number,
                        "narration_id": current_id,
                        "errors": ["locked narration manifest belongs to different source"],
                    }
                )
                continue
        else:
            _write_json(manifest_path, manifest)
        if source_job_path.exists():
            existing_source_job = _read_json(source_job_path)
            if existing_source_job != job:
                rejected.append(
                    {
                        "line": line_number,
                        "narration_id": current_id,
                        "errors": ["locked source job differs from the current job"],
                    }
                )
                continue
        else:
            _write_json(source_job_path, job)
        adaptation_path = narration_dir / "adaptation.json"
        existed = adaptation_path.exists()
        if existed:
            existing_manifest = _read_json(manifest_path)
            if existing_manifest.get("publication_status") == "published":
                rejected.append(
                    {
                        "line": line_number,
                        "narration_id": current_id,
                        "errors": ["published adaptation is immutable"],
                    }
                )
                continue
        if adaptation.get("condensation"):
            try:
                require_story_text_budget(config, adaptation)
                previous = _read_json(adaptation_path) if existed else None
                if previous != adaptation:
                    if previous is None or content_digest(previous) != adaptation["condensation"]["full_adaptation_sha256"]:
                        raise ValueError("condensed revision does not match the current full adaptation")
                    archive = narration_dir / "full-editions" / content_digest(previous)
                    archive.mkdir(parents=True, exist_ok=True)
                    for name in ("adaptation.json", "personal-story-review.json"):
                        original = narration_dir / name
                        if not original.is_file():
                            continue
                        saved = archive / name
                        raw = original.read_bytes()
                        if saved.exists():
                            if saved.read_bytes() != raw:
                                raise ValueError("preserved full edition already exists with different content")
                        else:
                            with saved.open("xb") as handle:
                                handle.write(raw)
            except (ValueError, OSError) as error:
                rejected.append({"line": line_number, "narration_id": current_id, "errors": [str(error)]})
                continue
        _write_json(adaptation_path, adaptation)
        if existed:
            updated += 1
        else:
            imported += 1
    report = {
        "contract_version": 1,
        "input": str(input_path),
        "jobs": str(jobs_path),
        "imported": imported,
        "updated": updated,
        "rejected": len(rejected),
        "rejections": rejected,
        "network_calls": 0,
    }
    _write_json(report_path, report)
    return {**report, "report": str(report_path)}


def _existing_cast_usage(root: Path) -> tuple[dict[str, int], dict[str, int], dict[str, int]]:
    people: dict[str, int] = {}
    genders: dict[str, int] = {}
    accents: dict[str, int] = {}
    for path in root.glob("*/cast.json"):
        try:
            cast = _read_json(path)
            narrator = cast["narrator"]
        except (FileNotFoundError, KeyError, OSError, ValueError, json.JSONDecodeError):
            continue
        for counts, value in (
            (people, narrator.get("person_id")),
            (genders, narrator.get("gender_presentation")),
            (accents, narrator.get("verified_natural_accent")),
        ):
            if isinstance(value, str):
                counts[value] = counts.get(value, 0) + 1
    return people, genders, accents


def create_storytelling_cast(
    config: ProjectConfig,
    narration_id_value: str,
    adaptation_path: Path,
    output_path: Path,
) -> tuple[dict[str, Any] | None, bool, str | None]:
    _require_storytelling_mode(config)
    if output_path.exists():
        return _read_json(output_path), False, None
    policy = config.load_voice_roster()
    candidates = policy.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        return None, False, "storytelling voice pool has no auditioned candidates"
    adaptation = _read_json(adaptation_path)
    if adaptation.get("narration_id") != narration_id_value:
        raise ValueError("Adaptation belongs to a different narration")
    required_fields = set(policy.get("required_candidate_metadata", []))
    usable = []
    for candidate in candidates:
        if not isinstance(candidate, dict) or any(
            not candidate.get(field) for field in required_fields
        ):
            continue
        if candidate.get("audition_status") not in {"auditioned", "approved", "frozen"}:
            continue
        languages = candidate.get("supported_languages", [])
        if adaptation.get("adaptation_language") not in languages:
            continue
        usable.append(candidate)
    constraints = adaptation.get("identity_constraints", [])
    field_by_trait = {
        "narrator_gender_presentation": "gender_presentation",
        "narrator_accent": "verified_natural_accent",
        "narrator_age_presentation": "vocal_age_presentation",
    }
    for constraint in constraints:
        field = field_by_trait.get(constraint.get("trait"))
        if field:
            usable = [
                candidate
                for candidate in usable
                if str(candidate.get(field, "")).casefold()
                == str(constraint.get("value", "")).casefold()
            ]
        elif constraint.get("trait") == "narrator_language":
            usable = [
                candidate
                for candidate in usable
                if constraint.get("value") in candidate.get("supported_languages", [])
            ]
    if not usable:
        return None, False, "no auditioned voice satisfies language and evidence constraints"
    profile = adaptation["narrator_profile"]
    desired = {
        str(value).casefold()
        for value in profile["personality_tags"] + profile["emotional_range_tags"]
    }
    people, genders, accents = _existing_cast_usage(config.episodes_dir)

    def selection_key(candidate: dict[str, Any]) -> tuple[Any, ...]:
        available = {
            str(value).casefold()
            for value in candidate.get("personality_tags", [])
            + candidate.get("emotional_range_tags", [])
        }
        fit = len(desired & available)
        tie = hashlib.sha256(
            f"storytelling-cast-v1:{narration_id_value}:{candidate['person_id']}".encode()
        ).hexdigest()
        return (
            -fit,
            people.get(candidate["person_id"], 0),
            genders.get(candidate["gender_presentation"], 0),
            accents.get(candidate["verified_natural_accent"], 0),
            tie,
        )

    narrator = min(usable, key=selection_key)
    seed = f"storytelling-cast-v1:{narration_id_value}"
    cast = {
        "contract_version": 1,
        "narration_id": narration_id_value,
        "source_story_id": adaptation["source_story_id"],
        "provider": policy["provider"],
        "selection_policy": policy["selection_policy"],
        "selection_seed_sha256": hashlib.sha256(seed.encode()).hexdigest(),
        "identity_claim": False,
        "evidence_constraints": constraints,
        "artistic_choices": [
            "Voice traits not listed as evidence constraints are artistic casting choices.",
            "The performed narrator is not represented as the source person.",
        ],
        "narrator": narrator,
        "status": "selected",
    }
    _write_json(output_path, cast)
    return cast, True, None
