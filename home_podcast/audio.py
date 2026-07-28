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
    return _render_assembled_episode(
        episode_id,
        voice_assembly_path,
        timeline_segments,
        cursor_ms,
        render_dir,
        output_dir,
        sound_design_path=sound_design_path,
        sfx_jobs_path=sfx_jobs_path,
    )


def render_dialogue_episode_audio(
    jobs_path: Path,
    work_dir: Path,
    output_dir: Path,
    *,
    sound_design_path: Path | None = None,
    sfx_jobs_path: Path | None = None,
) -> dict[str, Any]:
    jobs = _read_jobs(jobs_path)
    if not jobs:
        raise ValueError("Dialogue jobs file is empty")
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        raise RuntimeError("ffmpeg and ffprobe must be installed and available on PATH")
    missing_audio = [
        job["output_audio"]
        for job in jobs
        if not Path(job["output_audio"]).is_file()
    ]
    if missing_audio:
        raise FileNotFoundError(
            f"{len(missing_audio)} dialogue chunks are missing; "
            f"first missing chunk: {missing_audio[0]}"
        )
    missing_timestamps = [
        job["timestamp_data"]
        for job in jobs
        if not Path(job["timestamp_data"]).is_file()
    ]
    if missing_timestamps:
        raise FileNotFoundError(
            f"{len(missing_timestamps)} dialogue timestamp files are missing; "
            f"first missing file: {missing_timestamps[0]}"
        )

    episode_id = jobs[0]["episode_id"]
    if any(job.get("episode_id") != episode_id for job in jobs):
        raise ValueError("All dialogue jobs must belong to the same episode")
    render_dir = (work_dir / "render" / episode_id).resolve()
    normalized_dir = render_dir / "dialogue-normalized"
    normalized_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    concat_parts: list[Path] = []
    timeline_segments: list[dict[str, Any]] = []
    cursor_ms = 0
    seen_segment_ids: set[str] = set()
    for chunk_number, job in enumerate(jobs, start=1):
        normalized = normalized_dir / f"{chunk_number:03d}-{job['cache_key']}.wav"
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
        chunk_duration_ms = _duration_ms(ffprobe, normalized)
        timing = json.loads(Path(job["timestamp_data"]).read_text(encoding="utf-8"))
        ranges = _dialogue_input_ranges(timing, len(job["inputs"]))
        for input_index, item in enumerate(job["inputs"]):
            segment_id = item["segment_id"]
            if segment_id in seen_segment_ids:
                raise ValueError(f"Duplicate dialogue segment_id {segment_id!r}")
            seen_segment_ids.add(segment_id)
            start_seconds, end_seconds = ranges[input_index]
            start_offset_ms = round(start_seconds * 1000)
            end_offset_ms = round(end_seconds * 1000)
            if end_offset_ms > chunk_duration_ms + 100:
                raise ValueError(
                    f"Dialogue timestamp for {segment_id!r} exceeds its chunk duration"
                )
            timeline_segments.append(
                {
                    "segment_id": segment_id,
                    "speaker": item["speaker"],
                    "display_name": item.get("display_name", item["speaker"]),
                    "accent": item.get("accent"),
                    "text": item["text"],
                    "source_story_ids": item.get("source_story_ids", []),
                    "start_ms": cursor_ms + start_offset_ms,
                    "end_ms": cursor_ms + min(end_offset_ms, chunk_duration_ms),
                    "dialogue_chunk_id": job["chunk_id"],
                }
            )
        concat_parts.append(normalized)
        cursor_ms += chunk_duration_ms

    concat_file = render_dir / "dialogue-concat.txt"
    concat_file.write_text(
        "".join(f"file '{_ffmpeg_path(path)}'\n" for path in concat_parts),
        encoding="utf-8",
    )
    voice_assembly_path = render_dir / "dialogue-voice-assembly.wav"
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
    return _render_assembled_episode(
        episode_id,
        voice_assembly_path,
        timeline_segments,
        cursor_ms,
        render_dir,
        output_dir,
        sound_design_path=sound_design_path,
        sfx_jobs_path=sfx_jobs_path,
    )


