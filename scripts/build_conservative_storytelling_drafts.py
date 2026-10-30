from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any, Iterable


DEFAULT_DECISIONS_PATH = Path(
    "series/2013-12/storytelling-editorial-decisions.json"
)
_FIRST_PERSON = re.compile(
    r"(?:\bI\b|\b(?:me|my|mine|myself|we|us|our|ours|ourselves)\b)", re.I
)
_PAGE_NUMBER = re.compile(r"^(?:\[?\d{1,4}\]?|[ivxlcdm]{1,8})[.)]?$", re.I)
_URL = re.compile(r"^(?:https?://|www\.)\S+$", re.I)
_DELIVERY_TAG = re.compile(
    r"\[(?:sigh|laugh|breath|pause|hesitat|whisper)[^\]]*\]",
    re.I,
)
_NAVIGATION = {
    "back",
    "back to main page",
    "create a link",
    "e-mail",
    "email",
    "feedback",
    "home",
    "main menu",
    "return to main menu",
}
_MOJIBAKE = {
    "â€™": "’",
    "â€˜": "‘",
    "â€œ": "“",
    "â€": "”",
    "â€”": "—",
    "â€“": "–",
    "â€¦": "…",
    "Â©": "©",
    "Â®": "®",
    "Â": "",
}


def _read_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open(encoding="utf-8-sig") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number}: expected a JSON object")
            yield value


