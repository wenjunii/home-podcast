from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Iterable


CAPTURE_TIME_GAP = (
    "The crawl timestamp records capture time and does not establish when the "
    "narrative was written or published."
)


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


def _load_jobs(
    jobs_path: Path | None = None,
    jobs_root: Path | None = None,
) -> list[dict[str, Any]]:
    if (jobs_path is None) == (jobs_root is None):
        raise ValueError("Provide exactly one jobs source")
    if jobs_path is not None:
        return list(_read_jsonl(jobs_path))
    values = []
    assert jobs_root is not None
    for path in sorted(jobs_root.glob("*/source-job.json")):
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError(f"{path}: expected a JSON object")
        values.append(value)
    return values


def _assemble(draft: dict[str, Any], job: dict[str, Any]) -> dict[str, Any]:
    required = job.get("required_evidence_excerpts", [])
    if not isinstance(required, list) or not required:
        raise ValueError(f"{job['narration_id']}: job has no required evidence")

    sections = []
    used_indexes: set[int] = set()
    for number, authored in enumerate(draft.get("sections", []), 1):
        indexes = authored.get("evidence_indices", [])
        if indexes == "all":
            indexes = list(range(len(required)))
        if not isinstance(indexes, list) or not indexes:
            raise ValueError(
                f"{job['narration_id']}: section {number} needs evidence_indices"
            )
        evidence = []
        for index in indexes:
            if not isinstance(index, int) or isinstance(index, bool):
                raise ValueError(
                    f"{job['narration_id']}: section {number} has a non-integer "
                    "evidence index"
                )
            try:
                excerpt = required[index]
            except IndexError as error:
                raise ValueError(
                    f"{job['narration_id']}: section {number} evidence index "
                    f"{index} is out of range"
                ) from error
            used_indexes.add(index)
            evidence.append({"excerpt": excerpt, "usage": "paraphrase_support"})
        sections.append(
            {
                "section_id": f"{number:03d}",
                "text": authored["text"],
                "source_evidence": evidence,
                "delivery": authored["delivery"],
                "pause_after_ms": authored.get("pause_after_ms", 900),
            }
        )

    expected_indexes = set(range(len(required)))
    if used_indexes != expected_indexes:
        missing = sorted(expected_indexes - used_indexes)
        extra = sorted(used_indexes - expected_indexes)
        raise ValueError(
            f"{job['narration_id']}: evidence coverage mismatch; "
            f"missing={missing}, extra={extra}"
        )

    gaps = list(job.get("required_gap_disclosures", []))
    for gap in draft.get("additional_unresolved_gaps", []):
        if not isinstance(gap, str) or not gap.strip():
            raise ValueError(
                f"{job['narration_id']}: additional unresolved gaps must be strings"
            )
        if gap not in gaps:
            gaps.append(gap)
    if CAPTURE_TIME_GAP not in gaps:
        gaps.append(CAPTURE_TIME_GAP)
    return {
        "contract_version": 1,
        "narration_id": job["narration_id"],
        "source_story_id": job["source_story_id"],
        "source_content_hash": job["source_content_hash"],
        "title": draft["title"],
        "source_language": job["source_language"],
        "adaptation_language": job["adaptation_language"],
        "perspective_mode": draft["perspective_mode"],
        "identity_constraints": draft.get("identity_constraints", []),
        "narrator_profile": draft["narrator_profile"],
        "sections": sections,
        "unresolved_gaps": gaps,
        "adaptation_notes": draft.get(
            "adaptation_notes",
            [
                "The wording is conversationally reshaped from the recovered "
                "source without presenting the performed voice as the source person."
            ],
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Assemble Codex-authored storytelling drafts with exact job provenance."
        )
    )
    jobs_source = parser.add_mutually_exclusive_group(required=True)
    jobs_source.add_argument("--jobs", type=Path)
    jobs_source.add_argument(
        "--jobs-root",
        type=Path,
        help="Read locked source-job.json files from narration subdirectories.",
    )
    parser.add_argument("--drafts", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--selected-jobs-output",
        type=Path,
        help="Write the exact locked jobs selected by these drafts for import.",
    )
    parser.add_argument(
        "--merge",
        action="store_true",
        help="Preserve and update existing output records by narration ID.",
    )
    args = parser.parse_args()

    job_values = _load_jobs(args.jobs, args.jobs_root)
    jobs = {value["narration_id"]: value for value in job_values}
    drafts = list(_read_jsonl(args.drafts))
    if not drafts:
        raise ValueError("No authored drafts found")

    assembled = []
    seen: set[str] = set()
    for draft in drafts:
        narration_id = draft.get("narration_id")
        if not isinstance(narration_id, str) or narration_id not in jobs:
            raise ValueError(f"No current source job for {narration_id!r}")
        if narration_id in seen:
            raise ValueError(f"Duplicate authored draft: {narration_id}")
        seen.add(narration_id)
        assembled.append(_assemble(draft, jobs[narration_id]))

    if args.merge and args.output.exists():
        existing = list(_read_jsonl(args.output))
        replacements = {value["narration_id"]: value for value in assembled}
        merged = []
        for value in existing:
            current_id = value.get("narration_id")
            merged.append(replacements.pop(current_id, value))
        merged.extend(replacements.values())
        assembled = merged

    _write_jsonl_atomic(args.output, assembled)
    if args.selected_jobs_output:
        _write_jsonl_atomic(
            args.selected_jobs_output,
            [jobs[value["narration_id"]] for value in assembled],
        )
    print(
        json.dumps(
            {
                "authored_drafts": len(drafts),
                "output_records": len(assembled),
                "output": str(args.output.resolve()),
                "network_calls": 0,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
