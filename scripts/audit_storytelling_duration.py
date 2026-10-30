"""Audit every current draft against the single-short-edition policy; never write stories."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from home_podcast.config import ProjectConfig
from home_podcast.storytelling_duration import story_duration_preflight
from home_podcast.storytelling_quality import content_digest, personal_story_findings
from scripts.build_storytelling_preflight import _write_json_atomic, _write_jsonl_atomic


def audit(config: ProjectConfig) -> tuple[dict, list[dict]]:
    records = []
    jobs = []
    for path in sorted(config.episodes_dir.glob("*/adaptation.json")):
        adaptation = json.loads(path.read_text(encoding="utf-8"))
        job_path = path.parent / "source-job.json"
        source = json.loads(job_path.read_text(encoding="utf-8"))
        budget = story_duration_preflight(config, adaptation)
        findings = personal_story_findings(path.parent, adaptation)
        # A current, explicit editorial hold is a resolved decision, not a job
        # asking a writer to invent first-person testimony. Keep its original
        # length visible, and reopen it if its source/review binding goes stale.
        current_hold = (
            "personal_story_held_by_editorial_review" in findings
            and not {"invalid_personal_story_review", "stale_personal_story_review",
                     "personal_story_editorial_review_required"}.intersection(findings)
        )
        record = {
            "narration_id": adaptation["narration_id"], "title": adaptation["title"],
            "adaptation": path.relative_to(config.project_root).as_posix(),
            "source_job": job_path.relative_to(config.project_root).as_posix(),
            "adaptation_sha256": content_digest(adaptation),
            "source_job_sha256": content_digest(source),
            "duration_budget": budget, "editorial_findings": findings,
            "current_personal_story_approval": not findings,
            "current_editorial_hold": current_hold,
            "single_condensed_edition": bool(adaptation.get("condensation")),
            "next_action": (
                "held_original_preserved_not_for_production" if current_hold else
                "read_full_source_and_write_one_condensed_version" if budget["requires_condensation"]
                else "personal_story_editorial_review" if findings else "ready_for_speech_duration_validation"
            ),
        }
        records.append(record)
        if budget["requires_condensation"] and not current_hold:
            jobs.append({**record,
                "kind": "single_story_condensation_job",
                "policy": "one_story_under_five_minutes",
                "instructions": (
                    "Read the complete frozen source job and adaptation before writing. Author one coherent "
                    "first-person version in the active Codex task; never split, take only an opening, "
                    "or use a mechanical sentence selector. Target 450-550 words or fewer. Preserve the "
                    "personal arc, essential context and supported ending; document secondary omissions. "
                    "Keep existing editorial holds until individually reviewed. No text-provider calls."
                ),
            })
    summary = {
        "drafts_audited": len(records),
        "within_text_budget": sum(not r["duration_budget"]["requires_condensation"] for r in records),
        "needs_condensation": len(jobs),
        "over_text_budget_including_held_originals": sum(r["duration_budget"]["requires_condensation"] for r in records),
        "held_originals_over_budget": sum(r["current_editorial_hold"] and r["duration_budget"]["requires_condensation"] for r in records),
        "editorially_held_originals": sum(r["current_editorial_hold"] for r in records),
        "approved_personal_stories": sum(r["current_personal_story_approval"] for r in records),
        "approved_personal_stories_over_budget": sum(r["current_personal_story_approval"] for r in jobs),
        "pending_editorial_review_or_rewrite": sum(bool(r["editorial_findings"]) and not r["current_editorial_hold"] for r in records),
        "single_condensed_editions": sum(r["single_condensed_edition"] for r in records),
    }
    return {
        "kind": "single_story_duration_audit", "contract_version": 1,
        "policy": "one_story_under_five_minutes", "summary": summary,
        "audio_measurement_note": "These are text estimates, not measured audio or editorial approvals.",
        "narrations": records, "network_calls": 0, "paid_calls": 0, "models_loaded": 0,
    }, jobs


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    config = ProjectConfig.load(args.config)
    output = args.output_dir or config.work_dir / "condensation"
    report, jobs = audit(config)
    _write_json_atomic(output / "collection-duration-audit.json", report)
    _write_jsonl_atomic(output / "pending-condensation-jobs.jsonl", jobs)
    print(json.dumps({**report["summary"], "output": str(output), "network_calls": 0, "paid_calls": 0}, indent=2))


if __name__ == "__main__":
    main()
