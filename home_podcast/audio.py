from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import wave
from pathlib import Path
from typing import Any

from .sound_design import resolve_soundscape


def render_episode_audio(
    jobs_path: Path,
    work_dir: Path,
    output_dir: Path,
    *,
    sound_design_path: Path | None = None,
    sfx_jobs_path: Path | None = None,
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
    if any(job.get("episode_id") != episode_id for job in jobs):
        raise ValueError("All TTS jobs must belong to the same episode")
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
                "display_name": job.get("display_name", job["speaker"]),
                "accent": job.get("accent"),
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
    voice_assembly_path = render_dir / "voice-assembly.wav"
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
            "-c:a",
            "pcm_s16le",
            str(voice_assembly_path),
        ]
    )

    sound_cues: list[dict[str, Any]] = []
    soundscape_coverage: dict[str, Any] | None = None
    prepared_cues: list[Path] = []
    sound_design: dict[str, Any] | None = None
    if sound_design_path is not None:
        sound_design = json.loads(sound_design_path.read_text(encoding="utf-8"))
        if sound_design.get("episode_id") != episode_id:
            raise ValueError(
                f"Sound design belongs to {sound_design.get('episode_id')!r}, "
                f"not {episode_id!r}"
            )
        soundscape_coverage = resolve_soundscape(
            sound_design_path,
            timeline_segments,
            sfx_jobs_path,
        )
        sound_cues = soundscape_coverage["cues"]
        overrun = [cue for cue in sound_cues if cue["end_ms"] > cursor_ms]
        if overrun:
            cue = overrun[0]
            raise ValueError(
                f"Sound cue {cue['cue_id']!r} ends after the voice timeline "
                f"({cue['end_ms']} ms > {cursor_ms} ms)"
            )
        prepared_cues = [
            _prepare_sound_cue(ffmpeg, cue, render_dir / "sound-cues")
            for cue in sound_cues
        ]

    voices_master_path = (
        output_dir / f"{episode_id}-voices-only-master.wav"
    ).resolve()
    voices_mp3_path = (output_dir / f"{episode_id}-voices-only.mp3").resolve()
    _normalize_audio(
        ffmpeg,
        voice_assembly_path,
        voices_master_path,
        integrated_loudness=-16,
        true_peak=-1.5,
    )
    _encode_mp3(ffmpeg, voices_master_path, voices_mp3_path)

    master_path = (output_dir / f"{episode_id}-master.wav").resolve()
    mp3_path = (output_dir / f"{episode_id}.mp3").resolve()
    soundscape_master_path: Path | None = None
    soundscape_mp3_path: Path | None = None
    if sound_cues:
        soundscape_master_path = (
            output_dir / f"{episode_id}-soundscape-only-master.wav"
        ).resolve()
        soundscape_mp3_path = (
            output_dir / f"{episode_id}-soundscape-only.mp3"
        ).resolve()
        _mix_sound_cues(
            ffmpeg,
            sound_cues,
            prepared_cues,
            soundscape_master_path,
            cursor_ms,
        )
        _encode_mp3(ffmpeg, soundscape_master_path, soundscape_mp3_path)
        _mix_voice_and_sound_cues(
            ffmpeg,
            voice_assembly_path,
            sound_cues,
            prepared_cues,
            master_path,
            cursor_ms,
        )
    else:
        shutil.copyfile(voices_master_path, master_path)
    _encode_mp3(ffmpeg, master_path, mp3_path)
    tracks: dict[str, Any] = {
        "voices_only": {
            "master_audio": str(voices_master_path),
            "distribution_audio": str(voices_mp3_path),
            "contains": "human_voices_only",
        },
    }
    if soundscape_master_path is not None and soundscape_mp3_path is not None:
        tracks["soundscape_only"] = {
            "master_audio": str(soundscape_master_path),
            "distribution_audio": str(soundscape_mp3_path),
            "contains": "non_human_sound_only",
            "continuous": bool(
                soundscape_coverage and soundscape_coverage.get("continuous")
            ),
        }
        tracks["combined_preview"] = {
            "master_audio": str(master_path),
            "distribution_audio": str(mp3_path),
            "contains": "voices_and_soundscape",
        }
    timeline = {
        "contract_version": 1,
        "episode_id": episode_id,
        "duration_ms": cursor_ms,
        "master_audio": str(master_path),
        "distribution_audio": str(mp3_path),
        "tracks": tracks,
        "segments": timeline_segments,
        "sound_design": (
            {
                "cue_sheet": str(sound_design_path.resolve()),
                "disclosure": sound_design["sound_design_disclosure"],
            }
            if sound_design_path is not None and sound_design is not None
            else None
        ),
        "sound_cues": sound_cues,
        "soundscape_coverage": soundscape_coverage,
    }
    timeline_path = output_dir / f"{episode_id}-timeline.json"
    timeline_path.write_text(
        json.dumps(timeline, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return timeline


def _normalize_audio(
    ffmpeg: str,
    input_path: Path,
    output_path: Path,
    *,
    integrated_loudness: float,
    true_peak: float,
) -> None:
    _run(
        [
            ffmpeg,
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(input_path),
            "-af",
            (
                f"loudnorm=I={integrated_loudness:g}:"
                f"TP={true_peak:g}:LRA=11"
            ),
            "-ar",
            "48000",
            "-ac",
            "2",
            "-c:a",
            "pcm_s16le",
            str(output_path),
        ]
    )


def _encode_mp3(ffmpeg: str, input_path: Path, output_path: Path) -> None:
    _run(
        [
            ffmpeg,
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(input_path),
            "-codec:a",
            "libmp3lame",
            "-b:a",
            "192k",
            str(output_path),
        ]
    )


def _prepare_sound_cue(
    ffmpeg: str,
    cue: dict[str, Any],
    output_dir: Path,
) -> Path:
    asset = Path(cue["asset_audio"])
    stat = asset.stat()
    fingerprint = json.dumps(
        {
            "asset": str(asset.resolve()),
            "asset_size": stat.st_size,
            "asset_mtime_ns": stat.st_mtime_ns,
            "duration_ms": cue["duration_ms"],
            "gain_db": cue["gain_db"],
            "fade_in_ms": cue["fade_in_ms"],
            "fade_out_ms": cue["fade_out_ms"],
            "loop": cue["loop"],
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    cache_key = hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()[:16]
    safe_id = re.sub(r"[^A-Za-z0-9._-]+", "-", cue["cue_id"]).strip("-")
    output = output_dir / f"{safe_id}-{cache_key}.wav"
    if output.exists():
        return output
    output_dir.mkdir(parents=True, exist_ok=True)
    duration_seconds = cue["duration_ms"] / 1000
    filters = [
        "asetpts=PTS-STARTPTS",
        f"volume={cue['gain_db']}dB",
        f"apad=pad_dur={duration_seconds:.3f}",
        f"atrim=0:{duration_seconds:.3f}",
    ]
    fade_in_seconds = cue["fade_in_ms"] / 1000
    if fade_in_seconds:
        filters.append(f"afade=t=in:st=0:d={fade_in_seconds:.3f}")
    fade_out_seconds = cue["fade_out_ms"] / 1000
    if fade_out_seconds:
        fade_start = max(0.0, duration_seconds - fade_out_seconds)
        filters.append(
            f"afade=t=out:st={fade_start:.3f}:d={fade_out_seconds:.3f}"
        )
    command = [ffmpeg, "-y", "-loglevel", "error"]
    if cue["loop"]:
        command.extend(["-stream_loop", "-1"])
    command.extend(
        [
            "-i",
            str(asset),
            "-af",
            ",".join(filters),
            "-ar",
            "48000",
            "-ac",
            "2",
            "-c:a",
            "pcm_s16le",
            str(output),
        ]
    )
    _run(command)
    return output


def _mix_voice_and_sound_cues(
    ffmpeg: str,
    voice_path: Path,
    cues: list[dict[str, Any]],
    cue_paths: list[Path],
    output_path: Path,
    duration_ms: int,
) -> None:
    command = [ffmpeg, "-y", "-loglevel", "error", "-i", str(voice_path)]
    for cue_path in cue_paths:
        command.extend(["-i", str(cue_path)])

    filters: list[str] = []
    has_ducked_cues = any(cue["duck_under_dialogue"] for cue in cues)
    voice_format = (
        "aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo"
    )
    if has_ducked_cues:
        filters.append(f"[0:a]{voice_format},asplit=2[voice][speechkey]")
    else:
        filters.append(f"[0:a]{voice_format}[voice]")
    ducked_labels: list[str] = []
    unducked_labels: list[str] = []
    for index, cue in enumerate(cues, start=1):
        delayed_label = f"cue{index}"
        delay = cue["start_ms"]
        filters.append(
            f"[{index}:a]{voice_format},adelay={delay}|{delay}[{delayed_label}]"
        )
        if cue["duck_under_dialogue"]:
            ducked_labels.append(f"[{delayed_label}]")
        else:
            unducked_labels.append(f"[{delayed_label}]")

    final_inputs = ["[voice]"]
    if ducked_labels:
        duck_bus = _sound_bus(filters, ducked_labels, "duckbus")
        filters.append(
            f"{duck_bus}[speechkey]sidechaincompress="
            "threshold=0.015:ratio=6:attack=20:release=350[ducked]"
        )
        final_inputs.append("[ducked]")
    if unducked_labels:
        final_inputs.append(_sound_bus(filters, unducked_labels, "plainbus"))

    duration_seconds = duration_ms / 1000
    filters.append(
        "".join(final_inputs)
        + f"amix=inputs={len(final_inputs)}:duration=first,"
        + f"atrim=0:{duration_seconds:.3f},"
        + "loudnorm=I=-16:TP=-1.5:LRA=11[mixed]"
    )
    command.extend(
        [
            "-filter_complex",
            ";".join(filters),
            "-map",
            "[mixed]",
            "-ar",
            "48000",
            "-ac",
            "2",
            "-c:a",
            "pcm_s16le",
            str(output_path),
        ]
    )
    _run(command)


def _mix_sound_cues(
    ffmpeg: str,
    cues: list[dict[str, Any]],
    cue_paths: list[Path],
    output_path: Path,
    duration_ms: int,
) -> None:
    if not cues:
        raise ValueError("Cannot render a soundscape-only track without sound cues")
    command = [ffmpeg, "-y", "-loglevel", "error"]
    for cue_path in cue_paths:
        command.extend(["-i", str(cue_path)])

    audio_format = (
        "aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo"
    )
    filters: list[str] = []
    labels: list[str] = []
    for index, cue in enumerate(cues):
        label = f"sound{index}"
        delay = cue["start_ms"]
        filters.append(
            f"[{index}:a]{audio_format},adelay={delay}|{delay}[{label}]"
        )
        labels.append(f"[{label}]")
    sound_bus = _sound_bus(filters, labels, "soundscape")
    duration_seconds = duration_ms / 1000
    filters.append(
        f"{sound_bus}apad=pad_dur={duration_seconds:.3f},"
        f"atrim=0:{duration_seconds:.3f},"
        "loudnorm=I=-23:TP=-2:LRA=11[soundonly]"
    )
    command.extend(
        [
            "-filter_complex",
            ";".join(filters),
            "-map",
            "[soundonly]",
            "-ar",
            "48000",
            "-ac",
            "2",
            "-c:a",
            "pcm_s16le",
            str(output_path),
        ]
    )
    _run(command)


def _sound_bus(filters: list[str], labels: list[str], output_label: str) -> str:
    if len(labels) == 1:
        return labels[0]
    filters.append(
        "".join(labels)
        + f"amix=inputs={len(labels)}:dropout_transition=0[{output_label}]"
    )
    return f"[{output_label}]"


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
