from __future__ import annotations

import hashlib
import json
import os
import re
import unicodedata
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Callable

from .config import ProjectConfig
from .providers import CaprioleChatClient, ProviderTrafficBlockedError

LOCATION_ROLES = {
    "home",
    "origin",
    "destination",
    "setting",
    "memory",
    "mentioned",
}
IDENTITY_ATTRIBUTES = {
    "gender",
    "age",
    "race",
    "ethnicity",
    "nationality",
    "religion",
    "disability",
    "class",
    "other",
}
UNKNOWN_IDENTITY_ALIASES = {
    "age_at_time_of_speech": "age",
}
TARGET_TOKEN_MINIMUM = 68
CONTENT_TOKEN_LIMIT = 75
MAXIMUM_LOCAL_TRIM_TOKENS = 15
EVIDENCE_SNAP_MINIMUM_SIMILARITY = 0.88
REMOVABLE_TRAILING_MODIFIERS = {
    "atmospheric",
    "cinematic",
    "detailed",
    "gentle",
    "nostalgic",
    "quiet",
    "rich",
    "subtle",
    "tactile",
    "warm",
}


@dataclass(frozen=True)
class TokenCount:
    maximum: int
    by_tokenizer: dict[str, int]


class SdxlTokenCounter:
    """Count content tokens with every CLIP tokenizer bundled with an SDXL model."""

    def __init__(self, model_root: Path, tokenizers: dict[str, Any]) -> None:
        self.model_root = model_root
        self.tokenizers = tokenizers

    @classmethod
    def load(cls, model_reference: str) -> "SdxlTokenCounter":
        model_root = _resolve_sdxl_model_root(model_reference)
        try:
            from transformers import CLIPTokenizer
        except ImportError as error:
            raise RuntimeError(
                "Exact SDXL token validation requires the optional "
                "'transformers' package"
            ) from error

        tokenizers: dict[str, Any] = {}
        for name in ("tokenizer", "tokenizer_2"):
            tokenizer_path = model_root / name
            if not tokenizer_path.is_dir():
                continue
            tokenizers[name] = CLIPTokenizer.from_pretrained(
                str(tokenizer_path),
                local_files_only=True,
            )
        if not tokenizers:
            raise RuntimeError(
                f"No SDXL tokenizer directories found under {model_root}. "
                "Pass --tokenizer-model with a local SDXL model or snapshot path."
            )
        return cls(model_root, tokenizers)

    def count(self, text: str) -> TokenCount:
        counts: dict[str, int] = {}
        for name, tokenizer in self.tokenizers.items():
            token_ids = tokenizer(
                text,
                add_special_tokens=True,
                truncation=False,
            )["input_ids"]
            special_tokens = int(tokenizer.num_special_tokens_to_add(pair=False))
            counts[name] = max(0, len(token_ids) - special_tokens)
        return TokenCount(maximum=max(counts.values()), by_tokenizer=counts)


