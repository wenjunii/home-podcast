from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Iterable

from home_podcast.config import ProjectConfig
from home_podcast.storytelling import validate_storytelling_adaptation_data


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


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Audit every canonical storytelling adaptation against current jobs."
    )
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--jobs", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    config = ProjectConfig.load(args.config)
    jobs = list(_read_jsonl(args.jobs))
    failures = []
    source_job_mismatches = []
    manifest_mismatches = []
    seen_ids: set[str] = set()
    for job in jobs:
        narration_id = str(job["narration_id"])
        if narration_id in seen_ids:
            failures.append({"narration_id": narration_id, "errors": ["duplicate job"]})
            continue
        seen_ids.add(narration_id)
        directory = config.episodes_dir / narration_id
        adaptation_path = directory / "adaptation.json"
        source_job_path = directory / "source-job.json"
        manifest_path = directory / "manifest.json"
        missing = [
            path.name
            for path in (adaptation_path, source_job_path, manifest_path)
            if not path.is_file()
        ]
        if missing:
            failures.append(
                {"narration_id": narration_id, "errors": [f"missing {name}" for name in missing]}
            )
            continue
        adaptation = _read_json(adaptation_path)
        validation = validate_storytelling_adaptation_data(adaptation, job)
        if not validation["valid"]:
            failures.append(
                {"narration_id": narration_id, "errors": validation["errors"]}
            )
        stored_job = _read_json(source_job_path)
        immutable_job_fields = (
            "contract_version",
            "narration_id",
            "source_story_id",
            "source_content_hash",
            "source_language",
            "adaptation_language",
            "crawl_timestamp",
            "source_url",
            "source_file",
            "story_text",
            "required_evidence_excerpts",
            "required_gap_disclosures",
            "source_partition",
        )
        if any(stored_job.get(key) != job.get(key) for key in immutable_job_fields):
            source_job_mismatches.append(narration_id)
        manifest = _read_json(manifest_path)
        canonical_job = json.dumps(
            stored_job,
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8")
        expected_hash = hashlib.sha256(canonical_job).hexdigest()
        manifest_fields = {
            "narration_id": narration_id,
            "source_story_id": job["source_story_id"],
            "source_content_hash": job["source_content_hash"],
            "source_job_sha256": expected_hash,
        }
        if any(manifest.get(key) != value for key, value in manifest_fields.items()):
            manifest_mismatches.append(narration_id)

    report = {
        "contract_version": 1,
        "kind": "storytelling_collection_audit",
        "validation_scope": "structural_and_provenance_only_not_personal_story_editorial_approval",
        "personal_story_audit_command": "python -m scripts.audit_personal_story_content --config storytelling.real-december.json",
        "jobs": str(args.jobs.resolve()),
        "planned_narrations": len(jobs),
        "valid_adaptations": len(jobs) - len(failures),
        "adaptation_failures": failures,
        "source_job_mismatches": source_job_mismatches,
        "manifest_mismatches": manifest_mismatches,
        "valid": not failures and not source_job_mismatches and not manifest_mismatches,
        "network_calls": 0,
    }
    if args.report:
        _write_json_atomic(args.report, report)
        report["report"] = str(args.report.resolve())
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not report["valid"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
