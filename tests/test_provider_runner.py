from __future__ import annotations

import io
import unittest
import urllib.error

from home_podcast.provider_runner import (
    _parse_card,
    _sanitize_memorable_passages,
)
from home_podcast.providers.capriole import _safe_error_body
from home_podcast.providers.capriole import _consume_anthropic_sse
from home_podcast.providers.capriole import _consume_openai_sse
from home_podcast.providers.capriole import _anthropic_messages_model


class ProviderRunnerTests(unittest.TestCase):
    def test_normalizes_catalog_model_for_messages_endpoint(self) -> None:
        self.assertEqual(
            _anthropic_messages_model("anthropic/claude-opus-4-6"),
            "claude-opus-4-6",
        )

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

    def test_consumes_openai_compatible_sse(self) -> None:
        response = io.BytesIO(
            b'data: {"id":"req-1","model":"fable","choices":'
            b'[{"delta":{"content":"Hello "}}]}\n\n'
            b'data: {"id":"req-1","model":"fable","choices":'
            b'[{"delta":{"content":"home."}}]}\n\n'
            b'data: {"id":"req-1","model":"fable","choices":[],'
            b'"usage":{"input_tokens":10,"output_tokens":2}}\n\n'
            b"data: [DONE]\n\n"
        )
        result = _consume_openai_sse(response, "fallback")
        self.assertEqual(result.text, "Hello home.")
        self.assertEqual(result.model, "fable")
        self.assertEqual(result.usage["input_tokens"], 10)

    def test_consumes_anthropic_compatible_sse(self) -> None:
        response = io.BytesIO(
            b'event: message_start\n'
            b'data: {"type":"message_start","message":{"id":"msg-1",'
            b'"model":"claude-opus-4-6","usage":{"input_tokens":10}}}\n\n'
            b'event: content_block_delta\n'
            b'data: {"type":"content_block_delta","index":0,'
            b'"delta":{"type":"text_delta","text":"Hello home."}}\n\n'
            b'event: message_delta\n'
            b'data: {"type":"message_delta","usage":{"output_tokens":2}}\n\n'
            b'event: message_stop\n'
            b'data: {"type":"message_stop"}\n\n'
        )
        result = _consume_anthropic_sse(response, "fallback")
        self.assertEqual(result.text, "Hello home.")
        self.assertEqual(result.model, "claude-opus-4-6")
        self.assertEqual(result.usage["input_tokens"], 10)
        self.assertEqual(result.usage["output_tokens"], 2)


if __name__ == "__main__":
    unittest.main()
