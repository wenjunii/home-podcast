from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


DEFAULT_BASE_PROMPT = (
    "Thirty-second seamless loop of nearly silent neutral archival air: soft "
    "room tone, faint paper-fiber hush and extremely sparse warm digital grain, "
    "stable and unobtrusive, no identifiable place, no voices, no melody, no "
    "pulse, no dramatic events, designed to sit underneath an entire documentary "
    "podcast"
)


def build_scene_soundscape(
    visuals_path: Path,
    timeline_path: Path,
    sound_prompts: dict[str, dict[str, Any]],
    output_path: Path,
    *,
    expected_visuals_sha256: str | None = None,
) -> dict[str, Any]:
    visuals = _load_object(visuals_path)
    timeline = _load_object(timeline_path)
    visuals_sha256 = _file_sha256(visuals_path)
    if (
        expected_visuals_sha256 is not None
        and visuals_sha256 != expected_visuals_sha256
    ):
        raise ValueError(
            "Visual plan changed; review every scene-sound prompt before rebuilding"
        )
    if visuals.get("episode_id") != timeline.get("episode_id"):
        raise ValueError("Visual plan and timeline episode IDs do not match")
    if int(visuals.get("duration_ms", -1)) != int(
        timeline.get("duration_ms", -2)
    ):
        raise ValueError("Visual plan and timeline durations do not match")

    scenes = visuals.get("scenes")
    segments = timeline.get("segments")
    if not isinstance(scenes, list) or not scenes:
        raise ValueError("Visual plan contains no scenes")
    if not isinstance(segments, list) or not segments:
        raise ValueError("Timeline contains no segments")
    segment_by_id = {
        str(segment["segment_id"]): segment
        for segment in segments
        if isinstance(segment, dict) and "segment_id" in segment
    }
    scene_ids = [str(scene["scene_id"]) for scene in scenes]
    missing = [scene_id for scene_id in scene_ids if scene_id not in sound_prompts]
    extra = sorted(set(sound_prompts) - set(scene_ids))
    if missing or extra:
        raise ValueError(
            f"Scene-sound prompt coverage mismatch; missing={missing}, extra={extra}"
        )

    first_scene = scenes[0]
    first_segment_id = str(first_scene["segment_ids"][0])
    first_offset_ms = _scene_anchor_offset(first_scene, segment_by_id)
    cues: list[dict[str, Any]] = [
        {
            "cue_id": "continuous-archive-air",
            "kind": "ambience",
            "coverage_role": "base",
            "anchor": {
                "segment_id": first_segment_id,
                "point": "start",
                "offset_ms": first_offset_ms,
            },
            "duration_ms": min(int(visuals["duration_ms"]), 300000),
            "gain_db": -44,
            "mix_gain_db": 8.0,
            "fade_in_ms": 5000,
            "fade_out_ms": 7000,
            "loop": True,
            "duck_under_dialogue": True,
            "transcript_label": (
                "a nearly subliminal archival room tone continues throughout"
            ),
            "caption_duration_ms": 5000,
            "editorial_note": (
                "A full-episode synthetic safety bed fills every transition and "
                "prevents dead air without claiming a real room or archive."
            ),
            "provenance": {
                "presentation": "illustrative_sound_design",
                "disclosure": "Synthetic continuous ambience; not an archival recording.",
            },
            "source": {
                "type": "generated",
                "prompt": DEFAULT_BASE_PROMPT,
                "generation_duration_ms": 30000,
            },
        }
    ]

    for scene in scenes:
        scene_id = str(scene["scene_id"])
        prompt_spec = sound_prompts[scene_id]
        sound_prompt = _required_string(prompt_spec, "sound_prompt", scene_id)
        if "no voice" not in sound_prompt.casefold() and "no speech" not in sound_prompt.casefold():
            raise ValueError(
                f"{scene_id}.sound_prompt must explicitly exclude voices or speech"
            )
        transcript_label = _required_string(
            prompt_spec, "transcript_label", scene_id
        )
        duration_ms = int(scene["duration_ms"])
        fade_ms = min(2500, max(500, duration_ms // 5))
        segment_id = str(scene["segment_ids"][0])
        cue = {
            "cue_id": f"scene-{scene_id}",
            "kind": str(prompt_spec.get("kind", "ambience")),
            "coverage_role": "section",
            "visual_scene_id": scene_id,
            "anchor": {
                "segment_id": segment_id,
                "point": "start",
                "offset_ms": _scene_anchor_offset(scene, segment_by_id),
            },
            "duration_ms": duration_ms,
            "gain_db": float(prompt_spec.get("gain_db", -30)),
            "mix_gain_db": float(prompt_spec.get("mix_gain_db", 0)),
            "fade_in_ms": fade_ms,
            "fade_out_ms": fade_ms,
            "loop": True,
            "duck_under_dialogue": True,
            "transcript_label": transcript_label,
            "caption_duration_ms": min(5000, duration_ms),
            "editorial_note": (
                "Derived from the matching visual prompt and transcript. The sound "
                "is illustrative, not a historical or location recording."
            ),
            "provenance": {
                "presentation": "illustrative_sound_design",
                "disclosure": (
                    "Synthetic scene ambience derived from the visual plan; not an "
                    "archival or location recording."
                ),
                "visual_scene_id": scene_id,
                "visual_prompt_hash": visual_prompt_hash(scene),
            },
            "source": {
                "type": "generated",
                "prompt": sound_prompt,
                "generation_duration_ms": min(duration_ms, 30000),
                "visual_scene_id": scene_id,
                "visual_prompt_hash": visual_prompt_hash(scene),
            },
        }
        cues.append(cue)

    sound_design = {
        "contract_version": 1,
        "episode_id": str(visuals["episode_id"]),
        "sound_design_disclosure": (
            "All non-speech sounds are synthetic illustrative sound design. None "
            "are recordings of the people, places, objects, or events represented "
            "in the archived stories or generated visual prompts."
        ),
        "editorial_principles": [
            "Every visual scene receives one relevant non-speech sound layer.",
            "A nearly subliminal base bed covers the complete episode and every fade.",
            "Generated sound may evoke evidence but never masquerade as evidence.",
            "No generated cue contains speech, singing, narration, or intelligible words.",
            "Scene sounds begin at their visual boundary and never anticipate narration.",
            "Long cues loop; source generation is capped at the provider's 30-second limit.",
        ],
        "continuous_background": {
            "enabled": True,
            "base_cue_id": "continuous-archive-air",
            "minimum_specific_span_ms": 1000,
            "short_span_policy": "inherit_previous",
        },
        "scene_sound_policy": {
            "source_visuals": visuals_path.name,
            "source_visuals_sha256": visuals_sha256,
            "visual_scene_count": len(scenes),
            "scene_cue_count": len(scenes),
            "timing_source": timeline_path.name,
            "coverage": "one section cue per visual scene plus continuous base",
            "transition": "fade scene cue down to continuous base at each boundary",
        },
        "cues": cues,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(sound_design, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    report = validate_scene_soundscape(output_path, visuals_path, timeline_path)
    if not report["valid"]:
        raise ValueError("Invalid scene soundscape: " + "; ".join(report["errors"]))
    return {"output": str(output_path), **report}


def validate_scene_soundscape(
    sound_design_path: Path,
    visuals_path: Path,
    timeline_path: Path,
) -> dict[str, Any]:
    sound_design = _load_object(sound_design_path)
    visuals = _load_object(visuals_path)
    timeline = _load_object(timeline_path)
    errors: list[str] = []
    scenes = visuals.get("scenes")
    segments = timeline.get("segments")
    if not isinstance(scenes, list):
        scenes = []
        errors.append("Visual plan scenes must be an array")
    if not isinstance(segments, list):
        segments = []
        errors.append("Timeline segments must be an array")
    duration_ms = int(visuals.get("duration_ms", 0))
    if sound_design.get("episode_id") != visuals.get("episode_id"):
        errors.append("Sound design and visual plan episode IDs do not match")
    if timeline.get("episode_id") != visuals.get("episode_id"):
        errors.append("Timeline and visual plan episode IDs do not match")
    if int(timeline.get("duration_ms", -1)) != duration_ms:
        errors.append("Timeline and visual plan durations do not match")

    expected_start_ms = 0
    for scene in scenes:
        start_ms = int(scene.get("start_ms", -1))
        end_ms = int(scene.get("end_ms", -1))
        if start_ms != expected_start_ms:
            errors.append(
                f"{scene.get('scene_id')}: expected start {expected_start_ms}, "
                f"found {start_ms}"
            )
        if end_ms <= start_ms:
            errors.append(f"{scene.get('scene_id')}: invalid scene duration")
        expected_start_ms = end_ms
    if scenes and expected_start_ms != duration_ms:
        errors.append(
            f"Visual scenes end at {expected_start_ms}, expected {duration_ms}"
        )

    cues = sound_design.get("cues")
    if not isinstance(cues, list):
        cues = []
        errors.append("Sound design cues must be an array")
    base_cues = [
        cue for cue in cues if isinstance(cue, dict) and cue.get("coverage_role") == "base"
    ]
    if len(base_cues) != 1:
        errors.append("Sound design must contain exactly one continuous base cue")
    section_cues = [
        cue
        for cue in cues
        if isinstance(cue, dict) and cue.get("coverage_role") == "section"
    ]
    section_by_scene: dict[str, dict[str, Any]] = {}
    for cue in section_cues:
        scene_id = str(cue.get("visual_scene_id", ""))
        if not scene_id:
            errors.append(f"{cue.get('cue_id')}: missing visual_scene_id")
        elif scene_id in section_by_scene:
            errors.append(f"Duplicate scene sound cue for {scene_id}")
        else:
            section_by_scene[scene_id] = cue

    segment_by_id = {
        str(segment["segment_id"]): segment
        for segment in segments
        if isinstance(segment, dict) and "segment_id" in segment
    }
    generation_ms = sum(
        int(cue.get("source", {}).get("generation_duration_ms", 0))
        for cue in base_cues
        if isinstance(cue.get("source"), dict)
    )
    for scene in scenes:
        scene_id = str(scene["scene_id"])
        cue = section_by_scene.get(scene_id)
        if cue is None:
            errors.append(f"Missing scene sound cue for {scene_id}")
            continue
        anchor = cue.get("anchor", {})
        segment = segment_by_id.get(str(anchor.get("segment_id", "")))
        if segment is None:
            errors.append(f"{scene_id}: sound anchor segment is missing")
        else:
            resolved_start = int(segment["start_ms"]) + int(
                anchor.get("offset_ms", 0)
            )
            if resolved_start != int(scene["start_ms"]):
                errors.append(
                    f"{scene_id}: sound starts at {resolved_start}, "
                    f"visual starts at {scene['start_ms']}"
                )
        if int(cue.get("duration_ms", -1)) != int(scene["duration_ms"]):
            errors.append(f"{scene_id}: sound and visual durations do not match")
        source = cue.get("source")
        if not isinstance(source, dict):
            errors.append(f"{scene_id}: missing generated source")
            continue
        expected_hash = visual_prompt_hash(scene)
        if source.get("visual_prompt_hash") != expected_hash:
            errors.append(f"{scene_id}: stale visual prompt hash")
        if source.get("visual_scene_id") != scene_id:
            errors.append(f"{scene_id}: generated source scene ID does not match")
        prompt = str(source.get("prompt", ""))
        if "no voice" not in prompt.casefold() and "no speech" not in prompt.casefold():
            errors.append(f"{scene_id}: generated prompt does not exclude voices")
        expected_generation_ms = min(int(scene["duration_ms"]), 30000)
        if int(source.get("generation_duration_ms", -1)) != expected_generation_ms:
            errors.append(f"{scene_id}: generation duration does not match policy")
        generation_ms += int(source.get("generation_duration_ms", 0))

    expected_scene_ids = {str(scene["scene_id"]) for scene in scenes}
    extra_scene_ids = sorted(set(section_by_scene) - expected_scene_ids)
    if extra_scene_ids:
        errors.append(f"Sound design has unknown visual scenes: {extra_scene_ids}")
    policy = sound_design.get("scene_sound_policy", {})
    if policy.get("source_visuals_sha256") != _file_sha256(visuals_path):
        errors.append("Sound design source visual-plan hash is stale")

    return {
        "valid": not errors,
        "episode_id": visuals.get("episode_id"),
        "visual_scenes": len(scenes),
        "scene_cues": len(section_cues),
        "continuous_base_cues": len(base_cues),
        "coverage_start_ms": 0 if scenes else None,
        "coverage_end_ms": expected_start_ms if scenes else None,
        "coverage_duration_ms": duration_ms,
        "pending_generation_jobs": len(base_cues) + len(section_cues),
        "pending_generation_seconds_ceiling": round(generation_ms / 1000, 3),
        "errors": errors,
    }


def visual_prompt_hash(scene: dict[str, Any]) -> str:
    payload = json.dumps(
        scene.get("prompt", {}),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _scene_anchor_offset(
    scene: dict[str, Any], segment_by_id: dict[str, dict[str, Any]]
) -> int:
    segment_id = str(scene["segment_ids"][0])
    segment = segment_by_id.get(segment_id)
    if segment is None:
        raise ValueError(
            f"{scene.get('scene_id')}: first segment {segment_id!r} is missing"
        )
    offset_ms = int(scene["start_ms"]) - int(segment["start_ms"])
    if not -60000 <= offset_ms <= 60000:
        raise ValueError(
            f"{scene.get('scene_id')}: anchor offset {offset_ms} exceeds contract"
        )
    return offset_ms


def _required_string(value: dict[str, Any], key: str, label: str) -> str:
    result = value.get(key)
    if not isinstance(result, str) or not result.strip():
        raise ValueError(f"{label}.{key} must be a non-empty string")
    return result.strip()


def _load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