def _write_jsonl_atomic(path: Path, values: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        for value in values:
            handle.write(json.dumps(value, ensure_ascii=False, separators=(",", ":")))
            handle.write("\n")
    os.replace(temporary, path)


def _repair_for_speech(text: str) -> str:
    for damaged, repaired in _MOJIBAKE.items():
        text = text.replace(damaged, repaired)
    text = _DELIVERY_TAG.sub("", text)
    text = re.sub(r"(?<=[A-Za-z])-[ \t]*\n[ \t]*(?=[a-z])", "", text)
    text = re.sub(r"(?<=[A-Za-z]{2})-[ \t]+(?=[a-z]{2})", "", text)
    text = re.sub(r"[ \t]+([,.;:!?])", r"\1", text)
    text = re.sub(r"\s+([’'])\s+", r"\1", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    contractions = (
        (r"\bI am\b", "I'm"),
        (r"\bI cannot\b", "I can't"),
        (r"\bI do not\b", "I don't"),
        (r"\bI did not\b", "I didn't"),
        (r"\bI will not\b", "I won't"),
        (r"\bwe are\b", "we're"),
        (r"\bwe cannot\b", "we can't"),
        (r"\bwe do not\b", "we don't"),
        (r"\bit is\b", "it's"),
        (r"\bthat is\b", "that's"),
        (r"\bthere is\b", "there's"),
    )
    for pattern, replacement in contractions:
        text = re.sub(pattern, replacement, text, flags=re.I)
    return text.strip()


def _material_paragraphs(text: str) -> tuple[list[str], list[str]]:
    repaired = _repair_for_speech(text.replace("\r\n", "\n"))
    raw_paragraphs = [value.strip() for value in re.split(r"\n\s*\n", repaired)]
    material: list[str] = []
    omitted: list[str] = []
    for paragraph in raw_paragraphs:
        if not paragraph:
            continue
        lines = [line.strip() for line in paragraph.splitlines() if line.strip()]
        if not lines:
            continue
        normalized = " ".join(lines)
        lowered = normalized.casefold().strip("<>←→/ ")
        nonstory = (
            len(lines) == 1
            and (
                lowered in _NAVIGATION
                or _PAGE_NUMBER.fullmatch(normalized) is not None
                or _URL.fullmatch(normalized) is not None
                or lowered.startswith("copyright ")
                or lowered.startswith("© copyright ")
                or lowered.startswith("source: http")
            )
        )
        if nonstory:
            omitted.append(normalized)
        else:
            material.append(normalized)
    if not material:
        material = [repaired.replace("\n", " ").strip()]
    return material, omitted


def _title(job: dict[str, Any], paragraphs: list[str]) -> str:
    first = re.sub(r"^[\W_]+|[\W_]+$", "", paragraphs[0]).strip()
    words = first.split()
    if 1 < len(words) <= 14 and len(first) <= 100 and not first.endswith((".", "?", "!")):
        return first
    card = job.get("story_card", {})
    theme = str(card.get("primary_theme") or "recovered home story")
    return "A Recovered Story of " + theme.replace("-", " ").title()


def _sentences(paragraph: str) -> list[str]:
    values = re.split(r"(?<=[.!?])\s+(?=(?:[\"'‘“(]*[A-Z0-9]))", paragraph)
    return [value.strip() for value in values if value.strip()]


def _sections(paragraphs: list[str], target_words: int = 185) -> list[str]:
    units: list[str] = []
    for paragraph in paragraphs:
        parts = _sentences(paragraph)
        units.extend(parts or [paragraph])
    sections: list[str] = []
    current: list[str] = []
    current_words = 0
    for unit in units:
        words = len(re.findall(r"\b\w+\b", unit))
        if current and current_words + words > target_words:
            sections.append(" ".join(current).strip())
            current = []
            current_words = 0
        current.append(unit)
        current_words += words
    if current:
        sections.append(" ".join(current).strip())
    return [value for value in sections if value]


def _delivery(card: dict[str, Any], index: int, count: int) -> dict[str, Any]:
    tone = str(card.get("emotional_tone") or "reflective").casefold()
    if any(word in tone for word in ("grief", "sad", "loss", "tense", "angry")):
        emotion = "restrained " + tone[:70]
        intensity = 0.68
        pace = "slow"
        nonverbal = ["breath"] if index == 0 else ["sigh"]
    elif any(word in tone for word in ("warm", "hope", "joy", "nostalg")):
        emotion = tone[:80]
        intensity = 0.56
        pace = "conversational"
        nonverbal = ["soft_laugh"] if index == 0 else ["breath"]
    else:
        emotion = tone[:80] or "reflective"
        intensity = 0.5
        pace = "measured"
        nonverbal = ["breath"] if index == 0 else []
    if index == count - 1 and "voice_catch" not in nonverbal:
        nonverbal = [*nonverbal, "whispered_emphasis"]
    return {
        "emotion": emotion,
        "intensity": intensity,
        "pace": pace,
        "nonverbal": nonverbal,
        "direction": (
            "Keep the delivery conversational and evidence-bound; vary the "
            "rhythm with the source and do not add an inferred identity or accent."
        ),
    }


def _evidence_indexes(section_count: int, evidence_count: int) -> list[list[int]]:
    if section_count < 1 or evidence_count < 1:
        raise ValueError("sections and evidence must both be non-empty")
    assignments = [[] for _ in range(section_count)]
    for evidence_index in range(evidence_count):
        section_index = min(
            section_count - 1,
            evidence_index * section_count // evidence_count,
        )
        assignments[section_index].append(evidence_index)
    for section_index, indexes in enumerate(assignments):
        if not indexes:
            indexes.append(min(evidence_count - 1, section_index * evidence_count // section_count))
    return assignments


def _draft(job: dict[str, Any]) -> dict[str, Any]:
    paragraphs, omitted = _material_paragraphs(str(job.get("story_text", "")))
    spoken_sections = _sections(paragraphs)
    if not spoken_sections:
        raise ValueError(f"{job['narration_id']}: no spoken material remains")
    spoken = " ".join(spoken_sections)
    if not _FIRST_PERSON.search(spoken):
        raise ValueError(f"{job['narration_id']}: cleaned text lost first-person evidence")
    evidence = job.get("required_evidence_excerpts", [])
    assignments = _evidence_indexes(len(spoken_sections), len(evidence))
    sections = []
    for index, (text, indexes) in enumerate(zip(spoken_sections, assignments)):
        sections.append(
            {
                "text": text,
                "evidence_indices": indexes,
                "delivery": _delivery(job.get("story_card", {}), index, len(spoken_sections)),
                "pause_after_ms": 1100 if index == len(spoken_sections) - 1 else 650,
            }
        )
    extra_gaps = []
    source_text = str(job.get("story_text", "")).strip()
    if source_text and source_text[0].islower():
        extra_gaps.append("The recovered source begins in the middle of a sentence or thought.")
    if source_text and not re.search(r"[.!?\]”’'\"]\s*(?:\d+)?\s*$", source_text):
        extra_gaps.append("The recovered source ends without a complete closing sentence.")
    notes = [
        "This conservative spoken edition preserves the complete recovered source sequence while lightly normalizing OCR, spacing, and section rhythm.",
        "No demographic identity or accent is inferred during the bulk pass; explicit constraints require separate editorial confirmation.",
        "The performed voice is not presented as the source person.",
    ]
    if omitted:
        notes.append(
            "Isolated page numbers, bare URLs, source labels, copyright labels, and simple navigation controls are retained in provenance but omitted from speech."
        )
    return {
        "narration_id": job["narration_id"],
        "title": _title(job, paragraphs),
        "perspective_mode": "first_person_preserved",
        "identity_constraints": [],
        "narrator_profile": {
            "personality_tags": ["source-faithful", "reflective"],
            "emotional_range_tags": [str(job.get("story_card", {}).get("emotional_tone") or "reflective")],
            "energy": "variable" if len(spoken_sections) > 2 else "medium",
            "casting_notes": (
                "Choose a natural storyteller whose emotional range fits the source. "
                "Treat every unsupported voice trait as artistic casting, not identity."
            ),
        },
        "sections": sections,
        "additional_unresolved_gaps": extra_gaps,
        "adaptation_notes": notes,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build no-network, source-faithful spoken drafts for pending stories."
    )
    parser.add_argument("--jobs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--decisions", type=Path, default=DEFAULT_DECISIONS_PATH)
    parser.add_argument("--language", default="en")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    excluded_source_ids: set[str] = set()
    if args.decisions.exists():
        decisions = json.loads(args.decisions.read_text(encoding="utf-8"))
        excluded_source_ids = {
            str(value["source_story_id"])
            for value in decisions.get("exclusions", [])
        }

    selected = []
    skipped_language = 0
    skipped_exclusions = 0
    for job in _read_jsonl(args.jobs):
        if job["source_story_id"] in excluded_source_ids:
            skipped_exclusions += 1
            continue
        if job.get("source_language") != args.language:
            skipped_language += 1
            continue
        selected.append(job)
        if args.limit is not None and len(selected) >= args.limit:
            break

    report = {
        "pending_jobs_seen": sum(1 for _ in _read_jsonl(args.jobs)),
        "selected": len(selected),
        "skipped_editorial_exclusions": skipped_exclusions,
        "skipped_other_languages": skipped_language,
        "language": args.language,
        "output": str(args.output.resolve()),
        "network_calls": 0,
        "dry_run": args.dry_run,
    }
    if args.dry_run:
        print(json.dumps(report, indent=2))
        return

    drafts = [_draft(job) for job in selected]
    _write_jsonl_atomic(args.output, drafts)
    print(json.dumps({**report, "written": len(drafts)}, indent=2))


if __name__ == "__main__":
    main()