def import_visual_prompt_results(
    config: ProjectConfig,
    input_path: Path,
    jobs_path: Path,
    visuals_path: Path,
    *,
    output_path: Path | None = None,
    model_label: str = "codex-interactive",
    tokenizer_model: str | None = None,
    token_counter: Callable[[str], TokenCount] | None = None,
) -> dict[str, Any]:
    """Validate and apply locally authored visual prompts without a provider call."""

    prompt_path = config.project_root / "prompts" / "visual_prompt_writer.md"
    prompt_text = prompt_path.read_text(encoding="utf-8")
    prompt_hash = hashlib.sha256(prompt_text.encode("utf-8")).hexdigest()[:12]
    plan = _load_object(visuals_path)
    jobs = _read_jsonl(jobs_path)
    _validate_jobs(jobs, plan)
    job_by_scene = {str(job["scene_id"]): job for job in jobs}

    tokenizer_reference = (
        tokenizer_model
        or str(plan.get("prompt_policy", {}).get("model_id", "")).strip()
        or "stabilityai/sdxl-turbo"
    )
    if token_counter is None:
        counter_object = SdxlTokenCounter.load(tokenizer_reference)
        token_counter = counter_object.count
        tokenizer_source = str(counter_object.model_root)
    else:
        tokenizer_source = tokenizer_reference

    accepted: dict[str, dict[str, Any]] = {}
    for index, record in enumerate(_read_jsonl(input_path), start=1):
        candidate = record.get("result", record)
        if not isinstance(candidate, dict):
            raise ValueError(f"Visual result {index} must be an object")
        scene_id = str(candidate.get("scene_id", "")).strip()
        if scene_id not in job_by_scene:
            raise ValueError(
                f"Visual result {index} references unknown scene {scene_id!r}"
            )
        if scene_id in accepted:
            raise ValueError(f"Duplicate visual result for {scene_id}")
        accepted[scene_id] = _validate_result(
            candidate,
            job_by_scene[scene_id],
            token_counter,
        )
    if not accepted:
        raise ValueError("Visual result file is empty")

    destination = (output_path or visuals_path).resolve()
    updated_plan = _apply_results(
        plan,
        accepted,
        provider="codex_interactive",
        model=model_label,
        prompt_hash=prompt_hash,
        tokenizer_model=tokenizer_reference,
    )
    _write_json_atomic(destination, updated_plan)
    remaining = sum(
        scene.get("prompt", {}).get("status") == "pending_grounded_generation"
        for scene in updated_plan["scenes"]
    )
    return {
        "episode_id": str(plan["episode_id"]),
        "input_results": len(accepted),
        "applied": len(accepted),
        "remaining_pending": remaining,
        "completed": remaining == 0,
        "provider": "codex_interactive",
        "model_label": model_label,
        "prompt_hash": prompt_hash,
        "tokenizer_model": tokenizer_reference,
        "tokenizer_source": tokenizer_source,
        "output": str(destination),
        "network_calls": 0,
    }


