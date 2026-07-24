from __future__ import annotations

import json
import shutil
import subprocess
import wave
from pathlib import Path
from typing import Any


def render_episode_audio(
    jobs_path: Path,
    work_dir: Path,
    output_dir: Path,
) -> dict[str, Any]:
    jobs = _read_jobs(jobs_path)
    if not jobs:
        raise ValueError("TTS jobs file is empty")
    missing = [job["output_audio"] for job in jobs if not Path(job["output_audio"]).is_file()]
    if missing:
        raise FileNotFoundError(
            f"{len(missing)} synthesized clips are missing; first missing clip: {missing[0]}"
        )
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        raise RuntimeError("ffmpeg and ffprobe must be installed and available on PATH")

    episode_id = jobs[0]["episode_id"]
    render_dir = (work_dir / "render" / episode_id).resolve()
    normalized_dir = render_dir / "normalized"
    normalized_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    concat_parts: list[Path] = []
    timeline_segments: list[dict[str, Any]] = []
    cursor_ms = 0
    for index, job in enumerate(jobs, start=1):
        normalized = normalized_dir / f"{index:05d}-{job['cache_key']}.wav"
        if not normalized.exists():
            _run(
                [
                    ffmpeg,
                    "-y",
                    "-loglevel",
                    "error",
                    "-i",
                    job["output_audio"],
                    "-ar",
                    "48000",
                    "-ac",
                    "2",
                    "-c:a",
                    "pcm_s16le",
                    str(normalized),
                ]
            )
        duration_ms = _duration_ms(ffprobe, normalized)
        timeline_segments.append(
            {
                "segment_id": job["segment_id"],
                "speaker": job["speaker"],
                "text": job["text"],
                "source_story_ids": job.get("source_story_ids", []),
                "start_ms": cursor_ms,
                "end_ms": cursor_ms + duration_ms,
            }
        )
        concat_parts.append(normalized)
        cursor_ms += duration_ms
        pause_ms = int(job.get("pause_after_ms", 0))
        if pause_ms:
            silence = render_dir / f"silence-{pause_ms}ms.wav"
            if not silence.exists():
                _write_silence(silence, pause_ms)
            concat_parts.append(silence)
            cursor_ms += pause_ms

    concat_file = render_dir / "concat.txt"
    concat_file.write_text(
        "".join(f"file '{_ffmpeg_path(path)}'\n" for path in concat_parts),
        encoding="utf-8",
    )
    master_path = (output_dir / f"{episode_id}-master.wav").resolve()
    mp3_path = (output_dir / f"{episode_id}.mp3").resolve()
    _run(
        [
            ffmpeg,
            "-y",
            "-loglevel",
            "error",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_file),
            "-af",
            "loudnorm=I=-16:TP=-1.5:LRA=11",
            "-c:a",
            "pcm_s16le",
            str(master_path),
        ]
    )
    _run(
        [
            ffmpeg,
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(master_path),
            "-codec:a",
            "libmp3lame",
            "-b:a",
            "192k",
            str(mp3_path),
        ]
    )
    timeline = {
        "contract_version": 1,
        "episode_id": episode_id,
        "duration_ms": cursor_ms,
        "master_audio": str(master_path),
        "distribution_audio": str(mp3_path),
        "segments": timeline_segments,
    }
    timeline_path = output_dir / f"{episode_id}-timeline.json"
    timeline_path.write_text(
        json.dumps(timeline, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return timeline


def _read_jobs(path: Path) -> list[dict[str, Any]]:
    jobs = []
    with path.open(encoding="utf-8-sig") as handle:
        for line in handle:
            if line.strip():
                jobs.append(json.loads(line))
    return jobs


def _run(command: list[str]) -> None:
    subprocess.run(command, check=True)


def _duration_ms(ffprobe: str, path: Path) -> int:
    result = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return round(float(result.stdout.strip()) * 1000)


def _write_silence(path: Path, duration_ms: int) -> None:
    frame_rate = 48000
    frame_count = round(frame_rate * duration_ms / 1000)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as output:
        output.setnchannels(2)
        output.setsampwidth(2)
        output.setframerate(frame_rate)
        output.writeframes(b"\x00\x00\x00\x00" * frame_count)


def _ffmpeg_path(path: Path) -> str:
    return str(path.resolve()).replace("\\", "/").replace("'", "'\\''")
