from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from home_podcast.transcripts import render_transcripts


class TranscriptTests(unittest.TestCase):
    def test_includes_sound_disclosure_and_accessible_cue_labels(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            timeline_path = root / "timeline.json"
            bible_path = root / "show-bible.json"
            timeline_path.write_text(
                json.dumps(
                    {
                        "episode_id": "test-episode",
                        "sound_design": {
                            "disclosure": "All sounds are illustrative."
                        },
                        "sound_cues": [
                            {
                                "start_ms": 0,
                                "end_ms": 500,
                                "transcript_label": "soft paper movement",
                            }
                        ],
                        "segments": [
                            {
                                "segment_id": "s1",
                                "speaker": "curious_guide",
                                "text": "Hello.",
                                "source_story_ids": ["story-a"],
                                "start_ms": 0,
                                "end_ms": 1000,
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            bible_path.write_text(
                json.dumps(
                    {
                        "hosts": [
                            {
                                "id": "curious_guide",
                                "display_name": "Maya",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            paths = render_transcripts(timeline_path, bible_path, root / "output")
            markdown = paths["markdown"].read_text(encoding="utf-8")
            vtt = paths["vtt"].read_text(encoding="utf-8")
            self.assertIn("Sound design note: All sounds are illustrative.", markdown)
            self.assertIn("[soft paper movement]", markdown)
            self.assertIn("[soft paper movement]", vtt)
            self.assertNotIn("synthetic hosts", markdown)
            self.assertLess(
                markdown.index("[soft paper movement]"),
                markdown.index("Maya:"),
            )


if __name__ == "__main__":
    unittest.main()
