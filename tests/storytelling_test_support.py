"""Explicit evidence-backed review fixtures; never used by production code."""
import json
from pathlib import Path

from home_podcast.storytelling_quality import content_digest


def write_review(directory: Path) -> None:
    adaptation = json.loads((directory / "adaptation.json").read_text(encoding="utf-8"))
    source_path = directory / "source-job.json"
    if not source_path.exists():
        source_path.write_text(json.dumps({
            "story_text": "I remember the road home.",
        }), encoding="utf-8")
    source = json.loads(source_path.read_text(encoding="utf-8"))
    review = {
        "contract_version": 1, "narration_id": adaptation["narration_id"],
        "decision": "approved_personal_story", "reviewed_by": "test-fixture",
        "reason": "Personal memory fixture, not automated production approval.",
        "adaptation_sha256": content_digest(adaptation),
        "source_job_sha256": content_digest(source),
        "approved_section_ids": [s["section_id"] for s in adaptation["sections"]],
        "reviewed_analysis": {
            "summary": "The narrator remembers home.",
            "narrator_evidence": source["story_text"],
            "personal_experience_evidence": source["story_text"],
            "locations": [{"name": "Hocking Hills", "evidence_excerpt": source["story_text"]}]
            if "Hocking Hills" in source["story_text"] else [],
        },
    }
    (directory / "personal-story-review.json").write_text(json.dumps(review), encoding="utf-8")
