from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from home_podcast.script import render_tts_text, validate_script


class ScriptValidationTests(unittest.TestCase):
    def test_requires_complete_story_coverage_and_verbatim_quotes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = {
                "episode": {"episode_id": "2013-12.01"},
                "evidence": [
                    {"story_id": "story-a", "story_text": "Home travels with us."},
                    {"story_id": "story-b", "story_text": "A room can remember."},
                ],
            }
            bible = {
                "hosts": [
                    {"id": "curious_guide"},
                    {"id": "archive_nerd"},
                    {"id": "connector"},
                ]
            }
            script = {
                "contract_version": 1,
                "episode_id": "2013-12.01",
                "title": "A Home",
                "segments": [
                    {
                        "segment_id": "001",
                        "speaker": "curious_guide",
                        "kind": "host_dialogue",
                        "text": "Welcome home.",
                        "source_story_ids": [],
                        "pause_after_ms": 100,
                    },
                    {
                        "segment_id": "002",
                        "speaker": "connector",
                        "kind": "quote",
                        "text": "Home travels with us.",
                        "source_story_ids": ["story-a"],
                        "pause_after_ms": 200,
                    },
                    {
                        "segment_id": "003",
                        "speaker": "archive_nerd",
                        "kind": "host_dialogue",
                        "text": "And another fragment imagines a remembering room.",
                        "source_story_ids": ["story-b"],
                        "pause_after_ms": 0,
                    },
                ],
            }
            evidence_path = root / "evidence.json"
            bible_path = root / "bible.json"
            script_path = root / "script.json"
            evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
            bible_path.write_text(json.dumps(bible), encoding="utf-8")
            script_path.write_text(json.dumps(script), encoding="utf-8")
            report = validate_script(script_path, evidence_path, bible_path)
            self.assertTrue(report["valid"], report["errors"])

            script["segments"][1]["text"] = "This quote was invented."
            script_path.write_text(json.dumps(script), encoding="utf-8")
            report = validate_script(script_path, evidence_path, bible_path)
            self.assertFalse(report["valid"])

    def test_forbids_on_air_generation_identity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = {"episode": {"episode_id": "episode"}, "evidence": []}
            bible = {"hosts": [{"id": "curious_guide"}]}
            script = {
                "contract_version": 1,
                "episode_id": "episode",
                "title": "A Home",
                "segments": [
                    {
                        "segment_id": "001",
                        "speaker": "curious_guide",
                        "kind": "host_dialogue",
                        "text": "We are synthetic hosts.",
                        "source_story_ids": [],
                        "pause_after_ms": 0,
                    }
                ],
            }
            evidence_path = root / "evidence.json"
            bible_path = root / "bible.json"
            script_path = root / "script.json"
            evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
            bible_path.write_text(json.dumps(bible), encoding="utf-8")
            script_path.write_text(json.dumps(script), encoding="utf-8")
            report = validate_script(script_path, evidence_path, bible_path)
            self.assertFalse(report["valid"])
            self.assertIn("generation technology", report["errors"][0])

    def test_renders_delivery_as_non_transcript_audio_tags(self) -> None:
        rendered = render_tts_text(
            "That filename is incredible.",
            {},
            {"tone": "amused", "audio_tags": ["chuckles"]},
        )
        self.assertEqual(
            rendered,
            "[amused] [chuckles] That filename is incredible.",
        )
        self.assertEqual(
            render_tts_text(
                "That filename is incredible.",
                {},
                {"audio_tags": ["chuckles"]},
                supports_audio_tags=False,
            ),
            "That filename is incredible.",
        )


if __name__ == "__main__":
    unittest.main()
