from __future__ import annotations

import io
import unittest
import urllib.error

from home_podcast.provider_runner import (
    _parse_card,
    _sanitize_memorable_passages,
)
from home_podcast.providers.capriole import _safe_error_body


class ProviderRunnerTests(unittest.TestCase):
    def test_parses_fenced_json_and_forces_job_identity(self) -> None:
        job = {"story_id": "story-correct", "content_hash": "hash-correct"}
        card = _parse_card(
            """```json
            {
              "story_id": "story-wrong",
              "content_hash": "hash-wrong",
              "analysis": {"eligible": true}
            }
            ```""",
            job,
        )
        self.assertEqual(card["story_id"], "story-correct")
        self.assertEqual(card["content_hash"], "hash-correct")

    def test_discards_nonverbatim_memorable_passages(self) -> None:
        card = {
            "analysis": {
                "memorable_passages": [
                    "A house beside the river.",
                    "A paraphrase that was never in the source.",
                ]
            }
        }
        discarded = _sanitize_memorable_passages(
            card,
            {
                "story_text": "I remember a house beside the river. We left in June.",
                "accepted_filter_text": "home",
            },
        )
        self.assertEqual(discarded, 1)
        self.assertEqual(
            card["analysis"]["memorable_passages"],
            ["A house beside the river."],
        )

    def test_cloudfront_block_page_is_safely_summarized(self) -> None:
        error = urllib.error.HTTPError(
            "https://example.test",
            403,
            "Forbidden",
            {},
            io.BytesIO(
                b"<html><body><h1>403 ERROR</h1>"
                b"<p>Request blocked.</p></body></html>"
            ),
        )
        self.assertEqual(
            _safe_error_body(error),
            "upstream CDN blocked the request; this may be transient "
            "traffic or rate protection",
        )


if __name__ == "__main__":
    unittest.main()
