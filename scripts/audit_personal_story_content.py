"""Repeatable no-network content screening; never automatically approves a story."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from home_podcast.config import ProjectConfig
from home_podcast.storytelling import validate_storytelling_adaptation_data
from home_podcast.storytelling_quality import (
    personal_story_findings, require_current_speech_jobs, story_card_findings,
)
from scripts.build_storytelling_preflight import _write_json_atomic, _write_jsonl_atomic


def audit(config: ProjectConfig) -> tuple[dict, list[dict]]:
    records = []
    for path in sorted(config.episodes_dir.glob("*/adaptation.json")):
        adaptation = json.loads(path.read_text(encoding="utf-8"))
        job = json.loads((path.parent / "source-job.json").read_text(encoding="utf-8"))
        findings = personal_story_findings(path.parent, adaptation)
        validation = validate_storytelling_adaptation_data(adaptation, job)
        if not validation["valid"]:
            findings.append("contract_or_evidence_validation_failed")
        review_path = path.parent / "personal-story-review.json"
        review = json.loads(review_path.read_text(encoding="utf-8")) if review_path.exists() else {}
        records.append({
            "narration_id": adaptation["narration_id"],
            "title": adaptation["title"],
            "source_story_id": job["source_story_id"],
            "source_content_hash": job["source_content_hash"],
            "adaptation": str(path.relative_to(config.project_root)),
            "source_job": str((path.parent / "source-job.json").relative_to(config.project_root)),
            "structural_validation_valid": validation["valid"],
            "analysis_findings": story_card_findings(job),
            "blocking_findings": sorted(set(findings)),
            "editorial_decision": review.get("decision", "pending_personal_story_review"),
            "editorial_reason": review.get("reason", "No source-backed personal-story approval yet."),
            "next_action": "ready_for_voice_audition" if not findings else "review_source_and_rewrite_or_hold",
        })
    auditions = []
    plan = config.work_dir / "local-audio" / "voice-audition-plan.json"
    if plan.is_file():
        for job in json.loads(plan.read_text(encoding="utf-8")).get("jobs", []):
            error = None
            try:
                require_current_speech_jobs(config, [job], audition=True)
            except ValueError as exc:
                error = str(exc)
            auditions.append({
                "voice_id": job["voice_id"], "narration_id": job["source_narration_id"],
                "eligible_for_approval": error is None, "blocking_reason": error,
                "audio_retained": Path(job["output_audio"]).is_file(),
            })
    visuals = list(config.episodes_dir.glob("**/*visual*.json"))
    blockers = Counter(f for r in records for f in r["blocking_findings"])
    summary = {
        "narrations_screened": len(records),
        "structural_valid": sum(r["structural_validation_valid"] for r in records),
        "approved_personal_stories": sum(not r["blocking_findings"] for r in records),
        "blocked_pending_review_or_rewrite": sum(bool(r["blocking_findings"]) for r in records),
        "analysis_scaffolds_flagged": sum(bool(r["analysis_findings"]) for r in records),
        "blocking_finding_counts": dict(sorted(blockers.items())),
        "self_narrated_visual_files": len(visuals),
        "old_audition_jobs": len(auditions),
        "old_audition_jobs_blocked": sum(not a["eligible_for_approval"] for a in auditions),
    }
    report = {
        "contract_version": 1, "kind": "personal_story_content_audit", "summary": summary,
        "scope_note": "All drafts screened; only current evidence-backed sidecars count as editorially approved. Heuristic screening is not full semantic review.",
        "podcast_artifacts_preserved": True, "source_jobs_preserved": True,
        "network_calls": 0, "paid_calls": 0, "models_loaded": 0,
        "narrations": records, "auditions": auditions,
    }
    return report, [r for r in records if r["blocking_findings"]]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    config = ProjectConfig.load(args.config)
    directory = args.output_dir or config.work_dir / "quality"
    report, queue = audit(config)
    _write_json_atomic(directory / "personal-story-audit.json", report)
    _write_jsonl_atomic(directory / "personal-story-review-queue.jsonl", queue)
    print(json.dumps(report["summary"], indent=2))


if __name__ == "__main__":
    main()
