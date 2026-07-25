from __future__ import annotations

import unittest

from home_podcast.polisher import _parse_polish_output, _validate_polished_group


class ConversationPolisherTests(unittest.TestCase):
    def test_preserves_quotes_and_protected_fields(self) -> None:
        originals = [
            {
                "segment_id": "m1-s001",
                "speaker": "curious_guide",
                "kind": "quote",
                "text": "Home travels with us.",
                "source_story_ids": ["story-a"],
                "delivery": {},
                "pronunciation": {},
                "pause_after_ms": 100,
            }
        ]
        polished = [{**originals[0], "text": "A changed quote."}]
        checked = _validate_polished_group(originals, polished)
        self.assertEqual(checked[0]["text"], "Home travels with us.")

    def test_accepts_delivery_reactions_without_putting_tags_in_text(self) -> None:
        originals = [
            {
                "segment_id": "m1-s001",
                "speaker": "archive_nerd",
                "kind": "host_dialogue",
                "text": "That filename is genuinely strange.",
                "source_story_ids": ["story-a"],
                "delivery": {},
                "pronunciation": {},
                "pause_after_ms": 0,
            }
        ]
        polished = [
            {
                **originals[0],
                "text": "That filename is honestly strange.",
                "delivery": {"audio_tags": ["chuckles"]},
            }
        ]
        checked = _validate_polished_group(originals, polished)
        self.assertEqual(checked[0]["delivery"]["audio_tags"], ["chuckles"])
        self.assertNotIn("[chuckles]", checked[0]["text"])

    def test_repairs_malformed_model_quote_from_protected_original(self) -> None:
        original = {
            "segment_id": "m1-s001",
            "speaker": "connector",
            "kind": "quote",
            "text": "\"Home,\" she said.",
            "source_story_ids": ["story-a"],
            "delivery": {},
            "pronunciation": {},
            "pause_after_ms": 0,
        }
        malformed = (
            '{"segments":[{"segment_id":"m1-s001","speaker":"connector",'
            '"kind":"quote","text":""Home," she said.",'
            '"source_story_ids":["story-a"],"delivery":{},"pronunciation":{},'
            '"pause_after_ms":0}]}'
        )
        parsed = _parse_polish_output(malformed, originals=[original])
        self.assertEqual(parsed["segments"][0]["text"], "\"Home,\" she said.")


if __name__ == "__main__":
    unittest.main()
