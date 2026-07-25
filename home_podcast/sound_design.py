from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .script import load_json


SOUND_KINDS = {"ident", "ambience", "spot", "transition"}
ANCHOR_POINTS = {"start", "end"}
SOURCE_TYPES = {"generated", "licensed"}
PRESENTATIONS = {"illustrative_sound_design", "licensed_recording"}


def validate_sound_design(
    sound_design_path: Path,
    script_path: Path,
) -> dict[str, Any]:
    sound_design = load_json(sound_design_path)
    script = load_json(script_path)
    errors: list[str] = []
    warnings: list[str] = []

    if sound_design.get("contract_version") != 1:
        errors.append("contract_version must be 1")
    if sound_design.get("episode_id") != script.get("episode_id"):
        errors.append(f"episode_id must be {script.get('episode_id')!r}")
    disclosure = sound_design.get("sound_design_disclosure")
    if not isinstance(disclosure, str) or not disclosure.strip():
        errors.append("sound_design_disclosure must be a non-empty string")

    segment_ids = {
        segment.get("segment_id")
        for segment in script.get("segments", [])
        if isinstance(segment, dict)
    }
    cue_ids: set[str] = set()
    cues = sound_design.get("cues")
    if not isinstance(cues, list):
        errors.append("cues must be an array")
        cues = []
    for index, cue in enumerate(cues, start=1):
        label = f"cue {index}"
        if not isinstance(cue, dict):
            errors.append(f"{label} must be an object")
            continue
        cue_id = cue.get("cue_id")
        if not isinstance(cue_id, str) or not cue_id.strip():
            errors.append(f"{label} has no cue_id")
        elif cue_id in cue_ids:
            errors.append(f"duplicate cue_id {cue_id!r}")
        else:
            cue_ids.add(cue_id)
        if cue.get("kind") not in SOUND_KINDS:
            errors.append(f"{label} has unsupported kind {cue.get('kind')!r}")

        anchor = cue.get("anchor")
        if not isinstance(anchor, dict):
            errors.append(f"{label}.anchor must be an object")
        else:
            if anchor.get("segment_id") not in segment_ids:
                errors.append(
                    f"{label} anchors to unknown segment {anchor.get('segment_id')!r}"
                )
            if anchor.get("point") not in ANCHOR_POINTS:
                errors.append(f"{label}.anchor.point must be 'start' or 'end'")
            offset = anchor.get("offset_ms", 0)
            if not isinstance(offset, int) or not -60000 <= offset <= 60000:
                errors.append(
                    f"{label}.anchor.offset_ms must be an integer from -60000 to 60000"
                )

        duration = cue.get("duration_ms")
        if not isinstance(duration, int) or not 100 <= duration <= 300000:
            errors.append(f"{label}.duration_ms must be an integer from 100 to 300000")
            duration = 0
        gain = cue.get("gain_db")
        if not isinstance(gain, (int, float)) or not -60 <= gain <= 0:
            errors.append(f"{label}.gain_db must be a number from -60 to 0")
        valid_fades: list[int] = []
        for fade_name in ("fade_in_ms", "fade_out_ms"):
            fade = cue.get(fade_name, 0)
            if not isinstance(fade, int) or fade < 0 or fade > 30000:
                errors.append(f"{label}.{fade_name} must be an integer from 0 to 30000")
            else:
                valid_fades.append(fade)
        if isinstance(duration, int) and duration > 0:
            if len(valid_fades) == 2 and sum(valid_fades) > duration:
                errors.append(f"{label} fades cannot be longer than the cue")
        if not isinstance(cue.get("loop"), bool):
            errors.append(f"{label}.loop must be true or false")
        if not isinstance(cue.get("duck_under_dialogue"), bool):
            errors.append(f"{label}.duck_under_dialogue must be true or false")
        transcript_label = cue.get("transcript_label")
        if not isinstance(transcript_label, str) or not transcript_label.strip():
            errors.append(f"{label}.transcript_label must be a non-empty string")

        provenance = cue.get("provenance")
        if not isinstance(provenance, dict):
            errors.append(f"{label}.provenance must be an object")
        elif provenance.get("presentation") not in PRESENTATIONS:
            errors.append(
                f"{label}.provenance.presentation must explicitly identify the cue "
                "as illustrative sound design or a licensed recording"
            )

        source = cue.get("source")
        if not isinstance(source, dict):
            errors.append(f"{label}.source must be an object")
            continue
        source_type = source.get("type")
        if source_type not in SOURCE_TYPES:
            errors.append(f"{label}.source.type must be 'generated' or 'licensed'")
        elif source_type == "generated":
            if (
                isinstance(provenance, dict)
                and provenance.get("presentation") != "illustrative_sound_design"
            ):
                errors.append(
                    f"{label} generated audio must be presented as "
                    "illustrative_sound_design"
                )
            prompt = source.get("prompt")
            if not isinstance(prompt, str) or not prompt.strip():
                errors.append(f"{label}.source.prompt must be a non-empty string")
            generation_duration = source.get(
                "generation_duration_ms",
                min(duration if isinstance(duration, int) else 30000, 30000),
            )
            if (
                not isinstance(generation_duration, int)
                or not 100 <= generation_duration <= 30000
            ):
                errors.append(
                    f"{label}.source.generation_duration_ms must be from 100 to 30000"
                )
        elif source_type == "licensed":
            for field in ("path", "license", "credit"):
                if not isinstance(source.get(field), str) or not source[field].strip():
                    errors.append(f"{label}.source.{field} must be a non-empty string")

        note = str(cue.get("editorial_note", "")).casefold()
        if "actual recording" in note or "archival recording" in note:
            warnings.append(
                f"{label} editorial note may imply that designed audio is historical evidence"
            )

    return {
        "valid": not errors,
        "episode_id": script.get("episode_id"),
        "cues": len(cues),
        "generated_cues": sum(
            1
            for cue in cues
            if isinstance(cue, dict)
            and isinstance(cue.get("source"), dict)
            and cue["source"].get("type") == "generated"
        ),
        "errors": errors,
        "warnings": warnings,
    }