def generate_visual_prompt_jobs(
    config: ProjectConfig,
    jobs_path: Path,
    visuals_path: Path,
    *,
    output_path: Path | None = None,
    execute: bool = False,
    max_calls: int | None = None,
    limit: int | None = None,
    retry_invalid: bool = False,
    model: str | None = None,
    tokenizer_model: str | None = None,
    token_counter: Callable[[str], TokenCount] | None = None,
    client: CaprioleChatClient | None = None,
) -> dict[str, Any]:
    """Generate, validate, cache, and import evidence-grounded visual prompts.

    The command is a dry run unless ``execute`` is true. Provider responses are
    saved before parsing so a network interruption or validation failure never
    causes a completed paid response to disappear.
    """

    provider = config.visual_provider or config.script_provider
    if not provider:
        raise ValueError("visual_provider is not configured")
    provider_config = dict(provider)
    if model:
        provider_config["model"] = model
    provider_client = client or CaprioleChatClient.from_config(provider_config)

    prompt_path = config.project_root / "prompts" / "visual_prompt_writer.md"
    prompt_text = prompt_path.read_text(encoding="utf-8")
    prompt_hash = hashlib.sha256(prompt_text.encode("utf-8")).hexdigest()[:12]
    plan = _load_object(visuals_path)
    jobs = _read_jsonl(jobs_path)
    if limit is not None:
        jobs = jobs[: max(0, limit)]
    _validate_jobs(jobs, plan)

    tokenizer_reference = (
        tokenizer_model
        or str(plan.get("prompt_policy", {}).get("model_id", "")).strip()
        or "stabilityai/sdxl-turbo"
    )
    if token_counter is None:
        counter_object = SdxlTokenCounter.load(tokenizer_reference)
        token_counter = counter_object.count
        tokenizer_source = str(counter_object.model_root)
    else:
        tokenizer_source = tokenizer_reference

    cache_dir = (
        config.work_dir
        / "visuals"
        / "cache"
        / _safe_component(provider_client.model)
        / prompt_hash
        / str(plan["episode_id"])
    )
    cache_dir.mkdir(parents=True, exist_ok=True)
    accepted: dict[str, dict[str, Any]] = {}
    pending: list[tuple[dict[str, Any], Path, Path]] = []
    failures: list[dict[str, str]] = []
    cached = recovered_raw = invalid_raw = 0

    for job in jobs:
        normalized_path, raw_path = _cache_paths(cache_dir, job)
        if normalized_path.is_file():
            try:
                record = _load_object(normalized_path)
                result = _validate_result(
                    record.get("result", record),
                    job,
                    token_counter,
                )
                accepted[str(job["scene_id"])] = result
                cached += 1
                continue
            except (ValueError, json.JSONDecodeError):
                pass
        if raw_path.is_file() and not retry_invalid:
            try:
                raw_record = _load_object(raw_path)
                result = _validate_result(
                    _parse_result(str(raw_record["text"]), job),
                    job,
                    token_counter,
                )
                _write_valid_cache(
                    normalized_path,
                    result,
                    raw_record.get("generation", {}),
                    prompt_hash,
                    _job_hash(job),
                )
                accepted[str(job["scene_id"])] = result
                recovered_raw += 1
                continue
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
                invalid_raw += 1
                failures.append(
                    {
                        "scene_id": str(job.get("scene_id", "")),
                        "error": f"InvalidRawCache: {error}",
                    }
                )
                continue
        pending.append((job, normalized_path, raw_path))

    report: dict[str, Any] = {
        "episode_id": str(plan["episode_id"]),
        "jobs": len(jobs),
        "model": provider_client.model,
        "prompt_hash": prompt_hash,
        "tokenizer_model": tokenizer_reference,
        "tokenizer_source": tokenizer_source,
        "cached": cached,
        "recovered_from_raw_cache": recovered_raw,
        "invalid_raw_cache": invalid_raw,
        "api_calls_pending": len(pending),
        "execution_requested": execute,
        "max_calls": max_calls,
        "generated": 0,
        "applied": 0,
        "failed": len(failures),
        "deferred": len(pending),
        "remaining": len(jobs) - len(accepted),
        "usage": {},
        "failures": failures,
        "cache_dir": str(cache_dir),
        "output": None,
        "completed": False,
    }
    if not execute:
        _write_failure_log(cache_dir, failures)
        return report

    if pending and (max_calls is None or max_calls < 1):
        raise ValueError("Paid visual generation requires --max-calls of at least 1")
    if pending and not os.environ.get(provider_client.api_key_env):
        raise RuntimeError(
            f"Missing {provider_client.api_key_env}; provide it as an environment "
            "variable"
        )

    generated_calls = 0
    traffic_blocked = False
    for job, normalized_path, raw_path in pending:
        if generated_calls >= int(max_calls or 0):
            break
        scene_id = str(job["scene_id"])
        generated_calls += 1
        try:
            response = provider_client.complete(_build_prompt(prompt_text, job))
            generation = {
                "provider": "capriole",
                "model": response.model,
                "request_id": response.request_id,
                "usage": response.usage,
                "prompt_hash": prompt_hash,
                "job_hash": _job_hash(job),
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }
            _write_json_atomic(
                raw_path,
                {
                    "contract_version": 1,
                    "episode_id": job["episode_id"],
                    "scene_id": scene_id,
                    "text": response.text,
                    "generation": generation,
                },
            )
            result = _validate_result(
                _parse_result(response.text, job),
                job,
                token_counter,
            )
            _write_valid_cache(
                normalized_path,
                result,
                generation,
                prompt_hash,
                _job_hash(job),
            )
            accepted[scene_id] = result
            report["generated"] += 1
            for key, value in response.usage.items():
                report["usage"][key] = (
                    int(report["usage"].get(key, 0)) + int(value)
                )
            print(
                f"[{generated_calls}/{min(len(pending), int(max_calls or 0))}] "
                f"generated visual prompt {scene_id}",
                flush=True,
            )
        except ProviderTrafficBlockedError as error:
            failures.append(
                {
                    "scene_id": scene_id,
                    "error": f"{type(error).__name__}: {error}",
                }
            )
            traffic_blocked = True
            break
        except Exception as error:
            failures.append(
                {
                    "scene_id": scene_id,
                    "error": f"{type(error).__name__}: {error}",
                }
            )
            print(
                f"[{generated_calls}/{min(len(pending), int(max_calls or 0))}] "
                f"FAILED visual prompt {scene_id}: {error}",
                flush=True,
            )

    destination = (output_path or visuals_path).resolve()
    if accepted:
        updated_plan = _apply_results(
            plan,
            accepted,
            provider="capriole",
            model=provider_client.model,
            prompt_hash=prompt_hash,
            tokenizer_model=tokenizer_reference,
        )
        _write_json_atomic(destination, updated_plan)
        report["applied"] = len(accepted)
        report["output"] = str(destination)

    report["failed"] = len(failures)
    report["failures"] = failures
    report["provider_traffic_blocked"] = traffic_blocked
    report["deferred"] = max(0, len(pending) - generated_calls)
    report["remaining"] = len(jobs) - len(accepted)
    report["completed"] = report["remaining"] == 0 and not failures
    _write_failure_log(cache_dir, failures)
    report["failure_log"] = str(cache_dir / "failures.jsonl")
    return report


