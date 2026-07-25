from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from email.message import Message
from typing import Any


RETRYABLE_STATUS_CODES = {408, 409, 429, 500, 502, 503, 504}


@dataclass(frozen=True)
class ElevenLabsSoundEffectResponse:
    audio: bytes
    content_type: str
    request_id: str
    character_cost: str


@dataclass(frozen=True)
class ElevenLabsSpeechResponse:
    audio: bytes
    content_type: str
    request_id: str
    character_cost: str


class ElevenLabsSpeechClient:
    def __init__(
        self,
        *,
        endpoint: str,
        model: str = "eleven_v3",
        api_key_env: str = "ELEVENLABS_API_KEY",
        timeout_seconds: int = 180,
        max_attempts: int = 4,
        output_format: str = "mp3_44100_128",
        language_code: str | None = "en",
        voice_settings: dict[str, Any] | None = None,
    ) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.model = model
        self.api_key_env = api_key_env
        self.timeout_seconds = timeout_seconds
        self.max_attempts = max(1, max_attempts)
        self.output_format = output_format
        self.language_code = language_code
        self.voice_settings = voice_settings or {}

    @classmethod
    def from_config(cls, provider: dict[str, Any]) -> "ElevenLabsSpeechClient":
        if provider.get("type") != "elevenlabs_tts":
            raise ValueError("Configured speech provider is not ElevenLabs TTS")
        settings = provider.get("voice_settings", {})
        if not isinstance(settings, dict):
            raise ValueError("speech_provider.voice_settings must be an object")
        return cls(
            endpoint=str(provider["endpoint"]),
            model=str(provider.get("model", "eleven_v3")),
            api_key_env=str(provider.get("api_key_env", "ELEVENLABS_API_KEY")),
            timeout_seconds=int(provider.get("timeout_seconds", 180)),
            max_attempts=int(provider.get("max_attempts", 4)),
            output_format=str(provider.get("output_format", "mp3_44100_128")),
            language_code=provider.get("language_code", "en"),
            voice_settings=settings,
        )

    def generate(
        self,
        text: str,
        *,
        voice_id: str,
        previous_text: str | None = None,
        next_text: str | None = None,
        seed: int | None = None,
    ) -> ElevenLabsSpeechResponse:
        api_key = os.environ.get(self.api_key_env)
        if not api_key:
            raise RuntimeError(
                f"Missing {self.api_key_env}; provide it as an environment variable"
            )
        if not text.strip():
            raise ValueError("Speech text cannot be empty")
        if len(text) > 5000 and self.model == "eleven_v3":
            raise ValueError("Eleven v3 speech text cannot exceed 5000 characters")
        if not re.fullmatch(r"[A-Za-z0-9_-]+", voice_id):
            raise ValueError("voice_id contains unsupported characters")
        if seed is not None and not 0 <= seed <= 4_294_967_295:
            raise ValueError("seed must be from 0 to 4294967295")

        body: dict[str, Any] = {
            "text": text,
            "model_id": self.model,
        }
        if self.language_code:
            body["language_code"] = self.language_code
        if self.voice_settings:
            body["voice_settings"] = self.voice_settings
        if previous_text and self.model != "eleven_v3":
            body["previous_text"] = previous_text
        if next_text and self.model != "eleven_v3":
            body["next_text"] = next_text
        if seed is not None:
            body["seed"] = seed

        query = urllib.parse.urlencode({"output_format": self.output_format})
        request = urllib.request.Request(
            f"{self.endpoint}/{voice_id}?{query}",
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            method="POST",
            headers={
                "xi-api-key": api_key,
                "Content-Type": "application/json",
                "Accept": "audio/mpeg",
                "User-Agent": "home-podcast/0.1",
            },
        )
        last_error: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                with urllib.request.urlopen(
                    request,
                    timeout=self.timeout_seconds,
                ) as response:
                    audio = response.read()
                    if not audio:
                        raise RuntimeError("ElevenLabs returned an empty audio response")
                    headers = response.headers
                    return ElevenLabsSpeechResponse(
                        audio=audio,
                        content_type=str(
                            headers.get("Content-Type", "audio/mpeg")
                        ).split(";")[0],
                        request_id=str(
                            headers.get("request-id")
                            or headers.get("x-request-id")
                            or ""
                        ),
                        character_cost=str(headers.get("character-cost", "")),
                    )
            except urllib.error.HTTPError as error:
                last_error = RuntimeError(
                    f"ElevenLabs HTTP {error.code}: {_safe_error_body(error)}"
                )
                if error.code not in RETRYABLE_STATUS_CODES:
                    break
                retry_seconds = _retry_after_seconds(error.headers)
            except (urllib.error.URLError, TimeoutError, RuntimeError) as error:
                last_error = error
                retry_seconds = None
            if attempt < self.max_attempts:
                time.sleep(
                    retry_seconds
                    if retry_seconds is not None
                    else min(2 ** (attempt - 1), 8)
                )
        raise RuntimeError(f"ElevenLabs speech generation failed: {last_error}")


