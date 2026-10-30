"""CPU-only, non-destructive speech level matching and slow volume automation.

The target is active-speech RMS, NOT LUFS. No TTS/model, FFmpeg, network, time
stretch, trimming, or fast compressor is involved. Raw takes stay immutable.
NumPy/SciPy are imported only when explicitly processing audio.
"""
from __future__ import annotations

import hashlib
import json
import math
import wave
from pathlib import Path
from typing import Any

VERSION = "speech-leveling-v1"
PEAK_RIDING_VERSION = "speech-leveling-slow-peak-riding-v1"
DEFAULTS = {
    "contract_version": 1,
    "enabled": True,
    "target_speech_rms_dbfs": -22.0,
    "peak_ceiling_dbfs": -1.5,
    "correct_volume_drift": True,
    "analysis_window_seconds": 8.0,
    "smoothing_seconds": 1.5,
    "maximum_gain_change_db_per_second": 1.0,
    "maximum_boost_db": 26.0,
    "maximum_cut_db": 12.0,
    "speech_gate_dbfs": -65.0,
    "level_tolerance_db": 2.0,
    "maximum_end_to_start_difference_db": 3.0,
}


class MasteringQualityHold(ValueError):
    """A preserved finished copy failed the level gate; never a cache error."""

    def __init__(self, receipt):
        self.receipt = receipt
        super().__init__("Mastering held for review: " + ", ".join(
            receipt["metrics"]["quality_findings"]))


def validate_settings(value: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) - set(DEFAULTS):
        raise ValueError("Unknown speech mastering setting")
    result = {**DEFAULTS, **value}
    if type(result["contract_version"]) is not int or result["contract_version"] != 1:
        raise ValueError("Unsupported speech mastering contract")
    for key in ("enabled", "correct_volume_drift"):
        if type(result[key]) is not bool:
            raise ValueError(f"{key} must be boolean")
    bounds = {
        "target_speech_rms_dbfs": (-35, -16), "peak_ceiling_dbfs": (-6, -1),
        "analysis_window_seconds": (4, 30), "smoothing_seconds": (0.5, 5),
        "maximum_gain_change_db_per_second": (0.1, 2),
        "maximum_boost_db": (0, 30), "maximum_cut_db": (0, 24),
        "speech_gate_dbfs": (-80, -45), "level_tolerance_db": (0.5, 4),
        "maximum_end_to_start_difference_db": (1, 6),
    }
    for key, (low, high) in bounds.items():
        number = result[key]
        if (type(number) not in (int, float) or not math.isfinite(number)
                or not low <= number <= high):
            raise ValueError(f"Invalid {key}; expected {low} to {high}")
    return result


def load_settings(project_root: Path) -> dict[str, Any]:
    path = project_root / "config" / "speech_mastering.json"
    # Other/legacy projects without this opt-in file keep their existing behavior.
    return validate_settings(json.loads(path.read_text(encoding="utf-8"))) if path.exists() else {
        **DEFAULTS, "enabled": False,
    }


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _numerics():
    try:
        import numpy as np
        from scipy.ndimage import gaussian_filter1d
        from scipy.signal import resample_poly
    except ImportError as error:
        raise RuntimeError("Speech mastering needs NumPy and SciPy in the audio environment") from error
    return np, gaussian_filter1d, resample_poly


def read_wave(path: Path):
    np, _, _ = _numerics()
    with wave.open(str(path), "rb") as stream:
        rate, frames = stream.getframerate(), stream.getnframes()
        if stream.getnchannels() != 1 or stream.getsampwidth() != 2 or not frames:
            raise ValueError("Speech mastering requires nonempty mono PCM16 WAV")
        if rate < 8000 or frames > rate * 300:
            raise ValueError("Invalid sample rate or story exceeds 300 seconds")
        data = stream.readframes(frames)
    if len(data) != frames * 2:
        raise ValueError("Incomplete WAV payload")
    return np.frombuffer(data, dtype="<i2").astype(np.float64) / 32768.0, rate


