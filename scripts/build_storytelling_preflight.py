from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from home_podcast.config import ProjectConfig
from home_podcast.storytelling_duration import story_duration_preflight
from home_podcast.storytelling import validate_storytelling_adaptation_data
from home_podcast.storytelling_quality import (
    personal_story_findings, spoken_content_findings, story_card_findings,
)


_WORD = re.compile(r"\b[\w’'-]+\b", re.UNICODE)
_URL = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)
_EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_HTML = re.compile(r"</?[A-Za-z][^>]*>")
_MOJIBAKE = re.compile(
    r"(?:Ã[\x80-\xff]?|Â[\x80-\xff]?|â(?:€|€™|€œ|€|€”|€“|€¦|„|†)|"
    r"(?:Ã.|Ä.|Æ.|á».){2,})"
)
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_RAW_QUOTE_MARKER = re.compile(r"(?:^|\s)>{1,3}\s")
_MULTI_SPEAKER = re.compile(
    r"(?:\bFrom:\s.{0,100}\bDate:|\bOn\s.{0,160}\bwrote:|\bRest of post\b|"
    r"\breblogged this from\b|\bReply-to-All\b)",
    re.IGNORECASE,
)
_WEB_BOILERPLATE = re.compile(
    r"(?:DOCUMENT INFO|RELATED DOCUMENTS|OTHER DOCS BY|SHARED BY|"
    r"All rights reserved|Privacy Policy|Skip to Main Content|Search this site|"
    r"Add a Comment|View full topic|To post, e-mail|Need help\?\s*https?://|"
    r"Forum home:|Follow us on Facebook:|Read this blog on your|"
    r"Visitor Number|Categories:\s*Tags:|Stats:\s*views:)",
    re.IGNORECASE,
)
_CONVERSATIONAL = re.compile(
    r"\b(?:I'm|I've|I'd|I'll|can't|couldn't|didn't|doesn't|don't|hadn't|hasn't|"
    r"isn't|it's|that's|there's|wasn't|weren't|we're|we've|won't|wouldn't)\b|[?!]",
    re.IGNORECASE,
)
_CONSERVATIVE_NOTE = "This conservative spoken edition preserves"
_ARCHIVED_CONTACT_PLACEHOLDER = re.compile(
    r"\bthe archived (?:link|address)\b", re.IGNORECASE
)
_SPEECH_RESIDUE = re.compile(
    r"(?:This entry was posted in|\bTagged as:|"
    r"\bOne Community participants include:|\bFollow the comments\b|"
    r"\b\d+ Responses\b|\bSource URL:\s*|"
    r"\bSearch for:|-{8,}\s*next part\s*-{8,}|"
    r"If you have a suggestion you would like to share with other readers|"
    r"\bOne Comment on\b|\bComments are closed\b|"
    r"\b[A-Z][\w' -]{1,60}'s blog(?=.{0,120}\bSubmitted by Anonymous on\b)|"
    r"\bSubmitted by Anonymous on\b|"
    r"\bComments\s+[A-Z][\w@.-]+(?:\s+says:)?\s+(?:[A-Z][a-z]+\s+\d|\d{1,2}(?:st|nd|rd|th)?\s+[A-Z][a-z]+\s+\d{4}|\d{1,2}/\d{1,2}/\d{2,4})|"
    r"\bPosted in\s+[A-Z][\w ,&/-]{1,100}(?:\bFollow the comments\b|\s+\d+ Responses\b))",
    re.IGNORECASE,
)


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return value


def _read_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open(encoding="utf-8-sig") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number}: expected a JSON object")
            yield value


