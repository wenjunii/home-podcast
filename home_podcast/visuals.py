from __future__ import annotations

import json
import re
import sqlite3
from copy import deepcopy
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from typing import Any, Iterable

VISUAL_CONTRACT_VERSION = 1
DEFAULT_MIN_SCENE_MS = 15_000
DEFAULT_CROSSFADE_MS = 5_000
DEFAULT_MAX_SCENE_MS = 35_000
FALLBACK_PROMPT = (
    "cinematic documentary photograph about home, belonging, memory, and recovered "
    "digital history, natural light, emotionally truthful composition, fine archival "
    "grain, tactile detail, no readable text, no logos"
)
GLOBAL_STYLE_PROMPT = (
    "photorealistic documentary still, nuanced natural light, restrained cinematic "
    "color, authentic materials, fine detail, 35mm photography, subtle archival grain"
)


@dataclass
class _SceneRun:
    segments: list[dict[str, Any]]
    story_ids: list[str]
    covered_start_ms: int | None = None
    covered_end_ms: int | None = None

    @property
    def start_ms(self) -> int:
        if self.covered_start_ms is not None:
            return self.covered_start_ms
        return int(self.segments[0]["start_ms"])

    @property
    def end_ms(self) -> int:
        if self.covered_end_ms is not None:
            return self.covered_end_ms
        return int(self.segments[-1]["end_ms"])

    @property
    def duration_ms(self) -> int:
        return self.end_ms - self.start_ms


def prepare_visual_scenes(
    timeline_path: Path,
    catalog_path: Path,
    output_path: Path,
    jobs_path: Path | None = None,
    *,
    min_scene_ms: int = DEFAULT_MIN_SCENE_MS,
    crossfade_ms: int = DEFAULT_CROSSFADE_MS,
) -> dict[str, Any]:
    """Create a story-centered visual plan and optional grounded LLM job packet.

    Captions remain turn-sized for accessibility. Visual scenes are deliberately
    longer: consecutive turns with the same story context form one run, and short
    runs are folded into a neighboring run rather than generating a disposable image.
    """

    if min_scene_ms < 1_000:
        raise ValueError("min_scene_ms must be at least 1000")
    if crossfade_ms < 0:
        raise ValueError("crossfade_ms cannot be negative")
    timeline = _load_object(timeline_path)
    segments = timeline.get("segments")
    if not isinstance(segments, list) or not segments:
        raise ValueError("Timeline must contain at least one segment")
    _validate_segments(segments)

    episode_duration_ms = int(
        timeline.get("duration_ms", int(segments[-1]["end_ms"]))
    )
    runs = _cover_timeline(_initial_runs(segments), episode_duration_ms)
    runs = _merge_short_runs(runs, min_scene_ms)
    evidence = _load_story_evidence(catalog_path, _all_story_ids(runs))
    scenes = [
        _serialize_scene(
            run,
            index,
            len(runs),
            crossfade_ms=crossfade_ms,
            evidence=evidence,
        )
        for index, run in enumerate(runs, start=1)
    ]
    episode_id = str(timeline["episode_id"])
    visual_plan = {
        "contract_version": VISUAL_CONTRACT_VERSION,
        "episode_id": episode_id,
        "touchdesigner_version": "2025.32820",
        "duration_ms": episode_duration_ms,
        "master_track": "voices_only",
        "audio_file": _project_audio_path(timeline, episode_id),
        "timing_policy": {
            "clock": "voices_only_audio_playhead",
            "minimum_scene_ms": min_scene_ms,
            "short_passage_policy": "merge_with_semantically_adjacent_scene",
            "maximum_scene_ms": None,
            "split_policy": (
                "split only for a material change of story, location, period, "
                "subject, or visual action"
            ),
            "crossfade_ms": crossfade_ms,
            "interpolation": "slerp",
        },
        "prompt_policy": {
            "model_family": "SDXL",
            "model_id": "stabilityai/sdxl-turbo",
            "maximum_content_tokens_per_chunk": 75,
            "preferred_content_tokens_per_narrative_chunk": [68, 75],
            "native_generation_note": (
                "4K is an aesthetic direction; native StreamDiffusionTD output is "
                "generated smaller and may be upscaled downstream."
            ),
            "global_style_prompt": GLOBAL_STYLE_PROMPT,
        },
        "grounding_policy": {
            "locations_are_required_when_supported": True,
            "location_does_not_imply_identity": True,
            "never_infer_identity_from": [
                "name",
                "language",
                "accent",
                "location",
                "nationality",
                "historical_period",
            ],
            "unknown_person_policy": (
                "Prefer back views, hands, silhouettes, interiors, landscapes, "
                "objects, or archival material instead of an invented face."
            ),
        },
        "captions": [_caption(segment) for segment in segments],
        "scenes": scenes,
    }
    _write_json(output_path, visual_plan)
    if jobs_path is not None:
        _write_visual_jobs(jobs_path, visual_plan, evidence)
    return {
        "episode_id": episode_id,
        "output": str(output_path),
        "jobs": str(jobs_path) if jobs_path is not None else None,
        "speech_captions": len(visual_plan["captions"]),
        "visual_scenes": len(scenes),
        "minimum_scene_ms": min(scene["duration_ms"] for scene in scenes),
        "maximum_scene_ms": max(scene["duration_ms"] for scene in scenes),
        "stories_represented": len(_all_story_ids(runs)),
        "prompts_pending_grounded_generation": sum(
            scene["prompt"]["status"] != "approved" for scene in scenes
        ),
    }


