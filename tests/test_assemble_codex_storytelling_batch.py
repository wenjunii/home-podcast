from __future__ import annotations

import unittest
import json
import tempfile
from pathlib import Path

from scripts.assemble_codex_storytelling_batch import (
    CAPTURE_TIME_GAP,
    _assemble,
    _load_jobs,
)


class AssembleCodexStorytellingBatchTests(unittest.TestCase):
    def test_load_jobs_root_reads_locked_source_jobs_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            expected = [
                {"narration_id": "story-b", "value": 2},
                {"narration_id": "story-a", "value": 1},
            ]
            for index, value in enumerate(expected):
                target = root / f"narration-{index}" / "source-job.json"
                target.parent.mkdir()
                target.write_text(json.dumps(value), encoding="utf-8")
            (root / "not-a-narration.json").write_text("{}", encoding="utf-8")

            loaded = _load_jobs(jobs_root=root)

            self.assertEqual(loaded, expected)

    def test_assemble_injects_locked_identity_and_exact_evidence(self):
        job = {
            "narration_id": "2013-12--story-0123456789abcdef01234567",
            "source_story_id": "story-0123456789abcdef01234567",
            "source_content_hash": "a" * 64,
            "source_language": "en",
            "adaptation_language": "en",
            "required_evidence_excerpts": ["I carried the brass key home."],
            "required_gap_disclosures": ["The recovered source is missing its ending."],
        }
        draft = {
            "title": "The Brass Key",
            "perspective_mode": "first_person_preserved",
            "narrator_profile": {
                "personality_tags": ["reflective"],
                "emotional_range_tags": ["nostalgic"],
                "energy": "low",
                "casting_notes": "Keep it quiet.",
            },
            "sections": [
                {
                    "text": "I brought my brass key back home.",
                    "evidence_indices": [0],
                    "delivery": {
                        "emotion": "nostalgic",
                        "intensity": 0.4,
                        "pace": "measured",
                        "nonverbal": ["breath"],
                    },
                }
            ],
            "additional_unresolved_gaps": ["The opening context is unavailable."],
        }

        result = _assemble(draft, job)

        self.assertEqual(result["narration_id"], job["narration_id"])
        self.assertEqual(result["source_content_hash"], job["source_content_hash"])
        self.assertEqual(
            result["sections"][0]["source_evidence"],
            [
                {
                    "excerpt": "I carried the brass key home.",
                    "usage": "paraphrase_support",
                }
            ],
        )
        self.assertIn(CAPTURE_TIME_GAP, result["unresolved_gaps"])
        self.assertIn(
            "The recovered source is missing its ending.", result["unresolved_gaps"]
        )
        self.assertIn("The opening context is unavailable.", result["unresolved_gaps"])

    def test_assemble_rejects_incomplete_evidence_coverage(self):
        job = {
            "narration_id": "2013-12--story-0123456789abcdef01234567",
            "source_story_id": "story-0123456789abcdef01234567",
            "source_content_hash": "a" * 64,
            "source_language": "en",
            "adaptation_language": "en",
            "required_evidence_excerpts": ["first", "second"],
            "required_gap_disclosures": [],
        }
        draft = {
            "title": "Incomplete",
            "perspective_mode": "first_person_preserved",
            "narrator_profile": {},
            "sections": [
                {
                    "text": "I remember the first part.",
                    "evidence_indices": [0],
                    "delivery": {},
                }
            ],
        }

        with self.assertRaisesRegex(ValueError, "missing=\\[1\\]"):
            _assemble(draft, job)

    def test_assemble_accepts_all_evidence_shorthand(self):
        job = {
            "narration_id": "2013-12--story-0123456789abcdef01234567",
            "source_story_id": "story-0123456789abcdef01234567",
            "source_content_hash": "a" * 64,
            "source_language": "en",
            "adaptation_language": "en",
            "required_evidence_excerpts": ["first", "second"],
            "required_gap_disclosures": [],
        }
        draft = {
            "title": "Complete",
            "perspective_mode": "first_person_preserved",
            "narrator_profile": {
                "personality_tags": ["reflective"],
                "emotional_range_tags": ["warm"],
                "energy": "low",
                "casting_notes": "Keep it grounded.",
            },
            "sections": [
                {
                    "text": "I remember both parts.",
                    "evidence_indices": "all",
                    "delivery": {
                        "emotion": "reflective",
                        "intensity": 0.4,
                        "pace": "measured",
                        "nonverbal": [],
                    },
                }
            ],
        }

        result = _assemble(draft, job)

        self.assertEqual(
            [item["excerpt"] for item in result["sections"][0]["source_evidence"]],
            ["first", "second"],
        )


if __name__ == "__main__":
    unittest.main()
