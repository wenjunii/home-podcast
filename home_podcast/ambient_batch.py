"""Evidence-bound, resumable offline ambient batches for approved narrations.

Planning and dry-run never load media models. Only the isolated CUDA worker
generates; CPU finishing preserves raw takes and approved voices. No API keys,
network generation, automatic retries, source rewriting or TouchDesigner edits.
"""
from __future__ import annotations

import html
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone

from .ambient_mastering import (AmbientQualityHold, find_ffmpeg, load_settings,
                                master_ambient, measure_loudness, sha, VERSION, PEAK_SAFE_VERSION)
from .ambient_audibility import (check_loop_floor, inspect_file, inspect_samples,
                                load_policy, loop_material)
from .providers.ambient_gpu import BACKEND, MODEL_REVISION, SOURCE_REVISION
from .single_take_audio import effective_asr_path, hardware_guard, normalized_words, read, write_json
from .storytelling_quality import content_digest, require_personal_story


def anchor_ms(value, words, duration_ms):
    if value == "story_start":
        return 0
    if value == "story_end":
        return duration_ms
    if not isinstance(value, dict) or value.get("edge") not in {"start", "end"}:
        raise ValueError("Invalid timed speech anchor")
    needle = normalized_words(value.get("phrase", ""))
    flat = [(token, w) for w in words for token in normalized_words(w["word"])]
    matches = [i for i in range(len(flat) - len(needle) + 1)
               if needle and [v[0] for v in flat[i:i + len(needle)]] == needle]
    if not matches or (len(matches) != 1 and "occurrence" not in value):
        raise ValueError("Speech anchor missing or ambiguous: " + value.get("phrase", ""))
    occurrence = value.get("occurrence", 1)
    if type(occurrence) is not int or not 1 <= occurrence <= len(matches):
        raise ValueError("Invalid anchor occurrence")
    index = matches[occurrence - 1] + (len(needle) - 1 if value["edge"] == "end" else 0)
    return round(flat[index][1][value["edge"] + "_s"] * 1000)


