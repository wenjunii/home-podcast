from __future__ import annotations

import unittest

from home_podcast.script_runner import (
    _compact_evidence_packet,
    _parse_script_output,
    _script_metrics,
)


class ScriptRunnerTests(unittest.TestCase):
    def test_parses_fenced_script_json(self) -> None:
        script = _parse_script_output(
            """```json
            {
              "contract_version": 1,
              "episode_id": "2013-12.01",
              "title": "A Home",
              "segments": []
            }
            ```"""
        )
        self.assertEqual(script["episode_id"], "2013-12.01")

    def test_reports_spoken_word_and_time_estimates(self) -> None:
        metrics = _script_metrics(
            {
                "segments": [
                    {"text": "One two three."},
                    {"text": "Four five six."},
                ]
            }
        )
        self.assertEqual(metrics["spoken_words"], 6)
        self.assertEqual(metrics["spoken_characters"], 28)
        self.assertEqual(metrics["estimated_minutes"], 0.0)

    def test_compacts_duplicate_source_fields_before_generation(self) -> None:
        packet = {
            "episode": {"episode_id": "2013-12.01"},
            "show_bible": {"hosts": []},
            "writing_requirements": {},
            "evidence": [
                {
                    "story_id": "story-a",
                    "story_text": "The source once.",
                    "source_markdown": "The source a second time.",
                    "accepted_filter_text": "source",
                    "story_card": {
                        "summary": "A source.",
                        "memorable_passages": ["The source once."],
                    },
                }
            ],
        }
        compact = _compact_evidence_packet(packet)
        self.assertEqual(
            compact["evidence"][0]["story_card"]["summary"],
            "A source.",
        )
        self.assertNotIn("story_text", compact["evidence"][0])
        self.assertNotIn("source_markdown", compact["evidence"][0])
        self.assertNotIn("accepted_filter_text", compact["evidence"][0])


if __name__ == "__main__":
    unittest.main()
