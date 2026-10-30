"""Additional ambient-only small-speaker and loop-material checks.

Integrated LUFS alone cannot detect a nearly sub-bass-only recording. These
checks complement, not replace, level/peak checks and human listening. Only
environmental loop material may lose its generated edge fades; never speech.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
import wave

DEFAULTS = {
    "contract_version": 1, "enabled": True,
    "minimum_midrange_energy_fraction": .05, "midrange_low_hz": 250.0,
    "midrange_high_hz": 8000.0, "maximum_mono_loss_db": 6.0,
    "loop_edge_window_seconds": .5, "maximum_loop_edge_trim_seconds": 12.0,
    "maximum_loop_edge_trim_fraction": .15, "loop_edge_drop_db": 6.0,
    "maximum_loop_dip_db": 6.0,
}


def validate_policy(value):
    if not isinstance(value, dict) or set(value) - set(DEFAULTS):
        raise ValueError("Unknown ambient audibility policy")
    p = {**DEFAULTS, **value}
    if type(p["contract_version"]) is not int or p["contract_version"] != 1 or type(p["enabled"]) is not bool:
        raise ValueError("Invalid ambient audibility contract")
    bounds = {"minimum_midrange_energy_fraction": (.01, .5), "midrange_low_hz": (150, 500),
              "midrange_high_hz": (4000, 10000), "maximum_mono_loss_db": (3, 12),
              "loop_edge_window_seconds": (.1, 2), "maximum_loop_edge_trim_seconds": (0, 20),
              "maximum_loop_edge_trim_fraction": (0, .25), "loop_edge_drop_db": (3, 12),
              "maximum_loop_dip_db": (3, 12)}
    for key, (low, high) in bounds.items():
        if type(p[key]) not in (float, int) or not math.isfinite(p[key]) or not low <= p[key] <= high:
            raise ValueError("Invalid ambient audibility setting: " + key)
    return p


def load_policy(root):
    path = Path(root) / "config/ambient_audibility.json"
    return validate_policy(json.loads(path.read_text(encoding="utf-8"))) if path.exists() else {
        **DEFAULTS, "enabled": False,
    }


def inspect_samples(samples, rate, policy):
    import numpy as np
    from scipy.signal import welch
    p = validate_policy(policy)
    x = np.asarray(samples, dtype="float64")
    if x.ndim != 2 or not len(x) or not np.isfinite(x).all() or rate < 8000:
        raise ValueError("Invalid ambient samples")
    frequencies, power = welch(x, fs=rate, nperseg=min(32768, len(x)), axis=0)
    power = power.mean(axis=1)
    total = float(power.sum())
    selected = (frequencies >= p["midrange_low_hz"]) & (frequencies < p["midrange_high_hz"])
    fraction = float(power[selected].sum()) / max(total, 1e-30)
    stereo_energy = float(np.mean(x * x))
    mono_energy = float(np.mean(x.mean(axis=1) ** 2))
    loss = -10 * math.log10(max(mono_energy, 1e-30) / max(stereo_energy, 1e-30))
    findings = []
    if total < 1e-20 or fraction < p["minimum_midrange_energy_fraction"]:
        findings.append("insufficient_small_speaker_midrange")
    if loss > p["maximum_mono_loss_db"]:
        findings.append("excessive_mono_cancellation")
    return {"midrange_energy_fraction": round(fraction, 6), "mono_loss_db": round(loss, 3),
            "midrange_hz": [p["midrange_low_hz"], p["midrange_high_hz"]], "quality_findings": findings}


def inspect_file(path, policy):
    import numpy as np
    with wave.open(str(path), "rb") as stream:
        if stream.getsampwidth() != 2:
            raise ValueError("Audibility screening expects a finished PCM16 ambient asset")
        rate, channels = stream.getframerate(), stream.getnchannels()
        x = np.frombuffer(stream.readframes(stream.getnframes()), dtype="<i2").astype("float64")
    return inspect_samples(x.reshape(-1, channels) / 32768, rate, policy)


def loop_material(samples, rate, policy):
    """Use the stable environmental body, preserving the source recording.

    Generation often fades out over its last several seconds. Crossfading
    that native fade with another faded start creates a quiet hole. Select
    stable loop endpoints, within strict trimming limits, on derived copies.
    """
    import numpy as np
    p = validate_policy(policy)
    block = max(1, round(rate * p["loop_edge_window_seconds"]))
    full_blocks = len(samples) // block
    if full_blocks < 8:
        return samples, {"source_start_frame": 0, "source_end_frame": len(samples)}
    energy = np.array([np.mean(samples[i * block:(i + 1) * block].astype("float64") ** 2)
                       for i in range(full_blocks)])
    central = energy[full_blocks // 4:3 * full_blocks // 4]
    reference = float(np.median(central))
    threshold = reference * 10 ** (-p["loop_edge_drop_db"] / 10)
    trim = min(round(rate * p["maximum_loop_edge_trim_seconds"]),
               round(len(samples) * p["maximum_loop_edge_trim_fraction"])) // block
    left, right = 0, full_blocks
    while left < trim and energy[left] < threshold:
        left += 1
    while right > full_blocks - trim and energy[right - 1] < threshold:
        right -= 1
    start = left * block
    end = right * block if right < full_blocks else len(samples)
    return samples[start:end].copy(), {"source_start_frame": start, "source_end_frame": end,
                                      "source_frames_preserved": len(samples),
                                      "original_recording_unchanged": True}


def check_loop_floor(samples, rate, policy):
    import numpy as np
    p = validate_policy(policy)
    block = max(1, rate * 3)
    levels = [10 * math.log10(max(float(np.mean(samples[i:i + block].astype("float64") ** 2)), 1e-30))
              for i in range(0, len(samples) - block + 1, max(1, rate // 2))]
    if not levels:
        return {"maximum_three_second_dip_db": 0.0, "quality_findings": []}
    dip = float(np.median(levels) - min(levels))
    return {"maximum_three_second_dip_db": round(dip, 3),
            "quality_findings": ["loop_or_body_level_dip"] if dip > p["maximum_loop_dip_db"] else []}
