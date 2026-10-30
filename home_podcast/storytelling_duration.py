"""No-network duration gates for self-narrated stories, not podcast episodes.

Text estimates are conservative production preflight, not audio measurements.
Existing sources and recordings are never shortened or deleted by these gates.
"""
from __future__ import annotations

import math
import re
import shutil
import subprocess
import wave
from decimal import Decimal, InvalidOperation, ROUND_CEILING
from pathlib import Path
from typing import Any


PLANNING_WORDS_PER_MINUTE = 140
PERFORMANCE_HEADROOM_MS = 15_000
_WORDS = re.compile(r"\b[\w’'-]+\b", re.UNICODE)


def story_duration_limit_ms(config: Any) -> int | None:
    if getattr(config, "production_mode", None) != "self_narrated_storytelling":
        return None
    minutes = getattr(config, "target_minutes_max", None)
    if minutes is None:
        return None
    value = float(minutes)
    if not math.isfinite(value) or value <= 0:
        raise ValueError("Story maximum duration must be a positive number of minutes")
    return round(value * 60_000)


def story_duration_preflight(config: Any, adaptation: dict[str, Any]) -> dict[str, Any]:
    sections = adaptation.get("sections", [])
    word_count = sum(len(_WORDS.findall(str(section.get("text", "")))) for section in sections)
    pauses = [int(section.get("pause_after_ms", 0)) for section in sections]
    if any(pause < 0 for pause in pauses):
        raise ValueError("Story pauses cannot be negative")
    explicit_pause_ms = sum(pauses)
    estimate_ms = math.ceil(word_count * 60_000 / PLANNING_WORDS_PER_MINUTE) + explicit_pause_ms + PERFORMANCE_HEADROOM_MS
    limit_ms = story_duration_limit_ms(config)
    over_budget = limit_ms is not None and estimate_ms > limit_ms
    return {
        "maximum_duration_ms": limit_ms,
        "spoken_words": word_count,
        "planning_words_per_minute": PLANNING_WORDS_PER_MINUTE,
        "explicit_pause_ms": explicit_pause_ms,
        "performance_headroom_ms": PERFORMANCE_HEADROOM_MS,
        "estimated_duration_ms": estimate_ms,
        "requires_condensation": over_budget,
        "status": "held_for_single_condensed_version" if over_budget else "within_text_budget_pending_audio_measurement",
        "estimate_is_not_measured_audio": True,
        "overflow_policy": "Prepare one condensed, reviewed version; no parts, audio truncation or time compression. Preserve the full source and adaptation; document omissions.",
    }


def require_story_text_budget(config: Any, adaptation: dict[str, Any]) -> dict[str, Any]:
    report = story_duration_preflight(config, adaptation)
    if report["requires_condensation"]:
        raise ValueError(
            f"Story duration budget exceeded: estimated {report['estimated_duration_ms'] / 1000:.1f}s "
            f"including pauses/headroom; maximum {report['maximum_duration_ms'] / 1000:g}s. "
            "Preserve the complete source and prepare one reviewed condensed version before generation."
        )
    return report


def require_story_audio_frames(config: Any, frames: int, sample_rate: int) -> int:
    """Check exact frame duration, including pauses, before replacing a master."""
    if frames <= 0 or sample_rate <= 0:
        raise ValueError("Story audio must have positive frame count and sample rate")
    limit_ms = story_duration_limit_ms(config)
    if limit_ms is not None and frames * 1000 > limit_ms * sample_rate:
        raise ValueError(
            f"Story audio exceeds the {limit_ms / 1000:g}-second limit "
            f"({frames / sample_rate:.3f}s including pauses). "
            "Not accepted or promoted; retain the take and condense the narration. Do not cut off or speed up speech."
        )
    return (frames * 1000 + sample_rate - 1) // sample_rate


def require_story_audio_duration(config: Any, audio_path: Path) -> int | None:
    limit_ms = story_duration_limit_ms(config)
    if limit_ms is None:
        return None
    if audio_path.suffix.lower() == ".wav":
        with wave.open(str(audio_path), "rb") as audio:
            return require_story_audio_frames(config, audio.getnframes(), audio.getframerate())
    # Existing canonical ElevenLabs assets may be MP3. Probe them locally and
    # fail closed if their duration cannot be measured; never trust a sidecar.
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise RuntimeError("ffprobe is required to check non-WAV story audio duration")
    result = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of",
         "default=noprint_wrappers=1:nokey=1", str(audio_path)],
        check=True, capture_output=True, text=True, timeout=30,
    )
    try:
        seconds = Decimal(result.stdout.strip())
    except InvalidOperation as error:
        raise ValueError("Cannot verify story audio duration") from error
    if not seconds.is_finite() or seconds <= 0:
        raise ValueError("Story audio must have a finite positive duration")
    if seconds * 1000 > limit_ms:
        raise ValueError(
            f"Story audio exceeds the {limit_ms / 1000:g}-second limit "
            f"({seconds}s). Not accepted or promoted; retain the take and condense the narration."
        )
    return int((seconds * 1000).to_integral_value(rounding=ROUND_CEILING))