def _db(value):
    np, _, _ = _numerics()
    return 20 * np.log10(np.maximum(value, 1e-12))


def _frames(samples, rate):
    np, _, _ = _numerics()
    size = max(1, round(rate * 0.05))
    starts = np.arange(0, len(samples), size)
    counts = np.minimum(size, len(samples) - starts)
    energy = np.add.reduceat(samples * samples, starts) / counts
    return (starts + counts / 2) / rate, energy


def _activity(times, energy, intervals, settings):
    np, _, _ = _numerics()
    active = energy > 10 ** (settings["speech_gate_dbfs"] / 10)
    if intervals is not None:
        supported = np.zeros(len(times), dtype=bool)
        for start, end in intervals:
            if not math.isfinite(start + end) or not 0 <= start < end:
                raise ValueError("Invalid speech interval")
            supported |= (times >= start) & (times <= end)
        active &= supported
    else:
        # Local relative gate prevents long quiet pauses from driving up gain.
        levels = _db(np.sqrt(energy))
        for index, time in enumerate(times):
            nearby = levels[abs(times - time) <= settings["analysis_window_seconds"] / 2]
            active[index] &= levels[index] >= np.percentile(nearby, 80) - 20
    if not active.any():
        raise ValueError("No measurable speech above the silence gate; original preserved")
    return active


