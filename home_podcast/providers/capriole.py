from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


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
    ) -> None:
        self.endpoint = endpoint
        self.model = model
        self.api_key_env = api_key_env
        self.timeout_seconds = timeout_seconds
        self.max_attempts = max_attempts

    @classmethod
    def from_config(cls, provider: dict[str, Any]) -> "CaprioleChatClient":
        if provider.get("type") != "capriole":
            raise ValueError("Configured analysis provider is not Capriole")
        return cls(
            endpoint=str(provider["endpoint"]),
            model=str(provider["model"]),
            api_key_env=str(provider.get("api_key_env", "CAPRIOLE_API_KEY")),
            timeout_seconds=int(provider.get("timeout_seconds", 180)),
        )

    def complete(self, input_text: str) -> CaprioleResponse:
        api_key = os.environ.get(self.api_key_env)
        if not api_key:
            raise RuntimeError(
                f"Missing {self.api_key_env}; provide it as an environment variable"
            )
        payload = json.dumps(
            {"model": self.model, "input": input_text},
            ensure_ascii=False,
        ).encode("utf-8")
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
                    body = json.loads(response.read().decode("utf-8"))
                result = body.get("result", {})
                text = result.get("text")
                if not isinstance(text, str) or not text.strip():
                    raise RuntimeError("Capriole response did not contain result.text")
                usage = {
                    key: int(value)
                    for key, value in body.get("usage", {}).items()
                    if isinstance(value, (int, float))
                }
                return CaprioleResponse(
                    request_id=str(body.get("id", "")),
                    model=str(body.get("model", self.model)),
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
