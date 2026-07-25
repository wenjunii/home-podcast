from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def render_transcripts(
    timeline_path: Path,
    speaker_config_path: Path,
    output_dir: Path,
) -> dict[str, Path]:
    timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
    speaker_config = json.loads(speaker_config_path.read_text(encoding="utf-8"))
    display_names = {
        host["id"]: host.get("display_name", host["id"])
        for host in speaker_config["hosts"]
    }
    episode_id = timeline["episode_id"]
    output_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = output_dir / f"{episode_id}-transcript.md"
    vtt_path = output_dir / f"{episode_id}.vtt"
    srt_path = output_dir / f"{episode_id}.srt"

    markdown_lines = [
        f"# Transcript: {episode_id}",
        "",
    ]
    sound_design = timeline.get("sound_design")
    if isinstance(sound_design, dict) and sound_design.get("disclosure"):
        markdown_lines.extend(
            [
                f"_Sound design note: {sound_design['disclosure']}_",
                "",
            ]
        )
    vtt_lines = ["WEBVTT", ""]
    srt_lines: list[str] = []
    story_index: dict[str, list[str]] = {}

    caption_items: list[dict[str, Any]] = []
    for segment in timeline["segments"]:
        caption_items.append(
            {
                "type": "speech",
                "start_ms": int(segment["start_ms"]),
                "end_ms": int(segment["end_ms"]),
                "segment": segment,
            }
        )
        for story_id in segment.get("source_story_ids", []):
            story_index.setdefault(story_id, []).append(segment["segment_id"])
    for cue in timeline.get("sound_cues", []):
        label = str(cue.get("transcript_label", "")).strip()
        if label:
            caption_end_ms = int(cue["end_ms"])
            caption_duration_ms = cue.get("caption_duration_ms")
            if isinstance(caption_duration_ms, int):
                caption_end_ms = min(
                    caption_end_ms,
                    int(cue["start_ms"]) + caption_duration_ms,
                )
            caption_items.append(
                {
                    "type": "sound",
                    "start_ms": int(cue["start_ms"]),
                    "end_ms": caption_end_ms,
                    "text": f"[{label}]",
                }
            )

    caption_items.sort(
        key=lambda item: (
            item["start_ms"],
            0 if item["type"] == "sound" else 1,
            item["end_ms"],
        )
    )
    for cue_number, item in enumerate(caption_items, start=1):
        start = item["start_ms"]
        end = item["end_ms"]
        if item["type"] == "speech":
            segment = item["segment"]
            speaker = segment.get(
                "display_name",
                display_names.get(segment["speaker"], segment["speaker"]),
            )
            text = str(segment["text"])
            markdown_text = f"**[{_clock(start)}] {speaker}:** {text}"
            vtt_text = f"<v {speaker}>{text}"
            srt_text = f"{speaker}: {text}"
        else:
            text = item["text"]
            markdown_text = f"*[{_clock(start)}] {text}*"
            vtt_text = text
            srt_text = text
        markdown_lines.extend([markdown_text, ""])
        vtt_lines.extend(
            [
                f"{_vtt_time(start)} --> {_vtt_time(end)}",
                vtt_text,
                "",
            ]
        )
        srt_lines.extend(
            [
                str(cue_number),
                f"{_srt_time(start)} --> {_srt_time(end)}",
                srt_text,
                "",
            ]
        )

    markdown_lines.extend(["## Story source map", ""])
    for story_id, segment_ids in sorted(story_index.items()):
        markdown_lines.append(f"- `{story_id}` — segments {', '.join(segment_ids)}")
    markdown_lines.append("")

    markdown_path.write_text("\n".join(markdown_lines), encoding="utf-8")
    vtt_path.write_text("\n".join(vtt_lines), encoding="utf-8")
    srt_path.write_text("\n".join(srt_lines), encoding="utf-8")
    return {"markdown": markdown_path, "vtt": vtt_path, "srt": srt_path}


def _clock(milliseconds: int) -> str:
    total_seconds = milliseconds // 1000
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def _vtt_time(milliseconds: int) -> str:
    seconds, millis = divmod(milliseconds, 1000)
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{millis:03d}"


def _srt_time(milliseconds: int) -> str:
    return _vtt_time(milliseconds).replace(".", ",")