def render_soundscape_audio(
    timeline_path: Path,
    sound_design_path: Path,
    work_dir: Path,
    output_dir: Path,
    *,
    sfx_jobs_path: Path | None = None,
    voices_audio_path: Path | None = None,
) -> dict[str, Any]:
    """Render sound design against an existing reviewed episode timeline.

    This path deliberately does not rebuild speech. It is used when the
    reviewed timeline contains finer editorial segments than the provider's
    original dialogue jobs, as visual and scene-sound plans often do.
    """
    timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
    episode_id = timeline.get("episode_id")
    duration_ms = timeline.get("duration_ms")
    timeline_segments = timeline.get("segments")
    if not isinstance(episode_id, str) or not episode_id:
        raise ValueError("Timeline episode_id must be a non-empty string")
    if not isinstance(duration_ms, int) or duration_ms <= 0:
        raise ValueError("Timeline duration_ms must be a positive integer")
    if not isinstance(timeline_segments, list) or not timeline_segments:
        raise ValueError("Timeline segments must be a non-empty array")

    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        raise RuntimeError("ffmpeg and ffprobe must be installed and available on PATH")

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
        episode_duration_ms=duration_ms,
    )
    sound_cues = soundscape_coverage["cues"]
    if not sound_cues:
        raise ValueError("Sound design resolves to no audible cues")
    overrun = [cue for cue in sound_cues if cue["end_ms"] > duration_ms]
    if overrun:
        cue = overrun[0]
        raise ValueError(
            f"Sound cue {cue['cue_id']!r} ends after the reviewed timeline "
            f"({cue['end_ms']} ms > {duration_ms} ms)"
        )

    render_dir = (work_dir / "render" / episode_id).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    prepared_cues = [
        _prepare_sound_cue(ffmpeg, cue, render_dir / "sound-cues")
        for cue in sound_cues
    ]
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
        duration_ms,
    )
    _encode_mp3(ffmpeg, soundscape_master_path, soundscape_mp3_path)

    tracks: dict[str, Any] = {
        "soundscape_only": {
            "master_audio": str(soundscape_master_path),
            "distribution_audio": str(soundscape_mp3_path),
            "contains": "non_human_sound_only",
            "continuous": bool(soundscape_coverage.get("continuous")),
        }
    }
    if voices_audio_path is not None:
        voices_audio_path = voices_audio_path.expanduser().resolve()
        if not voices_audio_path.is_file():
            raise FileNotFoundError(
                f"Reviewed voices-only audio does not exist: {voices_audio_path}"
            )
        voice_duration_ms = _duration_ms(ffprobe, voices_audio_path)
        if abs(voice_duration_ms - duration_ms) > 100:
            raise ValueError(
                "Reviewed voices-only audio duration does not match the timeline "
                f"({voice_duration_ms} ms != {duration_ms} ms)"
            )
        combined_master_path = (
            output_dir / f"{episode_id}-master.wav"
        ).resolve()
        combined_mp3_path = (output_dir / f"{episode_id}.mp3").resolve()
        _mix_voice_and_sound_cues(
            ffmpeg,
            voices_audio_path,
            sound_cues,
            prepared_cues,
            combined_master_path,
            duration_ms,
        )
        _encode_mp3(ffmpeg, combined_master_path, combined_mp3_path)
        tracks["combined_preview"] = {
            "master_audio": str(combined_master_path),
            "distribution_audio": str(combined_mp3_path),
            "contains": "voices_and_soundscape",
            "voices_source": str(voices_audio_path),
        }

    return {
        "contract_version": 1,
        "episode_id": episode_id,
        "duration_ms": duration_ms,
        "timing_source": str(timeline_path.resolve()),
        "sound_design": {
            "cue_sheet": str(sound_design_path.resolve()),
            "disclosure": sound_design["sound_design_disclosure"],
        },
        "sound_cues": sound_cues,
        "soundscape_coverage": soundscape_coverage,
        "tracks": tracks,
    }


