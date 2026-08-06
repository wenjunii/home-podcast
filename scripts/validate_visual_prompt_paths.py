"""Validate interchangeable podcast visual paths and shared-audio alignment."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


LOCKED_ROOT_FIELDS = (
    "episode_id",
    "touchdesigner_version",
    "duration_ms",
    "master_track",
    "audio_file",
    "timing_policy",
    "grounding_policy",
    "captions",
)
LOCKED_SCENE_FIELDS = (
    "scene_id",
    "sequence",
    "start_ms",
    "end_ms",
    "duration_ms",
    "crossfade_in_ms",
    "crossfade_out_ms",
    "segment_ids",
    "source_story_ids",
    "transcript",
    "story_context",
    "grounding",
    "active_source_story_ids",
)


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_paths(
    original_path: Path,
    human_path: Path,
    sound_design_path: Path,
    voices_path: Path,
    soundscape_path: Path,
) -> dict:
    original = _load(original_path)
    human = _load(human_path)
    sound_design = _load(sound_design_path)
    errors: list[str] = []

    for field in LOCKED_ROOT_FIELDS:
        if original.get(field) != human.get(field):
            errors.append(f"root field differs: {field}")

    original_scenes = original.get("scenes", [])
    human_scenes = human.get("scenes", [])
    if len(original_scenes) != len(human_scenes):
        errors.append(
            "scene count differs: "
            f"{len(original_scenes)} original vs {len(human_scenes)} human"
        )

    human_primary = 0
    front_portraits = 0
    deliberate_absence = 0
    token_counts: list[int] = []
    for index, (source, alternative) in enumerate(
        zip(original_scenes, human_scenes, strict=False)
    ):
        scene_id = source.get("scene_id", f"index-{index}")
        for field in LOCKED_SCENE_FIELDS:
            if source.get(field) != alternative.get(field):
                errors.append(f"{scene_id}: locked field differs: {field}")
        if source.get("prompt", {}).get("seed") != alternative.get(
            "prompt", {}
        ).get("seed"):
            errors.append(f"{scene_id}: prompt seed differs")
        path_metadata = alternative.get("human_figure_path", {})
        mode = path_metadata.get("mode")
        if mode == "deliberate_absence":
            deliberate_absence += 1
        elif mode == "front_portrait_identity_safe":
            human_primary += 1
            front_portraits += 1
        else:
            errors.append(f"{scene_id}: invalid human figure mode: {mode!r}")
        chunks = alternative.get("prompt", {}).get("chunks", [])
        if not chunks:
            errors.append(f"{scene_id}: no prompt chunks")
        for chunk in chunks:
            count = int(chunk.get("content_token_count", 0))
            token_counts.append(count)
            if not 1 <= count <= 75:
                errors.append(f"{scene_id}: invalid SDXL token count: {count}")

    section_cues = {
        cue.get("visual_scene_id"): cue
        for cue in sound_design.get("cues", [])
        if cue.get("coverage_role") == "section"
    }
    for scene in original_scenes:
        scene_id = scene.get("scene_id")
        cue = section_cues.get(scene_id)
        if cue is None:
            errors.append(f"{scene_id}: no scene sound cue")
            continue
        if int(cue.get("duration_ms", -1)) != int(scene.get("duration_ms", -2)):
            errors.append(f"{scene_id}: sound cue duration differs")

    if len(section_cues) != len(original_scenes):
        errors.append(
            "scene sound cue count differs: "
            f"{len(section_cues)} cues vs {len(original_scenes)} scenes"
        )
    for audio_path, label in (
        (voices_path, "voices_only"),
        (soundscape_path, "soundscape_only"),
    ):
        if not audio_path.is_file():
            errors.append(f"missing {label} audio: {audio_path}")

    visual_path = human.get("visual_path", {})
    if visual_path.get("id") != "human_figures":
        errors.append("human plan visual_path.id must be human_figures")
    declared_audio = set(visual_path.get("audio_compatibility", []))
    if declared_audio != {"voices_only", "soundscape_only"}:
        errors.append("human plan must declare both shared audio tracks")
    if int(visual_path.get("front_portrait_scene_count", -1)) != front_portraits:
        errors.append("human plan front portrait count is inconsistent")
    if int(visual_path.get("clear_face_scene_count", -1)) != 0:
        errors.append("clear frontal faces require evidence not present in this job")

    report = {
        "episode_id": original.get("episode_id"),
        "original_path": str(original_path.resolve()),
        "human_figure_path": str(human_path.resolve()),
        "scene_count": len(original_scenes),
        "locked_scene_fields": list(LOCKED_SCENE_FIELDS),
        "human_primary_scenes": human_primary,
        "front_portrait_scenes": front_portraits,
        "deliberate_absence_scenes": deliberate_absence,
        "soundscape_scene_cues": len(section_cues),
        "audio_tracks": {
            "voices_only": str(voices_path.resolve()),
            "soundscape_only": str(soundscape_path.resolve()),
        },
        "minimum_content_tokens": min(token_counts) if token_counts else 0,
        "maximum_content_tokens": max(token_counts) if token_counts else 0,
        "errors": errors,
        "valid": not errors,
        "network_calls": 0,
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--original", type=Path, required=True)
    parser.add_argument("--human", type=Path, required=True)
    parser.add_argument("--sound-design", type=Path, required=True)
    parser.add_argument("--voices", type=Path, required=True)
    parser.add_argument("--soundscape", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = validate_paths(
        args.original,
        args.human,
        args.sound_design,
        args.voices,
        args.soundscape,
    )
    output = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(output, encoding="utf-8")
    print(output, end="")
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
