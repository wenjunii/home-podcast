from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from home_podcast.visual_prompt_runner import SdxlTokenCounter, TokenCount


TARGET_MINIMUM = 68
TOKEN_LIMIT = 75
DELIBERATE_ABSENCE_MARKERS = (
    "deliberate absence",
    "indigenous perspective",
    "perspective the account does not preserve",
)
ABSENCE_PATTERNS = (
    r"\bno (?:person|people|pedestrians|figure)(?: visible| present| depicted)? or\b",
    r"\bno (?:person|people|pedestrians|figure)(?: visible| present| depicted)?\b[,.]?",
    r"\bno figure visible\b[,.]?",
)
FRONT_ORIENTATION = re.compile(
    r"\bfront-facing\b|\bfacing (?:the )?camera\b",
    flags=re.IGNORECASE,
)
HUMAN_SUBJECT = re.compile(
    r"(?<!first-)\b(?:person|people|man|woman|student|figure|figures|adult|"
    r"adults|walker|walkers|child|children|hand|hands|silhouette|silhouettes)\b",
    flags=re.IGNORECASE,
)
GENERIC_REPLACEMENTS = (
    ("cinematic 4K documentary photography", "4K documentary photography"),
    ("cinematic 4K photography", "4K photography"),
    ("shallow depth of field", "shallow focus"),
    ("Fine natural grain, tactile detail", "fine natural grain"),
    ("fine natural grain, tactile detail", "fine natural grain"),
    ("soft bokeh background", "soft background"),
    ("quietly melancholic atmosphere", "melancholic atmosphere"),
)
INCOMPLETE_END_WORDS = {
    "a",
    "an",
    "the",
    "and",
    "or",
    "but",
    "with",
    "without",
    "at",
    "in",
    "on",
    "of",
    "to",
    "from",
    "for",
    "by",
    "beside",
    "behind",
    "across",
    "through",
    "into",
    "against",
    "faint",
    "warm",
    "cool",
    "soft",
    "one",
    "its",
    "their",
    "his",
    "her",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare no-network human-figure visual jobs and Codex results. "
            "Import the results with home_podcast import-visual-prompts."
        )
    )
    parser.add_argument("--source-visuals", type=Path, required=True)
    parser.add_argument("--source-jobs", type=Path, required=True)
    parser.add_argument("--base-output", type=Path, required=True)
    parser.add_argument("--jobs-output", type=Path, required=True)
    parser.add_argument("--results-output", type=Path, required=True)
    parser.add_argument("--report-output", type=Path)
    parser.add_argument("--tokenizer-model")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = prepare_human_figure_visual_path(
        args.source_visuals.resolve(),
        args.source_jobs.resolve(),
        args.base_output.resolve(),
        args.jobs_output.resolve(),
        args.results_output.resolve(),
        tokenizer_model=args.tokenizer_model,
    )
    if args.report_output is not None:
        _write_json(args.report_output.resolve(), report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def prepare_human_figure_visual_path(
    source_visuals: Path,
    source_jobs: Path,
    base_output: Path,
    jobs_output: Path,
    results_output: Path,
    *,
    tokenizer_model: str | None = None,
    token_counter: Callable[[str], TokenCount] | None = None,
) -> dict[str, Any]:
    plan = _load_object(source_visuals)
    jobs = _read_jsonl(source_jobs)
    scenes = plan.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        raise ValueError("Source visual plan contains no scenes")
    if len(jobs) != len(scenes):
        raise ValueError(
            f"Source jobs contain {len(jobs)} records for {len(scenes)} scenes"
        )
    jobs_by_scene = {str(job.get("scene_id", "")): job for job in jobs}
    scene_ids = [str(scene["scene_id"]) for scene in scenes]
    if set(jobs_by_scene) != set(scene_ids):
        raise ValueError("Source visual scenes and jobs do not have identical IDs")

    tokenizer_reference = (
        tokenizer_model
        or str(plan.get("prompt_policy", {}).get("model_id", "")).strip()
        or "stabilityai/sdxl-turbo"
    )
    if token_counter is None:
        counter = SdxlTokenCounter.load(tokenizer_reference)
        token_counter = counter.count
        tokenizer_source = str(counter.model_root)
    else:
        tokenizer_source = tokenizer_reference

    base_plan = deepcopy(plan)
    base_plan["visual_path"] = {
        "id": "human_figures",
        "label": "Human Figures",
        "source_plan": source_visuals.name,
        "timing_lock": "scene_ids, boundaries, captions, and story IDs unchanged",
        "audio_compatibility": ["voices_only", "soundscape_only"],
        "soundscape_alignment": (
            "Retain each source scene's location, objects, action, and emotional "
            "register so the existing scene-matched soundscape remains valid."
        ),
        "identity_policy": (
            "Use only evidence-backed identity claims. Prefer front-facing "
            "environmental portraits, but place an incompletely evidenced face in "
            "soft shadow, silhouette, reflection, or diffusion so unsupported "
            "demographic traits remain unreadable."
        ),
        "portrait_policy": (
            "Maximize front-facing portrait compositions without inventing a clear "
            "face or unsupported race, ethnicity, nationality, gender, or age."
        ),
    }

    output_jobs: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []
    changed = deliberate_absence = 0
    counts: list[int] = []
    for scene in base_plan["scenes"]:
        scene_id = str(scene["scene_id"])
        original_text = _prompt_text(scene)
        mode, prompt_text = _human_prompt(scene, original_text, token_counter)
        measured = token_counter(prompt_text)
        if not TARGET_MINIMUM <= measured.maximum <= TOKEN_LIMIT:
            raise ValueError(
                f"{scene_id}: human prompt has {measured.maximum} tokens"
            )
        counts.append(measured.maximum)
        if mode == "deliberate_absence":
            deliberate_absence += 1
        else:
            changed += 1

        source_hash = hashlib.sha256(original_text.encode("utf-8")).hexdigest()
        scene["human_figure_path"] = {
            "mode": mode,
            "source_prompt_sha256": source_hash,
            "location_and_identity_grounding_unchanged": True,
            "timing_unchanged": True,
            "audio_alignment_unchanged": True,
        }

        job = deepcopy(jobs_by_scene[scene_id])
        job["human_figure_path_context"] = {
            "source_prompt": original_text,
            "required_visual_priority": (
                "Make a supported human presence the primary subject unless "
                "deliberate absence is required by the sensitivity policy."
            ),
            "identity_policy": base_plan["visual_path"]["identity_policy"],
            "audio_alignment": base_plan["visual_path"]["soundscape_alignment"],
            "selected_mode": mode,
            "portrait_mode": (
                "deliberate_absence"
                if mode == "deliberate_absence"
                else "front_facing"
            ),
        }
        requirements = dict(job.get("requirements", {}))
        requirements["human_figure_primary"] = mode != "deliberate_absence"
        requirements["preserve_scene_timing"] = True
        requirements["preserve_soundscape_subject"] = True
        requirements["front_facing_portrait"] = mode != "deliberate_absence"
        job["requirements"] = requirements
        output_jobs.append(job)

        grounding = scene.get("grounding", {})
        sensitivity_notes = list(scene.get("prompt", {}).get("sensitivity_notes", []))
        if mode == "deliberate_absence":
            sensitivity_notes.append(
                "Human-focused path retains deliberate absence because depicting "
                "people would invent a perspective omitted by the source."
            )
        else:
            sensitivity_notes.append(
                "The primary human presence uses a front-facing environmental "
                "portrait, while soft silhouette, shadow, reflection, or diffusion "
                "keeps unsupported demographic traits unreadable."
            )
        results.append(
            {
                "scene_id": scene_id,
                "visual_intent": _visual_intent(scene, mode),
                "locations": deepcopy(grounding.get("locations", [])),
                "identity_claims": deepcopy(grounding.get("identity_claims", [])),
                "unknown_identity_attributes": list(
                    grounding.get("unknown_identity_attributes", [])
                ),
                "camera_policy": _camera_policy(mode),
                "prompt_chunks": [
                    {"role": "narrative", "text": prompt_text, "weight": 1.0}
                ],
                "seed": int(scene.get("prompt", {}).get("seed", 0)),
                "sensitivity_notes": _unique_strings(sensitivity_notes),
                "editorial_review_required": True,
            }
        )

    base_plan["visual_path"]["scene_count"] = len(scenes)
    base_plan["visual_path"]["human_primary_scene_count"] = (
        changed
    )
    base_plan["visual_path"]["deliberate_absence_scene_count"] = deliberate_absence
    base_plan["visual_path"]["front_portrait_scene_count"] = changed
    base_plan["visual_path"]["clear_face_scene_count"] = 0
    _write_json(base_output, base_plan)
    _write_jsonl(jobs_output, output_jobs)
    _write_jsonl(results_output, results)
    return {
        "episode_id": str(plan["episode_id"]),
        "scenes": len(scenes),
        "new_human_primary_prompts": changed,
        "retained_human_primary_prompts": 0,
        "human_primary_scenes": changed,
        "front_portrait_scenes": changed,
        "clear_face_scenes": 0,
        "deliberate_absence_scenes": deliberate_absence,
        "minimum_content_tokens": min(counts),
        "maximum_content_tokens": max(counts),
        "tokenizer_model": tokenizer_reference,
        "tokenizer_source": tokenizer_source,
        "network_calls": 0,
        "base_output": str(base_output),
        "jobs_output": str(jobs_output),
        "results_output": str(results_output),
    }


def _human_prompt(
    scene: dict[str, Any],
    original: str,
    token_counter: Callable[[str], TokenCount],
) -> tuple[str, str]:
    combined_notes = " ".join(
        [
            str(scene.get("prompt", {}).get("visual_intent", "")),
            *[str(note) for note in scene.get("prompt", {}).get("sensitivity_notes", [])],
            original,
        ]
    ).casefold()
    if any(marker in combined_notes for marker in DELIBERATE_ABSENCE_MARKERS):
        return "deliberate_absence", original

    sanitized = _front_portrait_body(original, scene)
    long_prefix, short_prefix, minimal_prefix = _subject_prefixes(
        scene,
        body_has_front_subject=bool(
            FRONT_ORIENTATION.search(sanitized)
            and HUMAN_SUBJECT.search(sanitized)
        ),
    )
    candidates = []
    for prefix in (long_prefix, short_prefix, minimal_prefix):
        candidates.extend(_candidate_prefixes(prefix, sanitized))
    fitted = _best_fitted(candidates, token_counter)
    if fitted is None:
        raise ValueError(f"{scene['scene_id']}: cannot fit human prompt to 68-75 tokens")
    return "front_portrait_identity_safe", fitted


def _subject_prefixes(
    scene: dict[str, Any],
    *,
    body_has_front_subject: bool,
) -> tuple[str, str, str]:
    if body_has_front_subject:
        return (
            "Identity-safe environmental portrait, face modeled in soft shadow and unsupported demographic traits unreadable, cinematic 4K documentary photography:",
            "Identity-safe environmental portrait, facial details diffused and unsupported traits unreadable, 4K documentary photography:",
            "Environmental portrait with facial details in soft silhouette, unsupported traits unreadable, 4K photography:",
        )
    gender = _explicit_gender(scene)
    if gender:
        subject = f"the documented {gender}"
    else:
        subject = "an anonymous figure"
    return (
        f"Front-facing environmental portrait of {subject} filling the foreground in soft silhouette, face and unsupported demographic traits unreadable, cinematic 4K documentary photography:",
        f"Front-facing 4K environmental portrait of {subject} filling the foreground, facial details hidden in soft shadow and unsupported traits unreadable:",
        f"Front-facing portrait of {subject} filling the foreground in soft silhouette, demographic details unreadable, 4K photography:",
    )


def _front_portrait_body(value: str, scene: dict[str, Any]) -> str:
    result = _sanitize_absence(value)
    replacements = (
        (r"\btwo adults seen only from behind\b", "two adults facing the camera as soft silhouettes"),
        (r"\bsilhouette of a person sitting\b", "front-facing silhouette of a person seated"),
        (r"\bback-view silhouette of\b", "front-facing silhouette of"),
        (r"\bback view of\b", "front-facing portrait of"),
        (r"\bback-view\b", "front-facing"),
        (
            r"\b((?:anonymous |solitary |lone |single )?(?:student|figure|man|woman|walker|walkers|adult|adults|silhouette)) seen only from behind\b",
            r"\1 facing the camera in soft silhouette",
        ),
        (
            r"\b((?:anonymous |solitary |lone |single )?(?:student|figure|man|woman|walker|walkers|adult|adults|silhouette)) seen from behind\b",
            r"\1 facing the camera in soft silhouette",
        ),
        (r"\bwalks away from camera\b", "faces the camera from the road"),
        (r"\balready several steps away\b", "standing near the foreground"),
        (r"\btight overhead shot of\b", "eye-level portrait beside"),
        (r"\boverhead close-up of\b", "eye-level portrait beside"),
        (r"\boverhead view of\b", "eye-level portrait beside"),
        (r"\btop-down photograph of\b", "eye-level portrait beside"),
    )
    for pattern, replacement in replacements:
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
    if _explicit_gender(scene) is None:
        result = re.sub(
            r"\bbehind him\b",
            "behind the figure",
            result,
            flags=re.IGNORECASE,
        )
    return result


def _explicit_gender(scene: dict[str, Any]) -> str | None:
    claims = scene.get("grounding", {}).get("identity_claims", [])
    for claim in claims:
        if str(claim.get("attribute", "")).casefold() != "gender":
            continue
        value = str(claim.get("value", "")).casefold()
        if re.search(r"\b(?:female|woman)\b", value):
            return "woman"
        if re.search(r"\b(?:male|man)\b", value):
            return "man"
    return None


def _candidate_prefixes(prefix: str, original: str) -> list[str]:
    variants = [original]
    current = original
    for source, replacement in GENERIC_REPLACEMENTS:
        current = current.replace(source, replacement)
        variants.append(current)
    candidates: list[str] = []
    for variant in variants:
        clauses = [part.strip() for part in re.split(r",\s+", variant) if part.strip()]
        for end in range(len(clauses), 1, -1):
            body = ", ".join(clauses[:end]).rstrip(" ,;:-")
            candidates.append(f"{prefix} {body}.")
        candidates.append(f"{prefix} {variant.rstrip(' .')}.")
    return _unique_strings(candidates)


def _best_fitted(
    candidates: list[str],
    token_counter: Callable[[str], TokenCount],
) -> str | None:
    fitted: list[tuple[int, int, str]] = []
    for candidate in candidates:
        candidate = _clean_prompt_ending(candidate)
        count = token_counter(candidate).maximum
        if TARGET_MINIMUM <= count <= TOKEN_LIMIT:
            fitted.append((count, len(candidate), candidate))
    if fitted:
        return max(fitted)[2]

    # Final bounded fallback: shorten only the tail, preserving the human-first
    # subject and the source prompt's leading location/action clauses.
    for candidate in candidates:
        words = candidate.split()
        for end in range(len(words) - 1, 12, -1):
            shortened = _clean_prompt_ending(" ".join(words[:end]))
            count = token_counter(shortened).maximum
            if TARGET_MINIMUM <= count <= TOKEN_LIMIT:
                fitted.append((count, len(shortened), shortened))
            if count < TARGET_MINIMUM:
                break
    return max(fitted)[2] if fitted else None


def _clean_prompt_ending(value: str) -> str:
    words = value.rstrip(" ,;:-.").split()
    while words and words[-1].casefold().strip("'\"") in INCOMPLETE_END_WORDS:
        words.pop()
    return " ".join(words).rstrip(" ,;:-.") + "."


def _sanitize_absence(value: str) -> str:
    result = value
    result = re.sub(
        ABSENCE_PATTERNS[0],
        "no",
        result,
        flags=re.IGNORECASE,
    )
    for pattern in ABSENCE_PATTERNS[1:]:
        result = re.sub(pattern, "", result, flags=re.IGNORECASE)
    # Once a foreground person is introduced, keep the original identity-safe
    # framing without contradictory claims that every human feature is outside
    # the frame.
    result = re.sub(
        r"anonymous hands just outside frame,?\s*",
        "",
        result,
        flags=re.IGNORECASE,
    )
    result = re.sub(
        r"driver'?s face outside frame",
        "driver's facial details unreadable",
        result,
        flags=re.IGNORECASE,
    )
    result = re.sub(
        r"face kept outside frame",
        "facial details unreadable",
        result,
        flags=re.IGNORECASE,
    )
    result = re.sub(
        r"faces outside frame",
        "facial details unreadable",
        result,
        flags=re.IGNORECASE,
    )
    result = re.sub(r"^empty\b", "Quiet", result, flags=re.IGNORECASE)
    result = re.sub(r"^inside an empty\b", "Inside a quiet", result, flags=re.IGNORECASE)
    result = re.sub(r"\s+([,.])", r"\1", result)
    result = re.sub(r"\s{2,}", " ", result)
    result = result.strip(" ,")
    return result[:1].upper() + result[1:]


def _prompt_text(scene: dict[str, Any]) -> str:
    chunks = scene.get("prompt", {}).get("chunks", [])
    texts = [str(chunk.get("text", "")).strip() for chunk in chunks]
    value = " ".join(text for text in texts if text)
    if not value:
        raise ValueError(f"{scene.get('scene_id', 'scene')}: source prompt is empty")
    return value


def _visual_intent(scene: dict[str, Any], mode: str) -> str:
    source_intent = str(scene.get("prompt", {}).get("visual_intent", "")).strip()
    if mode == "deliberate_absence":
        return (
            "Retain evidence-conscious deliberate absence in this sensitive scene; "
            + source_intent
        ).strip()
    return (
        "Make an identity-safe front-facing environmental portrait the primary "
        "composition while preserving the scene's location, action, objects, "
        "emotion, and audio alignment; "
        + source_intent
    ).strip()


def _camera_policy(mode: str) -> str:
    if mode == "deliberate_absence":
        return (
            "Deliberate absence: the source omits a vulnerable perspective, so do "
            "not invent people, faces, or demographic traits."
        )
    return (
        "Front-facing environmental portrait: keep an incompletely evidenced face "
        "in soft shadow, silhouette, reflection, diffusion, or archival occlusion. "
        "Unsupported race, ethnicity, nationality, gender, age, and other identity "
        "traits must remain unreadable."
    )


def _load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return value


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    records = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"{path}:{line_number}: expected JSON object")
        records.append(value)
    return records


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
            handle.write("\n")


def _unique_strings(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        normalized = str(value).strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
