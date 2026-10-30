from __future__ import annotations

import unittest

from scripts.build_storytelling_preflight import _quality_findings
from scripts.clean_storytelling_for_speech import _sanitize_text


class StorytellingPreflightTests(unittest.TestCase):
    def test_speech_cleanup_repairs_encoding_and_removes_contact_data(self):
        cleaned, operations = _sanitize_text(
            "Iâ€™m home. Visit https://example.test or me@example.test."
        )

        self.assertEqual(cleaned, "I'm home. Visit or.")
        self.assertIn("repaired_character_encoding", operations)
        self.assertIn("replaced_spoken_url", operations)
        self.assertIn("replaced_spoken_email_address", operations)

    def test_preflight_blocks_archived_contact_placeholders(self):
        adaptation = {
            "adaptation_notes": [],
            "sections": [
                {
                    "text": "I followed the archived link home.",
                    "delivery": {"nonverbal": ["breath"]},
                }
            ],
        }

        blockers, _ = _quality_findings(adaptation, {"valid": True})

        self.assertIn("archived_contact_placeholder", blockers)


if __name__ == "__main__":
    unittest.main()