def _validate_jobs(jobs: list[dict[str, Any]], plan: dict[str, Any]) -> None:
    if not jobs:
        raise ValueError("Visual prompt job file is empty")
    episode_id = str(plan.get("episode_id", ""))
    scenes = plan.get("scenes")
    if not isinstance(scenes, list):
        raise ValueError("Visual plan does not contain scenes")
    scene_by_id = {
        str(scene.get("scene_id")): scene
        for scene in scenes
        if isinstance(scene, dict)
    }
    seen: set[str] = set()
    for index, job in enumerate(jobs, start=1):
        label = f"Visual job {index}"
        for field in ("episode_id", "scene_id", "transcript"):
            if not isinstance(job.get(field), str) or not job[field].strip():
                raise ValueError(f"{label}.{field} must be a non-empty string")
        scene_id = str(job["scene_id"])
        if scene_id in seen:
            raise ValueError(f"Duplicate visual scene_id {scene_id!r}")
        seen.add(scene_id)
        if str(job["episode_id"]) != episode_id:
            raise ValueError(f"{label} episode does not match visual plan")
        scene = scene_by_id.get(scene_id)
        if scene is None:
            raise ValueError(f"{label} references unknown scene {scene_id}")
        for field in ("start_ms", "end_ms", "duration_ms"):
            if int(job.get(field, -1)) != int(scene.get(field, -2)):
                raise ValueError(f"{label}.{field} does not match visual plan")
        job_story_ids = _string_list(job.get("source_story_ids"))
        if job_story_ids != _string_list(scene.get("source_story_ids")):
            raise ValueError(f"{label}.source_story_ids does not match visual plan")
        evidence = job.get("source_evidence")
        if not isinstance(evidence, list):
            raise ValueError(f"{label}.source_evidence must be an array")
        evidence_ids = [
            str(item.get("story_id"))
            for item in evidence
            if isinstance(item, dict)
        ]
        if evidence_ids != job_story_ids:
            raise ValueError(f"{label}.source_evidence does not match story IDs")