def _write_json_atomic(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _write_jsonl_atomic(path: Path, values: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        for value in values:
            handle.write(json.dumps(value, ensure_ascii=False, separators=(",", ":")))
            handle.write("\n")
    os.replace(temporary, path)


def _spoken_text(adaptation: dict[str, Any]) -> str:
    return "\n".join(
        str(section.get("text", ""))
        for section in adaptation.get("sections", [])
        if isinstance(section, dict)
    )


def _quality_findings(
    adaptation: dict[str, Any], validation: dict[str, Any]
) -> tuple[list[str], list[str]]:
    text = _spoken_text(adaptation)
    sections = adaptation.get("sections", [])
    blockers = []
    warnings = []
    notes = " ".join(str(value) for value in adaptation.get("adaptation_notes", []))
    conservative = _CONSERVATIVE_NOTE in notes
    if not validation.get("valid"):
        blockers.append("contract_or_evidence_validation_failed")
    checks = (
        ("spoken_url", _URL),
        ("spoken_email_address", _EMAIL),
        ("spoken_html_markup", _HTML),
        ("spoken_mojibake", _MOJIBAKE),
        ("spoken_control_character", _CONTROL),
        ("raw_reply_quote_markers", _RAW_QUOTE_MARKER),
    )
    for label, pattern in checks:
        if pattern.search(text):
            blockers.append(label)
    if "\ufffd" in text:
        blockers.append("unicode_replacement_character")
    if _MULTI_SPEAKER.search(text):
        blockers.append("possible_multi_speaker_source")
    if _ARCHIVED_CONTACT_PLACEHOLDER.search(text):
        blockers.append("archived_contact_placeholder")
    if _SPEECH_RESIDUE.search(text):
        blockers.append("web_or_comment_residue")
    if _WEB_BOILERPLATE.search(text):
        if conservative:
            blockers.append("web_or_document_boilerplate")
        else:
            warnings.append("intentional_archive_interface_reference")
    if any(len(str(section.get("text", ""))) > 2500 for section in sections):
        blockers.append("section_exceeds_2500_characters")

    if conservative:
        warnings.append("conservative_spoken_edition")
    blockers.extend(spoken_content_findings(adaptation))
    word_count = len(_WORD.findall(text))
    if word_count > 4000:
        warnings.append("longform_over_4000_words")
    if word_count and len(_CONVERSATIONAL.findall(text)) / word_count < 0.002:
        warnings.append("low_conversational_marker_density")
    if not any(
        section.get("delivery", {}).get("nonverbal")
        for section in sections
        if isinstance(section, dict)
    ):
        warnings.append("no_nonverbal_performance_cues")
    return sorted(set(blockers)), sorted(set(warnings))


def build_preflight(
    config: ProjectConfig,
    jobs_path: Path,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    jobs = list(_read_jsonl(jobs_path))
    records = []
    inventory = []
    blocker_counts: Counter[str] = Counter()
    warning_counts: Counter[str] = Counter()
    readiness_counts: Counter[str] = Counter()
    total_words = 0
    total_characters = 0
    total_estimated_min_seconds = 0.0
    total_estimated_max_seconds = 0.0

    for job in jobs:
        narration_id = str(job["narration_id"])
        directory = config.episodes_dir / narration_id
        adaptation_path = directory / "adaptation.json"
        source_job_path = directory / "source-job.json"
        manifest_path = directory / "manifest.json"
        artifact_blockers = []
        for path in (adaptation_path, source_job_path, manifest_path):
            if not path.is_file():
                artifact_blockers.append(f"missing_{path.name.replace('.', '_')}")
        if artifact_blockers:
            blockers = artifact_blockers
            warnings = []
            adaptation: dict[str, Any] = {}
            validation = {"valid": False, "errors": artifact_blockers}
        else:
            adaptation = _read_json(adaptation_path)
            validation = validate_storytelling_adaptation_data(adaptation, job)
            blockers, warnings = _quality_findings(adaptation, validation)
            blockers = sorted(set(blockers + personal_story_findings(directory, adaptation)))
            warnings.extend(story_card_findings(job))

        sections = adaptation.get("sections", [])
        text = _spoken_text(adaptation)
        word_count = len(_WORD.findall(text))
        character_count = len(text)
        pause_seconds = sum(
            int(section.get("pause_after_ms", 0)) / 1000
            for section in sections
            if isinstance(section, dict)
        )
        estimated_min_seconds = word_count / 165 * 60 + pause_seconds
        estimated_max_seconds = word_count / 135 * 60 + pause_seconds
        duration_budget = story_duration_preflight(config, adaptation)
        if duration_budget["requires_condensation"]:
            blockers = sorted(set(blockers + ["story_requires_condensation"]))
        total_words += word_count
        total_characters += character_count
        total_estimated_min_seconds += estimated_min_seconds
        total_estimated_max_seconds += estimated_max_seconds
        for value in blockers:
            blocker_counts[value] += 1
        for value in warnings:
            warning_counts[value] += 1
        readiness = (
            "blocked_before_voice_audition"
            if blockers
            else "ready_for_voice_audition"
        )
        readiness_counts[readiness] += 1
        profile = adaptation.get("narrator_profile", {})
        card = job.get("story_card", {})
        review_path = directory / "personal-story-review.json"
        review = _read_json(review_path) if review_path.is_file() else {}
        reviewed_analysis = review.get("reviewed_analysis", {}) if not blockers else {}
        origin = (
            "conservative_source_faithful"
            if _CONSERVATIVE_NOTE
            in " ".join(str(value) for value in adaptation.get("adaptation_notes", []))
            else "editorially_authored_or_translated"
        )
        record = {
            "narration_id": narration_id,
            "source_story_id": job["source_story_id"],
            "source_content_hash": job["source_content_hash"],
            "title": adaptation.get("title"),
            "source_language": job.get("source_language"),
            "adaptation_language": job.get("adaptation_language"),
            "translation_required": job.get("source_language")
            != job.get("adaptation_language"),
            "crawl_timestamp": job.get("crawl_timestamp"),
            "capture_time_is_not_publication_time": True,
            "source_url": job.get("source_url"),
            "source_completeness": job.get("source_completeness"),
            "source_partition": job.get("source_partition"),
            "primary_theme": card.get("primary_theme"),
            "secondary_themes": card.get("secondary_themes", []),
            "locations": reviewed_analysis.get("locations", []),
            "reviewed_personal_analysis": reviewed_analysis,
            "analysis_screening_findings": story_card_findings(job),
            "personal_story_review_decision": review.get("decision", "pending_review"),
            "sensitivity_notes": card.get("sensitivity_notes", []),
            "pronunciation_items": card.get("pronunciation_items", []),
            "perspective_mode": adaptation.get("perspective_mode"),
            "identity_constraints": adaptation.get("identity_constraints", []),
            "voice_brief": {
                "personality_tags": profile.get("personality_tags", []),
                "emotional_range_tags": profile.get("emotional_range_tags", []),
                "energy": profile.get("energy"),
                "casting_notes": profile.get("casting_notes", ""),
            },
            "section_count": len(sections),
            "spoken_word_count": word_count,
            "spoken_character_count": character_count,
            "duration_budget": duration_budget,
            "estimated_duration_seconds": {
                "fast_165_wpm": round(estimated_min_seconds, 2),
                "slow_135_wpm": round(estimated_max_seconds, 2),
            },
            "adaptation_origin": origin,
            "readiness": readiness,
            "blocking_findings": blockers,
            "editorial_warnings": warnings,
            "validation_errors": validation.get("errors", []),
        }
        records.append(record)
        if readiness == "ready_for_voice_audition":
            for section in sections:
                inventory.append(
                    {
                        "narration_id": narration_id,
                        "source_story_id": job["source_story_id"],
                        "section_id": section["section_id"],
                        "text": section["text"],
                        "text_sha256": hashlib.sha256(
                            section["text"].encode("utf-8")
                        ).hexdigest(),
                        "spoken_character_count": len(section["text"]),
                        "spoken_word_count": len(_WORD.findall(section["text"])),
                        "delivery": section["delivery"],
                        "pause_after_ms": section["pause_after_ms"],
                        "cast_status": "pending_storytelling_voice_audition",
                    }
                )

    summary = {
        "planned_narrations": len(jobs),
        "readiness": dict(sorted(readiness_counts.items())),
        "blocking_findings": dict(sorted(blocker_counts.items())),
        "editorial_warnings": dict(sorted(warning_counts.items())),
        "sections_ready_for_voice_audition": len(inventory),
        "spoken_words": total_words,
        "spoken_characters": total_characters,
        "duration_estimate_scope": "all_drafts_including_blocked_not_a_production_runtime",
        "reviewed_personal_story_words": sum(
            r["spoken_word_count"] for r in records
            if r["readiness"] == "ready_for_voice_audition"
        ),
        "reviewed_personal_story_duration_hours": {
            speed: round(sum(r["estimated_duration_seconds"][speed] for r in records
                             if r["readiness"] == "ready_for_voice_audition") / 3600, 2)
            for speed in ("fast_165_wpm", "slow_135_wpm")
        },
        "estimated_collection_duration_hours": {
            "fast_165_wpm": round(total_estimated_min_seconds / 3600, 2),
            "slow_135_wpm": round(total_estimated_max_seconds / 3600, 2),
        },
    }
    index = {
        "contract_version": 1,
        "kind": "storytelling_production_index",
        "archive_volume": "2013-12",
        "capture_time_note": (
            "December 2013 is Common Crawl capture time, not publication time."
        ),
        "summary": summary,
        "narrations": records,
    }
    audit = {
        "contract_version": 1,
        "kind": "storytelling_pre_elevenlabs_audit",
        "archive_volume": "2013-12",
        "valid": not blocker_counts,
        "summary": summary,
        "blocked_narrations": [
            {
                "narration_id": value["narration_id"],
                "blocking_findings": value["blocking_findings"],
            }
            for value in records
            if value["blocking_findings"]
        ],
        "network_calls": 0,
        "paid_calls": 0,
        "model_servers_started": False,
    }
    return index, audit, inventory


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Build the deterministic production index, editorial audit, and "
            "provider-neutral section inventory before ElevenLabs work."
        )
    )
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--jobs", type=Path, required=True)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    args = parser.parse_args()

    index, audit, inventory = build_preflight(
        ProjectConfig.load(args.config), args.jobs
    )
    _write_json_atomic(args.index, index)
    _write_json_atomic(args.audit, audit)
    _write_jsonl_atomic(args.inventory, inventory)
    print(
        json.dumps(
            {
                **audit["summary"],
                "valid": audit["valid"],
                "index": str(args.index.resolve()),
                "audit": str(args.audit.resolve()),
                "inventory": str(args.inventory.resolve()),
                "network_calls": 0,
                "paid_calls": 0,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    if not audit["valid"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
