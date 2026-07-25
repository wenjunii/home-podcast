from __future__ import annotations

import io
import json
import os
import urllib.error
import unittest
from email.message import Message
from unittest.mock import patch

from home_podcast.providers.elevenlabs import (
    ElevenLabsSpeechClient,
    ElevenLabsSoundEffectsClient,
    _safe_error_body,
)


class _Response:
    def __init__(self, audio: bytes = b"ID3-test-audio") -> None:
        self.audio = audio
        self.headers = Message()
        self.headers["Content-Type"] = "audio/mpeg"
        self.headers["request-id"] = "request-1"
        self.headers["character-cost"] = "42"

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self.audio


class ElevenLabsClientTests(unittest.TestCase):
    def test_builds_documented_speech_request(self) -> None:
        client = ElevenLabsSpeechClient(
            endpoint="https://api.example.test/v1/text-to-speech",
            model="eleven_multilingual_v2",
            max_attempts=1,
            voice_settings={"stability": 0.5},
        )
        with (
            patch.dict(os.environ, {"ELEVENLABS_API_KEY": "secret-test-value"}),
            patch(
                "home_podcast.providers.elevenlabs.urllib.request.urlopen",
                return_value=_Response(),
            ) as urlopen,
        ):
            response = client.generate(
                "A recovered home.",
                voice_id="voice-123",
                previous_text="Before.",
                next_text="After.",
                seed=42,
            )

        request = urlopen.call_args.args[0]
        body = json.loads(request.data)
        self.assertEqual(
            request.full_url,
            "https://api.example.test/v1/text-to-speech/"
            "voice-123?output_format=mp3_44100_128",
        )
        self.assertEqual(request.get_header("Xi-api-key"), "secret-test-value")
        self.assertEqual(body["text"], "A recovered home.")
        self.assertEqual(body["model_id"], "eleven_multilingual_v2")
        self.assertEqual(body["language_code"], "en")
        self.assertEqual(body["voice_settings"], {"stability": 0.5})
        self.assertEqual(body["previous_text"], "Before.")
        self.assertEqual(body["next_text"], "After.")
        self.assertEqual(body["seed"], 42)
        self.assertEqual(response.audio, b"ID3-test-audio")

    def test_omits_unsupported_neighbor_context_for_eleven_v3(self) -> None:
        client = ElevenLabsSpeechClient(
            endpoint="https://api.example.test/v1/text-to-speech",
            model="eleven_v3",
            max_attempts=1,
        )
        with (
            patch.dict(os.environ, {"ELEVENLABS_API_KEY": "secret-test-value"}),
            patch(
                "home_podcast.providers.elevenlabs.urllib.request.urlopen",
                return_value=_Response(),
            ) as urlopen,
        ):
            client.generate(
                "A recovered home.",
                voice_id="voice-123",
                previous_text="Before.",
                next_text="After.",
            )

        body = json.loads(urlopen.call_args.args[0].data)
        self.assertNotIn("previous_text", body)
        self.assertNotIn("next_text", body)

    def test_speech_requires_environment_credential(self) -> None:
        client = ElevenLabsSpeechClient(
            endpoint="https://api.example.test/v1/text-to-speech",
            max_attempts=1,
        )
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "ELEVENLABS_API_KEY"):
                client.generate("A line.", voice_id="voice-123")

    def test_builds_documented_sound_generation_request(self) -> None:
        client = ElevenLabsSoundEffectsClient(
            endpoint="https://api.example.test/v1/sound-generation",
            model="eleven_text_to_sound_v2",
            max_attempts=1,
        )
        with (
            patch.dict(os.environ, {"ELEVENLABS_API_KEY": "secret-test-value"}),
            patch(
                "home_podcast.providers.elevenlabs.urllib.request.urlopen",
                return_value=_Response(),
            ) as urlopen,
        ):
            response = client.generate(
                "Quiet paper movement.",
                duration_seconds=1.5,
                loop=True,
            )

        request = urlopen.call_args.args[0]
        body = json.loads(request.data)
        self.assertEqual(request.full_url, client.endpoint)
        self.assertEqual(request.get_header("Xi-api-key"), "secret-test-value")
        self.assertEqual(body["text"], "Quiet paper movement.")
        self.assertEqual(body["duration_seconds"], 1.5)
        self.assertTrue(body["loop"])
        self.assertEqual(body["prompt_influence"], 0.3)
        self.assertEqual(body["model_id"], "eleven_text_to_sound_v2")
        self.assertEqual(response.audio, b"ID3-test-audio")
        self.assertEqual(response.request_id, "request-1")

    def test_requires_environment_credential(self) -> None:
        client = ElevenLabsSoundEffectsClient(
            endpoint="https://api.example.test/v1/sound-generation",
            max_attempts=1,
        )
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "ELEVENLABS_API_KEY"):
                client.generate("A sound.", duration_seconds=1, loop=False)

    def test_retries_rate_limit_and_redacts_secret_like_error(self) -> None:
        headers = Message()
        headers["Retry-After"] = "0"
        exposed_value = "sk_" + "a" * 48
        error = urllib.error.HTTPError(
            "https://api.example.test",
            429,
            "Too Many Requests",
            headers,
            io.BytesIO(
                json.dumps(
                    {"detail": {"message": f"Do not print {exposed_value}"}}
                ).encode("utf-8")
            ),
        )
        self.assertNotIn(exposed_value, _safe_error_body(error))

        second_error = urllib.error.HTTPError(
            "https://api.example.test",
            429,
            "Too Many Requests",
            headers,
            io.BytesIO(b'{"detail":{"message":"slow down"}}'),
        )
        client = ElevenLabsSoundEffectsClient(
            endpoint="https://api.example.test/v1/sound-generation",
            max_attempts=2,
        )
        with (
            patch.dict(os.environ, {"ELEVENLABS_API_KEY": "secret-test-value"}),
            patch(
                "home_podcast.providers.elevenlabs.urllib.request.urlopen",
                side_effect=[second_error, _Response()],
            ) as urlopen,
            patch("home_podcast.providers.elevenlabs.time.sleep"),
        ):
            response = client.generate("A sound.", duration_seconds=1, loop=False)
        self.assertEqual(urlopen.call_count, 2)
        self.assertEqual(response.request_id, "request-1")


if __name__ == "__main__":
    unittest.main()