def prepare_sfx_jobs(
    sound_design_path: Path,
    script_path: Path,
    output_path: Path,
    cache_dir: Path,
    *,
    provider: str,
    model: str,
) -> int:
    report = validate_sound_design(sound_design_path, script_path)
    if not report["valid"]:
        raise ValueError("Invalid sound design: " + "; ".join(report["errors"]))
    sound_design = load_json(sound_design_path)
    jobs: list[dict[str, Any]] = []
    for cue in sound_design["cues"]:
        source = cue["source"]
        if source["type"] != "generated":
            continue
        generation_duration_ms = source.get(
            "generation_duration_ms", min(cue["duration_ms"], 30000)
        )
        fingerprint = json.dumps(
            {
                "provider": provider,
                "model": model,
                "prompt": source["prompt"],
                "generation_duration_ms": generation_duration_ms,
                "loop": cue["loop"],
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        cache_key = hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()
        output_audio = (cache_dir / f"{cache_key}.wav").resolve()
        jobs.append(
            {
                "contract_version": 1,
                "episode_id": sound_design["episode_id"],
                "cue_id": cue["cue_id"],
                "provider": provider,
                "model": model,
                "prompt": source["prompt"],
                "generation_duration_ms": generation_duration_ms,
                "loop": cue["loop"],
                "cache_key": cache_key,
                "output_audio": str(output_audio),
                "cached": output_audio.exists(),
            }
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        for job in jobs:
            handle.write(json.dumps(job, ensure_ascii=False) + "\n")
    return len(jobs)


def resolve_sound_cues(
    sound_design_path: Path,
    timeline_segments: list[dict[str, Any]],
    sfx_jobs_path: Path | None = None,
) -> list[dict[str, Any]]:
    sound_design = load_json(sound_design_path)
    segment_by_id = {
        segment["segment_id"]: segment
        for segment in timeline_segments
        if isinstance(segment, dict) and "segment_id" in segment
    }
    generated_assets = _read_generated_assets(sfx_jobs_path)
    resolved: list[dict[str, Any]] = []
    for cue in sound_design.get("cues", []):
        anchor = cue["anchor"]
        segment = segment_by_id.get(anchor["segment_id"])
        if segment is None:
            raise ValueError(
                f"Sound cue {cue['cue_id']!r} anchors to missing timeline segment "
                f"{anchor['segment_id']!r}"
            )
        anchor_ms = segment["start_ms"] if anchor["point"] == "start" else segment["end_ms"]
        start_ms = anchor_ms + int(anchor.get("offset_ms", 0))
        if start_ms < 0:
            raise ValueError(f"Sound cue {cue['cue_id']!r} starts before the episode")
        source = cue["source"]
        if source["type"] == "generated":
            asset_path = generated_assets.get(cue["cue_id"])
            if asset_path is None:
                raise ValueError(
                    f"Generated sound cue {cue['cue_id']!r} has no completed SFX job"
                )
        else:
            candidate = Path(source["path"]).expanduser()
            asset_path = (
                candidate.resolve()
                if candidate.is_absolute()
                else (sound_design_path.parent / candidate).resolve()
            )
        if not asset_path.is_file():
            raise FileNotFoundError(
                f"Sound asset for cue {cue['cue_id']!r} does not exist: {asset_path}"
            )
        resolved.append(
            {
                "cue_id": cue["cue_id"],
                "kind": cue["kind"],
                "start_ms": start_ms,
                "end_ms": start_ms + cue["duration_ms"],
                "duration_ms": cue["duration_ms"],
                "gain_db": cue["gain_db"],
                "fade_in_ms": cue.get("fade_in_ms", 0),
                "fade_out_ms": cue.get("fade_out_ms", 0),
                "loop": cue["loop"],
                "duck_under_dialogue": cue["duck_under_dialogue"],
                "transcript_label": cue["transcript_label"],
                "asset_audio": str(asset_path),
                "source_type": source["type"],
                "provenance": cue["provenance"],
            }
        )
    return sorted(resolved, key=lambda cue: (cue["start_ms"], cue["cue_id"]))


def _read_generated_assets(path: Path | None) -> dict[str, Path]:
    if path is None:
        return {}
    assets: dict[str, Path] = {}
    with path.open(encoding="utf-8-sig") as handle:
        for line in handle:
            if not line.strip():
                continue
            job = json.loads(line)
            cue_id = job.get("cue_id")
            output_audio = job.get("output_audio")
            if isinstance(cue_id, str) and isinstance(output_audio, str):
                if cue_id in assets:
                    raise ValueError(f"Duplicate generated SFX job for cue {cue_id!r}")
                assets[cue_id] = Path(output_audio).expanduser().resolve()
    return assets