def level_samples(samples, rate, settings, intervals=None, *, peak_safe_riding=False):
    """Return PCM16-ready floats and audit metrics; never change sample timing."""
    np, gaussian_filter1d, resample_poly = _numerics()
    settings = validate_settings(settings)
    if not settings["enabled"]:
        raise ValueError("Speech mastering is disabled")
    samples = np.asarray(samples, dtype=np.float64)
    if (samples.ndim != 1 or not len(samples) or not np.isfinite(samples).all()
            or np.max(np.abs(samples)) > 1 or rate < 8000 or len(samples) > 300 * rate):
        raise ValueError("Invalid input samples or runtime")
    times, energy = _frames(samples, rate)
    active = _activity(times, energy, intervals, settings)
    knots = np.arange(0, len(samples) / rate + 0.25, 0.25)
    global_level = float(_db(np.sqrt(np.mean(energy[active]))))
    levels = []
    for time in knots:
        chosen = active & (abs(times - time) <= settings["analysis_window_seconds"] / 2)
        levels.append(float(_db(np.sqrt(np.mean(energy[chosen])))) if chosen.any() else np.nan)
    levels = np.asarray(levels)
    valid = np.isfinite(levels)
    levels = np.interp(knots, knots[valid], levels[valid])
    if not settings["correct_volume_drift"]:
        levels[:] = global_level
    gains = np.clip(settings["target_speech_rms_dbfs"] - levels,
                    -settings["maximum_cut_db"], settings["maximum_boost_db"])
    gains = gaussian_filter1d(gains, settings["smoothing_seconds"] / 0.25, mode="nearest")
    step = settings["maximum_gain_change_db_per_second"] * 0.25
    for index in range(1, len(gains)):
        gains[index] = np.clip(gains[index], gains[index - 1] - step, gains[index - 1] + step)
    for index in range(len(gains) - 2, -1, -1):
        gains[index] = np.clip(gains[index], gains[index + 1] - step, gains[index + 1] + step)
    peak_riding_reduction = 0.0
    if peak_safe_riding:
        # Constrain BOTH endpoints around each oversampled peak, then spread
        # attenuation at the same slow, configured gain-change speed. This is
        # offline volume automation, not clipping or a fast peak limiter.
        before_peak_riding = gains.copy()
        oversampled = resample_poly(samples, 4, 1)
        starts = np.arange(0, len(oversampled), max(1, round(rate * 4 * 0.25)))
        peaks = np.maximum.reduceat(np.abs(oversampled), starts)
        ceilings = settings["peak_ceiling_dbfs"] - _db(peaks) - 0.03
        for index, ceiling in enumerate(ceilings):
            gains[index:min(len(gains), index + 2)] = np.minimum(
                gains[index:min(len(gains), index + 2)], ceiling)
        for index in range(1, len(gains)):
            gains[index] = min(gains[index], gains[index - 1] + step)
        for index in range(len(gains) - 2, -1, -1):
            gains[index] = min(gains[index], gains[index + 1] + step)
        peak_riding_reduction = float(np.max(before_peak_riding - gains))
    envelope = np.interp(np.arange(len(samples)) / rate, knots, gains)
    result = samples * 10 ** (envelope / 20)
    # A single final attenuation protects headroom without flattening transients.
    interpolated_peak = float(np.max(np.abs(resample_poly(result, 4, 1))))
    trim = min(0.0, settings["peak_ceiling_dbfs"] - float(_db(interpolated_peak)) - 0.01)
    result *= 10 ** (trim / 20)
    result = np.rint(result * 32768) / 32768
    if np.max(np.abs(result)) >= 1:
        raise ValueError("Mastering would clip; original preserved")
    _, after_energy = _frames(result, rate)

    def statistics(values):
        rows = []
        for start in np.arange(0, len(samples) / rate, 10):
            chosen = active & (times >= start) & (times < start + 10)
            if chosen.sum() >= 2:
                rows.append({"start_s": float(start), "speech_rms_dbfs": round(
                    float(_db(np.sqrt(np.mean(values[chosen])))), 3)})
        edge = min(20, len(samples) / rate / 3)
        first = active & (times < edge)
        last = active & (times >= len(samples) / rate - edge)
        def mean_db(mask):
            return float(_db(np.sqrt(np.mean(values[mask])))) if mask.any() else None
        first_db, last_db = mean_db(first), mean_db(last)
        return {
            "speech_rms_dbfs": round(mean_db(active), 3),
            "first_speech_rms_dbfs": None if first_db is None else round(first_db, 3),
            "last_speech_rms_dbfs": None if last_db is None else round(last_db, 3),
            "end_minus_start_db": None if first_db is None or last_db is None else round(last_db - first_db, 3),
            "edge_window_seconds": edge, "ten_second_windows": rows,
        }
    before, after = statistics(energy), statistics(after_energy)
    peak_after = float(_db(np.max(np.abs(resample_poly(result, 4, 1)))))
    findings = []
    if abs(after["speech_rms_dbfs"] - settings["target_speech_rms_dbfs"]) > settings["level_tolerance_db"]:
        findings.append("speech_level_outside_target_tolerance")
    drift = after["end_minus_start_db"]
    if drift is not None and abs(drift) > settings["maximum_end_to_start_difference_db"]:
        findings.append("remaining_start_to_end_volume_difference")
    if peak_after > settings["peak_ceiling_dbfs"] + 0.01:
        findings.append("peak_ceiling_exceeded")
    return result, {
        "before": before, "after": after, "quality_findings": findings,
        "gain_min_db": round(float(gains.min() + trim), 3),
        "gain_max_db": round(float(gains.max() + trim), 3),
        "headroom_trim_db": round(trim, 3),
        "four_times_oversampled_peak_dbfs": round(peak_after, 3),
        "sample_peak_dbfs": round(float(_db(np.max(np.abs(result)))), 3),
        "gain_knots": [{"time_s": round(float(t), 3), "gain_db": round(float(g + trim), 5)}
                       for t, g in zip(knots, gains)],
        "activity_basis": "audio_bound_asr_words" if intervals is not None else "local_energy_gate_not_semantic_vad",
        "level_measurement": "unweighted_active_speech_RMS_not_LUFS",
        "same_frames_and_pauses": True, "fast_compression_or_limiting": False,
        "slow_peak_aware_gain": bool(peak_safe_riding),
        "maximum_peak_riding_reduction_db": round(peak_riding_reduction, 3),
    }


