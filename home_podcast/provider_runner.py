from __future__ import annotations

import hashlib
import json
import re
from concurrent.futures import CancelledError, ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from .analysis import store_story_card
from .config import ProjectConfig
from .providers import CaprioleChatClient, ProviderTrafficBlockedError


def analyze_story_jobs(
    config: ProjectConfig,
    jobs_path: Path,
    *,
    workers: int = 3,
    limit: int | None = None,
) -> dict[str, Any]:
    if not config.analysis_provider:
        raise ValueError("analysis_provider is not configured")
    client = CaprioleChatClient.from_config(config.analysis_provider)
    prompt_text = (config.project_root / "prompts" / "story_analysis.md").read_text(
        encoding="utf-8"
    )
    prompt_hash = hashlib.sha256(prompt_text.encode("utf-8")).hexdigest()[:12]
    analyzer = "capriole"
    analyzer_version = f"{client.model}@{prompt_hash}"
    cache_dir = (
        config.work_dir
        / "analysis"
        / "cache"
        / _safe_component(client.model)
        / prompt_hash
    )
    cache_dir.mkdir(parents=True, exist_ok=True)
    jobs = _read_jsonl(jobs_path)
    if limit is not None:
        jobs = jobs[:limit]

    total_usage: dict[str, int] = {}
    cached = generated = imported = failed = stale = 0
    cancelled_due_provider_block = 0
    provider_block_failures = 0
    traffic_halt_triggered = False
    failures: list[dict[str, str]] = []
    pending: list[dict[str, Any]] = []
    for job in jobs:
        cache_path = _cache_path(cache_dir, job)
        if cache_path.exists():
            try:
                card = json.loads(cache_path.read_text(encoding="utf-8"))
                if store_story_card(
                    config,
                    card,
                    analyzer=analyzer,
                    analyzer_version=analyzer_version,
                ):
                    cached += 1
                    imported += 1
                    continue
                stale += 1
            except (ValueError, json.JSONDecodeError):
                pass
        pending.append(job)

    def generate(job: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        response = client.complete(_build_prompt(prompt_text, job))
        card = _parse_card(response.text, job)
        discarded_passages = _sanitize_memorable_passages(card, job)
        metadata = {
            "provider": analyzer,
            "model": response.model,
            "request_id": response.request_id,
            "usage": response.usage,
            "prompt_hash": prompt_hash,
            "discarded_nonverbatim_passages": discarded_passages,
        }
        card["_generation"] = metadata
        return card, metadata

    completed = cached
    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        future_to_job = {executor.submit(generate, job): job for job in pending}
        for future in as_completed(future_to_job):
            job = future_to_job[future]
            completed += 1
            try:
                card, metadata = future.result()
                if not store_story_card(
                    config,
                    card,
                    analyzer=analyzer,
                    analyzer_version=analyzer_version,
                ):
                    stale += 1
                    continue
                _write_json_atomic(_cache_path(cache_dir, job), card)
                generated += 1
                imported += 1
                for key, value in metadata["usage"].items():
                    total_usage[key] = total_usage.get(key, 0) + int(value)
                print(
                    f"[{completed}/{len(jobs)}] analyzed {job['story_id']}",
                    flush=True,
                )
            except CancelledError:
                continue
            except ProviderTrafficBlockedError as error:
                failed += 1
                provider_block_failures += 1
                failures.append(
                    {
                        "story_id": str(job.get("story_id", "")),
                        "error": f"{type(error).__name__}: {error}",
                    }
                )
                print(
                    f"[{completed}/{len(jobs)}] BLOCKED {job.get('story_id')}: {error}",
                    flush=True,
                )
                if provider_block_failures >= 2 and not traffic_halt_triggered:
                    traffic_halt_triggered = True
                    for other in future_to_job:
                        if other.cancel():
                            cancelled_due_provider_block += 1
            except Exception as error:
                failed += 1
                failures.append(
                    {
                        "story_id": str(job.get("story_id", "")),
                        "error": f"{type(error).__name__}: {error}",
                    }
                )
                print(
                    f"[{completed}/{len(jobs)}] FAILED {job.get('story_id')}: {error}",
                    flush=True,
                )
    failure_path = cache_dir / "failures.jsonl"
    with failure_path.open("w", encoding="utf-8", newline="\n") as handle:
        for failure in failures:
            handle.write(json.dumps(failure, ensure_ascii=False) + "\n")
    return {
        "jobs": len(jobs),
        "cached": cached,
        "generated": generated,
        "imported": imported,
        "failed": failed,
        "stale": stale,
        "provider_traffic_blocked": traffic_halt_triggered,
        "cancelled_due_provider_block": cancelled_due_provider_block,
        "usage": total_usage,
        "analyzer_version": analyzer_version,
        "cache_dir": str(cache_dir),
        "failure_log": str(failure_path),
    }


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    jobs = []
    with path.open(encoding="utf-8-sig") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"Line {line_number}: expected a JSON object")
            jobs.append(value)
    return jobs


def _build_prompt(template: str, job: dict[str, Any]) -> str:
    return (
        f"{template.rstrip()}\n\n"
        "Return raw JSON only, without Markdown fences or commentary. The top-level "
        "object must contain story_id, content_hash, and analysis.\n\n"
        "SOURCE JOB:\n"
        f"{json.dumps(job, ensure_ascii=False, separators=(',', ':'))}"
    )


def _parse_card(text: str, job: dict[str, Any]) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("Model output did not contain a JSON object")
        value = json.loads(cleaned[start : end + 1])
    if not isinstance(value, dict):
        raise ValueError("Model output must be a JSON object")
    if "analysis" not in value and "eligible" in value:
        value = {
            "story_id": job["story_id"],
            "content_hash": job["content_hash"],
            "analysis": value,
        }
    value["story_id"] = job["story_id"]
    value["content_hash"] = job["content_hash"]
    return value


def _sanitize_memorable_passages(
    card: dict[str, Any], job: dict[str, Any]
) -> int:
    analysis = card.get("analysis")
    if not isinstance(analysis, dict):
        return 0
    passages = analysis.get("memorable_passages")
    if not isinstance(passages, list):
        return 0
    source = str(job.get("story_text", ""))
    valid = [
        passage
        for passage in passages
        if isinstance(passage, str)
        and passage.strip()
        and _normalize_text(passage) in _normalize_text(source)
    ]
    discarded = len(passages) - len(valid)
    if not valid:
        accepted = str(job.get("accepted_filter_text", "")).strip()
        if accepted and _normalize_text(accepted) in _normalize_text(source):
            valid = [accepted]
    analysis["memorable_passages"] = valid
    return discarded


def _cache_path(cache_dir: Path, job: dict[str, Any]) -> Path:
    return cache_dir / f"{job['story_id']}-{job['content_hash'][:16]}.json"


def _safe_component(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value)


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def _write_json_atomic(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