def _validate_result(
    original: Any,
    job: dict[str, Any],
    token_counter: Callable[[str], TokenCount],
) -> dict[str, Any]:
    if not isinstance(original, dict):
        raise ValueError("Model result must be a JSON object")
    result = deepcopy(original)
    result["scene_id"] = str(job["scene_id"])
    for field in ("visual_intent", "camera_policy"):
        if not isinstance(result.get(field), str) or not result[field].strip():
            raise ValueError(f"{field} must be a non-empty string")

    evidence_by_id = {
        str(item["story_id"]): item
        for item in job["source_evidence"]
        if isinstance(item, dict) and item.get("story_id")
    }
    locations, discarded_location_notes = _filter_repository_artifact_locations(
        result.get("locations")
    )
    result["locations"] = _validate_evidence_claims(
        locations,
        evidence_by_id,
        claim_type="location",
    )
    result["identity_claims"] = _validate_evidence_claims(
        result.get("identity_claims"),
        evidence_by_id,
        claim_type="identity",
    )

    unknown = list(
        dict.fromkeys(
            _normalize_unknown_identity_attribute(value)
            for value in _string_list(
                result.get("unknown_identity_attributes")
            )
        )
    )
    invalid_unknown = sorted(set(unknown) - IDENTITY_ATTRIBUTES)
    if invalid_unknown:
        raise ValueError(
            "unknown_identity_attributes contains unsupported values: "
            + ", ".join(invalid_unknown)
        )
    result["unknown_identity_attributes"] = unknown

    chunks = result.get("prompt_chunks")
    if not isinstance(chunks, list) or not 1 <= len(chunks) <= 3:
        raise ValueError(
            "prompt_chunks must contain one to three narrative candidates"
        )
    candidates: list[tuple[str, TokenCount, dict[str, Any] | None]] = []
    overlong_candidates: list[tuple[str, TokenCount]] = []
    measured: list[int] = []
    for index, chunk in enumerate(chunks):
        if not isinstance(chunk, dict):
            raise ValueError(f"prompt_chunks[{index}] must be an object")
        if chunk.get("role") != "narrative":
            raise ValueError("prompt chunk role must be narrative")
        text = str(chunk.get("text", "")).strip()
        if not text:
            raise ValueError("prompt chunk text must not be empty")
        try:
            weight = float(chunk.get("weight", 1))
        except (TypeError, ValueError) as error:
            raise ValueError("prompt chunk weight must be numeric") from error
        if weight != 1.0:
            raise ValueError("every narrative prompt candidate must have weight 1.0")
        token_count = token_counter(text)
        measured.append(token_count.maximum)
        if TARGET_TOKEN_MINIMUM <= token_count.maximum <= CONTENT_TOKEN_LIMIT:
            existing_repair = chunk.get("local_repair")
            if not isinstance(existing_repair, dict):
                existing_repair = None
            candidates.append((text, token_count, existing_repair))
        elif (
            CONTENT_TOKEN_LIMIT
            < token_count.maximum
            <= CONTENT_TOKEN_LIMIT + MAXIMUM_LOCAL_TRIM_TOKENS
        ):
            overlong_candidates.append((text, token_count))
    if not candidates:
        for text, original_count in sorted(
            overlong_candidates,
            key=lambda candidate: candidate[1].maximum,
        ):
            repaired = _trim_prompt_to_token_limit(text, token_counter)
            if repaired is None:
                continue
            repaired_text, repaired_count = repaired
            candidates.append(
                (
                    repaired_text,
                    repaired_count,
                    {
                        "method": "trim_trailing_words",
                        "original_content_token_count": original_count.maximum,
                    },
                )
            )
            break
    if not candidates:
        raise ValueError(
            "no prompt candidate is within 68-75 SDXL content tokens; "
            f"measured {measured}"
        )
    text, token_count, repair = max(
        candidates,
        key=lambda candidate: candidate[1].maximum,
    )
    selected_chunk = {
        "role": "narrative",
        "text": text,
        "weight": 1.0,
        "content_token_count": token_count.maximum,
        "content_token_counts": token_count.by_tokenizer,
    }
    if repair is not None:
        selected_chunk["local_repair"] = repair
    result["prompt_chunks"] = [selected_chunk]

    seed = result.get("seed")
    if not isinstance(seed, int) or isinstance(seed, bool) or seed < 0:
        raise ValueError("seed must be a non-negative integer")
    result["sensitivity_notes"] = _string_list(result.get("sensitivity_notes"))
    result["sensitivity_notes"].extend(discarded_location_notes)
    result["editorial_review_required"] = True
    return result


def _validate_evidence_claims(
    value: Any,
    evidence_by_id: dict[str, dict[str, Any]],
    *,
    claim_type: str,
) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ValueError(f"{claim_type} claims must be an array")
    validated: list[dict[str, Any]] = []
    for index, original in enumerate(value, start=1):
        if not isinstance(original, dict):
            raise ValueError(f"{claim_type} claim {index} must be an object")
        claim = dict(original)
        story_id = str(claim.get("story_id", "")).strip()
        if story_id not in evidence_by_id:
            raise ValueError(
                f"{claim_type} claim {index} references unsupported story {story_id!r}"
            )
        excerpt = str(claim.get("evidence_excerpt", "")).strip()
        if not excerpt:
            raise ValueError(f"{claim_type} claim {index} has no evidence excerpt")
        story_text = str(evidence_by_id[story_id].get("story_text", ""))
        prior_match = str(claim.get("evidence_match", ""))
        prior_similarity = claim.get("evidence_similarity")
        resolved = _resolve_evidence_excerpt(excerpt, story_text)
        if resolved is None:
            raise ValueError(
                f"{claim_type} claim {index} excerpt is not verbatim source evidence"
            )
        excerpt, evidence_match, evidence_similarity = resolved
        if claim_type == "location":
            name = str(claim.get("name", "")).strip()
            role = str(claim.get("role", "")).strip()
            confidence = str(claim.get("confidence", "")).strip()
            if not name:
                raise ValueError(f"location claim {index} has no name")
            if role not in LOCATION_ROLES:
                raise ValueError(f"location claim {index} has invalid role {role!r}")
            if confidence not in {"explicit", "strong_context"}:
                raise ValueError(
                    f"location claim {index} has invalid confidence {confidence!r}"
                )
            claim["historical_period"] = (
                str(claim.get("historical_period", "unknown")).strip() or "unknown"
            )
        else:
            attribute = str(claim.get("attribute", "")).strip()
            claim_value = str(claim.get("value", "")).strip()
            if attribute not in IDENTITY_ATTRIBUTES:
                raise ValueError(
                    f"identity claim {index} has invalid attribute {attribute!r}"
                )
            if not claim_value:
                raise ValueError(f"identity claim {index} has no value")
            if claim.get("confidence") != "explicit":
                raise ValueError(
                    f"identity claim {index} must have explicit confidence"
                )
        claim["story_id"] = story_id
        claim["evidence_excerpt"] = excerpt
        if (
            evidence_match == "verbatim_normalized"
            and prior_match
            in {"source_snapped_punctuation", "high_confidence_source_snap"}
        ):
            claim["evidence_match"] = prior_match
            if isinstance(prior_similarity, (int, float)):
                claim["evidence_similarity"] = prior_similarity
        else:
            claim["evidence_match"] = evidence_match
            claim.pop("evidence_similarity", None)
            if evidence_similarity is not None:
                claim["evidence_similarity"] = evidence_similarity
        validated.append(claim)
    return validated


