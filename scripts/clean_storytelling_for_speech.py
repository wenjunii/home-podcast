from __future__ import annotations

import argparse
import copy
import json
import os
import re
from pathlib import Path
from typing import Any, Iterable

from ftfy import fix_text

from home_podcast.config import ProjectConfig
from home_podcast.storytelling import validate_storytelling_adaptation_data


_URL = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)
_EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_OBSCURED_EMAIL = re.compile(r"<email obscured>", re.IGNORECASE)
_ARCHIVED_CONTACT_PLACEHOLDER = re.compile(
    r"\bthe archived (?:link|address)\b", re.IGNORECASE
)
_HTML = re.compile(r"</?[A-Za-z][^>]*>")
_RAW_QUOTE_MARKER = re.compile(r"(?:^|\s)>{1,3}\s")
_SPOKEN_STAGE_DIRECTION = re.compile(
    r"\[\s*(?:laughs?|laughter|sighs?|pauses?|breathes?|inaudible|crosstalk)[^\]]*\]",
    re.IGNORECASE,
)
_SKIP_PREFIX = re.compile(r"^\s*Skip to Main Content(?: Area)?\s*", re.IGNORECASE)
_TAIL_MARKER = re.compile(
    r"(?:DOCUMENT INFO|RELATED DOCUMENTS|OTHER DOCS BY|SHARED BY|"
    r"All rights reserved|Privacy Policy|Search this site|Add a Comment|"
    r"View full topic|To post, e-mail|Forum home:|Follow us on Facebook:|"
    r"Read this blog on your|Categories:\s*Tags:|Stats:\s*views:|"
    r"This entry was posted in|\bTagged as:|"
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
_CONSERVATIVE_NOTE = "This conservative spoken edition preserves"
_BAD_TITLES = {
    "about me",
    "about us",
    "all threads by date",
    "plans & pricing",
    "remember me | forgot password",
    "skip to main content",
}
_REPAIR = {
    "â„¢": "™",
    "â€œ": "“",
    "â€": "”",
    "â€™": "’",
    "â€˜": "‘",
    "â€”": "—",
    "â€“": "–",
    "â€¦": "…",
    "Â©": "©",
    "Â®": "®",
    "\ufffd": "",
}


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


def _sanitize_text(text: str) -> tuple[str, list[str]]:
    operations = []
    updated = _SKIP_PREFIX.sub("", text)
    if updated != text:
        operations.append("removed_skip_navigation_prefix")
    text = updated
    for damaged, repaired in _REPAIR.items():
        if damaged in text:
            text = text.replace(damaged, repaired)
            operations.append("repaired_character_encoding")
    repaired_text = fix_text(text)
    if repaired_text != text:
        text = repaired_text
        operations.append("repaired_character_encoding")
    updated = _OBSCURED_EMAIL.sub("", text)
    updated = _EMAIL.sub("", updated)
    if updated != text:
        operations.append("replaced_spoken_email_address")
    text = updated
    updated = _URL.sub("", text)
    if updated != text:
        operations.append("replaced_spoken_url")
    text = updated
    updated = _ARCHIVED_CONTACT_PLACEHOLDER.sub("", text)
    if updated != text:
        operations.append("removed_archived_contact_placeholder")
    text = updated
    updated = _HTML.sub(" ", text)
    if updated != text:
        operations.append("removed_html_markup")
    text = updated
    updated = _RAW_QUOTE_MARKER.sub(" ", text)
    if updated != text:
        operations.append("removed_raw_reply_quote_markers")
    text = updated
    updated = _SPOKEN_STAGE_DIRECTION.sub(" ", text)
    if updated != text:
        operations.append("moved_spoken_stage_direction_out_of_text")
    text = updated
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    text = re.sub(r"\s+([)>\]])", r"\1", text)
    text = re.sub(r"([(<\[])\s+", r"\1", text)
    text = re.sub(r"(?:<\s*>|\(\s*\)|\[\s*\])", " ", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\s*\n\s*", " ", text)
    return text.strip(), operations


def _split_section(section: dict[str, Any], limit: int = 2200) -> list[dict[str, Any]]:
    text = str(section["text"]).strip()
    if len(text) <= limit:
        return [section]
    pieces = []
    while len(text) > limit:
        candidates = [
            match.end()
            for match in re.finditer(r"[.!?][\"”’']?\s+", text[: limit + 1])
            if match.end() >= 1100
        ]
        split_at = candidates[-1] if candidates else text.rfind(" ", 1100, limit + 1)
        if split_at < 1:
            split_at = limit
        pieces.append(text[:split_at].strip())
        text = text[split_at:].strip()
    if text:
        pieces.append(text)
    split_sections = []
    for index, piece in enumerate(pieces):
        value = copy.deepcopy(section)
        value["text"] = piece
        if index < len(pieces) - 1:
            value["pause_after_ms"] = min(350, int(value.get("pause_after_ms", 0)))
        split_sections.append(value)
    return split_sections


def _omissions_from_section(
    section: dict[str, Any], classification: str, reason: str
) -> list[dict[str, str]]:
    values = []
    for item in section.get("source_evidence", []):
        excerpt = item.get("excerpt") if isinstance(item, dict) else None
        if isinstance(excerpt, str) and excerpt:
            values.append(
                {
                    "excerpt": excerpt,
                    "classification": classification,
                    "reason": reason,
                }
            )
    return values


def _clean_adaptation(
    adaptation: dict[str, Any], job: dict[str, Any]
) -> tuple[dict[str, Any], list[str]]:
    value = copy.deepcopy(adaptation)
    notes = " ".join(str(item) for item in value.get("adaptation_notes", []))
    conservative = _CONSERVATIVE_NOTE in notes
    operations: list[str] = []
    omissions = list(value.get("editorial_omissions", []))
    cleaned_sections = []
    truncate_rest = False
    for section in value.get("sections", []):
        if truncate_rest:
            omissions.extend(
                _omissions_from_section(
                    section,
                    "webpage_boilerplate",
                    "Removed from speech because it follows a deterministic webpage or document-footer boundary.",
                )
            )
            continue
        current = copy.deepcopy(section)
        text = str(current.get("text", ""))
        spoken_stage_direction = _SPOKEN_STAGE_DIRECTION.search(text)
        if conservative and text.lstrip().lower().startswith("select category") and len(text) > 1000:
            omissions.extend(
                _omissions_from_section(
                    current,
                    "non_narrative_taxonomy",
                    "Removed a long category and tag taxonomy that is not part of the first-person narration.",
                )
            )
            operations.append("removed_non_narrative_taxonomy_section")
            continue
        if conservative:
            marker = _TAIL_MARKER.search(text)
            if marker:
                before = text[: marker.start()].strip()
                omissions.extend(
                    _omissions_from_section(
                        current,
                        "webpage_boilerplate",
                        "Removed a deterministic webpage or document footer from the spoken adaptation.",
                    )
                )
                operations.append("trimmed_web_or_document_footer")
                truncate_rest = True
                if len(before.split()) < 12:
                    continue
                text = before
        text, current_operations = _sanitize_text(text)
        operations.extend(current_operations)
        if spoken_stage_direction:
            delivery = current.setdefault("delivery", {})
            nonverbal = list(delivery.get("nonverbal", []))
            tag = "soft_laugh" if "laugh" in spoken_stage_direction.group(0).casefold() else "breath"
            if tag not in nonverbal:
                nonverbal.append(tag)
            delivery["nonverbal"] = nonverbal
        if not text:
            omissions.extend(
                _omissions_from_section(
                    current,
                    "navigation_or_contact_data",
                    "Removed a section that became empty after contact and navigation cleanup.",
                )
            )
            operations.append("removed_empty_sanitized_section")
            continue
        current["text"] = text
        split_values = _split_section(current)
        if len(split_values) > 1:
            operations.append("split_long_section_for_tts")
        cleaned_sections.extend(split_values)

    for index, section in enumerate(cleaned_sections, 1):
        section["section_id"] = f"{index:03d}"
    value["sections"] = cleaned_sections
    repaired_title = fix_text(str(value.get("title", "")))
    if repaired_title != value.get("title"):
        value["title"] = repaired_title
        operations.append("repaired_title_character_encoding")
    unique_omissions = []
    seen_omissions = set()
    for omission in omissions:
        key = (
            omission.get("excerpt"),
            omission.get("classification"),
            omission.get("reason"),
        )
        if key in seen_omissions:
            continue
        seen_omissions.add(key)
        unique_omissions.append(omission)
    if unique_omissions:
        value["editorial_omissions"] = unique_omissions
    if str(value.get("title", "")).strip().casefold() in _BAD_TITLES:
        theme = str(job.get("story_card", {}).get("primary_theme") or "home and belonging")
        value["title"] = "A Recovered Story of " + theme.replace("-", " ").title()
        operations.append("replaced_navigation_title")
    if operations:
        cleanup_note = (
            "Pre-ElevenLabs cleanup removed raw contact data, links, markup, "
            "reply syntax, and deterministic non-narrative page residue while "
            "preserving omitted excerpts in editorial_omissions."
        )
        adaptation_notes = list(value.get("adaptation_notes", []))
        if cleanup_note not in adaptation_notes:
            adaptation_notes.append(cleanup_note)
        value["adaptation_notes"] = adaptation_notes
    return value, sorted(set(operations))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Mechanically clean validated narration drafts for speech input."
    )
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--jobs", type=Path, required=True)
    parser.add_argument("--backup-root", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()

    config = ProjectConfig.load(args.config)
    jobs = list(_read_jsonl(args.jobs))
    changed = []
    unchanged = []
    rejected = []
    operation_counts: dict[str, int] = {}
    for job in jobs:
        narration_id = str(job["narration_id"])
        path = config.episodes_dir / narration_id / "adaptation.json"
        manifest_path = path.parent / "manifest.json"
        if not path.is_file() or not manifest_path.is_file():
            rejected.append({"narration_id": narration_id, "errors": ["missing canonical artifacts"]})
            continue
        manifest = _read_json(manifest_path)
        if manifest.get("publication_status") == "published":
            rejected.append({"narration_id": narration_id, "errors": ["published adaptation is immutable"]})
            continue
        original = _read_json(path)
        candidate, operations = _clean_adaptation(original, job)
        if candidate == original:
            unchanged.append(narration_id)
            continue
        validation = validate_storytelling_adaptation_data(candidate, job)
        if not validation["valid"]:
            rejected.append(
                {
                    "narration_id": narration_id,
                    "operations": operations,
                    "errors": validation["errors"],
                }
            )
            continue
        changed.append({"narration_id": narration_id, "operations": operations})
        for operation in operations:
            operation_counts[operation] = operation_counts.get(operation, 0) + 1
        if args.execute:
            backup_path = args.backup_root / narration_id / "adaptation.json"
            if not backup_path.exists():
                _write_json_atomic(backup_path, original)
            _write_json_atomic(path, candidate)

    report = {
        "contract_version": 1,
        "kind": "storytelling_speech_cleanup_report",
        "execute": args.execute,
        "jobs_seen": len(jobs),
        "changed": len(changed),
        "unchanged": len(unchanged),
        "rejected": len(rejected),
        "operation_counts": dict(sorted(operation_counts.items())),
        "changed_narrations": changed,
        "rejections": rejected,
        "network_calls": 0,
        "paid_calls": 0,
    }
    _write_json_atomic(args.report, report)
    print(json.dumps({key: value for key, value in report.items() if key not in {"changed_narrations", "rejections"}}, indent=2))
    if rejected:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