def fit_ambient(samples, frames, crossfade_frames, *, audibility_policy=None, sample_rate=44100):
    """Crossfade-loop an environmental asset; never stretch or alter speech."""
    import numpy as np
    if frames <= 0 or len(samples) < 2:
        raise ValueError("Invalid environmental loop")
    if len(samples) >= frames:
        return samples[:frames].copy()
    if audibility_policy and audibility_policy["enabled"]:
        samples, _ = loop_material(samples, sample_rate, audibility_policy)
    overlap = max(1, min(crossfade_frames, len(samples) // 4))
    out = np.zeros((frames, samples.shape[1]), dtype=samples.dtype)
    out[:len(samples)] = samples
    end = len(samples)
    while end < frames:
        start = end - overlap
        length = min(len(samples), frames - start)
        fade = np.sin(np.linspace(0, math.pi / 2, overlap)) ** 2
        out[start:end] = out[start:end] * (1 - fade[:, None]) + samples[:overlap] * fade[:, None]
        out[end:start + length] = samples[overlap:length]
        end = start + length
    if audibility_policy and audibility_policy["enabled"]:
        checked = check_loop_floor(out, sample_rate, audibility_policy)
        if checked["quality_findings"]:
            raise ValueError("Environmental loop has a quiet join or unstable body; hold for review")
    return out


class AmbientBatch:
    def __init__(self, config, brief_path):
        self.config, self.root = config, config.project_root.resolve()
        self.brief_path = self.inside(brief_path)
        self.brief = read(self.brief_path)
        run_id = self.brief.get("run_id", "")
        if not re.fullmatch(r"ambient-[a-z0-9][a-z0-9-]{3,90}", run_id):
            raise ValueError("Unsafe ambient run_id")
        self.work = self.inside(config.work_dir / "local-audio" / run_id)
        self.out = self.inside(config.audio_dir / run_id)
        self.plan_path = self.work / "plan.json"
        self.runtime = self.inside(config.work_dir / "ambient-runtime")

    def inside(self, path):
        path = Path(path)
        path = (path if path.is_absolute() else self.root / path).resolve()
        if not path.is_relative_to(self.root) or path == self.root:
            raise ValueError("Batch path must remain inside this project")
        return path

    def relative(self, path):
        return self.inside(path).relative_to(self.root).as_posix()

    def prepare(self):
        if self.plan_path.exists():
            p = self.load()
            return self.dry_run(p)
        b = self.brief
        if b.get("contract_version") != 1 or not 1 <= len(b.get("stories", [])) <= 50:
            raise ValueError("Invalid ambient batch brief")
        if b.get("steps") != 8 or not 1 <= b.get("cfg", 0) <= 3 or not b.get("negative_prompt"):
            raise ValueError("Use the tested bounded GPU generation settings")
        mix = b["mix"]
        if set(mix) != {"speech_duck_db", "fade_in_seconds", "fade_out_seconds", "cue_crossfade_seconds"}:
            raise ValueError("Unknown ambient mix setting")
        if any(type(v) not in (float, int) or not math.isfinite(v) or not 0 <= v <= 15 for v in mix.values()):
            raise ValueError("Invalid ambient mix value")
        settings = load_settings(self.root)
        solo_revision = b.get("solo_mastering_revision", PEAK_SAFE_VERSION)
        if solo_revision not in {VERSION, PEAK_SAFE_VERSION}:
            raise ValueError("Unknown solo ambient mastering revision")
        if not settings["enabled"]:
            raise ValueError("Enable the reviewed shared ambient level standard first")
        protected = {}
        def protect(path):
            protected[self.relative(path)] = sha(self.inside(path))
        for path in (list(self.root.glob("*.toe")) + list((self.root / "touchdesigner").rglob("*.py"))
                     + list((self.root / "config").glob("*.json")) + [self.brief_path]):
            protect(path)
        manifest_path = self.inside(b["speech_manifest"])
        approval_path = self.inside(b["speech_approval"])
        manifest, approval = read(manifest_path), read(approval_path)
        if approval["manifest_sha256"] != sha(manifest_path):
            raise ValueError("Speech approval is stale")
        protect(manifest_path)
        protect(approval_path)
        speech = {s["narration_id"]: s for s in manifest["stories"]}
        approvals = {s["narration_id"]: s for s in approval["stories"]}
        stories, assets, seen = [], {}, set()
        for design in b["stories"]:
            sid = design["narration_id"]
            if not re.fullmatch(r"\d{4}-\d{2}--story-[0-9a-f]{24}(?:--[a-z0-9-]+)?", sid) or sid in seen:
                raise ValueError("Unsafe or duplicate story ID")
            seen.add(sid)
            directory = self.config.episodes_dir / sid
            review = require_personal_story(directory)
            adaptation, source = read(directory / "adaptation.json"), read(directory / "source-job.json")
            approved, item = approvals[sid], speech[sid]
            if approved["listening_approval"] != "approved_by_user":
                raise ValueError("Use only listening-approved narration audio")
            for key, value in (("adaptation_sha256", adaptation), ("source_job_sha256", source),
                               ("editorial_review_sha256", review)):
                if approved[key] != content_digest(value):
                    raise ValueError("Current story differs from approved narration")
            voice, raw = self.inside(item["listening_audio_path"]), self.inside(item["audio_path"])
            if (sha(voice) != item["listening_audio_sha256"] or sha(raw) != item["audio_sha256"]
                    or not 0 < item["duration_ms"] <= 300000):
                raise ValueError("Approved voice changed or exceeds five minutes")
            transcript = "\n\n".join(s["text"] for s in adaptation["sections"])
            asr_path = effective_asr_path(raw.parent, {"text": transcript,
                                                      "cache_key": read(raw.parent / "generation.json")["cache_key"]})
            for path in ([directory / n for n in ("adaptation.json", "source-job.json", "personal-story-review.json")]
                         + [voice, raw, voice.parent / "mastering.json", raw.parent / "generation.json", asr_path]):
                protect(path)
            words = [w for s in read(asr_path)["segments"] for w in s["words"]]
            cues, skipped = [], []
            for cue in design["cues"]:
                if (not re.fullmatch(r"[a-z0-9-]{2,60}", cue["cue_id"]) or
                        cue["role"] not in {"base", "specific"} or not cue.get("interpretation")
                        or not cue.get("source_evidence") or cue["source_evidence"] not in source["story_text"]):
                    raise ValueError("Cue lacks current exact source evidence")
                start = anchor_ms(cue["start"], words, item["duration_ms"])
                end = anchor_ms(cue["end"], words, item["duration_ms"])
                for anchor in (cue["start"], cue["end"]):
                    if isinstance(anchor, dict) and not _contains_words(transcript, anchor["phrase"]):
                        raise ValueError("Sound anchor is absent from the reviewed narration")
                if not 0 <= start < end <= item["duration_ms"]:
                    raise ValueError("Cue exceeds narration timing")
                if cue["role"] == "base" and (start != 0 or end != item["duration_ms"]):
                    raise ValueError("One base must cover the complete story")
                if cue["role"] == "specific" and end - start < 15000:
                    skipped.append({**cue, "start_ms": start, "end_ms": end,
                                    "reason": "under_15_seconds_inherit_background"})
                    continue
                seed = cue["seed"]
                if type(seed) is not int or not 0 <= seed < 2**32:
                    raise ValueError("Invalid independent ambient seed")
                asset_duration = cue.get("asset_duration_ms", min(120000, end - start))
                # A continuous, non-event base may reuse the beginning of a
                # longer cached texture. Keep specific-event sources bounded
                # by their evidence-timed span, and never extend the output.
                source_limit = 120000 if cue["role"] == "base" else min(120000, end - start)
                if type(asset_duration) is not int or not 1000 <= asset_duration <= source_limit:
                    raise ValueError("Invalid bounded ambient source duration")
                payload = {"backend": BACKEND, "model_revision": MODEL_REVISION, "source_revision": SOURCE_REVISION,
                           "prompt": cue["prompt"], "negative_prompt": b["negative_prompt"],
                           "generation_duration_ms": asset_duration, "seed": seed,
                           "cfg": b["cfg"], "steps": b["steps"]}
                key = content_digest(payload)
                asset = {**payload, "cache_key": key, "output_audio": self.relative(
                    self.config.audio_dir / "cache/stable-audio-3-cuda" / (key + ".wav"))}
                assets[key] = asset
                cues.append({**cue, "start_ms": start, "end_ms": end, "asset_key": key})
            if len({c["cue_id"] for c in cues}) != len(cues) or sum(c["role"] == "base" for c in cues) != 1:
                raise ValueError("Duplicate cue ID or missing single continuous base")
            captions = {}
            for suffix in ("srt", "vtt"):
                path = raw.parent / ("captions." + suffix)
                if path.is_file():
                    protect(path)
                    captions[suffix] = self.relative(path)
            stories.append({"narration_id": sid, "title": adaptation["title"], "duration_ms": item["duration_ms"],
                            "voice_path": self.relative(voice), "voice_sha256": sha(voice),
                            "transcript": transcript, "captions": captions, "cues": cues, "skipped_cues": skipped,
                            "direction": design["direction"], "location_note": design["location_note"],
                            "reviewed_locations": review["reviewed_analysis"]["locations"]})
        p = {"contract_version": 1, "run_id": b["run_id"], "stories": stories, "assets": list(assets.values()),
             "audibility_policy": load_policy(self.root),
             "solo_mastering_revision": solo_revision,
             "settings": settings, "mix": mix, "protected_sha256": protected}
        p["plan_digest"] = content_digest(p)
        write_json(self.plan_path, p, exclusive=True)
        return self.dry_run(p)

    def load(self):
        p = read(self.plan_path)
        self.validate(p)
        return p

    def validate(self, p):
        if p["run_id"] != self.brief["run_id"] or content_digest({k: v for k, v in p.items() if k != "plan_digest"}) != p["plan_digest"]:
            raise ValueError("Frozen ambient plan changed")
        for path, checksum in p["protected_sha256"].items():
            if sha(self.inside(path)) != checksum:
                raise ValueError("Protected input changed: " + path)
        for a in p["assets"]:
            if content_digest({k: v for k, v in a.items() if k not in {"cache_key", "output_audio"}}) != a["cache_key"]:
                raise ValueError("Ambient cache identity changed")
            if self.inside(a["output_audio"]).parent != (self.config.audio_dir / "cache/stable-audio-3-cuda").resolve():
                raise ValueError("Unsafe ambient cache output")
        for s in p["stories"]:
            require_personal_story(self.config.episodes_dir / s["narration_id"])

    def cached(self, asset):
        path = self.inside(asset["output_audio"])
        receipt_path = path.with_suffix(".generation.json")
        if not path.exists() or not receipt_path.exists():
            return False
        receipt = read(receipt_path)
        execution = self.inside(receipt["execution_receipt"])
        return (receipt.get("cache_key") == asset["cache_key"] and receipt.get("audio_sha256") == sha(path)
                and receipt.get("frames") == round(asset["generation_duration_ms"] * 44.1)
                and receipt.get("sample_rate") == 44100 and receipt.get("channels") == 2
                and execution.is_file() and read(execution).get("verified_cuda_matrix_operations", 0) > 0)

    def dry_run(self, p=None):
        p = p or self.load()
        self.validate(p)
        pending, blocked = [], []
        for a in p["assets"]:
            if self.cached(a):
                continue
            path = self.inside(a["output_audio"])
            (blocked if path.exists() or path.with_suffix(".attempt.json").exists() else pending).append(a)
        return {"run_id": p["run_id"], "stories": len(p["stories"]), "assets": len(p["assets"]),
                "cached_assets": len(p["assets"]) - len(pending) - len(blocked),
                "pending_local_generation_calls": len(pending), "blocked_prior_attempts": len(blocked),
                "pending_generation_seconds": sum(a["generation_duration_ms"] for a in pending) / 1000,
                "soundscape_duration_ms": sum(s["duration_ms"] for s in p["stories"]),
                "skipped_short_cues": sum(len(s["skipped_cues"]) for s in p["stories"]),
                "models_loaded": 0, "network_calls": 0, "paid_calls": 0}

    def render(self, *, execute=False, max_calls=None, worker=False, engine_factory=None):
        p = self.load()
        report = self.dry_run(p)
        if not execute:
            return report
        if report["blocked_prior_attempts"]:
            raise ValueError("Prior ambient attempt held; no automatic retry or overwrite")
        if not report["pending_local_generation_calls"]:
            return report
        if type(max_calls) is not int or max_calls != report["pending_local_generation_calls"]:
            raise ValueError("Use the exact pending local generation ceiling from dry-run")
        if not worker:
            python = self.runtime / "venv/Scripts/python.exe"
            if not python.is_file():
                raise ValueError("The isolated GPU runtime is not installed; no automatic download")
            subprocess.run([str(python), "-m", "scripts.run_ambient_batch_gpu", "--config",
                            str(self.config.config_path), "--brief", str(self.brief_path),
                            "--max-calls", str(max_calls)], cwd=self.root, check=True)
            return read(self.work / "render-report.json")
        from .providers.ambient_gpu import StableAudio3CUDARenderer, verify_runtime
        hardware = hardware_guard()
        runtime = verify_runtime(self.runtime)
        import numpy as np
        import soundfile as sf
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
        execution_path = self.work / ("gpu-execution-" + stamp + ".json")
        engine = (engine_factory or StableAudio3CUDARenderer)(
            project_root=self.root, runtime=self.runtime, profile_prefix=self.work / ("gpu-profile-" + stamp))
        completed = []
        try:
            for asset in p["assets"]:
                if self.cached(asset):
                    continue
                self.validate(p)
                path = self.inside(asset["output_audio"])
                path.parent.mkdir(parents=True, exist_ok=True)
                attempt = path.with_suffix(".attempt.json")
                write_json(attempt, {"cache_key": asset["cache_key"], "status": "generating"}, exclusive=True)
                print(f"Ambient {len(completed) + 1}/{max_calls}: {asset['cache_key'][:12]}", flush=True)
                audio, metrics = engine.generate(prompt=asset["prompt"], negative_prompt=asset["negative_prompt"],
                                                  seconds=asset["generation_duration_ms"] / 1000,
                                                  seed=asset["seed"], cfg=asset["cfg"], steps=asset["steps"])
                if audio.shape != (round(asset["generation_duration_ms"] * 44.1), 2) or not np.isfinite(audio).all():
                    raise ValueError("Invalid raw ambient audio geometry")
                with path.open("xb") as stream:
                    sf.write(stream, audio, 44100, format="WAV", subtype="FLOAT")
                receipt = {**metrics, "cache_key": asset["cache_key"], "audio_sha256": sha(path),
                           "frames": len(audio), "sample_rate": 44100, "channels": 2,
                           "execution_receipt": self.relative(execution_path), "hardware": hardware,
                           "runtime": runtime, "status": "generated_awaiting_quality_and_listening"}
                write_json(path.with_suffix(".generation.json"), receipt, exclusive=True)
                write_json(attempt, {"cache_key": asset["cache_key"], "status": "completed"})
                completed.append(receipt)
        finally:
            write_json(execution_path, engine.close(), exclusive=True)
        self.validate(p)
        report = {**self.dry_run(p), "generated": len(completed), "models_loaded": 1,
                  "render_seconds_after_loading": round(sum(r["wall_seconds"] for r in completed), 3),
                  "execution_receipt": self.relative(execution_path)}
        write_json(self.work / "render-report.json", report)
        return report

    def quality(self):
        p = self.load()
        results, held = [], []
        policy = p.get("audibility_policy", {"enabled": False})
        base_keys = {c["asset_key"] for s in p["stories"] for c in s["cues"] if c["role"] == "base"}
        for a in p["assets"]:
            if not self.cached(a):
                raise ValueError("Ambient batch is not completely generated")
            try:
                receipt = master_ambient(self.inside(a["output_audio"]), p["settings"], root=self.root)
                accepted = {"asset_key": a["cache_key"], "mastering": receipt}
                if policy["enabled"] and a["cache_key"] in base_keys:
                    audibility = inspect_file(receipt["audio_path"], policy)
                    if audibility["quality_findings"]:
                        held.append({"asset_key": a["cache_key"], "findings": audibility["quality_findings"],
                                     "audibility": audibility})
                        continue
                    accepted["audibility"] = audibility
                results.append(accepted)
                print("Ambient level checked: " + a["cache_key"][:12], flush=True)
            except AmbientQualityHold as error:
                held.append({"asset_key": a["cache_key"], "findings": error.receipt["quality_findings"]})
        result = {"plan_digest": p["plan_digest"], "accepted_assets": len(results),
                  "held_assets": held, "assets": results, "network_calls": 0, "paid_calls": 0}
        write_json(self.work / "quality.json", result)
        return result

    def audit(self):
        p = self.load()
        quality = read(self.work / "quality.json")
        if quality["plan_digest"] != p["plan_digest"] or quality["held_assets"]:
            raise ValueError("Resolve ambient quality holds before speech screening")
        wanted = {a["asset_key"]: a["mastering"] for a in quality["assets"]}
        destination = self.work / "speech-diagnostic.json"
        if destination.exists():
            previous = read(destination)
            if (previous["plan_digest"] == p["plan_digest"] and
                    {a["asset_key"]: a["audio_sha256"] for a in previous["assets"]} ==
                    {k: sha(Path(v["audio_path"])) for k, v in wanted.items()}):
                return previous
            raise ValueError("Ambient speech diagnostic stale; do not overwrite")
        os.environ["HF_HUB_OFFLINE"] = os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
        sys.path.insert(0, str(self.config.work_dir / "local-audio/asr-runtime"))
        from faster_whisper import WhisperModel
        cached = Path.home() / ".cache/huggingface/hub/models--Systran--faster-whisper-small/snapshots"
        models = [d for d in cached.iterdir() if (d / "model.bin").is_file()]
        if len(models) != 1:
            raise ValueError("Expected one already cached ASR model; no download")
        model = WhisperModel(str(models[0]), device="cpu", compute_type="int8", cpu_threads=4, local_files_only=True)
        assets = []
        for key, receipt in wanted.items():
            path = Path(receipt["audio_path"])
            segments, info = model.transcribe(str(path), language="en", beam_size=5, vad_filter=True,
                                              condition_on_previous_text=False)
            rows = [{"start_s": s.start, "end_s": s.end, "text": s.text.strip()} for s in segments]
            assets.append({"asset_key": key, "audio_sha256": sha(path), "recognized_segments": rows,
                           "vad_speech_seconds": round(info.duration_after_vad, 3)})
            print(f"Speech screen {key[:12]}: {len(rows)} possible segments", flush=True)
        result = {"plan_digest": p["plan_digest"], "assets": assets, "device": "cpu",
                  "recognized_segments": sum(len(a["recognized_segments"]) for a in assets),
                  "caution": "Automated screening is not proof of no vocals/music and does not replace listening.",
                  "network_calls": 0, "paid_calls": 0}
        write_json(destination, result, exclusive=True)
        return result

    def package(self):
        import numpy as np
        import soundfile as sf
        from scipy.ndimage import gaussian_filter1d
        from scipy.signal import resample_poly
        p = self.load()
        q = read(self.work / "quality.json")
        if q["plan_digest"] != p["plan_digest"] or q["held_assets"]:
            raise ValueError("Resolve held ambient assets before assembly")
        speech = read(self.work / "speech-diagnostic.json")
        if speech["plan_digest"] != p["plan_digest"] or speech["recognized_segments"]:
            raise ValueError("Possible ambient speech requires review before assembly")
        masters = {r["asset_key"]: r["mastering"] for r in q["assets"]}
        assets = {r["cache_key"]: r for r in p["assets"]}
        if set(masters) != set(assets):
            raise ValueError("Incomplete ambient level receipts")
        summaries, rate = [], 44100
        for s in p["stories"]:
            directory = self.out / s["narration_id"]
            directory.mkdir(parents=True, exist_ok=True)
            count = round(s["duration_ms"] * 44.1)
            stem = np.zeros((count, 2), np.float32)
            for cue in s["cues"]:
                a = assets[cue["asset_key"]]
                receipt = master_ambient(self.inside(a["output_audio"]), p["settings"], root=self.root)
                if receipt != masters[cue["asset_key"]]:
                    raise ValueError("Ambient level receipt stale")
                clip, sr = sf.read(receipt["audio_path"], dtype="float32", always_2d=True)
                frames = round(cue["end_ms"] * 44.1) - round(cue["start_ms"] * 44.1)
                if sr != rate:
                    raise ValueError("Ambient sample rate changed")
                clip = fit_ambient(clip, frames, round(p["mix"]["cue_crossfade_seconds"] * rate),
                                   audibility_policy=p.get("audibility_policy"), sample_rate=rate)
                envelope = np.ones(frames, np.float32)
                if cue["role"] == "base":
                    envelope *= 10 ** ((-6 if len(s["cues"]) > 1 else 0) / 20)
                else:
                    fade = min(round(p["mix"]["cue_crossfade_seconds"] * rate), frames // 2)
                    if fade:
                        envelope[:fade] *= np.sin(np.linspace(0, math.pi / 2, fade)) ** 2
                        envelope[-fade:] *= np.sin(np.linspace(math.pi / 2, 0, fade)) ** 2
                start = round(cue["start_ms"] * 44.1)
                stem[start:start + frames] += clip * envelope[:, None]
            voice, sr = sf.read(str(self.inside(s["voice_path"])), dtype="float32", always_2d=True)
            divisor = math.gcd(rate, sr)
            voice = resample_poly(voice, rate // divisor, sr // divisor, axis=0)
            if len(voice) != count:
                raise ValueError("Approved narration duration changed")
            hop = round(rate * .025)
            activity = np.array([_rms(voice[i:i + hop]) > 10 ** (-43 / 20) for i in range(0, count, hop)], np.float32)
            activity = gaussian_filter1d(activity, 8)
            duck = np.interp(np.arange(count), np.arange(len(activity)) * hop, -p["mix"]["speech_duck_db"] * activity)
            stem *= (10 ** (duck / 20))[:, None]
            fi, fo = [round(p["mix"][key] * rate) for key in ("fade_in_seconds", "fade_out_seconds")]
            if fi: stem[:fi] *= np.sin(np.linspace(0, math.pi / 2, fi))[:, None] ** 2
            if fo: stem[-fo:] *= np.sin(np.linspace(math.pi / 2, 0, fo))[:, None] ** 2
            premaster = directory / "soundscape-before-leveling.wav"
            _write_audio(premaster, stem, floating=True)
            finish = master_ambient(premaster, p["settings"], root=self.root, role="stem")
            _copy_checked(finish["audio_path"], directory / "soundscape-only.wav")
            stem, _ = sf.read(finish["audio_path"], dtype="float32", always_2d=True)
            if p.get("audibility_policy", {}).get("enabled"):
                checked = inspect_samples(stem, rate, p["audibility_policy"])
                if checked["quality_findings"]:
                    raise ValueError("Finished ambient stem failed small-speaker or mono screening")
            solo = master_ambient(directory / "soundscape-only.wav", p["settings"], root=self.root, role="solo",
                                  revision=p.get("solo_mastering_revision", VERSION))
            _copy_checked(solo["audio_path"], directory / "ambient-solo-review.wav")
            combined = voice + stem
            gain = min(0, -1 - _db(np.max(np.abs(combined))))
            _write_audio(directory / "voice-and-ambient-review.wav", combined * np.float32(10 ** (gain / 20)))
            minimum = _minimum_interior(stem, fi, fo, rate)
            if minimum < -60:
                raise ValueError("Interior ambient dropout; review the preserved edition")
            summary = {**s, "frames": count, "stem_mastering": finish, "solo_mastering": solo,
                       "review_mix_gain_db": gain, "minimum_interior_rms_dbfs": minimum,
                       "ambient_listening_approval": "pending", "continuous_base": True,
                       "files": {n: sha(directory / n) for n in (
                           "soundscape-only.wav", "ambient-solo-review.wav", "voice-and-ambient-review.wav")}}
            if p.get("audibility_policy", {}).get("enabled"):
                summary["audibility"] = checked
            write_json(directory / "soundscape.json", summary)
            summaries.append(summary)
            print("Packaged ambient: " + s["title"], flush=True)
        result = {"run_id": p["run_id"], "plan_digest": p["plan_digest"], "stories": summaries,
                  "assets": len(p["assets"]), "listening_approval": "pending", "paid_calls": 0, "network_calls": 0}
        write_json(self.out / "manifest.json", result)
        self._page(p, summaries)
        self.validate(p)
        return {"stories": len(summaries), "assets": len(p["assets"]), "page": str(self.out / "index.html"),
                "duration_ms": sum(s["duration_ms"] for s in summaries), "paid_calls": 0}

    def _page(self, p, summaries):
        e = html.escape
        batch = re.search(r"-batch-(\d+)(?:-|$)", p["run_id"])
        title = "Ambient production batch " + batch.group(1) if batch else p["run_id"]
        count = "Ten" if len(summaries) == 10 else str(len(summaries))
        cards = []
        for i, s in enumerate(summaries, 1):
            prefix = s["narration_id"]
            voice = os.path.relpath(self.inside(s["voice_path"]), self.out).replace(os.sep, "/")
            links = " · ".join(f'<a href="{os.path.relpath(self.inside(v), self.out).replace(os.sep, "/")}">{k.upper()} captions</a>'
                               for k, v in s["captions"].items())
            choices = "".join(f'<li>{e(c["cue_id"])} ({c["start_ms"]/1000:.2f}–{c["end_ms"]/1000:.2f}s): {e(c["interpretation"])}</li>' for c in s["cues"])
            skips = "".join(f'<li>Skipped {e(c["cue_id"])}: less than 15 seconds; background continues.</li>' for c in s["skipped_cues"])
            cards.append(f'''<article id="story-{i}"><h2>{i}. {e(s['title'])}</h2><p>{s['duration_ms']/1000:.2f} seconds · {e(s['direction'])}</p>
<label>Voice + ambient</label><audio controls preload="metadata" src="{prefix}/voice-and-ambient-review.wav"></audio>
<label>Ambient only — matched solo level</label><audio controls preload="metadata" src="{prefix}/ambient-solo-review.wav"></audio>
<label>Approved voice only — unchanged</label><audio controls preload="metadata" src="{voice}"></audio>
<p><a href="{prefix}/soundscape-only.wav">Production ambient stem</a> · {links}</p>
<details><summary>Transcript and sound choices</summary><p>{e(s['location_note'])}</p><div class="transcript">{e(s['transcript'])}</div><ul>{choices}{skips}</ul></details></article>''')
        page = '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Ambient production batch 01</title>
<style>body{background:#10171a;color:#edf2eb;font:17px/1.6 system-ui;margin:0}main{max-width:960px;padding:36px 24px;margin:auto}h1,h2{line-height:1.25}article{background:#1b292d;padding:25px;border-radius:16px;margin:24px 0}label{color:#bad8cc}audio{width:100%;display:block;margin:8px 0 22px}a{color:#99dbc7}.transcript{white-space:pre-wrap}details{font-size:15px}summary{cursor:pointer}</style>
<main><h1>Ten stories: ambient production batch 01</h1><p>All narration recordings are already approved and unchanged. These illustrative generated sounds are not archival recordings. Please review relevance, unwanted voices or music, comfortable balance, and smooth transitions.</p>
<p>Shared level standard: source sounds -24 LUFS; production stems -30 LUFS; raised solo previews -23 LUFS. Continuous backgrounds, gentle start/end fades, and speech ducking are retained. Short specific sounds inherit the ongoing background.</p>'''
        page = page.replace("<title>Ambient production batch 01</title>", f"<title>{e(title)}</title>")
        page = page.replace("Ten stories: ambient production batch 01", f"{count} stories: {e(title.lower())}")
        self.out.mkdir(parents=True, exist_ok=True)
        (self.out / "index.html").write_text(page + "".join(cards) + '''</main><script>document.querySelectorAll('audio').forEach(a=>a.addEventListener('play',()=>document.querySelectorAll('audio').forEach(b=>{if(a!==b)b.pause()})))</script></html>''', encoding="utf-8")

    def verify(self):
        import numpy as np
        import soundfile as sf
        from scipy.signal import resample_poly
        p, manifest = self.load(), read(self.out / "manifest.json")
        if manifest["plan_digest"] != p["plan_digest"] or len(manifest["stories"]) != len(p["stories"]):
            raise ValueError("Incomplete or stale listening package")
        diagnostic = read(self.work / "speech-diagnostic.json")
        quality = read(self.work / "quality.json")
        checksums = {a["asset_key"]: a["mastering"]["audio_sha256"] for a in quality["assets"]}
        if (diagnostic["plan_digest"] != p["plan_digest"] or diagnostic["recognized_segments"]
                or checksums != {a["asset_key"]: a["audio_sha256"] for a in diagnostic["assets"]}):
            raise ValueError("Ambient speech screen missing, flagged, or stale")
        for a in p["assets"]:
            if not self.cached(a): raise ValueError("Generated cache invalid")
            r = master_ambient(self.inside(a["output_audio"]), p["settings"], root=self.root)
            if r["audio_sha256"] != checksums[a["cache_key"]]:
                raise ValueError("Finished asset changed")
        ffmpeg, levels = find_ffmpeg(self.root), []
        for expected, actual in zip(p["stories"], manifest["stories"]):
            if any(expected[k] != actual[k] for k in expected):
                raise ValueError("Story evidence, cue timing or voice changed")
            directory, audio = self.out / expected["narration_id"], {}
            for name, checksum in actual["files"].items():
                path = directory / name
                if sha(path) != checksum: raise ValueError("Output checksum changed")
                audio[name], rate = sf.read(str(path), dtype="float64", always_2d=True)
                if rate != 44100 or audio[name].shape != (round(expected["duration_ms"] * 44.1), 2):
                    raise ValueError("Output audio timing changed")
                if np.max(np.abs(audio[name])) >= 1: raise ValueError("Clipped listening file")
            for name, role in (("soundscape-only.wav", "stem"), ("ambient-solo-review.wav", "solo")):
                m = measure_loudness(directory / name, ffmpeg)
                if (m["integrated_lufs"] is None or abs(m["integrated_lufs"] - p["settings"][role + "_target_lufs"]) > p["settings"]["level_tolerance_lu"]
                        or m["true_peak_dbfs"] > p["settings"][role + "_true_peak_dbfs"] + .15):
                    raise ValueError("Output loudness or peak limit failed")
                if role == "stem": levels.append(m["integrated_lufs"])
            if p.get("audibility_policy", {}).get("enabled"):
                checked = inspect_samples(audio["soundscape-only.wav"], 44100, p["audibility_policy"])
                if checked["quality_findings"] or checked != actual.get("audibility"):
                    raise ValueError("Finished ambient audibility failed or receipt changed")
            voice, sr = sf.read(str(self.inside(expected["voice_path"])), dtype="float64", always_2d=True)
            div = math.gcd(44100, sr)
            voice = resample_poly(voice, 44100 // div, sr // div, axis=0)
            mixed = audio["voice-and-ambient-review.wav"] / 10 ** (actual["review_mix_gain_db"] / 20)
            if np.max(np.abs(mixed - voice - audio["soundscape-only.wav"])) > .0002:
                raise ValueError("Review mix is not approved voice plus finished stem")
            fi, fo = [round(p["mix"][k] * 44100) for k in ("fade_in_seconds", "fade_out_seconds")]
            if _minimum_interior(audio["soundscape-only.wav"], fi, fo, 44100) < -60:
                raise ValueError("Interior ambient dropout")
        page = (self.out / "index.html").read_text(encoding="utf-8")
        links = re.findall(r'(?:href|src)="([^"#]+)"', page)
        if any(not (self.out / link).is_file() for link in links):
            raise ValueError("Broken listening page link")
        result = {"stories_verified": len(p["stories"]), "assets_verified": len(p["assets"]),
                  "duration_ms": sum(s["duration_ms"] for s in p["stories"]),
                  "stem_lufs_range": [min(levels), max(levels)], "page_audio_players": page.count("<audio "),
                  "protected_files_unchanged": len(p["protected_sha256"]), "original_voices_unchanged": True,
                  "cue_timing_verified": True, "recognized_ambient_speech_segments": 0,
                  "listening_approval": "pending", "network_calls": 0, "paid_calls": 0}
        write_json(self.work / "verification.json", result)
        return result


def _contains_words(text, phrase):
    words, needle = normalized_words(text), normalized_words(phrase)
    return bool(needle) and any(words[i:i + len(needle)] == needle for i in range(len(words) - len(needle) + 1))


def _rms(x):
    import numpy as np
    return math.sqrt(float(np.mean(x.astype("float64") ** 2)))


def _db(value): return 20 * math.log10(max(float(value), 1e-12))


def _minimum_interior(x, fi, fo, rate):
    middle = x[fi:len(x) - fo if fo else len(x)]
    return min(_db(_rms(middle[i:i + rate])) for i in range(0, len(middle), rate))


def _write_audio(path, audio, floating=False):
    import numpy as np
    import soundfile as sf
    expected = audio.astype("float32") if floating else np.rint(audio * 32768).astype("int16")
    if not floating and np.max(np.abs(audio)) >= 1:
        raise ValueError("Refusing clipped output")
    if path.exists():
        existing, rate = sf.read(str(path), dtype="float32" if floating else "int16", always_2d=True)
        if rate != 44100 or not np.array_equal(existing, expected):
            raise ValueError("Existing ambient edition differs; no overwrite")
    else:
        with path.open("xb") as stream:
            sf.write(stream, expected, 44100, format="WAV", subtype="FLOAT" if floating else "PCM_16")


def _copy_checked(source, destination):
    if destination.exists() and sha(source) != sha(destination):
        raise ValueError("Existing ambient derivative changed")
    if not destination.exists():
        shutil.copyfile(source, destination)