def _filter_repository_artifact_locations(
    value: Any,
) -> tuple[Any, list[str]]:
    if not isinstance(value, list):
        return value, []
    kept: list[Any] = []
    notes: list[str] = []
    for claim in value:
        if not isinstance(claim, dict):
            kept.append(claim)
            continue
        name = str(claim.get("name", "")).casefold()
        excerpt = str(claim.get("evidence_excerpt", ""))
        is_repository_name = any(
            marker in name
            for marker in (
                "archive.org",
                "digital context",
                "digital repository",
                "genealogy page",
                "internet archive",
                "rootsweb",
                "web page",
                "website",
            )
        )
        is_file_reference = bool(
            re.search(
                r"(?:[/\\]|^)[^/\\]+\.(?:txt|json|xml|html?|warc|wet|gz)$",
                excerpt.strip(),
                flags=re.IGNORECASE,
            )
        )
        is_repository_description = bool(
            re.search(
                r"\b(?:ocr|raw text|scanned|text file|url|website)\b",
                excerpt,
                flags=re.IGNORECASE,
            )
        )
        if is_repository_name and (
            is_file_reference or is_repository_description or "http" in excerpt
        ):
            notes.append(
                "Discarded a generated repository, URL, or file reference that "
                "was not a story-grounded physical location."
            )
            continue
        kept.append(claim)
    return kept, notes


def _trim_prompt_to_token_limit(
    text: str,
    token_counter: Callable[[str], TokenCount],
) -> tuple[str, TokenCount] | None:
    words = text.split()
    if len(words) < 2:
        return None
    single_word_repairs: list[tuple[str, TokenCount]] = []
    for remove_at in range(max(0, len(words) - 6), len(words) - 1):
        removable_word = re.sub(
            r"^\W+|\W+$",
            "",
            words[remove_at],
        ).casefold()
        if removable_word not in REMOVABLE_TRAILING_MODIFIERS:
            continue
        candidate = " ".join(words[:remove_at] + words[remove_at + 1 :])
        count = token_counter(candidate)
        if TARGET_TOKEN_MINIMUM <= count.maximum <= CONTENT_TOKEN_LIMIT:
            single_word_repairs.append((candidate, count))
    if single_word_repairs:
        return max(
            single_word_repairs,
            key=lambda candidate: candidate[1].maximum,
        )
    for removed in range(1, min(len(words), MAXIMUM_LOCAL_TRIM_TOKENS + 2)):
        candidate = " ".join(words[:-removed]).rstrip(" ,;:-")
        if not candidate:
            return None
        count = token_counter(candidate)
        if TARGET_TOKEN_MINIMUM <= count.maximum <= CONTENT_TOKEN_LIMIT:
            return candidate, count
        if count.maximum < TARGET_TOKEN_MINIMUM:
            return None
    return None


def _normalize_unknown_identity_attribute(value: str) -> str:
    normalized = value.strip().casefold()
    if normalized in UNKNOWN_IDENTITY_ALIASES:
        return UNKNOWN_IDENTITY_ALIASES[normalized]
    for attribute in IDENTITY_ATTRIBUTES:
        if normalized.startswith(attribute + " of "):
            return attribute
    return normalized