def master_speech(source: Path, output_root: Path, settings: dict[str, Any],
                  *, asr_path: Path | None = None,
                  peak_safe_riding: bool = False) -> dict[str, Any]:
    """Create/reuse a content-keyed playback master; reject changed/partial caches."""
    settings = validate_settings(settings)
    source = source.resolve()
    if not settings["enabled"]:
        return {"status": "disabled", "audio_path": str(source), "raw_audio_path": str(source)}
    np, _, _ = _numerics()
    source_hash = sha256(source)
    identity = {"version": PEAK_RIDING_VERSION if peak_safe_riding else VERSION,
                "raw_audio_sha256": source_hash, "settings": settings,
                "asr_sha256": sha256(asr_path) if asr_path else None}
    key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    folder = output_root.resolve() / key[:20]
    output, receipt_path = folder / "voices-leveled.wav", folder / "mastering.json"
    if output == source:
        raise ValueError("Cannot overwrite the raw take")
    if folder.exists():
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        if (receipt.get("identity") != identity or receipt.get("cache_key") != key
                or sha256(output) != receipt.get("audio_sha256")):
            raise ValueError("Changed mastering cache; original preserved, no overwrite")
        if receipt.get("status") == "held":
            raise MasteringQualityHold(receipt)
        if receipt.get("status") != "ready":
            raise ValueError("Invalid mastering cache status; original preserved")
        return receipt
    intervals = None
    if asr_path:
        report = json.loads(asr_path.read_text(encoding="utf-8"))
        if report.get("audio_sha256") != source_hash:
            raise ValueError("ASR report does not match the raw take")
        intervals = [(float(word["start_s"]), float(word["end_s"]))
                     for segment in report["segments"] for word in segment["words"]
                     if word["end_s"] > word["start_s"]]
    samples, rate = read_wave(source)
    if intervals and max(end for _, end in intervals) > len(samples) / rate + 0.1:
        raise ValueError("ASR timing exceeds audio duration")
    leveled, metrics = level_samples(samples, rate, settings, intervals,
                                    peak_safe_riding=peak_safe_riding)
    if sha256(source) != source_hash:
        raise ValueError("Raw take changed during processing")
    folder.mkdir(parents=True, exist_ok=False)
    with output.open("xb") as binary, wave.open(binary, "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(rate)
        stream.writeframes(np.rint(leveled * 32768).astype("<i2").tobytes())
    verified, verified_rate = read_wave(output)
    if len(verified) != len(samples) or verified_rate != rate:
        raise ValueError("Mastering changed timing")
    receipt = {
        "identity": identity, "cache_key": key,
        "status": "held" if metrics["quality_findings"] else "ready",
        "audio_path": str(output), "audio_sha256": sha256(output),
        "raw_audio_path": str(source), "raw_audio_preserved": sha256(source) == source_hash,
        "duration_ms": math.ceil(len(samples) * 1000 / rate),
        "frames": len(samples), "sample_rate": rate, "metrics": metrics,
        "listening_approval": "pending", "network_calls": 0, "paid_calls": 0,
        "tts_calls": 0,
    }
    with receipt_path.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(receipt, indent=2) + "\n")
    if receipt["status"] != "ready":
        raise MasteringQualityHold(receipt)
    return receipt


def master_speech_for_playback(source: Path, output_root: Path, settings: dict[str, Any],
                              *, asr_path: Path | None = None) -> dict[str, Any]:
    """Reuse v1; try one slow peak-aware copy only for peak-induced low level.

    Both copies remain immutable. The same RMS, drift and peak gates apply;
    cache corruption and other holds never trigger this finishing fallback.
    """
    settings = validate_settings(settings)
    try:
        return master_speech(source, output_root, settings, asr_path=asr_path)
    except MasteringQualityHold as error:
        metrics = error.receipt["metrics"]
        if (metrics["quality_findings"] != ["speech_level_outside_target_tolerance"]
                or metrics["headroom_trim_db"] >= 0
                or metrics["after"]["speech_rms_dbfs"] >= settings["target_speech_rms_dbfs"]):
            raise
        return master_speech(source, output_root, settings, asr_path=asr_path,
                             peak_safe_riding=True)
