from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def render_transcripts(
    timeline_path: Path,
    show_bible_path: Path,
    output_dir: Path,
) -> dict[str, Path]:
    timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
    show_bible = json.loads(show_bible_path.read_text(encoding="utf-8"))
    display_names = {host["id"]: host["display_name"] for host in show_bible["hosts"]}
    episode_id = timeline["episode_id"]
    output_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = output_dir / f"{episode_id}-transcript.md"
    vtt_path = output_dir / f"{episode_id}.vtt"
    srt_path = output_dir / f"{episode_id}.srt"

    markdown_lines = [
        f"# Transcript: {episode_id}",
        "",
        "_This program is performed by synthetic hosts. Story fragments are readings "
        "of archived source material, not simulations of the original authors._",
        "",
    ]
    vtt_lines = ["WEBVTT", ""]
    srt_lines: list[str] = []
    story_index: dict[str, list[str]] = {}
    for cue_number, segment in enumerate(timeline["segments"], start=1):
        speaker = display_names.get(segment["speaker"], segment["speaker"])
        start = int(segment["start_ms"])
        end = int(segment["end_ms"])
        text = str(segment["text"])
        markdown_lines.extend(
            [
                f"**[{_clock(start)}] {speaker}:** {text}",
                "",
            ]
        )
        vtt_lines.extend(
            [
                f"{_vtt_time(start)} --> {_vtt_time(end)}",
                f"<v {speaker}>{text}",
                "",
            ]
        )
        srt_lines.extend(
            [
                str(cue_number),
                f"{_srt_time(start)} --> {_srt_time(end)}",
                f"{speaker}: {text}",
                "",
            ]
        )
        for story_id in segment.get("source_story_ids", []):
            story_index.setdefault(story_id, []).append(segment["segment_id"])
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
