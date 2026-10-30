"""Editorial gates for the personal-history collection (not the podcast).

Text heuristics can reject obvious residue, but cannot establish autobiographical
truth. A current, evidence-backed editorial review is required as well. Reviews
are sidecars: frozen source jobs and old podcast artifacts are never rewritten.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .storytelling_duration import require_story_text_budget


REVIEW_FILENAME = "personal-story-review.json"
CONSERVATIVE_MARKER = "This conservative spoken edition preserves"
_SOURCE_COMMENTARY = re.compile(
    r"\bthe source (?:says|describes|tells|records|calls|gives|leaves|does not|doesn't)\b|"
    r"\b(?:the |this |a )?(?:recovered|captured|surviving|archived) "
    r"(?:text|page|post|fragment|passage|account|record|excerpt|comments?|notes?)\b|"
    r"\b(?:in|from|by|of|to) the source\b|\bsource (?:text|evidence)\b",
    re.I,
)
_INTERFACE = re.compile(
    r"\b(?:recent posts|blogroll|posts tagged|posted in|posted by|"
    r"comments are closed|leave a (?:comment|reply)|subscribe (?:now|to)|"
    r"RSS (?:feed|entries)|all rights reserved|privacy policy|"
    r"click here|read on\s*\.{2,}|archive(?:s)?\s*[:\n])\b",
    re.I,
)
_PROMOTION = re.compile(
    r"\b(?:buy now|add to (?:cart|basket)|shop now|order now|"
    r"limited.time offer|free shipping|book (?:your|a) (?:session|consultation)|"
    r"contact us (?:today|for)|our (?:products|services|clients|customers))\b",
    re.I,
)
_MONTH_YEAR = re.compile(
    r"\b(?:January|February|March|April|May|June|July|August|September|"
    r"October|November|December)\s+\d{4}\b", re.I,
)
_FIRST_PERSON = re.compile(r"\b(?:I|I'm|I've|I'd|I'll|me|my|mine|we|our|us)\b", re.I)


def content_digest(value: dict[str, Any]) -> str:
    """Portable semantic hash: whitespace-only JSON changes do not revoke review."""
    return hashlib.sha256(json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")).hexdigest()


def spoken_content_findings(adaptation: dict[str, Any]) -> list[str]:
    text = "\n".join(str(s.get("text", "")) for s in adaptation.get("sections", []))
    findings = []
    for label, pattern in (
        ("spoken_source_commentary", _SOURCE_COMMENTARY),
        ("spoken_web_navigation", _INTERFACE),
        ("possible_spoken_advertising", _PROMOTION),
    ):
        if pattern.search(text):
            findings.append(label)
    if not _FIRST_PERSON.search(text):
        findings.append("no_first_person_spoken_perspective")
    # Several dates are not inherently wrong. Flag only adjacent archive-like
    # month/year entries, not a life story with dated events between them.
    months = list(_MONTH_YEAR.finditer(text))
    if any(
        all(not text[left.end():right.start()].strip(" ,;|\n()-")
            for left, right in zip(group, group[1:]))
        for group in (months[i:i + 4] for i in range(max(0, len(months) - 3)))
    ):
        findings.append("spoken_archive_month_list")
    if any(CONSERVATIVE_MARKER in str(n) for n in adaptation.get("adaptation_notes", [])):
        findings.append("conservative_copy_requires_personal_story_rewrite")
    return sorted(set(findings))


def story_card_findings(job: dict[str, Any]) -> list[str]:
    card = job.get("story_card", {})
    text = json.dumps(card, ensure_ascii=False)
    findings = []
    if str(card.get("summary", "")).startswith("This recovered narrative preserves"):
        findings.append("mechanical_analysis_scaffold_not_editorial_review")
    if "Recovered narrative passage" in text:
        findings.append("unreviewed_passage_inventory")
    return findings


def personal_story_findings(
    directory: Path, adaptation: dict[str, Any] | None = None,
) -> list[str]:
    """Fail closed on missing, held, incomplete, or stale editorial approval."""
    try:
        adaptation = adaptation or json.loads(
            (directory / "adaptation.json").read_text(encoding="utf-8"))
        job = json.loads((directory / "source-job.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ["missing_or_invalid_personal_story_artifacts"]
    findings = spoken_content_findings(adaptation)
    try:
        review = json.loads((directory / REVIEW_FILENAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return sorted(set(findings + ["personal_story_editorial_review_required"]))
    if not isinstance(review, dict):
        return sorted(set(findings + ["invalid_personal_story_review"]))
    if review.get("decision") != "approved_personal_story":
        findings.append("personal_story_held_by_editorial_review")
    if (review.get("contract_version") != 1
            or review.get("narration_id") != adaptation.get("narration_id")
            or not review.get("reviewed_by") or not review.get("reason")):
        findings.append("invalid_personal_story_review")
    if (review.get("adaptation_sha256") != content_digest(adaptation)
            or review.get("source_job_sha256") != content_digest(job)):
        findings.append("stale_personal_story_review")
    if review.get("decision") != "approved_personal_story":
        return sorted(set(findings))
    analysis = review.get("reviewed_analysis", {})
    source = str(job.get("story_text", ""))
    if not isinstance(analysis, dict):
        analysis = {}
    for field in ("narrator_evidence", "personal_experience_evidence"):
        excerpt = analysis.get(field)
        if not isinstance(excerpt, str) or not excerpt.strip() or excerpt not in source:
            findings.append(f"missing_or_invalid_{field}")
    if not analysis.get("summary"):
        findings.append("missing_reviewed_personal_story_analysis")
    if review.get("approved_section_ids") != [
        s.get("section_id") for s in adaptation.get("sections", [])
    ]:
        findings.append("personal_story_section_review_incomplete")
    for location in analysis.get("locations", []):
        if (not isinstance(location, dict) or not location.get("name")
                or not location.get("evidence_excerpt")
                or location["evidence_excerpt"] not in source):
            findings.append("invalid_reviewed_location_evidence")
    return sorted(set(findings))


def require_personal_story(directory: Path) -> dict[str, Any]:
    findings = personal_story_findings(directory)
    if findings:
        raise ValueError(f"Personal-story production gate: {directory.name}: "
                         + ", ".join(findings))
    return json.loads((directory / REVIEW_FILENAME).read_text(encoding="utf-8"))


def require_current_speech_jobs(config: Any, jobs: list[dict[str, Any]], *, audition: bool) -> None:
    """A valid cache hash alone must not authorize a stale pre-review script."""
    checked: dict[str, dict[str, Any]] = {}
    for job in jobs:
        narration_id = str(job.get("source_narration_id" if audition else "narration_id", ""))
        directory = config.episodes_dir / narration_id
        if narration_id not in checked:
            require_personal_story(directory)
            checked[narration_id] = json.loads(
                (directory / "adaptation.json").read_text(encoding="utf-8"))
            if not audition:
                require_story_text_budget(config, checked[narration_id])
        adaptation = checked[narration_id]
        if job.get("adaptation_sha256") != content_digest(adaptation):
            raise ValueError("Stale speech plan: rebuild from the reviewed personal story")
        section_id = job.get("source_section_id" if audition else "section_id")
        sections = [s for s in adaptation["sections"] if s["section_id"] == section_id]
        text = job.get("reference_text" if audition else "text", "")
        expected_text = (re.sub(r"\s+", " ", sections[0]["text"]).strip()
                         if audition and len(sections) == 1 else
                         sections[0]["text"] if len(sections) == 1 else "")
        if (len(sections) != 1 or not text
                or (text not in expected_text if audition else text != expected_text)):
            raise ValueError("Speech plan text no longer matches the reviewed personal story")
        if audition:
            require_story_text_budget(config, {"sections": [{"text": text}]})


def validate_personal_visual_plan(plan: dict[str, Any], adaptation: dict[str, Any]) -> None:
    """Ground each scene in an approved personal section, not archive chrome.

    This does not require a first-person camera: portraits remain welcome.
    """
    sections = {s["section_id"]: s for s in adaptation["sections"]}
    if plan.get("narration_id") != adaptation["narration_id"]:
        raise ValueError("Personal visuals must identify the reviewed narration")
    for scene in plan.get("scenes", []):
        ids = scene.get("section_ids", [])
        excerpt = scene.get("personal_story_excerpt", "")
        if (not ids or any(i not in sections for i in ids) or not excerpt
                or not any(excerpt in sections[i]["text"] for i in ids)):
            raise ValueError("Personal visual scene needs reviewed section IDs and an exact spoken excerpt")
        if spoken_content_findings({"sections": [{"text": "I remember. " + excerpt}]}):
            raise ValueError("Personal visual scene contains source commentary or navigation")
