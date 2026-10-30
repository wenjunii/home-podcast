from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


@dataclass(frozen=True)
class OllamaJsonResponse:
    value: dict[str, Any]
    model: str
    done_reason: str
    prompt_eval_count: int
    eval_count: int
    total_duration_ns: int


class OllamaLocalClient:
    """Small local-only Ollama adapter used by the live storytelling worker.

    The adapter deliberately rejects non-loopback endpoints. Recovered Homes
    uses Ollama as an optional local runtime and never treats a previously
    configured paid provider key as authorization for this path.
    """

    def __init__(
        self,
        *,
        base_url: str = "http://127.0.0.1:11434",
        model: str = "gemma4:12b",
        timeout_seconds: float = 300.0,
    ) -> None:
        parsed = urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or parsed.hostname not in _LOCAL_HOSTS:
            raise ValueError("Ollama endpoint must be a loopback address")
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = float(timeout_seconds)

    def list_models(self) -> list[str]:
        payload = self._request("GET", "/api/tags")
        models = payload.get("models", [])
        return [
            str(item.get("name", ""))
            for item in models
            if isinstance(item, dict) and item.get("name")
        ]

    def generate_json(
        self,
        prompt: str,
        schema: dict[str, Any],
        *,
        seed: int,
        temperature: float = 0.85,
        top_p: float = 0.95,
        top_k: int = 64,
        num_ctx: int = 32768,
        keep_alive: str = "10m",
    ) -> OllamaJsonResponse:
        payload = self._request(
            "POST",
            "/api/generate",
            {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "format": schema,
                "keep_alive": keep_alive,
                "options": {
                    "seed": int(seed),
                    "temperature": float(temperature),
                    "top_p": float(top_p),
                    "top_k": int(top_k),
                    "num_ctx": int(num_ctx),
                },
            },
        )
        raw = payload.get("response")
        if not isinstance(raw, str) or not raw.strip():
            raise RuntimeError("Ollama returned an empty structured response")
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as error:
            raise RuntimeError("Ollama returned invalid JSON") from error
        if not isinstance(value, dict):
            raise RuntimeError("Ollama structured response must be a JSON object")
        return OllamaJsonResponse(
            value=value,
            model=str(payload.get("model") or self.model),
            done_reason=str(payload.get("done_reason") or ""),
            prompt_eval_count=int(payload.get("prompt_eval_count") or 0),
            eval_count=int(payload.get("eval_count") or 0),
            total_duration_ns=int(payload.get("total_duration") or 0),
        )

    def unload(self) -> None:
        """Ask the local Ollama daemon to release this model immediately."""

        self._request(
            "POST",
            "/api/generate",
            {
                "model": self.model,
                "prompt": "",
                "stream": False,
                "keep_alive": 0,
            },
        )

    def _request(
        self,
        method: str,
        path: str,
        value: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        body = None
        headers = {"Accept": "application/json"}
        if value is not None:
            body = json.dumps(value, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = Request(
            f"{self.base_url}{path}",
            data=body,
            headers=headers,
            method=method,
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"Local Ollama request failed with HTTP {error.code}: {detail[:500]}"
            ) from error
        except URLError as error:
            raise RuntimeError(
                f"Local Ollama is unavailable at {self.base_url}: {error.reason}"
            ) from error
        if not isinstance(payload, dict):
            raise RuntimeError("Ollama response must be a JSON object")
        return payload