def _render_assembled_episode(
    episode_id: str,
    voice_assembly_path: Path,
    timeline_segments: list[dict[str, Any]],
    duration_ms: int,
    render_dir: Path,
    output_dir: Path,
    *,
    sound_design_path: Path | None,
    sfx_jobs_path: Path | None,
) -> dict[str, Any]:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg must be installed and available on PATH")
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
            episode_duration_ms=duration_ms,
        )
        sound_cues = soundscape_coverage["cues"]
        overrun = [cue for cue in sound_cues if cue["end_ms"] > duration_ms]
        if overrun:
            cue = overrun[0]
            raise ValueError(
                f"Sound cue {cue['cue_id']!r} ends after the voice timeline "
                f"({cue['end_ms']} ms > {duration_ms} ms)"
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
            duration_ms,
        )
        _encode_mp3(ffmpeg, soundscape_master_path, soundscape_mp3_path)
        _mix_voice_and_sound_cues(
            ffmpeg,
            voice_assembly_path,
            sound_cues,
            prepared_cues,
            master_path,
            duration_ms,
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
        "duration_ms": duration_ms,
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


def _dialogue_input_ranges(
    timestamp_data: dict[str, Any],
    input_count: int,
) -> dict[int, tuple[float, float]]:
    segments = timestamp_data.get("voice_segments")
    if not isinstance(segments, list) or not segments:
        raise ValueError("Dialogue timestamp data has no voice segments")
    grouped: dict[int, list[tuple[float, float]]] = {}
    previous_start = -1.0
    for position, segment in enumerate(segments, start=1):
        if not isinstance(segment, dict):
            raise ValueError(f"Voice segment {position} must be an object")
        input_index = segment.get("dialogue_input_index")
        start = segment.get("start_time_seconds")
        end = segment.get("end_time_seconds")
        if not isinstance(input_index, int) or not 0 <= input_index < input_count:
            raise ValueError(f"Voice segment {position} has invalid input index")
        if not isinstance(start, (int, float)) or not isinstance(end, (int, float)):
            raise ValueError(f"Voice segment {position} needs numeric timestamps")
        if start < 0 or end <= start:
            raise ValueError(f"Voice segment {position} has an invalid range")
        if start < previous_start:
            raise ValueError("Dialogue voice segments must be ordered")
        previous_start = float(start)
        grouped.setdefault(input_index, []).append((float(start), float(end)))
    missing = sorted(set(range(input_count)) - set(grouped))
    if missing:
        raise ValueError(f"Dialogue timestamps omit input indexes: {missing}")
    return {
        input_index: (
            min(item[0] for item in ranges),
            max(item[1] for item in ranges),
        )
        for input_index, ranges in grouped.items()
    }


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
            "level_mode": "integrated_loudness_target_v1",
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
        f"loudnorm=I={cue['gain_db']}:TP=-2:LRA=11",
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

    duration_seconds = duration_ms / 1000
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
        mix_gain_db = float(cue.get("mix_gain_db", 0))
        filters.append(
            f"[{index}:a]{voice_format},volume={mix_gain_db:g}dB,"
            f"adelay={delay}|{delay},"
            f"apad=whole_dur={duration_seconds:.3f},"
            f"atrim=0:{duration_seconds:.3f}[{delayed_label}]"
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
    duration_seconds = duration_ms / 1000
    for index, cue in enumerate(cues):
        label = f"sound{index}"
        delay = cue["start_ms"]
        mix_gain_db = float(cue.get("mix_gain_db", 0))
        filters.append(
            f"[{index}:a]{audio_format},volume={mix_gain_db:g}dB,"
            f"adelay={delay}|{delay},"
            f"apad=whole_dur={duration_seconds:.3f},"
            f"atrim=0:{duration_seconds:.3f}[{label}]"
        )
        labels.append(f"[{label}]")
    sound_bus = _sound_bus(filters, labels, "soundscape")
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
        + (
            f"amix=inputs={len(labels)}:dropout_transition=0,"
            f"volume={len(labels)}[{output_label}]"
        )
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
