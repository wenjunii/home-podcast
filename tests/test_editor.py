from __future__ import annotations

import unittest

from home_podcast.editor import (
    _apply_deletion_plan,
    _parse_trim_plan,
    _spoken_words,
)


class EditorTests(unittest.TestCase):
    def test_parses_fenced_trim_plan(self) -> None:
        plan = _parse_trim_plan(
            '```json\n{"delete_segment_ids":["m1-s002"],'
            '"editorial_note":"Tighter."}\n```'
        )
        self.assertEqual(plan["delete_segment_ids"], ["m1-s002"])

    def test_applies_deletions_but_protects_quotes(self) -> None:
        script = {
            "segments": [
                {
                    "segment_id": "m1-s001",
                    "kind": "quote",
                    "text": "Home.",
                },
                {
                    "segment_id": "m1-s002",
                    "kind": "host_dialogue",
                    "text": "A repeated explanation goes here.",
                },
            ]
        }
        candidate, metrics = _apply_deletion_plan(
            script,
            {"delete_segment_ids": ["m1-s002"]},
        )
        self.assertEqual(len(candidate["segments"]), 1)
        self.assertEqual(metrics["deleted_segments"], 1)
        self.assertEqual(_spoken_words(candidate), 1)
        with self.assertRaisesRegex(ValueError, "protected"):
            _apply_deletion_plan(
                script,
                {"delete_segment_ids": ["m1-s001"]},
            )

    def test_replaces_only_transition_text(self) -> None:
        script = {
            "segments": [
                {
                    "segment_id": "m1-s001",
                    "kind": "transition",
                    "text": "Old handoff.",
                },
                {
                    "segment_id": "m2-s001",
                    "kind": "host_dialogue",
                    "text": "A sourced turn.",
                },
            ]
        }
        candidate, metrics = _apply_deletion_plan(
            script,
            {
                "delete_segment_ids": [],
                "replace_segments": [
                    {"segment_id": "m1-s001", "text": "New handoff."}
                ],
            },
        )
        self.assertEqual(candidate["segments"][0]["text"], "New handoff.")
        self.assertEqual(metrics["replaced_transitions"], 1)
        with self.assertRaisesRegex(ValueError, "Only transition"):
            _apply_deletion_plan(
                script,
                {
                    "delete_segment_ids": [],
                    "replace_segments": [
                        {"segment_id": "m2-s001", "text": "Unsafe rewrite."}
                    ],
                },
            )


if __name__ == "__main__":
    unittest.main()