def _resolve_evidence_excerpt(
    excerpt: str,
    story_text: str,
) -> tuple[str, str, float | None] | None:
    normalized_excerpt = _normalize_evidence(excerpt)
    normalized_story = _normalize_evidence(story_text)
    if normalized_excerpt in normalized_story:
        return excerpt, "verbatim_normalized", None

    canonical_excerpt, _ = _canonicalize_with_positions(excerpt)
    canonical_story, story_positions = _canonicalize_with_positions(story_text)
    direct_start = canonical_story.find(canonical_excerpt)
    if direct_start >= 0 and canonical_excerpt:
        exact = _source_span(
            story_text,
            story_positions,
            direct_start,
            direct_start + len(canonical_excerpt),
        )
        return exact, "source_snapped_punctuation", 1.0

    query_words = _canonical_words(canonical_excerpt)
    source_word_matches = list(
        re.finditer(r"\w+(?:['-]\w+)*", canonical_story, flags=re.UNICODE)
    )
    source_words = [match.group(0) for match in source_word_matches]
    if len(query_words) < 5 or not source_words:
        return None

    best: tuple[float, int, int] | None = None
    minimum_window = max(1, len(query_words) - 3)
    maximum_window = min(len(source_words), len(query_words) + 3)
    for window_length in range(minimum_window, maximum_window + 1):
        for start in range(0, len(source_words) - window_length + 1):
            end = start + window_length
            similarity = SequenceMatcher(
                None,
                query_words,
                source_words[start:end],
                autojunk=False,
            ).ratio()
            if best is None or similarity > best[0]:
                best = (similarity, start, end)
    if best is None or best[0] < EVIDENCE_SNAP_MINIMUM_SIMILARITY:
        return None
    _, word_start, word_end = best
    character_start = source_word_matches[word_start].start()
    character_end = source_word_matches[word_end - 1].end()
    exact = _source_span(
        story_text,
        story_positions,
        character_start,
        character_end,
    )
    return exact, "high_confidence_source_snap", round(best[0], 6)


def _canonical_words(value: str) -> list[str]:
    return re.findall(r"\w+(?:['-]\w+)*", value, flags=re.UNICODE)


def _canonicalize_with_positions(value: str) -> tuple[str, list[int]]:
    translations = {
        "‘": "'",
        "’": "'",
        "‚": "'",
        "‛": "'",
        "“": '"',
        "”": '"',
        "„": '"',
        "‟": '"',
        "‐": "-",
        "‑": "-",
        "‒": "-",
        "–": "-",
        "—": "-",
        "―": "-",
        "…": "...",
    }
    characters: list[str] = []
    positions: list[int] = []
    previous_was_space = False
    for original_index, original_character in enumerate(value):
        translated = translations.get(original_character, original_character)
        expanded = unicodedata.normalize("NFKC", translated).casefold()
        for character in expanded:
            if character.isspace():
                if previous_was_space:
                    continue
                character = " "
                previous_was_space = True
            else:
                previous_was_space = False
            characters.append(character)
            positions.append(original_index)
    while characters and characters[0] == " ":
        characters.pop(0)
        positions.pop(0)
    while characters and characters[-1] == " ":
        characters.pop()
        positions.pop()
    return "".join(characters), positions


def _source_span(
    source: str,
    positions: list[int],
    canonical_start: int,
    canonical_end: int,
) -> str:
    original_start = positions[canonical_start]
    original_end = positions[canonical_end - 1] + 1
    return source[original_start:original_end].strip()


