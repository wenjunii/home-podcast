from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, BinaryIO


class ProviderTrafficBlockedError(RuntimeError):
    """The upstream edge rejected traffic before the model handled it."""


@dataclass(frozen=True)
class CaprioleResponse:
    request_id: str
    model: str
    text: str
    usage: dict[str, int]


class CaprioleChatClient:
    def __init__(
        self,
        *,
        endpoint: str,
        model: str,
        api_key_env: str = "CAPRIOLE_API_KEY",
        timeout_seconds: int = 180,
        max_attempts: int = 4,
        protocol: str = "native_chat",
        max_tokens: int = 4096,
    ) -> None:
        self.endpoint = endpoint
        self.model = model
        self.api_key_env = api_key_env
        self.timeout_seconds = timeout_seconds
        self.max_attempts = max_attempts
        self.protocol = protocol
        self.max_tokens = max_tokens

    @classmethod
    def from_config(cls, provider: dict[str, Any]) -> "CaprioleChatClient":
        if provider.get("type") != "capriole":
            raise ValueError("Configured analysis provider is not Capriole")
        return cls(
            endpoint=str(provider["endpoint"]),
            model=str(provider["model"]),
            api_key_env=str(provider.get("api_key_env", "CAPRIOLE_API_KEY")),
            timeout_seconds=int(provider.get("timeout_seconds", 180)),
            max_attempts=int(provider.get("max_attempts", 4)),
            protocol=str(provider.get("protocol", "native_chat")),
            max_tokens=int(provider.get("max_tokens", 4096)),
        )

    def complete(self, input_text: str) -> CaprioleResponse:
        api_key = os.environ.get(self.api_key_env)
        if not api_key:
            raise RuntimeError(
                f"Missing {self.api_key_env}; provide it as an environment variable"
            )
        if self.protocol == "native_chat":
            body = {"model": self.model, "input": input_text}
        elif self.protocol == "openai_chat_completions_stream":
            body = {
                "model": self.model,
                "messages": [{"role": "user", "content": input_text}],
                "stream": True,
                "stream_options": {"include_usage": True},
            }
        elif self.protocol == "anthropic_messages_stream":
            body = {
                "model": _anthropic_messages_model(self.model),
                "max_tokens": self.max_tokens,
                "messages": [{"role": "user", "content": input_text}],
                "stream": True,
            }
        else:
            raise ValueError(f"Unsupported Capriole protocol: {self.protocol}")
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            self.endpoint,
            data=payload,
            method="POST",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "User-Agent": "home-podcast/0.1",
            },
        )
        last_error: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                with urllib.request.urlopen(
                    request, timeout=self.timeout_seconds
                ) as response:
                    if self.protocol == "openai_chat_completions_stream":
                        return _consume_openai_sse(response, self.model)
                    if self.protocol == "anthropic_messages_stream":
                        return _consume_anthropic_sse(response, self.model)
                    response_body = json.loads(response.read().decode("utf-8"))
                result = response_body.get("result", {})
                text = result.get("text")
                if not isinstance(text, str) or not text.strip():
                    raise RuntimeError("Capriole response did not contain result.text")
                usage = _numeric_usage(response_body.get("usage", {}))
                return CaprioleResponse(
                    request_id=str(response_body.get("id", "")),
                    model=str(response_body.get("model", self.model)),
                    text=text,
                    usage=usage,
                )
            except urllib.error.HTTPError as error:
                safe_body = _safe_error_body(error)
                if error.code == 403 and safe_body.startswith(
                    "upstream CDN blocked"
                ):
                    raise ProviderTrafficBlockedError(
                        f"Capriole HTTP 403: {safe_body}"
                    ) from error
                last_error = RuntimeError(
                    f"Capriole HTTP {error.code}: {safe_body}"
                )
                if error.code not in {408, 409, 429, 500, 502, 503, 504}:
                    break
            except (urllib.error.URLError, TimeoutError, RuntimeError) as error:
                last_error = error
            if attempt < self.max_attempts:
                time.sleep(min(2 ** (attempt - 1), 8))
        raise RuntimeError(f"Capriole request failed: {last_error}")


def _safe_error_body(error: urllib.error.HTTPError) -> str:
    try:
        text = error.read().decode("utf-8", errors="replace")
    except Exception:
        return error.reason or "request failed"
    compact = " ".join(text.split())
    lowered = compact.casefold()
    if "<html" in lowered and "request blocked" in lowered:
        return (
            "upstream CDN blocked the request; this may be transient "
            "traffic or rate protection"
        )
    return compact[:500]


def _consume_openai_sse(
    response: BinaryIO,
    fallback_model: str,
) -> CaprioleResponse:
    text_parts: list[str] = []
    request_id = ""
    model = fallback_model
    usage: dict[str, int] = {}
    for raw_line in response:
        line = raw_line.decode("utf-8", errors="replace").strip()
        if not line or line.startswith(":") or not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if data == "[DONE]":
            break
        event = json.loads(data)
        if "error" in event:
            raise RuntimeError(
                f"Capriole stream error: {str(event['error'])[:500]}"
            )
        request_id = str(event.get("id", request_id))
        model = str(event.get("model", model))
        event_usage = _numeric_usage(event.get("usage", {}))
        if event_usage:
            usage = event_usage
        for choice in event.get("choices", []):
            delta = choice.get("delta", {})
            content = delta.get("content")
            if isinstance(content, str):
                text_parts.append(content)
    text = "".join(text_parts)
    if not text.strip():
        raise RuntimeError("Capriole stream did not contain response text")
    return CaprioleResponse(
        request_id=request_id,
        model=model,
        text=text,
        usage=usage,
    )


def _consume_anthropic_sse(
    response: BinaryIO,
    fallback_model: str,
) -> CaprioleResponse:
    text_parts: list[str] = []
    request_id = ""
    model = fallback_model
    usage: dict[str, int] = {}
    for raw_line in response:
        line = raw_line.decode("utf-8", errors="replace").strip()
        if not line or line.startswith(":") or not line.startswith("data:"):
            continue
        event = json.loads(line[5:].strip())
        event_type = event.get("type")
        if event_type == "error":
            raise RuntimeError(
                f"Capriole stream error: {str(event.get('error'))[:500]}"
            )
        if event_type == "message_start":
            message = event.get("message", {})
            request_id = str(message.get("id", request_id))
            model = str(message.get("model", model))
            usage.update(_numeric_usage(message.get("usage", {})))
        elif event_type == "content_block_delta":
            delta = event.get("delta", {})
            text = delta.get("text")
            if isinstance(text, str):
                text_parts.append(text)
        elif event_type == "message_delta":
            usage.update(_numeric_usage(event.get("usage", {})))
    text = "".join(text_parts)
    if not text.strip():
        raise RuntimeError("Capriole stream did not contain response text")
    return CaprioleResponse(
        request_id=request_id,
        model=model,
        text=text,
        usage=usage,
    )


def _numeric_usage(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    return {
        key: int(item)
        for key, item in value.items()
        if isinstance(item, (int, float))
    }


def _anthropic_messages_model(value: str) -> str:
    prefix = "anthropic/"
    return value[len(prefix) :] if value.startswith(prefix) else value