class ElevenLabsSoundEffectsClient:
    def __init__(
        self,
        *,
        endpoint: str,
        model: str = "eleven_text_to_sound_v2",
        api_key_env: str = "ELEVENLABS_API_KEY",
        timeout_seconds: int = 180,
        max_attempts: int = 4,
        prompt_influence: float = 0.3,
    ) -> None:
        if not 0 <= prompt_influence <= 1:
            raise ValueError("prompt_influence must be from 0 to 1")
        self.endpoint = endpoint
        self.model = model
        self.api_key_env = api_key_env
        self.timeout_seconds = timeout_seconds
        self.max_attempts = max(1, max_attempts)
        self.prompt_influence = prompt_influence

    @classmethod
    def from_config(
        cls,
        provider: dict[str, Any],
    ) -> "ElevenLabsSoundEffectsClient":
        if provider.get("type") != "elevenlabs_sound_effects":
            raise ValueError("Configured sound-effects provider is not ElevenLabs")
        return cls(
            endpoint=str(provider["endpoint"]),
            model=str(provider.get("model", "eleven_text_to_sound_v2")),
            api_key_env=str(provider.get("api_key_env", "ELEVENLABS_API_KEY")),
            timeout_seconds=int(provider.get("timeout_seconds", 180)),
            max_attempts=int(provider.get("max_attempts", 4)),
            prompt_influence=float(provider.get("prompt_influence", 0.3)),
        )

    def generate(
        self,
        prompt: str,
        *,
        duration_seconds: float,
        loop: bool,
    ) -> ElevenLabsSoundEffectResponse:
        api_key = os.environ.get(self.api_key_env)
        if not api_key:
            raise RuntimeError(
                f"Missing {self.api_key_env}; provide it as an environment variable"
            )
        if not prompt.strip():
            raise ValueError("Sound-effect prompt cannot be empty")
        if not 0.5 <= duration_seconds <= 30:
            raise ValueError("duration_seconds must be from 0.5 to 30")
        body = {
            "text": prompt,
            "loop": loop,
            "duration_seconds": duration_seconds,
            "prompt_influence": self.prompt_influence,
            "model_id": self.model,
        }
        request = urllib.request.Request(
            self.endpoint,
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            method="POST",
            headers={
                "xi-api-key": api_key,
                "Content-Type": "application/json",
                "Accept": "audio/mpeg",
                "User-Agent": "home-podcast/0.1",
            },
        )
        last_error: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                with urllib.request.urlopen(
                    request,
                    timeout=self.timeout_seconds,
                ) as response:
                    audio = response.read()
                    if not audio:
                        raise RuntimeError("ElevenLabs returned an empty audio response")
                    headers = response.headers
                    return ElevenLabsSoundEffectResponse(
                        audio=audio,
                        content_type=str(
                            headers.get("Content-Type", "audio/mpeg")
                        ).split(";")[0],
                        request_id=str(
                            headers.get("request-id")
                            or headers.get("x-request-id")
                            or ""
                        ),
                        character_cost=str(headers.get("character-cost", "")),
                    )
            except urllib.error.HTTPError as error:
                last_error = RuntimeError(
                    f"ElevenLabs HTTP {error.code}: {_safe_error_body(error)}"
                )
                if error.code not in RETRYABLE_STATUS_CODES:
                    break
                retry_seconds = _retry_after_seconds(error.headers)
            except (urllib.error.URLError, TimeoutError, RuntimeError) as error:
                last_error = error
                retry_seconds = None
            if attempt < self.max_attempts:
                time.sleep(
                    retry_seconds
                    if retry_seconds is not None
                    else min(2 ** (attempt - 1), 8)
                )
        raise RuntimeError(f"ElevenLabs sound generation failed: {last_error}")


def _safe_error_body(error: urllib.error.HTTPError) -> str:
    try:
        value = json.loads(error.read().decode("utf-8", errors="replace"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return str(error.reason or "request failed")[:300]
    if not isinstance(value, dict):
        return "request failed"
    detail = value.get("detail", value)
    if isinstance(detail, dict):
        message = detail.get("message") or detail.get("status") or "request failed"
    else:
        message = str(detail)
    compact = " ".join(str(message).split())[:300]
    return re.sub(r"sk[_-][A-Za-z0-9_-]{20,}", "[redacted]", compact)


def _retry_after_seconds(headers: Message | None) -> float | None:
    if headers is None:
        return None
    value = headers.get("Retry-After")
    if value is None:
        return None
    try:
        return max(0.0, min(float(value), 60.0))
    except ValueError:
        return None