def _apply_results(
    plan: dict[str, Any],
    results: dict[str, dict[str, Any]],
    *,
    provider: str,
    model: str,
    prompt_hash: str,
    tokenizer_model: str,
) -> dict[str, Any]:
    updated = deepcopy(plan)
    for scene in updated["scenes"]:
        scene_id = str(scene["scene_id"])
        result = results.get(scene_id)
        if result is None:
            continue
        locations = result["locations"]
        identity_claims = result["identity_claims"]
        scene["grounding"] = {
            "location_status": (
                "machine_verified_evidence" if locations else "no_explicit_location"
            ),
            "locations": locations,
            "identity_status": (
                "machine_verified_evidence"
                if identity_claims
                else "identity_not_explicit"
            ),
            "identity_claims": identity_claims,
            "unknown_identity_attributes": result[
                "unknown_identity_attributes"
            ],
            "supporting_story_ids": scene["source_story_ids"],
            "editorial_review_required": True,
        }
        scene["prompt"] = {
            "status": "generated_pending_editorial_review",
            "visual_intent": result["visual_intent"],
            "camera_policy": result["camera_policy"],
            "chunks": result["prompt_chunks"],
            "seed": result["seed"],
            "sensitivity_notes": result["sensitivity_notes"],
            "editorial_notes": [
                "Location and identity excerpts passed deterministic source checks.",
                "Human editorial approval is still required before publication.",
            ],
        }
    updated["visual_prompt_generation"] = {
        "provider": provider,
        "model": model,
        "prompt_hash": prompt_hash,
        "tokenizer_model": tokenizer_model,
        "generated_scene_count": sum(
            scene["prompt"].get("status")
            == "generated_pending_editorial_review"
            for scene in updated["scenes"]
        ),
        "editorial_review_required": True,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    return updated


def _build_prompt(template: str, job: dict[str, Any]) -> str:
    return (
        f"{template.rstrip()}\n\n"
        "Return one raw JSON object only, with no Markdown fences or commentary. "
        "Use only this scene job's supplied evidence. Return three differently "
        "sized prompt candidates. The runner will reject non-verbatim location "
        "or identity excerpts and will retain only the longest candidate within "
        "68-75 exact SDXL content tokens.\n\n"
        "SOURCE SCENE JOB:\n"
        f"{json.dumps(job, ensure_ascii=False, separators=(',', ':'))}"
    )


def _parse_result(text: str, job: dict[str, Any]) -> dict[str, Any]:
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
        try:
            value = json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError as error:
            raise ValueError(f"Model output contained invalid JSON: {error}") from error
    if not isinstance(value, dict):
        raise ValueError("Model output must be a JSON object")
    value["scene_id"] = str(job["scene_id"])
    return value


def _write_valid_cache(
    path: Path,
    result: dict[str, Any],
    generation: Any,
    prompt_hash: str,
    job_hash: str,
) -> None:
    _write_json_atomic(
        path,
        {
            "contract_version": 1,
            "result": result,
            "generation": generation if isinstance(generation, dict) else {},
            "prompt_hash": prompt_hash,
            "job_hash": job_hash,
        },
    )


def _cache_paths(
    cache_dir: Path,
    job: dict[str, Any],
) -> tuple[Path, Path]:
    stem = f"{_safe_component(str(job['scene_id']))}-{_job_hash(job)}"
    return cache_dir / f"{stem}.json", cache_dir / f"{stem}.response.json"


def _job_hash(job: dict[str, Any]) -> str:
    canonical = json.dumps(
        job,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def _resolve_sdxl_model_root(model_reference: str) -> Path:
    candidate = Path(model_reference).expanduser()
    if candidate.is_dir():
        return candidate.resolve()

    hub_root = Path(
        os.environ.get(
            "HF_HUB_CACHE",
            Path(
                os.environ.get(
                    "HF_HOME",
                    Path.home() / ".cache" / "huggingface",
                )
            )
            / "hub",
        )
    ).expanduser()
    model_cache = hub_root / ("models--" + model_reference.replace("/", "--"))
    refs_main = model_cache / "refs" / "main"
    if refs_main.is_file():
        revision = refs_main.read_text(encoding="utf-8").strip()
        snapshot = model_cache / "snapshots" / revision
        if snapshot.is_dir():
            return snapshot.resolve()
    snapshots = model_cache / "snapshots"
    if snapshots.is_dir():
        candidates = sorted(
            (
                path
                for path in snapshots.iterdir()
                if path.is_dir() and (path / "tokenizer").is_dir()
            ),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        if candidates:
            return candidates[0].resolve()
    raise RuntimeError(
        f"SDXL tokenizer files are not cached for {model_reference!r}. "
        "Pass --tokenizer-model with a local SDXL model or Hugging Face snapshot."
    )


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    with path.open(encoding="utf-8-sig") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"Line {line_number}: expected a JSON object")
            values.append(value)
    return values


def _load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return value


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [
        str(item).strip()
        for item in value
        if isinstance(item, str) and item.strip()
    ]


def _normalize_evidence(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def _safe_component(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value)


def _write_failure_log(cache_dir: Path, failures: list[dict[str, str]]) -> None:
    path = cache_dir / "failures.jsonl"
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for failure in failures:
            handle.write(json.dumps(failure, ensure_ascii=False) + "\n")


def _write_json_atomic(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
