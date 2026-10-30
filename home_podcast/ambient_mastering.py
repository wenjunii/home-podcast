"""Shared, non-destructive perceived-loudness standard for local ambience.

Two-pass FFmpeg EBU R128 loudness normalization, followed by an independent
measurement and a small-speaker-band check. No model, network, trimming,
stretching, or new sound is involved. Raw generations are never overwritten.
This is independent of speech mastering and the historical podcast mix policy.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time

VERSION = "ambient-lufs-audibility-v1"
PEAK_SAFE_VERSION = "ambient-lufs-audibility-v2-peak-safe"
DEFAULTS = {
    "contract_version": 1, "enabled": True,
    "asset_target_lufs": -24.0, "stem_target_lufs": -30.0, "solo_target_lufs": -23.0,
    "asset_true_peak_dbfs": -3.0, "stem_true_peak_dbfs": -7.0,
    "solo_true_peak_dbfs": -3.0, "highpass_hz": 60.0, "lowpass_hz": 14000.0,
    "loudness_range_lu": 11.0, "level_tolerance_lu": 0.7,
    "maximum_audible_band_loss_lu": 8.0,
}


class AmbientQualityHold(ValueError):
    def __init__(self, receipt):
        self.receipt = receipt
        super().__init__("Ambient held for review: " + ", ".join(receipt["quality_findings"]))


def validate_settings(value):
    if not isinstance(value, dict) or set(value) - set(DEFAULTS):
        raise ValueError("Unknown ambient mastering setting")
    result = {**DEFAULTS, **value}
    if type(result["contract_version"]) is not int or result["contract_version"] != 1:
        raise ValueError("Unsupported ambient mastering contract")
    if type(result["enabled"]) is not bool:
        raise ValueError("Ambient enabled must be boolean")
    for key, number in result.items():
        if key in {"contract_version", "enabled"}:
            continue
        if type(number) not in (int, float) or not math.isfinite(number):
            raise ValueError("Invalid ambient setting: " + key)
        low, high = (-50, -16) if key.endswith("target_lufs") else (-12, -1)
        if key == "highpass_hz": low, high = 20, 150
        elif key == "lowpass_hz": low, high = 8000, 20000
        elif key == "loudness_range_lu": low, high = 3, 20
        elif key == "level_tolerance_lu": low, high = 0.1, 1
        elif key == "maximum_audible_band_loss_lu": low, high = 6, 20
        if not low <= number <= high:
            raise ValueError("Out-of-range ambient setting: " + key)
    return result


def load_settings(root):
    path = Path(root) / "config/ambient_mastering.json"
    return validate_settings(json.loads(path.read_text(encoding="utf-8"))) if path.exists() else {
        **DEFAULTS, "enabled": False,
    }


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def find_ffmpeg(root):
    bundled = Path(root) / "work/storytelling-real-december/tools/ffmpeg-9.0.2/ffmpeg-9.0.2-essentials_build/bin/ffmpeg.exe"
    found = str(bundled) if bundled.is_file() else shutil.which("ffmpeg")
    if not found:
        raise RuntimeError("Ambient mastering needs FFmpeg; no model or download is started")
    return found


def _run(command):
    # Bounded CPU resources also prevent Windows DLL initialization failures
    # when several offline audio checks share this workstation.
    command = [command[0], "-threads", "1", "-filter_threads", "1", *command[1:]]
    result = _spawn(command)
    if result.returncode:
        raise RuntimeError(f"Ambient FFmpeg processing failed ({result.returncode}): " + result.stderr[-1200:])
    return result.stderr


def _environment():
    environment = dict(os.environ)
    # The bundled FFmpeg does not depend on Conda. Avoid its incompatible
    # DLL search entries without changing the user's shell environment.
    environment["PATH"] = os.pathsep.join(
        part for part in environment.get("PATH", "").split(os.pathsep)
        if not re.search(r"anaconda|miniconda", part, re.IGNORECASE))
    return environment


def _spawn(command):
    # On this Windows workstation even ffprobe can intermittently fail before
    # main() with STATUS_DLL_INIT_FAILED. Retry only that empty-output startup
    # failure, never a decoding/filter error or any generation/model call.
    for attempt in range(3):
        result = subprocess.run(command, capture_output=True, text=True, check=False,
                                env=_environment())
        if (result.returncode not in {3221225794, -1073741502} or
                result.stdout or result.stderr or attempt == 2):
            return result
        time.sleep(.15)
    raise AssertionError("Unreachable")


def _measurement(path, ffmpeg, filters="", *, target=-24, ceiling=-3, lra=11):
    # Only input_* values are used; this pass does not write audio.
    log = _run([str(ffmpeg), "-hide_banner", "-nostats", "-i", str(path), "-af",
                filters + f"loudnorm=I={target:g}:TP={ceiling:g}:LRA={lra:g}:print_format=json",
                "-f", "null", "-"])
    matches = re.findall(r"\{[^{}]+\}", log)
    if not matches:
        raise RuntimeError("Missing FFmpeg loudness measurement")
    return json.loads(matches[-1])


def measure_loudness(path, ffmpeg):
    value = _measurement(path, ffmpeg)
    # JSON receipts never contain non-standard NaN/Infinity numbers.
    def finite(key):
        number = float(value[key])
        return number if math.isfinite(number) else None
    return {"integrated_lufs": finite("input_i"), "true_peak_dbfs": finite("input_tp"),
            "loudness_range_lu": finite("input_lra")}


def _geometry(path, ffmpeg):
    probe = Path(ffmpeg).with_name("ffprobe" + Path(ffmpeg).suffix)
    command = [str(probe), "-v", "error", "-select_streams", "a:0", "-show_entries",
               "stream=sample_rate,channels,duration_ts,time_base", "-of", "json", str(path)]
    result = _spawn(command)
    result.check_returncode()
    stream = json.loads(result.stdout)["streams"][0]
    numerator, denominator = map(int, stream["time_base"].split("/"))
    rate = int(stream["sample_rate"])
    return {"sample_rate": rate, "channels": int(stream["channels"]),
            "frames": round(int(stream["duration_ts"]) * numerator / denominator * rate)}


def master_ambient(source, settings, *, root, role="asset", ffmpeg=None, revision=VERSION):
    """Return a hash-bound PCM16 derivative, or hold it without promoting.

    Call this for every new local generation and again for the completed stem.
    role='solo' creates the louder inspection edition, not a production mix.
    """
    settings = validate_settings(settings)
    source = Path(source).resolve()
    if role not in {"asset", "stem", "solo"}:
        raise ValueError("Unknown ambient mastering role")
    if revision not in {VERSION, PEAK_SAFE_VERSION}:
        raise ValueError("Unknown ambient mastering revision")
    if not settings["enabled"]:
        return {"audio_path": str(source), "enabled": False}
    ffmpeg = ffmpeg or find_ffmpeg(root)
    version_result = _spawn([str(ffmpeg), "-version"])
    version_result.check_returncode()
    tool_version = version_result.stdout.splitlines()[0]
    identity = {"version": revision, "settings": settings, "source_sha256": sha(source),
                "role": role, "ffmpeg_version": tool_version}
    key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    directory = source.parent / "ambient-mastered" / key[:20]
    output, receipt_path = directory / "ambient-leveled.wav", directory / "mastering.json"
    if receipt_path.exists():
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        if (receipt.get("cache_key") != key or receipt.get("identity") != identity
                or not output.is_file() or sha(output) != receipt["audio_sha256"]):
            raise ValueError("Ambient mastering cache changed; original preserved")
        if receipt["quality_findings"]:
            raise AmbientQualityHold(receipt)
        return receipt
    if directory.exists():
        raise ValueError("Incomplete ambient master is held; no automatic overwrite")
    geometry = _geometry(source, ffmpeg)
    if geometry["channels"] not in (1, 2) or not geometry["frames"]:
        raise ValueError("Ambient mastering requires nonempty mono or stereo audio")
    directory.mkdir(parents=True)
    target, ceiling = settings[role + "_target_lufs"], settings[role + "_true_peak_dbfs"]
    # Filtering applies once, only to raw assets. Finished stems retain their
    # existing fades, layering and narration-relative ducking.
    lowpass = min(settings["lowpass_hz"], geometry["sample_rate"] * 0.45)
    filters = (f"highpass=f={settings['highpass_hz']:g},lowpass=f={lowpass:g},"
               if role == "asset" else "")
    measured = _measurement(source, ffmpeg, filters, target=target, ceiling=ceiling,
                            lra=settings["loudness_range_lu"])
    if not all(math.isfinite(float(measured[k])) for k in ("input_i", "input_tp", "input_thresh")):
        directory.rmdir()  # empty directory made by this call only
        raise ValueError("Silent or unmeasurable ambience; raw generation preserved")
    normalize = (
        f"loudnorm=I={target:g}:TP={ceiling:g}:LRA={settings['loudness_range_lu']:g}:"
        f"measured_I={measured['input_i']}:measured_TP={measured['input_tp']}:"
        f"measured_LRA={measured['input_lra']}:measured_thresh={measured['input_thresh']}:"
        f"offset={measured['target_offset']}:linear=true:print_format=json")
    # A temporary directory is local to this one content-addressed derivative.
    with tempfile.TemporaryDirectory(dir=directory) as temporary:
        candidate = Path(temporary) / "candidate.wav"
        _run([str(ffmpeg), "-n", "-hide_banner", "-nostats", "-i", str(source), "-af",
              filters + normalize, "-ar", str(geometry["sample_rate"]), "-ac",
              str(geometry["channels"]), "-c:a", "pcm_s16le", str(candidate)])
        # Dynamic fallback may miss the target for highly transient material.
        # Bounded measured corrections use an oversampled, latency-compensated
        # peak limiter when needed. Never silently accept an under-level file.
        metrics = measure_loudness(candidate, ffmpeg)
        for iteration in range(3):
            if metrics["integrated_lufs"] is None:
                break
            correction = target - metrics["integrated_lufs"]
            peak_unsafe = metrics["true_peak_dbfs"] is None or metrics["true_peak_dbfs"] > ceiling + .05
            if abs(correction) <= 0.1 and (revision == VERSION or not peak_unsafe):
                break
            if metrics["true_peak_dbfs"] is None:
                break
            headroom = ceiling - metrics["true_peak_dbfs"] - 0.1
            adjustment = f"volume={correction:g}dB"
            if correction > headroom:
                # The opt-in revision also corrects a peak-only overshoot.
                # Leave increasing reconstruction margin at the final rate;
                # never relax the measured peak or loudness acceptance gates.
                margin = .5 + .2 * iteration if revision == PEAK_SAFE_VERSION else .2
                limit = 10 ** ((ceiling - margin) / 20)
                adjustment = (f"aresample=192000,{adjustment},alimiter=limit={limit:.9f}:"
                              "attack=5:release=100:level=false:latency=true,"
                              f"aresample={geometry['sample_rate']}")
            corrected = Path(temporary) / f"corrected-{iteration}.wav"
            _run([str(ffmpeg), "-n", "-hide_banner", "-nostats", "-i", str(candidate),
                  "-af", adjustment, "-c:a", "pcm_s16le", str(corrected)])
            candidate = corrected
            metrics = measure_loudness(candidate, ffmpeg)
        band_lowpass = min(8000, geometry["sample_rate"] * .45)
        band = _measurement(candidate, ffmpeg, f"highpass=f=150,lowpass=f={band_lowpass:g},")
        band_lufs = float(band["input_i"])
        metrics["audible_band_lufs"] = band_lufs if math.isfinite(band_lufs) else None
        findings = []
        if (metrics["integrated_lufs"] is None or
                abs(metrics["integrated_lufs"] - target) > settings["level_tolerance_lu"]):
            findings.append("loudness_target_not_reached")
        if metrics["true_peak_dbfs"] is None or metrics["true_peak_dbfs"] > ceiling + 0.15:
            findings.append("true_peak_ceiling_exceeded")
        if (not math.isfinite(band_lufs) or metrics["integrated_lufs"] is None or
                metrics["integrated_lufs"] - band_lufs > settings["maximum_audible_band_loss_lu"]):
            findings.append("insufficient_audible_band_energy")
        if _geometry(candidate, ffmpeg) != geometry:
            findings.append("audio_duration_or_channels_changed")
        candidate.replace(output)
    if sha(source) != identity["source_sha256"]:
        raise ValueError("Ambient source changed during mastering")
    receipt = {"cache_key": key, "identity": identity, "audio_path": str(output),
               "audio_sha256": sha(output), **geometry, "metrics": metrics,
               "target_lufs": target, "true_peak_ceiling_dbfs": ceiling,
               "quality_findings": findings, "network_calls": 0, "paid_calls": 0,
               "listening_approval": "pending"}
    receipt_path.write_text(json.dumps(receipt, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    if findings:
        raise AmbientQualityHold(receipt)
    return receipt
