from __future__ import annotations

from .storytelling_quality import (
    content_digest, require_personal_story, spoken_content_findings,
    validate_personal_visual_plan,
)

import hashlib
import json
import os
import random
import re
import secrets
import sys
import time
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .config import ProjectConfig
from .storytelling_duration import (
    require_story_audio_duration, require_story_text_budget,
)
from .providers.ollama import OllamaLocalClient
from .providers.qwen_tts import Qwen3TTSLocalRenderer
from .storytelling import validate_storytelling_adaptation_data
from .visual_prompt_runner import (
    CONTENT_TOKEN_LIMIT,
    TARGET_TOKEN_MINIMUM,
    SdxlTokenCounter,
)


LIVE_CONTRACT_VERSION = 1
FIRST_PERSON_MODES = {"first_person_preserved", "attributed_first_person"}
_CONTENT_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "been", "but", "by",
    "for", "from", "had", "has", "have", "he", "her", "hers", "him",
    "his", "i", "in", "is", "it", "its", "me", "my", "of", "on", "or",
    "our", "she", "that", "the", "their", "them", "they", "this", "to",
    "was", "we", "were", "with", "you",
}
CONTROL_DEFAULTS = {
    "enabled": False,
    "profile": "3080_safe",
    "narration_variation": True,
    "speech_variation": True,
    "visual_variation": True,
    "casting_mode": "interpretive",
    "seed_mode": "random",
    "fixed_seed": 201312,
    "current_narration_id": "",
    "canonical_visuals": "",
    "canonical_human_visuals": "",
    "regeneration_nonce": 0,
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return value


def _write_json_atomic(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def load_live_config(config: ProjectConfig) -> dict[str, Any]:
    path = config.project_root / "config" / "live_storytelling.json"
    value = _read_object(path)
    if value.get("contract_version") != LIVE_CONTRACT_VERSION:
        raise ValueError("Unsupported live storytelling config version")
    profiles = value.get("profiles")
    if not isinstance(profiles, dict) or not profiles:
        raise ValueError("Live storytelling config requires runtime profiles")
    return value


def runtime_paths(config: ProjectConfig) -> dict[str, Path]:
    root = config.work_dir / "runtime"
    return {
        "root": root,
        "control": root / "control.json",
        "status": root / "status.json",
        "current": root / "current.json",
        "requests": root / "requests",
        "variants": root / "variants",
    }


def read_live_control(config: ProjectConfig) -> dict[str, Any]:
    path = runtime_paths(config)["control"]
    stored = _read_object(path) if path.is_file() else {}
    return _normalize_control({**CONTROL_DEFAULTS, **stored})


def update_live_control(
    config: ProjectConfig,
    changes: dict[str, Any],
) -> dict[str, Any]:
    unknown = sorted(set(changes) - set(CONTROL_DEFAULTS))
    if unknown:
        raise ValueError(f"Unknown live control fields: {', '.join(unknown)}")
    control = _normalize_control({**read_live_control(config), **changes})
    control["updated_at"] = _utc_now()
    _write_json_atomic(runtime_paths(config)["control"], control)
    return control


def _normalize_control(value: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(value)
    normalized["enabled"] = bool(value.get("enabled", False))
    for field in ("narration_variation", "speech_variation", "visual_variation"):
        normalized[field] = bool(value.get(field, True))
    profile = str(value.get("profile") or "3080_safe")
    if profile not in {"3080_safe", "5090_live"}:
        raise ValueError("profile must be 3080_safe or 5090_live")
    normalized["profile"] = profile
    if profile == "3080_safe":
        normalized["enabled"] = False
    casting_mode = str(value.get("casting_mode") or "interpretive")
    if casting_mode not in {"evidence_conservative", "interpretive"}:
        raise ValueError("casting_mode is invalid")
    normalized["casting_mode"] = casting_mode
    seed_mode = str(value.get("seed_mode") or "random")
    if seed_mode not in {"fixed", "random"}:
        raise ValueError("seed_mode must be fixed or random")
    normalized["seed_mode"] = seed_mode
    normalized["fixed_seed"] = max(0, int(value.get("fixed_seed") or 0))
    normalized["regeneration_nonce"] = max(
        0, int(value.get("regeneration_nonce") or 0)
    )
    for field in (
        "current_narration_id",
        "canonical_visuals",
        "canonical_human_visuals",
    ):
        normalized[field] = str(value.get(field) or "")
    return normalized


def live_storytelling_doctor(
    config: ProjectConfig,
    *,
    profile_name: str,
    check_ollama: bool = True,
) -> dict[str, Any]:
    live_config = load_live_config(config)
    profile = _profile(live_config, profile_name)
    checks: dict[str, Any] = {
        "profile_exists": True,
        "profile_enabled": bool(profile.get("local_generation_enabled")),
        "canonical_fallback_required": True,
    }
    if not profile.get("local_generation_enabled"):
        checks["qwen_tts"] = {
            "required": False,
            "available": None,
            "reason": "3080-safe profile does not import local TTS dependencies",
        }
        checks["ollama"] = {
            "required": False,
            "available": None,
            "reason": "3080-safe profile does not load local generation models",
        }
        ready = True
    else:
        checks["qwen_tts"] = {
            "required": True,
            **Qwen3TTSLocalRenderer.dependency_status(),
        }
        model = str(profile.get("ollama", {}).get("model") or "gemma4:12b")
        if check_ollama:
            try:
                client = _ollama_client(profile)
                models = client.list_models()
                checks["ollama"] = {
                    "required": True,
                    "available": model in models,
                    "model": model,
                    "installed_models": models,
                }
            except RuntimeError as error:
                checks["ollama"] = {
                    "required": True,
                    "available": False,
                    "model": model,
                    "error": str(error),
                }
        else:
            checks["ollama"] = {
                "required": True,
                "available": None,
                "model": model,
                "reason": "local endpoint check skipped",
            }
        ready = bool(checks["ollama"].get("available")) and bool(
            checks["qwen_tts"].get("available")
        )
    return {
        "contract_version": LIVE_CONTRACT_VERSION,
        "profile": profile_name,
        "ready": ready,
        "checks": checks,
        "network_calls": 0,
        "local_loopback_calls": 1 if check_ollama and profile_name == "5090_live" else 0,
        "paid_calls": 0,
    }


def prepare_live_variation(
    config: ProjectConfig,
    narration_id: str,
    *,
    profile_name: str,
    loop_index: int,
    casting_mode: str = "interpretive",
    seed: int | None = None,
    canonical_visuals_path: Path | None = None,
    canonical_human_visuals_path: Path | None = None,
) -> dict[str, Any]:
    live_config = load_live_config(config)
    profile = _profile(live_config, profile_name)
    narration_dir = config.episodes_dir / narration_id
    adaptation_path = narration_dir / "adaptation.json"
    source_job_path = narration_dir / "source-job.json"
    if not adaptation_path.is_file() or not source_job_path.is_file():
        raise ValueError(f"Narration is missing canonical artifacts: {narration_id}")
    adaptation = _read_object(adaptation_path)
    source_job = _read_object(source_job_path)
    if adaptation.get("perspective_mode") not in FIRST_PERSON_MODES:
        raise ValueError("Live storytelling accepts first-person adaptations only")
    review = require_personal_story(narration_dir)
    require_story_text_budget(config, adaptation)
    source_job = deepcopy(source_job)
    source_job.setdefault("story_card", {})["locations"] = review["reviewed_analysis"].get("locations", [])
    validation = validate_storytelling_adaptation_data(adaptation, source_job)
    if not validation["valid"]:
        raise ValueError(
            "Canonical adaptation failed validation: " + "; ".join(validation["errors"])
        )
    resolved_seed = int(seed) if seed is not None else secrets.randbits(31)
    casting_card = create_interpretive_casting_card(
        adaptation,
        source_job,
        live_config,
        seed=resolved_seed,
        loop_index=loop_index,
        casting_mode=casting_mode,
    )
    visual_sources: dict[str, tuple[Path, dict[str, Any]]] = {}
    for default_id, path in (
        ("original", canonical_visuals_path),
        ("human_figures", canonical_human_visuals_path),
    ):
        if path is None:
            continue
        value = _read_object(path)
        validate_personal_visual_plan(value, adaptation)
        declared = value.get("visual_path", {}).get("id")
        visual_id = str(declared or default_id)
        if visual_id in visual_sources:
            raise ValueError(f"Duplicate canonical visual path ID: {visual_id}")
        visual_sources[visual_id] = (path, value)
    variant_id = _variant_id(narration_id, loop_index, resolved_seed, casting_card["cast_id"])
    paths = runtime_paths(config)
    request_path = paths["requests"] / f"{variant_id}.json"
    visual_scene_count = sum(
        len(value.get("scenes", [])) for _, value in visual_sources.values()
    )
    local_enabled = bool(profile.get("local_generation_enabled"))
    request = {
        "contract_version": LIVE_CONTRACT_VERSION,
        "kind": "live_storytelling_variation_request",
        "created_at": _utc_now(),
        "variant_id": variant_id,
        "narration_id": narration_id,
        "loop_index": int(loop_index),
        "profile": profile_name,
        "local_generation_enabled": local_enabled,
        "casting_mode": casting_mode,
        "seeds": {
            "casting": resolved_seed,
            "narration": _derived_seed(resolved_seed, "narration"),
            "speech": _derived_seed(resolved_seed, "speech"),
            "visual_prompt": _derived_seed(resolved_seed, "visual-prompt"),
            "image": _derived_seed(resolved_seed, "image"),
        },
        "canonical": {
            "adaptation": str(adaptation_path.resolve()),
            "source_job": str(source_job_path.resolve()),
            "adaptation_sha256": content_digest(adaptation),
            "visuals": {
                visual_id: str(path.resolve())
                for visual_id, (path, _value) in visual_sources.items()
            },
            "audio": _canonical_audio_path(narration_dir, narration_id),
        },
        "casting_card": casting_card,
        "pending_local_work": {
            "ollama_narration_calls": 1 if local_enabled else 0,
            "ollama_visual_calls": len(visual_sources) if local_enabled else 0,
            "qwen_tts_sections": len(adaptation["sections"]) if local_enabled else 0,
        },
        "visual_scene_count": visual_scene_count,
        "status": "prepared",
        "network_policy": "loopback_only",
        "paid_calls": 0,
    }
    _write_json_atomic(request_path, request)
    return {**request, "request": str(request_path)}


def create_interpretive_casting_card(
    adaptation: dict[str, Any],
    source_job: dict[str, Any],
    live_config: dict[str, Any],
    *,
    seed: int,
    loop_index: int,
    casting_mode: str,
) -> dict[str, Any]:
    if casting_mode not in {"evidence_conservative", "interpretive"}:
        raise ValueError("casting_mode is invalid")
    if adaptation.get("perspective_mode") not in FIRST_PERSON_MODES:
        raise ValueError("Interpretive casting requires a first-person adaptation")
    casting = live_config.get("interpretive_casting", {})
    rng = random.Random(int(seed))
    constraints = {
        str(item.get("trait")): item
        for item in adaptation.get("identity_constraints", [])
        if isinstance(item, dict)
    }

    def choose(trait: str, pool_name: str, conservative_default: str) -> dict[str, str]:
        constraint = constraints.get(trait)
        if constraint:
            return {
                "value": str(constraint["value"]),
                "evidence_status": "source_locked",
                "evidence_excerpt": str(constraint["evidence_excerpt"]),
            }
        values = casting.get(pool_name, [])
        if casting_mode == "evidence_conservative":
            selected = conservative_default
        elif isinstance(values, list) and values:
            selected = str(rng.choice(values))
        else:
            selected = conservative_default
        return {
            "value": selected,
            "evidence_status": "artistic_casting",
            "evidence_excerpt": "",
        }

    gender = choose(
        "narrator_gender_presentation", "gender_presentations", "androgynous"
    )
    age = choose("narrator_age_presentation", "age_presentations", "adult")
    accent = choose(
        "narrator_accent", "accent_profiles", "clear international English"
    )
    explicit_visual_identity = [
        constraints[trait]
        for trait in (
            "narrator_race",
            "narrator_ethnicity",
            "narrator_nationality",
            "narrator_disability",
        )
        if trait in constraints
    ]
    appearance_values = casting.get("appearance_profiles", [])
    if explicit_visual_identity:
        explicit_values = ", ".join(
            str(item["value"]) for item in explicit_visual_identity
        )
        appearance = (
            f"a respectfully cast person consistent with the source-explicit "
            f"identity details {explicit_values}, with individual features and no "
            "stereotyped cultural shorthand"
        )
        appearance_provenance = {
            "value": appearance,
            "evidence_status": "source_locked_requires_editorial_visual_cast",
            "evidence_excerpt": " | ".join(
                str(item["evidence_excerpt"]) for item in explicit_visual_identity
            ),
        }
    elif casting_mode == "interpretive" and appearance_values:
        appearance = str(rng.choice(appearance_values))
        appearance_provenance = {
            "value": appearance,
            "evidence_status": "artistic_casting",
            "evidence_excerpt": "",
        }
    else:
        appearance = "identity-neutral adult presence with softly readable features"
        appearance_provenance = {
            "value": appearance,
            "evidence_status": "artistic_casting",
            "evidence_excerpt": "",
        }
    source_personality = [
        str(value)
        for value in adaptation.get("narrator_profile", {}).get("personality_tags", [])
        if str(value).strip()
    ]
    allowed_personality = [
        str(value) for value in casting.get("personality_variations", [])
    ]
    personality = list(dict.fromkeys(source_personality))
    if casting_mode == "interpretive":
        rng.shuffle(personality)
        personality = personality[:2]
    if casting_mode == "interpretive" and allowed_personality:
        rng.shuffle(allowed_personality)
        for value in allowed_personality:
            if value not in personality:
                personality.append(value)
            if len(personality) >= 3:
                break
    personality = personality[:3] or ["reflective"]
    voice_description = (
        f"A {age['value']} {gender['value']} voice using a natural, subtle "
        f"{accent['value']} accent; {', '.join(personality)}, intimate first-person "
        "spoken-word delivery, emotionally responsive without caricature."
    )
    locations = _source_locations(source_job)
    cast_payload = (
        f"{adaptation['narration_id']}:{loop_index}:{seed}:"
        f"{gender['value']}:{age['value']}:{accent['value']}:{appearance}"
    )
    cast_id = "cast-" + hashlib.sha256(cast_payload.encode("utf-8")).hexdigest()[:20]
    return {
        "contract_version": LIVE_CONTRACT_VERSION,
        "kind": "interpretive_casting_card",
        "cast_id": cast_id,
        "narration_id": adaptation["narration_id"],
        "loop_index": int(loop_index),
        "casting_seed": int(seed),
        "mode": casting_mode,
        "identity_claim": False,
        "source_identity_constraints": list(constraints.values()),
        "language": adaptation.get("adaptation_language", "en"),
        "voice": {
            "gender_presentation": gender["value"],
            "age_presentation": age["value"],
            "accent_profile": accent["value"],
            "tts_instruction": voice_description,
        },
        "visual": {
            "appearance": appearance,
            "gender_presentation": gender["value"],
            "age_presentation": age["value"],
            "continuity_instruction": (
                "Keep this same person visually consistent for every scene in this "
                "rendition; prefer front-facing environmental portraits when a person "
                "is present."
            ),
        },
        "personality": personality,
        "trait_provenance": {
            "gender_presentation": gender,
            "age_presentation": age,
            "accent_profile": accent,
            "appearance": appearance_provenance,
        },
        "source_locations_not_used_to_infer_identity": locations,
        "policy": [
            "Explicit source traits are locked; unspecified traits are artistic casting.",
            "Location, language, name, and accent do not imply race or ethnicity.",
            "The same cast remains stable for this complete rendition.",
        ],
    }


def execute_live_variation(
    config: ProjectConfig,
    request_path: Path,
    *,
    narration_variation: bool = True,
    speech_variation: bool = True,
    visual_variation: bool = True,
    ollama_client: OllamaLocalClient | None = None,
    speech_renderer: Qwen3TTSLocalRenderer | None = None,
    token_counter: Callable[[str], Any] | None = None,
) -> dict[str, Any]:
    request = _read_object(request_path)
    if request.get("kind") != "live_storytelling_variation_request":
        raise ValueError("Not a live storytelling request")
    live_config = load_live_config(config)
    profile = _profile(live_config, str(request["profile"]))
    canonical = request["canonical"]
    canonical_path = Path(canonical["adaptation"])
    if Path(canonical["source_job"]).resolve() != (canonical_path.parent / "source-job.json").resolve():
        raise ValueError("Live request source job is not the reviewed canonical source")
    review = require_personal_story(canonical_path.parent)
    adaptation = _read_object(canonical_path)
    if canonical.get("adaptation_sha256") != content_digest(adaptation):
        raise ValueError("Live request is stale; prepare it from the reviewed personal story")
    require_story_text_budget(config, adaptation)
    variant_dir = runtime_paths(config)["variants"] / str(request["variant_id"])
    variant_dir.mkdir(parents=True, exist_ok=True)
    _write_json_atomic(variant_dir / "casting-card.json", request["casting_card"])
    source_job = _read_object(Path(canonical["source_job"]))
    source_job.setdefault("story_card", {})["locations"] = review["reviewed_analysis"].get("locations", [])
    calls = {"ollama": 0, "qwen_tts_sections": 0, "paid": 0}
    generation_records = []

    if not profile.get("local_generation_enabled"):
        narration_variation = speech_variation = visual_variation = False

    if narration_variation:
        client = ollama_client or _ollama_client(profile)
        narration_instructions = (
            config.project_root / "prompts" / "live_narration_variation.md"
        ).read_text(encoding="utf-8")
        narration_prompt = _narration_prompt(
            adaptation,
            source_job,
            request["casting_card"],
            instructions=narration_instructions,
        )
        response = client.generate_json(
            narration_prompt,
            _narration_schema(adaptation),
            seed=int(request["seeds"]["narration"]),
            **_ollama_sampling(profile),
        )
        adaptation = _accept_narration_variant(
            response.value,
            adaptation,
            source_job,
            request,
        )
        calls["ollama"] += 1
        generation_records.append(
            _ollama_record("narration", response, narration_prompt)
        )
    else:
        adaptation = deepcopy(adaptation)
        adaptation["variant_id"] = request["variant_id"]
        adaptation["live_variation"] = {
            "mode": "canonical",
            "casting_card": request["casting_card"]["cast_id"],
        }
    require_story_text_budget(config, adaptation)
    adaptation_path = variant_dir / "adaptation.json"
    _write_json_atomic(adaptation_path, adaptation)

    visual_paths: dict[str, Path] = {}
    canonical_visual_sources = canonical.get("visuals") or {}
    if isinstance(canonical_visual_sources, str):
        canonical_visual_sources = {"original": canonical_visual_sources}
    for visual_id, canonical_visual_source in canonical_visual_sources.items():
        canonical_visuals = _read_object(Path(canonical_visual_source))
        validate_personal_visual_plan(canonical_visuals, _read_object(canonical_path))
        if visual_variation:
            client = ollama_client or _ollama_client(profile)
            if token_counter is None:
                tokenizer_model = str(
                    canonical_visuals.get("prompt_policy", {}).get("model_id")
                    or "stabilityai/sdxl-turbo"
                )
                token_counter = SdxlTokenCounter.load(tokenizer_model).count
            visual_instructions = (
                config.project_root / "prompts" / "live_visual_variation.md"
            ).read_text(encoding="utf-8")
            visual_prompt = _visual_prompt(
                canonical_visuals,
                request["casting_card"],
                instructions=visual_instructions,
            )
            response = client.generate_json(
                visual_prompt,
                _visual_schema(canonical_visuals),
                seed=_derived_seed(
                    int(request["seeds"]["visual_prompt"]), str(visual_id)
                ),
                **_ollama_sampling(profile),
            )
            canonical_visuals = _accept_visual_variant(
                response.value,
                canonical_visuals,
                request,
                token_counter,
            )
            calls["ollama"] += 1
            generation_records.append(
                _ollama_record("visual_prompts", response, visual_prompt)
            )
        visual_path = variant_dir / f"visual-scenes-{visual_id}.json"
        _write_json_atomic(visual_path, canonical_visuals)
        visual_paths[str(visual_id)] = visual_path

    audio_path = canonical.get("audio")
    timeline_path = None
    if speech_variation:
        renderer = speech_renderer or _speech_renderer(profile)
        render = renderer.render(
            adaptation,
            request["casting_card"],
            variant_dir / "audio",
            speech_seed=int(request["seeds"]["speech"]),
        )
        audio_path = str(render.audio_path.resolve())
        timeline_path = str(render.timeline_path.resolve())
        calls["qwen_tts_sections"] = render.sections
        for visual_path in visual_paths.values():
            retimed_visuals = _retime_visual_plan(
                _read_object(visual_path), _read_object(render.timeline_path)
            )
            _write_json_atomic(visual_path, retimed_visuals)

    ready = bool(audio_path and Path(str(audio_path)).is_file())
    if speech_variation and not ready:
        raise RuntimeError("Local speech render did not produce a playable WAV")
    if ready:
        require_story_audio_duration(config, Path(str(audio_path)))
    bundle = {
        "contract_version": LIVE_CONTRACT_VERSION,
        "kind": "live_storytelling_ready_bundle",
        "status": "ready" if ready else "prepared_without_audio",
        "created_at": _utc_now(),
        "variant_id": request["variant_id"],
        "narration_id": request["narration_id"],
        "loop_index": request["loop_index"],
        "profile": request["profile"],
        "cast_id": request["casting_card"]["cast_id"],
        "assets": {
            "adaptation": str(adaptation_path.resolve()),
            "audio": audio_path,
            "timeline": timeline_path,
            "captions_vtt": (
                str((variant_dir / "audio" / "captions.vtt").resolve())
                if timeline_path
                else None
            ),
            "captions_srt": (
                str((variant_dir / "audio" / "captions.srt").resolve())
                if timeline_path
                else None
            ),
            "visuals": {
                visual_id: str(path.resolve())
                for visual_id, path in visual_paths.items()
            },
            "casting_card": str((variant_dir / "casting-card.json").resolve()),
        },
        "seeds": request["seeds"],
        "generation": generation_records,
        "calls": calls,
        "fallback": {
            "adaptation": canonical["adaptation"],
            "audio": canonical.get("audio"),
            "visuals": canonical.get("visuals"),
        },
    }
    bundle_path = variant_dir / "bundle.json"
    _write_json_atomic(bundle_path, bundle)
    if ready:
        _write_json_atomic(
            runtime_paths(config)["current"],
            {
                "contract_version": LIVE_CONTRACT_VERSION,
                "status": "ready",
                "variant_id": request["variant_id"],
                "narration_id": request["narration_id"],
                "bundle": str(bundle_path.resolve()),
                "promoted_at": _utc_now(),
            },
        )
    return {**bundle, "bundle": str(bundle_path), "paid_calls": 0}


def run_live_worker(
    config: ProjectConfig,
    *,
    once: bool = False,
    poll_seconds: float = 0.5,
    max_iterations: int | None = None,
) -> dict[str, Any]:
    paths = runtime_paths(config)
    processed_nonce = None
    iterations = 0
    last_result: dict[str, Any] | None = None
    cached_client: OllamaLocalClient | None = None
    cached_renderer: Qwen3TTSLocalRenderer | None = None
    cached_profile = ""
    while True:
        iterations += 1
        control = read_live_control(config)
        nonce = int(control["regeneration_nonce"])
        if control["enabled"] and control["profile"] == "5090_live":
            if not control["speech_variation"] and cached_renderer is not None:
                _release_local_models(None, cached_renderer)
                cached_renderer = None
            if (
                not control["narration_variation"]
                and not control["visual_variation"]
                and cached_client is not None
            ):
                _release_local_models(cached_client, None)
                cached_client = None
        if not control["enabled"] or control["profile"] == "3080_safe":
            if cached_client is not None or cached_renderer is not None:
                _release_local_models(cached_client, cached_renderer)
                cached_client = None
                cached_renderer = None
                cached_profile = ""
            processed_nonce = None
            _write_worker_status(config, "disabled", control=control)
        elif not control["current_narration_id"]:
            _write_worker_status(config, "waiting_for_narration", control=control)
        elif nonce != processed_nonce:
            processed_nonce = nonce
            try:
                needs_ollama = bool(
                    control["narration_variation"] or control["visual_variation"]
                )
                if cached_profile != control["profile"]:
                    _release_local_models(cached_client, cached_renderer)
                    profile = _profile(load_live_config(config), control["profile"])
                    cached_client = _ollama_client(profile) if needs_ollama else None
                    cached_renderer = (
                        _speech_renderer(profile)
                        if control["speech_variation"]
                        else None
                    )
                    cached_profile = control["profile"]
                elif needs_ollama and cached_client is None:
                    profile = _profile(load_live_config(config), control["profile"])
                    cached_client = _ollama_client(profile)
                if control["speech_variation"] and cached_renderer is None:
                    profile = _profile(load_live_config(config), control["profile"])
                    cached_renderer = _speech_renderer(profile)
                elif not control["speech_variation"] and cached_renderer is not None:
                    _release_local_models(None, cached_renderer)
                    cached_renderer = None
                if not needs_ollama and cached_client is not None:
                    _release_local_models(cached_client, None)
                    cached_client = None
                visuals = (
                    Path(control["canonical_visuals"])
                    if control["canonical_visuals"]
                    else None
                )
                human_visuals = (
                    Path(control["canonical_human_visuals"])
                    if control["canonical_human_visuals"]
                    else None
                )
                prepared = prepare_live_variation(
                    config,
                    control["current_narration_id"],
                    profile_name=control["profile"],
                    loop_index=nonce,
                    casting_mode=control["casting_mode"],
                    seed=(control["fixed_seed"] if control["seed_mode"] == "fixed" else None),
                    canonical_visuals_path=visuals,
                    canonical_human_visuals_path=human_visuals,
                )
                _write_worker_status(
                    config,
                    "generating",
                    control=control,
                    variant_id=prepared["variant_id"],
                )
                last_result = execute_live_variation(
                    config,
                    Path(prepared["request"]),
                    narration_variation=control["narration_variation"],
                    speech_variation=control["speech_variation"],
                    visual_variation=control["visual_variation"],
                    ollama_client=cached_client,
                    speech_renderer=cached_renderer,
                )
                _write_worker_status(
                    config,
                    str(last_result["status"]),
                    control=control,
                    variant_id=last_result["variant_id"],
                    bundle=last_result["bundle"],
                )
            except Exception as error:
                _write_worker_status(
                    config,
                    "fallback",
                    control=control,
                    error=f"{type(error).__name__}: {error}",
                )
        if once or (max_iterations is not None and iterations >= max_iterations):
            break
        time.sleep(max(0.1, float(poll_seconds)))
    _release_local_models(cached_client, cached_renderer)
    return {
        "iterations": iterations,
        "last_result": last_result,
        "status": str(paths["status"]),
        "paid_calls": 0,
    }


def _release_local_models(
    client: OllamaLocalClient | None,
    renderer: Qwen3TTSLocalRenderer | None,
) -> None:
    if client is not None:
        try:
            client.unload()
        except RuntimeError:
            pass
    if renderer is not None:
        renderer._model = None
    torch = sys.modules.get("torch")
    if torch is not None:
        try:
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass


def _write_worker_status(
    config: ProjectConfig,
    state: str,
    *,
    control: dict[str, Any],
    **extra: Any,
) -> None:
    _write_json_atomic(
        runtime_paths(config)["status"],
        {
            "contract_version": LIVE_CONTRACT_VERSION,
            "state": state,
            "updated_at": _utc_now(),
            "profile": control["profile"],
            "enabled": control["enabled"],
            **extra,
        },
    )


def _profile(live_config: dict[str, Any], name: str) -> dict[str, Any]:
    profile = live_config.get("profiles", {}).get(name)
    if not isinstance(profile, dict):
        raise ValueError(f"Unknown runtime profile: {name}")
    return profile


def _ollama_client(profile: dict[str, Any]) -> OllamaLocalClient:
    settings = profile.get("ollama", {})
    return OllamaLocalClient(
        base_url=str(settings.get("base_url") or "http://127.0.0.1:11434"),
        model=str(settings.get("model") or "gemma4:12b"),
        timeout_seconds=float(settings.get("timeout_seconds") or 300),
    )


def _ollama_sampling(profile: dict[str, Any]) -> dict[str, Any]:
    value = profile.get("ollama", {})
    return {
        "temperature": float(value.get("temperature", 0.85)),
        "top_p": float(value.get("top_p", 0.95)),
        "top_k": int(value.get("top_k", 64)),
        "num_ctx": int(value.get("num_ctx", 32768)),
        "keep_alive": str(value.get("keep_alive") or "10m"),
    }


def _speech_renderer(profile: dict[str, Any]) -> Qwen3TTSLocalRenderer:
    value = profile.get("qwen_tts", {})
    return Qwen3TTSLocalRenderer(
        model_name=str(
            value.get("model") or "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign"
        ),
        mode=str(value.get("mode") or "voice_design"),
        device_map=str(value.get("device_map") or "cuda:0"),
        dtype=str(value.get("dtype") or "bfloat16"),
        attention=str(value.get("attention") or "sdpa"),
    )


def _derived_seed(seed: int, purpose: str) -> int:
    digest = hashlib.blake2b(
        f"{int(seed)}:{purpose}".encode("utf-8"), digest_size=8
    ).digest()
    return int.from_bytes(digest, "big") % 2_147_483_647


def _variant_id(narration_id: str, loop_index: int, seed: int, cast_id: str) -> str:
    digest = hashlib.sha256(
        f"{narration_id}:{loop_index}:{seed}:{cast_id}".encode("utf-8")
    ).hexdigest()[:16]
    return f"{narration_id}--loop-{int(loop_index):04d}--{digest}"


def _canonical_audio_path(narration_dir: Path, narration_id: str) -> str | None:
    candidates = (
        narration_dir / "audio" / f"{narration_id}-voices-only.wav",
        narration_dir / "audio" / f"{narration_id}-voices-only.mp3",
        narration_dir / "audio" / "voices-only.wav",
        narration_dir / "audio" / "voices-only.mp3",
    )
    return next((str(path.resolve()) for path in candidates if path.is_file()), None)


def _source_locations(source_job: dict[str, Any]) -> list[dict[str, str]]:
    values = []
    for item in source_job.get("story_card", {}).get("locations", []):
        if not isinstance(item, dict):
            continue
        name = item.get("place") or item.get("name")
        excerpt = item.get("evidence_excerpt")
        if name and excerpt:
            values.append({"name": str(name), "evidence_excerpt": str(excerpt)})
    return values


def _protected_terms(adaptation: dict[str, Any], source_job: dict[str, Any]) -> list[str]:
    terms = []
    card = source_job.get("story_card", {})
    for item in card.get("locations", []) + card.get("people", []):
        if not isinstance(item, dict):
            continue
        value = item.get("place") or item.get("name_or_role") or item.get("name")
        if isinstance(value, str) and value.strip():
            terms.append(value.strip())
    terms.extend(
        str(value).strip()
        for value in card.get("pronunciation_items", [])
        if str(value).strip()
    )
    canonical_text = " ".join(
        str(section.get("text", "")) for section in adaptation.get("sections", [])
    )
    # Old cards may contain unrelated sidebar places/names. They must never
    # become compulsory additions to a reviewed personal narration.
    terms = [term for term in terms if term.casefold() in canonical_text.casefold()]
    terms.extend(re.findall(r"\b\d[\d,.:-]*\b", canonical_text))
    return list(dict.fromkeys(terms))


def _narration_prompt(
    adaptation: dict[str, Any],
    source_job: dict[str, Any],
    casting_card: dict[str, Any],
    *,
    instructions: str = "",
) -> str:
    packet = {
        "instructions": instructions,
        "task": (
            "Create one conversational first-person spoken variation of the approved "
            "canonical adaptation. Change phrasing and rhythm, not facts."
        ),
        "hard_rules": [
            "Use first person only; do not introduce a host or third-person narrator.",
            "Return exactly the supplied section IDs in the supplied order.",
            "Do not add, remove, combine, resolve, or reinterpret facts.",
            "Preserve every protected term, number, relationship, place, and exact quote.",
            "Treat the casting card as performance casting, never as source biography.",
            "Keep nonverbal direction out of spoken text.",
            "Keep each section between 70 and 135 percent of its canonical word count.",
        ],
        "protected_terms": _protected_terms(adaptation, source_job),
        "casting_card": casting_card,
        "metadata_only_source_gaps_never_speak": adaptation.get("unresolved_gaps", []),
        "sections": adaptation.get("sections", []),
    }
    return json.dumps(packet, ensure_ascii=False)


def _narration_schema(adaptation: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "required": ["sections"],
        "properties": {
            "sections": {
                "type": "array",
                "minItems": len(adaptation["sections"]),
                "maxItems": len(adaptation["sections"]),
                "items": {
                    "type": "object",
                    "required": ["section_id", "text", "delivery", "pause_after_ms"],
                    "properties": {
                        "section_id": {"type": "string"},
                        "text": {"type": "string", "minLength": 1},
                        "delivery": {
                            "type": "object",
                            "required": [
                                "emotion",
                                "intensity",
                                "pace",
                                "nonverbal",
                                "direction",
                            ],
                            "properties": {
                                "emotion": {"type": "string"},
                                "intensity": {"type": "number", "minimum": 0, "maximum": 1},
                                "pace": {
                                    "enum": [
                                        "very_slow",
                                        "slow",
                                        "measured",
                                        "conversational",
                                        "quick",
                                    ]
                                },
                                "nonverbal": {
                                    "type": "array",
                                    "items": {
                                        "enum": [
                                            "breath",
                                            "soft_laugh",
                                            "chuckle",
                                            "sigh",
                                            "hesitation",
                                            "voice_catch",
                                            "whispered_emphasis",
                                        ]
                                    },
                                },
                                "direction": {"type": "string"},
                            },
                        },
                        "pause_after_ms": {"type": "integer", "minimum": 0, "maximum": 10000},
                    },
                },
            }
        },
    }


def _accept_narration_variant(
    result: dict[str, Any],
    canonical: dict[str, Any],
    source_job: dict[str, Any],
    request: dict[str, Any],
) -> dict[str, Any]:
    sections = result.get("sections")
    if not isinstance(sections, list):
        raise ValueError("Narration variation has no sections")
    canonical_sections = canonical["sections"]
    expected_ids = [str(item["section_id"]) for item in canonical_sections]
    actual_ids = [str(item.get("section_id", "")) for item in sections]
    if actual_ids != expected_ids:
        raise ValueError("Narration variation changed section IDs or order")
    protected = _protected_terms(canonical, source_job)
    candidate_text = " ".join(str(item.get("text", "")) for item in sections)
    if not re.search(r"\b(?:I|me|my|mine|myself|we|us|our|ours)\b", candidate_text, re.I):
        raise ValueError("Narration variation is not first person")
    for term in protected:
        if term.casefold() not in candidate_text.casefold():
            raise ValueError(f"Narration variation dropped protected term: {term}")
    new_sections = []
    for candidate, source in zip(sections, canonical_sections):
        text = str(candidate.get("text") or "").strip()
        if not text:
            raise ValueError(f"Section {source['section_id']} is empty")
        if re.search(r"\[(?:sigh|laugh|breath|pause|hesitat|whisper)", text, re.I):
            raise ValueError("Narration variation put delivery direction in spoken text")
        source_words = max(1, len(re.findall(r"\b\w+\b", str(source["text"]))))
        candidate_words = len(re.findall(r"\b\w+\b", text))
        ratio = candidate_words / source_words
        if not 0.70 <= ratio <= 1.35:
            raise ValueError(
                f"Section {source['section_id']} length ratio {ratio:.2f} is outside 0.70-1.35"
            )
        canonical_content = _content_words(str(source["text"]))
        candidate_content = _content_words(text)
        if canonical_content:
            lexical_coverage = len(canonical_content & candidate_content) / len(
                canonical_content
            )
            if lexical_coverage < 0.50:
                raise ValueError(
                    f"Section {source['section_id']} preserved only "
                    f"{lexical_coverage:.0%} of canonical content terms"
                )
        allowed_numbers = set(
            re.findall(
                r"\b\d[\d,.:-]*\b",
                f"{source.get('text', '')} {source_job.get('story_text', '')}",
            )
        )
        candidate_numbers = set(re.findall(r"\b\d[\d,.:-]*\b", text))
        unsupported_numbers = sorted(candidate_numbers - allowed_numbers)
        if unsupported_numbers:
            raise ValueError(
                f"Section {source['section_id']} introduced unsupported numbers: "
                + ", ".join(unsupported_numbers)
            )
        for evidence in source.get("source_evidence", []):
            if evidence.get("usage") == "direct_quote" and evidence["excerpt"] not in text:
                raise ValueError("Narration variation changed an exact quotation")
        new_sections.append(
            {
                **deepcopy(source),
                "text": text,
                "delivery": deepcopy(candidate.get("delivery", source["delivery"])),
                "pause_after_ms": int(
                    candidate.get("pause_after_ms", source.get("pause_after_ms", 0))
                ),
            }
        )
    variation = deepcopy(canonical)
    variation["sections"] = new_sections
    variation["variant_id"] = request["variant_id"]
    variation["live_variation"] = {
        "mode": "ollama_constrained_rewrite",
        "canonical_adaptation": request["canonical"]["adaptation"],
        "cast_id": request["casting_card"]["cast_id"],
        "narration_seed": request["seeds"]["narration"],
    }
    quality_findings = spoken_content_findings(variation)
    if quality_findings:
        raise ValueError("Narration variation failed personal-story gate: "
                         + ", ".join(quality_findings))
    validation = validate_storytelling_adaptation_data(variation, source_job)
    if not validation["valid"]:
        raise ValueError(
            "Narration variation failed source gate: " + "; ".join(validation["errors"])
        )
    return variation


def _content_words(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z][a-z'-]{2,}", text.casefold())
        if token not in _CONTENT_STOPWORDS
    }


def _visual_prompt(
    plan: dict[str, Any],
    casting_card: dict[str, Any],
    *,
    instructions: str = "",
) -> str:
    scenes = []
    for scene in plan.get("scenes", []):
        prompt_chunks = scene.get("prompt", {}).get("chunks", [])
        canonical_prompt = " ".join(
            str(chunk.get("text", ""))
            for chunk in prompt_chunks
            if isinstance(chunk, dict)
        )
        scenes.append(
            {
                "scene_id": scene.get("scene_id"),
                "transcript": scene.get("transcript", ""),
                "section_ids": scene.get("section_ids", []),
                "personal_story_excerpt": scene.get("personal_story_excerpt", ""),
                "canonical_prompt": canonical_prompt,
                "visual_intent": scene.get("prompt", {}).get("visual_intent", ""),
                "grounding": scene.get("grounding", {}),
                "soundscape_context": scene.get("soundscape_context", {}),
            }
        )
    packet = {
        "instructions": instructions,
        "task": "Create one casting-aware SDXL prompt variation for every scene.",
        "hard_rules": [
            "Return every scene ID exactly once and in order.",
            "Each prompt must be 68-75 SDXL content tokens and include 4K photography.",
            "Preserve the scene's location, period, action, objects, emotion, "
            "and soundscape relevance.",
            "Use the same cast for every scene in this rendition.",
            "Prefer front-facing environmental portraits when a person is present.",
            "Never infer identity from location, language, name, or accent.",
            "Do not introduce readable text, logos, flags, or famous landmarks.",
        ],
        "casting_card": casting_card,
        "scenes": scenes,
    }
    return json.dumps(packet, ensure_ascii=False)


def _visual_schema(plan: dict[str, Any]) -> dict[str, Any]:
    count = len(plan.get("scenes", []))
    return {
        "type": "object",
        "required": ["cast_id", "scenes"],
        "properties": {
            "cast_id": {"type": "string"},
            "scenes": {
                "type": "array",
                "minItems": count,
                "maxItems": count,
                "items": {
                    "type": "object",
                    "required": ["scene_id", "prompt"],
                    "properties": {
                        "scene_id": {"type": "string"},
                        "prompt": {"type": "string", "minLength": 1},
                    },
                },
            },
        },
    }


def _accept_visual_variant(
    result: dict[str, Any],
    canonical: dict[str, Any],
    request: dict[str, Any],
    token_counter: Callable[[str], Any],
) -> dict[str, Any]:
    cast_id = str(request["casting_card"]["cast_id"])
    if result.get("cast_id") != cast_id:
        raise ValueError("Visual variation returned a different cast_id")
    scenes = result.get("scenes")
    if not isinstance(scenes, list):
        raise ValueError("Visual variation has no scenes")
    canonical_scenes = canonical.get("scenes", [])
    expected = [str(scene["scene_id"]) for scene in canonical_scenes]
    actual = [str(scene.get("scene_id", "")) for scene in scenes]
    if actual != expected:
        raise ValueError("Visual variation changed scene IDs or order")
    updated = deepcopy(canonical)
    image_seed = int(request["seeds"]["image"])
    for index, (scene, candidate) in enumerate(zip(updated["scenes"], scenes)):
        text = re.sub(r"\s+", " ", str(candidate.get("prompt") or "")).strip()
        if "4k photography" not in text.casefold():
            raise ValueError(f"Scene {scene['scene_id']} is missing 4K photography")
        counts = token_counter(text)
        maximum = int(getattr(counts, "maximum", counts))
        if not TARGET_TOKEN_MINIMUM <= maximum <= CONTENT_TOKEN_LIMIT:
            raise ValueError(
                f"Scene {scene['scene_id']} has {maximum} SDXL tokens; expected 68-75"
            )
        for location in scene.get("grounding", {}).get("locations", []):
            name = str(location.get("name") or location.get("place") or "").strip()
            canonical_text = " ".join(
                str(chunk.get("text", ""))
                for chunk in scene.get("prompt", {}).get("chunks", [])
            )
            if name and name.casefold() in canonical_text.casefold():
                if name.casefold() not in text.casefold():
                    raise ValueError(
                        f"Scene {scene['scene_id']} dropped grounded location {name}"
                    )
        scene["prompt"]["chunks"] = [
            {
                "role": "narrative",
                "text": text,
                "weight": 1.0,
                "content_token_count": maximum,
                "content_token_counts": getattr(counts, "by_tokenizer", {}),
            }
        ]
        scene["prompt"]["seed"] = _derived_seed(image_seed + index, "scene")
        scene["prompt"]["status"] = "live_generated_validated"
        scene["live_variation"] = {
            "variant_id": request["variant_id"],
            "cast_id": cast_id,
            "prompt_seed": request["seeds"]["visual_prompt"],
            "canonical_timing_preserved": True,
            "editorial_status": "runtime_preview_not_publication_approved",
        }
    updated["live_variation"] = {
        "variant_id": request["variant_id"],
        "cast_id": cast_id,
        "canonical_scene_boundaries_preserved": True,
        "identity_claim": False,
    }
    return updated


def _ollama_record(purpose: str, response: Any, prompt: str) -> dict[str, Any]:
    return {
        "provider": "ollama_local",
        "purpose": purpose,
        "model": response.model,
        "done_reason": response.done_reason,
        "prompt_eval_count": response.prompt_eval_count,
        "eval_count": response.eval_count,
        "total_duration_ns": response.total_duration_ns,
        "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "generated_at": _utc_now(),
        "paid": False,
    }


def _retime_visual_plan(
    plan: dict[str, Any],
    timeline: dict[str, Any],
) -> dict[str, Any]:
    """Retarget canonical scene boundaries to the rendered local speech.

    Storytelling visual plans may associate scenes with ``section_id`` or list
    that ID in ``segment_ids``. When those links are complete, each section's
    scenes are proportionally distributed inside the exact rendered speech
    interval. Older plans receive a whole-program proportional retime. In both
    cases scene order and semantic content remain unchanged.
    """

    updated = deepcopy(plan)
    scenes = updated.get("scenes", [])
    sections = timeline.get("sections", [])
    new_duration = int(timeline.get("duration_ms") or 0)
    old_duration = int(updated.get("duration_ms") or 0)
    if not scenes or not sections or new_duration <= 0 or old_duration <= 0:
        raise ValueError("Visual retiming requires positive scenes and speech timing")
    section_by_id = {str(item["section_id"]): item for item in sections}

    def scene_section_id(scene: dict[str, Any]) -> str | None:
        direct = scene.get("section_id")
        if direct is not None and str(direct) in section_by_id:
            return str(direct)
        for value in scene.get("segment_ids", []):
            if str(value) in section_by_id:
                return str(value)
        return None

    associations = [scene_section_id(scene) for scene in scenes]
    if all(associations):
        for section_id in dict.fromkeys(associations):
            indexes = [
                index for index, value in enumerate(associations) if value == section_id
            ]
            timing = section_by_id[str(section_id)]
            section_start = int(timing["start_ms"])
            section_end = int(timing["end_ms"])
            canonical_start = int(scenes[indexes[0]]["start_ms"])
            canonical_end = int(scenes[indexes[-1]]["end_ms"])
            canonical_span = max(1, canonical_end - canonical_start)
            new_span = max(1, section_end - section_start)
            previous = section_start
            for offset, index in enumerate(indexes):
                scene = scenes[index]
                start = previous
                if offset == len(indexes) - 1:
                    end = section_end
                else:
                    relative_end = (
                        int(scene["end_ms"]) - canonical_start
                    ) / canonical_span
                    end = section_start + round(relative_end * new_span)
                    end = max(start + 1, min(section_end, end))
                scene["start_ms"] = start
                scene["end_ms"] = end
                scene["duration_ms"] = end - start
                previous = end
    else:
        previous = 0
        for index, scene in enumerate(scenes):
            start = previous
            end = (
                new_duration
                if index == len(scenes) - 1
                else round(int(scene["end_ms"]) / old_duration * new_duration)
            )
            end = max(start + 1, min(new_duration, end))
            scene["start_ms"] = start
            scene["end_ms"] = end
            scene["duration_ms"] = end - start
            previous = end
    scenes[0]["start_ms"] = 0
    scenes[-1]["end_ms"] = new_duration
    scenes[-1]["duration_ms"] = new_duration - int(scenes[-1]["start_ms"])
    for scene in scenes:
        half = max(0, int(scene["duration_ms"]) // 2)
        scene["crossfade_in_ms"] = min(
            int(scene.get("crossfade_in_ms") or 0), half
        )
        scene["crossfade_out_ms"] = min(
            int(scene.get("crossfade_out_ms") or 0), half
        )
    updated["duration_ms"] = new_duration
    updated["captions"] = [
        {
            "caption_id": f"caption-{index:04d}",
            "start_ms": int(item["start_ms"]),
            "end_ms": int(item["speech_end_ms"]),
            "speaker": "Narrator",
            "text": str(item["text"]),
            "section_id": str(item["section_id"]),
        }
        for index, item in enumerate(sections, 1)
    ]
    updated.setdefault("live_variation", {})["timing"] = {
        "source": "local_tts_section_timeline",
        "strategy": (
            "semantic_section_proportional"
            if all(associations)
            else "whole_program_proportional_fallback"
        ),
        "canonical_duration_ms": old_duration,
        "rendered_duration_ms": new_duration,
    }
    return updated