def expand_visual_scenes(
    source_plan_path: Path,
    timeline_path: Path,
    catalog_path: Path,
    output_path: Path,
    jobs_path: Path,
    *,
    min_scene_ms: int = DEFAULT_MIN_SCENE_MS,
    max_scene_ms: int = DEFAULT_MAX_SCENE_MS,
    crossfade_ms: int = DEFAULT_CROSSFADE_MS,
) -> dict[str, Any]:
    """Split long generated scenes while preserving one prompt per source scene.

    New boundaries are selected only from speech-segment starts. Each original
    prompt is retained in the child passage whose transcript best matches it;
    the other children receive pending prompt jobs. This makes a denser visual
    cut without paying to regenerate already accepted work.
    """

    if min_scene_ms < 1_000:
        raise ValueError("min_scene_ms must be at least 1000")
    if max_scene_ms < min_scene_ms:
        raise ValueError("max_scene_ms must be at least min_scene_ms")
    if crossfade_ms < 0:
        raise ValueError("crossfade_ms cannot be negative")

    source_plan = _load_object(source_plan_path)
    timeline = _load_object(timeline_path)
    if str(source_plan.get("episode_id")) != str(timeline.get("episode_id")):
        raise ValueError("Source visual plan and timeline episode IDs do not match")
    if int(source_plan.get("duration_ms", -1)) != int(
        timeline.get("duration_ms", -2)
    ):
        raise ValueError("Source visual plan and timeline durations do not match")
    source_scenes = source_plan.get("scenes")
    segments = timeline.get("segments")
    if not isinstance(source_scenes, list) or not source_scenes:
        raise ValueError("Source visual plan contains no scenes")
    if not isinstance(segments, list) or not segments:
        raise ValueError("Timeline contains no speech segments")
    _validate_segments(segments)
    segment_by_id = {
        str(segment["segment_id"]): segment
        for segment in segments
    }

    expanded: list[dict[str, Any]] = []
    preserved_count = 0
    for parent in source_scenes:
        parent_segments = [
            segment_by_id[str(segment_id)]
            for segment_id in parent.get("segment_ids", [])
            if str(segment_id) in segment_by_id
        ]
        if not parent_segments:
            raise ValueError(
                f"{parent.get('scene_id', 'scene')}: no timeline segments found"
            )
        partitions = _partition_scene_segments(
            parent,
            parent_segments,
            min_scene_ms=min_scene_ms,
            max_scene_ms=max_scene_ms,
        )
        preserve_index = _best_prompt_partition(parent, partitions)
        for partition_index, partition in enumerate(partitions):
            child = _expanded_child_scene(
                parent,
                partition,
                preserve_prompt=partition_index == preserve_index,
            )
            if partition_index == preserve_index:
                preserved_count += 1
            expanded.append(child)

    for index, scene in enumerate(expanded, start=1):
        scene["scene_id"] = f"visual-{index:03d}"
        scene["sequence"] = index
        if scene["prompt"].get("status") == "pending_grounded_generation":
            scene["prompt"]["seed"] = 20_132_000 + index
        effective_crossfade = min(crossfade_ms, int(scene["duration_ms"]) // 3)
        scene["crossfade_in_ms"] = 0 if index == 1 else effective_crossfade
        scene["crossfade_out_ms"] = (
            0 if index == len(expanded) else effective_crossfade
        )

    updated = deepcopy(source_plan)
    updated["timing_policy"] = {
        **dict(source_plan.get("timing_policy", {})),
        "minimum_scene_ms": min_scene_ms,
        "maximum_scene_ms": max_scene_ms,
        "split_policy": (
            "split long passages at speech boundaries; preserve one validated "
            "prompt per original scene and generate complementary child prompts"
        ),
        "crossfade_ms": crossfade_ms,
    }
    updated["scenes"] = expanded
    updated["scene_expansion"] = {
        "source_plan": source_plan_path.name,
        "source_scene_count": len(source_scenes),
        "expanded_scene_count": len(expanded),
        "preserved_prompt_count": preserved_count,
        "pending_prompt_count": len(expanded) - preserved_count,
        "minimum_scene_ms": min_scene_ms,
        "target_maximum_scene_ms": max_scene_ms,
        "boundary_policy": "speech_segment_starts",
    }
    updated.pop("visual_prompt_generation", None)

    evidence = _load_story_evidence(
        catalog_path,
        _unique_strings(
            story_id
            for scene in expanded
            for story_id in scene["source_story_ids"]
        ),
    )
    _write_json(output_path, updated)
    _write_visual_jobs(jobs_path, updated, evidence, pending_only=True)
    durations = [int(scene["duration_ms"]) for scene in expanded]
    pending_count = sum(
        scene["prompt"].get("status") == "pending_grounded_generation"
        for scene in expanded
    )
    return {
        "episode_id": str(updated["episode_id"]),
        "source_scenes": len(source_scenes),
        "visual_scenes": len(expanded),
        "preserved_prompts": preserved_count,
        "prompts_pending_grounded_generation": pending_count,
        "minimum_scene_ms": min(durations),
        "maximum_scene_ms": max(durations),
        "average_scene_ms": round(sum(durations) / len(durations)),
        "output": str(output_path),
        "jobs": str(jobs_path),
    }


def _partition_scene_segments(
    parent: dict[str, Any],
    segments: list[dict[str, Any]],
    *,
    min_scene_ms: int,
    max_scene_ms: int,
) -> list[dict[str, Any]]:
    start_ms = int(parent["start_ms"])
    end_ms = int(parent["end_ms"])
    duration_ms = end_ms - start_ms
    desired_count = max(1, (duration_ms + max_scene_ms - 1) // max_scene_ms)
    desired_count = min(desired_count, len(segments))
    best: tuple[tuple[int, int], tuple[int, ...], int] | None = None
    for partition_count in range(desired_count, 0, -1):
        target_ms = duration_ms / partition_count
        for split_indices in combinations(
            range(1, len(segments)),
            partition_count - 1,
        ):
            boundary_times = [
                start_ms,
                *(int(segments[index]["start_ms"]) for index in split_indices),
                end_ms,
            ]
            durations = [
                boundary_times[index + 1] - boundary_times[index]
                for index in range(partition_count)
            ]
            if any(duration < min_scene_ms for duration in durations):
                continue
            over_limit_penalty = sum(
                max(0, duration - max_scene_ms) ** 2
                for duration in durations
            )
            balance_penalty = round(
                sum((duration - target_ms) ** 2 for duration in durations)
            )
            score = (over_limit_penalty, balance_penalty)
            if best is None or score < best[0]:
                best = (score, split_indices, partition_count)
        if best is not None:
            break
    if best is None:
        raise ValueError(
            f"{parent.get('scene_id', 'scene')}: insufficient speech boundaries "
            "for requested visual density"
        )

    indices = (0, *best[1], len(segments))
    partition_count = best[2]
    partitions: list[dict[str, Any]] = []
    for partition_index in range(partition_count):
        segment_start = indices[partition_index]
        segment_end = indices[partition_index + 1]
        partition_start_ms = (
            start_ms
            if partition_index == 0
            else int(segments[segment_start]["start_ms"])
        )
        partition_end_ms = (
            end_ms
            if partition_index == partition_count - 1
            else int(segments[segment_end]["start_ms"])
        )
        partitions.append(
            {
                "partition_index": partition_index,
                "start_ms": partition_start_ms,
                "end_ms": partition_end_ms,
                "segments": segments[segment_start:segment_end],
            }
        )
    return partitions


def _best_prompt_partition(
    parent: dict[str, Any],
    partitions: list[dict[str, Any]],
) -> int:
    if len(partitions) == 1:
        return 0
    prompt = parent.get("prompt", {})
    prompt_text = " ".join(
        str(chunk.get("text", ""))
        for chunk in prompt.get("chunks", [])
        if isinstance(chunk, dict)
    )
    prompt_text += " " + str(prompt.get("visual_intent", ""))
    prompt_tokens = _matching_tokens(prompt_text)
    parent_center = (int(parent["start_ms"]) + int(parent["end_ms"])) / 2
    ranked: list[tuple[int, float, int]] = []
    for index, partition in enumerate(partitions):
        transcript = " ".join(
            str(segment.get("text", ""))
            for segment in partition["segments"]
        )
        overlap = len(prompt_tokens.intersection(_matching_tokens(transcript)))
        partition_center = (
            int(partition["start_ms"]) + int(partition["end_ms"])
        ) / 2
        ranked.append((overlap, -abs(partition_center - parent_center), -index))
    return max(range(len(partitions)), key=lambda index: ranked[index])


def _matching_tokens(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ0-9']+", value.casefold())
        if len(token) >= 4
    }


def _expanded_child_scene(
    parent: dict[str, Any],
    partition: dict[str, Any],
    *,
    preserve_prompt: bool,
) -> dict[str, Any]:
    segments = partition["segments"]
    child = deepcopy(parent)
    child["origin_scene_id"] = str(parent["scene_id"])
    child["origin_prompt_preserved"] = preserve_prompt
    child["start_ms"] = int(partition["start_ms"])
    child["end_ms"] = int(partition["end_ms"])
    child["duration_ms"] = child["end_ms"] - child["start_ms"]
    child["segment_ids"] = [str(segment["segment_id"]) for segment in segments]
    child["active_source_story_ids"] = _unique_strings(
        story_id
        for segment in segments
        for story_id in segment.get("source_story_ids", [])
    )
    child["transcript"] = " ".join(
        str(segment["text"]).strip()
        for segment in segments
        if str(segment.get("text", "")).strip()
    )
    if preserve_prompt:
        child["prompt"] = deepcopy(parent["prompt"])
        child["grounding"] = deepcopy(parent["grounding"])
        child["prompt"]["editorial_notes"] = _unique_strings(
            list(child["prompt"].get("editorial_notes", []))
            + [
                "Prompt preserved from the parent scene during dense expansion; "
                "confirm its placement against this shorter transcript passage."
            ]
        )
    else:
        preserved_prompt_text = " ".join(
            str(chunk.get("text", "")).strip()
            for chunk in parent.get("prompt", {}).get("chunks", [])
            if isinstance(chunk, dict) and str(chunk.get("text", "")).strip()
        )
        child["complementary_prompt_context"] = {
            "origin_scene_id": str(parent["scene_id"]),
            "avoid_existing_prompt": preserved_prompt_text,
            "instruction": (
                "Create a materially different composition for the same broader "
                "story context, grounded in this child transcript."
            ),
        }
        child["grounding"] = {
            "location_status": "pending_evidence_review",
            "locations": [],
            "identity_status": "pending_evidence_review",
            "identity_claims": [],
            "unknown_identity_attributes": [
                "gender",
                "age",
                "race",
                "ethnicity",
                "nationality",
            ],
            "supporting_story_ids": list(parent["source_story_ids"]),
            "editorial_review_required": True,
        }
        child["prompt"] = {
            "status": "pending_grounded_generation",
            "visual_intent": (
                "Create a complementary evidence-grounded image for this shorter "
                "passage without repeating the preserved parent composition."
            ),
            "chunks": [
                {
                    "role": "narrative",
                    "text": FALLBACK_PROMPT,
                    "weight": 1.0,
                    "content_token_count": None,
                }
            ],
            "seed": 0,
            "sensitivity_notes": [],
            "editorial_notes": [
                "Generate a distinct composition for this child passage.",
                "Do not invent a visible demographic identity.",
            ],
        }
    return child


def validate_visual_plan(path: Path) -> dict[str, Any]:
    plan = _load_object(path)
    errors: list[str] = []
    warnings: list[str] = []
    scenes = plan.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        return {"valid": False, "errors": ["Plan contains no scenes"], "warnings": []}
    expected_start = 0
    for index, scene in enumerate(scenes, start=1):
        label = str(scene.get("scene_id", f"scene {index}"))
        start_ms = int(scene.get("start_ms", -1))
        end_ms = int(scene.get("end_ms", -1))
        if start_ms != expected_start:
            errors.append(
                f"{label}: starts at {start_ms}, expected contiguous start {expected_start}"
            )
        if end_ms <= start_ms:
            errors.append(f"{label}: end_ms must be after start_ms")
        expected_start = end_ms
        prompt = scene.get("prompt", {})
        chunks = prompt.get("chunks", [])
        if not isinstance(chunks, list) or not chunks:
            errors.append(f"{label}: prompt.chunks must not be empty")
        for chunk in chunks:
            text = str(chunk.get("text", "")).strip()
            if not text:
                errors.append(f"{label}: prompt chunk is empty")
            token_count = chunk.get("content_token_count")
            if isinstance(token_count, int) and token_count > 75:
                errors.append(
                    f"{label}: prompt chunk exceeds 75 content tokens ({token_count})"
                )
        if prompt.get("status") != "approved":
            warnings.append(f"{label}: prompt still requires grounded editorial approval")
        grounding = scene.get("grounding", {})
        if grounding.get("location_status") not in {
            "verified",
            "machine_verified_evidence",
            "no_explicit_location",
        }:
            warnings.append(f"{label}: location evidence has not been verified")
        if grounding.get("identity_status") not in {
            "verified",
            "machine_verified_evidence",
            "identity_not_explicit",
        }:
            warnings.append(f"{label}: identity evidence has not been verified")
    duration_ms = int(plan.get("duration_ms", -1))
    if expected_start != duration_ms:
        errors.append(
            f"Final scene ends at {expected_start}, episode duration is {duration_ms}"
        )
    return {"valid": not errors, "errors": errors, "warnings": warnings}


def _initial_runs(segments: list[dict[str, Any]]) -> list[_SceneRun]:
    runs: list[_SceneRun] = []
    for segment in segments:
        story_ids = _unique_strings(segment.get("source_story_ids", []))
        if not runs:
            runs.append(_SceneRun([segment], story_ids))
            continue
        if not story_ids:
            runs[-1].segments.append(segment)
            continue
        if story_ids == runs[-1].story_ids:
            runs[-1].segments.append(segment)
            continue
        runs.append(_SceneRun([segment], story_ids))
    if len(runs) > 1 and not runs[0].story_ids:
        runs[1].segments = runs[0].segments + runs[1].segments
        runs = runs[1:]
    return runs


def _merge_short_runs(runs: list[_SceneRun], minimum_ms: int) -> list[_SceneRun]:
    result = list(runs)
    while len(result) > 1:
        short_index = next(
            (index for index, run in enumerate(result) if run.duration_ms < minimum_ms),
            None,
        )
        if short_index is None:
            break
        target_index = _merge_target(result, short_index)
        left_index = min(short_index, target_index)
        right_index = max(short_index, target_index)
        left = result[left_index]
        right = result[right_index]
        merged = _SceneRun(
            segments=left.segments + right.segments,
            story_ids=_unique_strings(left.story_ids + right.story_ids),
            covered_start_ms=left.start_ms,
            covered_end_ms=right.end_ms,
        )
        result[left_index : right_index + 1] = [merged]
    return result


def _merge_target(runs: list[_SceneRun], index: int) -> int:
    if index == 0:
        return 1
    if index == len(runs) - 1:
        return index - 1
    current_ids = set(runs[index].story_ids)
    previous_overlap = len(current_ids.intersection(runs[index - 1].story_ids))
    next_overlap = len(current_ids.intersection(runs[index + 1].story_ids))
    if next_overlap > previous_overlap:
        return index + 1
    if previous_overlap > next_overlap:
        return index - 1
    # A transition normally completes the preceding thought. Favor holding the
    # previous image instead of flashing a new one for a short bridge.
    return index - 1


def _cover_timeline(runs: list[_SceneRun], duration_ms: int) -> list[_SceneRun]:
    if not runs:
        return []
    result: list[_SceneRun] = []
    for index, run in enumerate(runs):
        start_ms = 0 if index == 0 else int(run.segments[0]["start_ms"])
        end_ms = (
            int(runs[index + 1].segments[0]["start_ms"])
            if index + 1 < len(runs)
            else duration_ms
        )
        result.append(
            _SceneRun(
                segments=run.segments,
                story_ids=run.story_ids,
                covered_start_ms=start_ms,
                covered_end_ms=end_ms,
            )
        )
    return result


def _serialize_scene(
    run: _SceneRun,
    index: int,
    scene_count: int,
    *,
    crossfade_ms: int,
    evidence: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    effective_crossfade = min(
        crossfade_ms,
        run.duration_ms // 3,
    )
    story_evidence = [evidence[story_id] for story_id in run.story_ids if story_id in evidence]
    return {
        "scene_id": f"visual-{index:03d}",
        "sequence": index,
        "start_ms": run.start_ms,
        "end_ms": run.end_ms,
        "duration_ms": run.duration_ms,
        "crossfade_in_ms": 0 if index == 1 else effective_crossfade,
        "crossfade_out_ms": 0 if index == scene_count else effective_crossfade,
        "segment_ids": [str(segment["segment_id"]) for segment in run.segments],
        "source_story_ids": run.story_ids,
        "transcript": " ".join(str(segment["text"]).strip() for segment in run.segments),
        "story_context": [
            {
                "story_id": item["story_id"],
                "language": item["language"],
                "summary": item.get("summary", ""),
                "emotional_tone": item.get("emotional_tone", ""),
                "sensitivity_notes": item.get("sensitivity_notes", []),
            }
            for item in story_evidence
        ],
        "grounding": {
            "location_status": "pending_evidence_review",
            "locations": [],
            "identity_status": "pending_evidence_review",
            "identity_claims": [],
            "unknown_identity_attributes": [
                "gender",
                "age",
                "race",
                "ethnicity",
                "nationality",
            ],
            "supporting_story_ids": run.story_ids,
        },
        "prompt": {
            "status": "pending_grounded_generation",
            "visual_intent": "Hold one evidence-grounded image for this story passage.",
            "chunks": [
                {
                    "role": "narrative",
                    "text": FALLBACK_PROMPT,
                    "weight": 1.0,
                    "content_token_count": None,
                }
            ],
            "seed": 20_131_200 + index,
            "editorial_notes": [
                "Replace fallback only after location and identity evidence review.",
                "Do not invent a visible demographic identity.",
            ],
        },
    }


def _load_story_evidence(
    catalog_path: Path,
    story_ids: Iterable[str],
) -> dict[str, dict[str, Any]]:
    if not catalog_path.is_file():
        raise FileNotFoundError(f"Catalog does not exist: {catalog_path}")
    requested = list(story_ids)
    if not requested:
        return {}
    uri = f"file:{catalog_path.as_posix()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    try:
        evidence: dict[str, dict[str, Any]] = {}
        for story_id in requested:
            story = connection.execute(
                "SELECT * FROM stories WHERE id = ?",
                (story_id,),
            ).fetchone()
            if story is None:
                raise ValueError(f"Timeline references missing story {story_id}")
            card_row = connection.execute(
                """
                SELECT card_json FROM story_cards
                WHERE story_id = ? AND content_hash = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (story_id, story["content_hash"]),
            ).fetchone()
            card = json.loads(card_row["card_json"]) if card_row else {}
            evidence[story_id] = {
                "story_id": story_id,
                "content_hash": str(story["content_hash"]),
                "language": str(story["language"]),
                "heading": str(story["heading"]),
                "source_url": str(story["source_url"]),
                "crawl_timestamp": str(story["crawl_timestamp"]),
                "summary": str(card.get("summary", "")),
                "emotional_tone": str(card.get("emotional_tone", "")),
                "memorable_passages": card.get("memorable_passages", []),
                "sensitivity_notes": card.get("sensitivity_notes", []),
                "story_text": str(story["story_text"]),
            }
        return evidence
    finally:
        connection.close()


def _write_visual_jobs(
    path: Path,
    plan: dict[str, Any],
    evidence: dict[str, dict[str, Any]],
    *,
    pending_only: bool = False,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for scene in plan["scenes"]:
            if (
                pending_only
                and scene.get("prompt", {}).get("status")
                != "pending_grounded_generation"
            ):
                continue
            scene_evidence = [
                evidence[story_id]
                for story_id in scene["source_story_ids"]
                if story_id in evidence
            ]
            job = {
                "contract_version": 1,
                "episode_id": plan["episode_id"],
                "scene_id": scene["scene_id"],
                "start_ms": scene["start_ms"],
                "end_ms": scene["end_ms"],
                "duration_ms": scene["duration_ms"],
                "transcript": scene["transcript"],
                "source_story_ids": scene["source_story_ids"],
                "source_evidence": scene_evidence,
                "complementary_prompt_context": scene.get(
                    "complementary_prompt_context"
                ),
                "requirements": {
                    "maximum_content_tokens_per_chunk": 75,
                    "target_narrative_tokens": [68, 75],
                    "locations_must_be_evidence_grounded": True,
                    "identity_must_be_evidence_grounded": True,
                    "location_does_not_imply_identity": True,
                    "style": (
                        "cinematic 4K-quality documentary photography, natural "
                        "emotion, tactile detail, historically coherent"
                    ),
                    "unknown_identity_visuals": [
                        "back view",
                        "hands",
                        "silhouette",
                        "interior",
                        "landscape",
                        "object",
                        "archival material",
                    ],
                },
            }
            handle.write(json.dumps(job, ensure_ascii=False) + "\n")


def _caption(segment: dict[str, Any]) -> dict[str, Any]:
    return {
        "caption_id": str(segment["segment_id"]),
        "start_ms": int(segment["start_ms"]),
        "end_ms": int(segment["end_ms"]),
        "speaker": str(segment.get("display_name", segment.get("speaker", ""))),
        "text": str(segment["text"]),
    }


def _project_audio_path(timeline: dict[str, Any], episode_id: str) -> str:
    tracks = timeline.get("tracks", {})
    voices = tracks.get("voices_only", {}) if isinstance(tracks, dict) else {}
    candidate = voices.get("distribution_audio") or voices.get("master_audio")
    if candidate:
        name = Path(str(candidate)).name
        return f"episodes/{episode_id}/audio/{name}"
    return f"episodes/{episode_id}/audio/{episode_id}-voices-only.mp3"


def _all_story_ids(runs: Iterable[_SceneRun]) -> list[str]:
    return _unique_strings(story_id for run in runs for story_id in run.story_ids)


def _unique_strings(values: Iterable[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def _validate_segments(segments: list[dict[str, Any]]) -> None:
    previous_end = 0
    for index, segment in enumerate(segments, start=1):
        start_ms = int(segment["start_ms"])
        end_ms = int(segment["end_ms"])
        if start_ms < previous_end:
            raise ValueError(
                f"Timeline segment {index} overlaps the preceding segment "
                f"({start_ms} < {previous_end})"
            )
        if end_ms <= start_ms:
            raise ValueError(f"Timeline segment {index} has non-positive duration")
        previous_end = end_ms


def _load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
