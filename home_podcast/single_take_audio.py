"""Offline whole-story VoiceDesign production promoted from the reviewed 3080 runner.

No model is imported for planning, validation, packaging or approval. One frozen
cast, one seed and one uninterrupted model call cover the complete story. The
legacy proof runner remains intact; this module is the supported CLI workflow.
"""
from __future__ import annotations

import array
import difflib
import gc
import hashlib
import html
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
import wave
from datetime import datetime, timezone
from pathlib import Path

from home_podcast.config import ProjectConfig
from home_podcast.storytelling import validate_storytelling_adaptation_data
from home_podcast.storytelling_duration import require_story_audio_duration, require_story_text_budget
from home_podcast.storytelling_quality import content_digest, require_personal_story

MODEL = "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign"
REVISION = "5ecdb67327fd37bb2e042aab12ff7391903235d3"
MODEL_PATH = Path.home() / ".cache/huggingface/hub/models--Qwen--Qwen3-TTS-12Hz-1.7B-VoiceDesign/snapshots" / REVISION
SETTINGS = {
    "max_new_tokens": 5000, "do_sample": True, "temperature": 0.9,
    "top_p": 1.0, "top_k": 50, "repetition_penalty": 1.05,
    "subtalker_dosample": True, "subtalker_temperature": 0.9,
    "subtalker_top_p": 1.0, "subtalker_top_k": 50,
}
NARRATION_ID = r"[0-9]{4}-[0-9]{2}--story-[0-9a-f]{24}(?:--[a-z0-9]+(?:-[a-z0-9]+)*)?"
COMMON_DIRECTION = (
    "Tell the complete first-person story to one trusted friend. Maintain ONE recognizable "
    "speaker, with the same natural timbre, register and accent throughout; vary feeling and "
    "rhythm, not identity. Keep clear ordinary speaking volume even in tender passages. Use "
    "natural thought pauses, occasional small breaths and varied emphasis, not identical gaps "
    "after every sentence. Preserve comfortable conversational pacing. Read every supplied "
    "word in order, without adding a preamble, extra words, stage directions, music, other "
    "speakers or background noise. Instructions describe delivery and must not be spoken."
)


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, value: dict, *, exclusive: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    if exclusive:
        with path.open("x", encoding="utf-8") as stream:
            stream.write(text)
    else:
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(text, encoding="utf-8")
        temporary.replace(path)


def validate_casting(card: dict, adaptation: dict, source: dict) -> None:
    if not card.get("casting_note") or not card.get("voice_description") or not card.get("performance_direction"):
        raise ValueError("A reviewed voice brief and performance direction are required")
    casting = card.get("casting", {})
    for key in ("gender_presentation", "accent", "vocal_age", "personality"):
        choice = casting.get(key, {})
        if not choice.get("value") or choice.get("basis") not in {"source_explicit", "artistic_choice"}:
            raise ValueError("Casting must distinguish evidence from artistic choice")
        if choice["basis"] == "source_explicit":
            evidence = choice.get("evidence_excerpt", "")
            if not evidence or evidence not in source["story_text"]:
                raise ValueError("Unsupported casting evidence")
    for constraint in adaptation.get("identity_constraints", []):
        if constraint["evidence_excerpt"] not in source["story_text"]:
            raise ValueError("Unsupported identity constraint")
        field = {"narrator_gender_presentation": "gender_presentation",
                 "narrator_accent": "accent", "narrator_age_presentation": "vocal_age"}.get(constraint["trait"])
        if field:
            selected = casting[field]
            if selected["value"] != constraint["value"] or selected["basis"] != "source_explicit":
                raise ValueError(f"Casting conflicts with source-explicit {field}")


def inspect_wave(path: Path) -> dict:
    with wave.open(str(path), "rb") as stream:
        rate, channels, width, frames = (stream.getframerate(), stream.getnchannels(),
                                         stream.getsampwidth(), stream.getnframes())
        if channels != 1 or width != 2 or rate <= 0 or frames <= 0:
            raise ValueError("Expected nonempty mono PCM16 audio")
        pcm = stream.readframes(frames)
    if len(pcm) != frames * 2:
        raise ValueError("Incomplete WAV payload")
    values = array.array("h", pcm)
    if sys.byteorder != "little":
        values.byteswap()
    peak = max(abs(value) for value in values)
    rms = math.sqrt(sum(value * value for value in values) / frames)
    if peak < 100 or rms < 1:
        raise ValueError("Silent or near-silent render")
    return {"wav_sha256": sha(path), "duration_ms": (frames * 1000 + rate - 1) // rate,
            "frames": frames, "sample_rate": rate, "channels": channels,
            "peak_dbfs": round(20 * math.log10(peak / 32768), 2),
            "rms_dbfs": round(20 * math.log10(rms / 32768), 2),
            "clipped_sample_fraction": sum(abs(v) >= 32760 for v in values) / frames}


def offline() -> None:
    for key in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "HF_HUB_DISABLE_IMPLICIT_TOKEN", "HF_HUB_DISABLE_TELEMETRY"):
        os.environ[key] = "1"


def hardware_guard() -> str:
    check = subprocess.run(["powershell", "-NoProfile", "-Command",
                            "@(Get-Process -Name TouchDesigner -ErrorAction SilentlyContinue).Count"],
                           capture_output=True, text=True, check=True, timeout=20)
    if check.stdout.strip() != "0":
        raise ValueError("Close TouchDesigner before this offline GPU production step")
    gpu = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.free", "--format=csv,noheader,nounits"],
                         capture_output=True, text=True, check=True, timeout=20).stdout.strip()
    rows = gpu.splitlines()
    if len(rows) != 1 or "3080" not in rows[0] or int(rows[0].rsplit(",", 1)[1]) < 8000:
        raise ValueError("Requires the idle 3080 machine with at least 8 GB free VRAM")
    return gpu


def generate_once(model, job: dict):
    # Deliberately not a loop over sections: one speaker is designed for the whole story.
    return model.generate_voice_design(text=job["text"], language="English", instruct=job["instruct"],
                                       non_streaming_mode=True, **job["generation_settings"])


def normalized_words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower().replace("'", "").replace("’", ""))


def compare_text(expected: str, actual: str) -> dict:
    left, right = normalized_words(expected), normalized_words(actual)
    matcher = difflib.SequenceMatcher(a=left, b=right, autojunk=False)
    differences = [{"kind": tag, "expected": " ".join(left[i:j]), "recognized": " ".join(right[k:l]),
                    "expected_word_range": [i, j], "recognized_word_range": [k, l]}
                   for tag, i, j, k, l in matcher.get_opcodes() if tag != "equal"]
    return {"expected_words": len(left), "recognized_words": len(right),
            "sequence_match_ratio": round(matcher.ratio(), 4), "differences": differences}


def content_findings(report: dict) -> list[str]:
    """Fail closed on likely omission/repetition, without calling ASR proof of fidelity."""
    findings = []
    if report.get("sequence_match_ratio", 0) < 0.93:
        findings.append("low_script_asr_agreement")
    for difference in report.get("differences", []):
        if len(difference.get("expected", "").split()) >= 8:
            findings.append("possible_missing_or_changed_passage")
        if len(difference.get("recognized", "").split()) >= 10:
            findings.append("possible_added_or_repeated_passage")
    return sorted(set(findings))


def caption_rows(segments: list[dict], duration_ms: int) -> list[dict]:
    words = [word for segment in segments for word in segment["words"] if word["word"].strip()]
    if not words:
        raise ValueError("ASR produced no timed words")
    previous, groups, group = 0, [], []
    for word in words:
        start, end = round(word["start_s"] * 1000), round(word["end_s"] * 1000)
        if start < 0 or end < start or end > duration_ms + 100:
            raise ValueError("ASR word timestamp outside audio")
        start, end = max(start, previous), min(end, duration_ms)
        if end <= start:
            if not group:
                raise ValueError("Cannot caption a zero-duration word at a boundary")
            group[-1]["text"] += " " + word["word"].strip()
            continue
        group.append({"start_ms": start, "end_ms": end, "text": word["word"].strip()})
        previous = end
        sentence_end = bool(re.search(r"[.!?][\"']?$", word["word"].strip()))
        if (sentence_end or len(group) >= 11 or sum(len(w["text"]) + 1 for w in group) >= 72
                or end - group[0]["start_ms"] >= 5500):
            groups.append(group)
            group = []
    if group:
        groups.append(group)
    return [{"start_ms": group[0]["start_ms"], "speech_end_ms": group[-1]["end_ms"],
             "text": " ".join(word["text"] for word in group)} for group in groups]


def listening_copy(directory: Path) -> dict:
    """Optional constant gain only: preserve the original take, dynamics and frames."""
    original, destination = directory / "voices-only.wav", directory / "listening.wav"
    measured = inspect_wave(original)
    gain = round(min(-23.0 - measured["rms_dbfs"], -1.5 - measured["peak_dbfs"]), 4)
    identity = {"raw_audio_sha256": measured["wav_sha256"], "gain_db": gain,
                "method": "one_constant_linear_gain_for_entire_story", "target_rms_dbfs": -23.0,
                "maximum_sample_peak_dbfs": -1.5, "speed_change": False, "silence_edits": False,
                "compression_or_limiting": False}
    metadata_path = directory / "listening-levels.json"
    if destination.exists() or metadata_path.exists():
        receipt = read(metadata_path)
        if any(receipt.get(key) != value for key, value in identity.items()) or sha(destination) != receipt["wav_sha256"]:
            raise ValueError("Changed listening copy; review instead of overwriting it")
        return receipt
    with wave.open(str(original), "rb") as source:
        values = array.array("h", source.readframes(source.getnframes()))
        if sys.byteorder != "little":
            values.byteswap()
        factor = 10 ** (gain / 20)
        adjusted = [round(value * factor) for value in values]
        if max(abs(value) for value in adjusted) > 32767:
            raise ValueError("Listening gain would clip; original preserved")
        samples = array.array("h", adjusted)
        if sys.byteorder != "little":
            samples.byteswap()
        with destination.open("xb") as binary, wave.open(binary, "wb") as target:
            target.setparams(source.getparams())
            target.writeframes(samples.tobytes())
    rendered = inspect_wave(destination)
    if any(rendered[field] != measured[field] for field in ("frames", "duration_ms", "sample_rate", "channels")):
        raise ValueError("Listening copy changed timing")
    receipt = {**identity, **rendered, "raw_audio_preserved": sha(original) == identity["raw_audio_sha256"]}
    if not receipt["raw_audio_preserved"]:
        raise ValueError("Original audio changed")
    write_json(metadata_path, receipt, exclusive=True)
    return receipt


def asr_tail_candidate(job: dict, report: dict) -> dict | None:
    """Identify only an impossible-timed extra outro after the ENTIRE script.

    This is not enough to remove it: a separate, unprompted recognition of the
    closing audio must also recover the exact expected closing passage.
    """
    expected = normalized_words(job["text"])
    recognized = normalized_words(report.get("recognized_text", ""))
    if recognized[:len(expected)] != expected or len(recognized) - len(expected) < 8:
        return None
    kept, extra, count = [], [], 0
    for segment in report["segments"]:
        count += len(normalized_words(segment["text"]))
        (kept if count <= len(expected) else extra).append(segment)
    if not kept or not extra or normalized_words(" ".join(s["text"] for s in kept)) != expected:
        return None
    words = [w for s in extra for w in s["words"]]
    if (not words or extra[-1]["end_s"] - extra[0]["start_s"] > 0.5
            or extra[0]["start_s"] < kept[-1]["end_s"]
            or sum(w["end_s"] == w["start_s"] for w in words) / len(words) < 0.75):
        return None
    context = []
    for segment in reversed(kept):
        context.insert(0, segment)
        if (kept[-1]["end_s"] - context[0]["start_s"] >= 8
                and len(normalized_words(" ".join(s["text"] for s in context))) >= 20):
            break
    if len(normalized_words(" ".join(s["text"] for s in context))) < 20:
        return None
    return {"kept_segments": kept, "extra_segments": extra,
            "start_s": max(0.0, context[0]["start_s"] - 0.25),
            "expected_context": " ".join(s["text"] for s in context)}


def tail_checked_report(job: dict, original: dict, check: dict,
                        original_hash: str, check_hash: str) -> dict:
    candidate = asr_tail_candidate(job, original)
    if (candidate is None or check.get("original_asr_sha256") != original_hash
            or check.get("audio_sha256") != original["audio_sha256"]
            or check.get("cache_key") != job["cache_key"]
            or check.get("asr_model") != original["asr_model"]
            or check.get("asr_revision") != original["asr_revision"]
            or check.get("start_s") != candidate["start_s"]
            or check.get("script_prompt_supplied") is not False
            or " ".join(s["text"] for s in check.get("segments", [])) != check.get("recognized_text")
            or normalized_words(check.get("recognized_text", "")) != normalized_words(candidate["expected_context"])):
        raise ValueError("Unresolved or stale ASR tail check; retain the content hold")
    recognized = " ".join(s["text"] for s in candidate["kept_segments"])
    result = {**original, "segments": candidate["kept_segments"], "recognized_text": recognized,
              **compare_text(job["text"], recognized),
              "asr_tail_resolution": {"kind": "impossible_timed_outro_rechecked_on_closing_audio",
                                      "original_asr_sha256": original_hash, "tail_check_sha256": check_hash,
                                      "original_audio_unchanged": True, "listening_approval": "pending"}}
    result["content_findings"] = content_findings(result)
    return result


def human_confirmed_outro_report(job: dict, original: dict, review: dict,
                                 diagnostic: dict, original_hash: str,
                                 review_hash: str, diagnostic_hash: str) -> dict:
    """Resolve an impossible-timed ASR outro only with an explicit human check.

    This is not automatic listening approval. Keep all in-body recognition,
    every recording sample, and all original reports unchanged.
    """
    count = review.get("removed_trailing_segments")
    ending = normalized_words(review.get("confirmed_spoken_ending", ""))
    expected = normalized_words(job["text"])
    diagnostic_words = normalized_words(diagnostic.get("recognized_text", ""))
    if (review.get("decision") != "asr_outro_not_spoken"
            or review.get("confirmed_by_human") is not True
            or not review.get("reviewer") or not review.get("user_decision")
            or review.get("audio_sha256") != original.get("audio_sha256")
            or review.get("cache_key") != job["cache_key"]
            or original.get("cache_key") != job["cache_key"]
            or review.get("original_asr_sha256") != original_hash
            or review.get("closing_diagnostic_sha256") != diagnostic_hash
            or diagnostic.get("audio_sha256") != original.get("audio_sha256")
            or diagnostic.get("original_asr_sha256") != original_hash
            or diagnostic.get("script_prompt_supplied") is not False
            or " ".join(s["text"] for s in diagnostic.get("segments", [])) != diagnostic.get("recognized_text")
            or diagnostic.get("asr_model") != original.get("asr_model")
            or diagnostic.get("asr_revision") != original.get("asr_revision")
            or len(diagnostic_words) < 20 or expected[-len(diagnostic_words):] != diagnostic_words
            or len(ending) < 2 or expected[-len(ending):] != ending
            or type(count) is not int or not 1 <= count < len(original["segments"])):
        raise ValueError("Missing, stale or unsupported human outro review")
    kept, removed = original["segments"][:-count], original["segments"][-count:]
    recognized = " ".join(s["text"] for s in kept)
    if (normalized_words(recognized)[-len(ending):] != ending
            or len(normalized_words(" ".join(s["text"] for s in removed))) < 8
            or removed[0]["start_s"] < kept[-1]["end_s"]
            or not 0 <= removed[-1]["end_s"]-removed[0]["start_s"] <= .5):
        raise ValueError("Human outro review cannot remove in-body or normally timed speech")
    result = {**original, "segments": kept, "recognized_text": recognized,
              **compare_text(job["text"], recognized),
              "asr_tail_resolution": {"kind": "human_confirmed_unspoken_asr_outro",
                                      "original_asr_sha256": original_hash,
                                      "human_review_sha256": review_hash,
                                      "closing_diagnostic_sha256": diagnostic_hash,
                                      "original_audio_unchanged": True,
                                      "listening_approval": "pending"}}
    result["content_findings"] = content_findings(result)
    return result


def human_confirmed_span_report(job: dict, original: dict, review: dict,
                                diagnostic: dict, original_hash: str,
                                review_hash: str, diagnostic_hash: str) -> dict:
    """Restore a human-heard ASR omission using real unprompted word timings."""
    from copy import deepcopy
    expected = normalized_words(job["text"])
    recognized_check = normalized_words(diagnostic.get("recognized_text", ""))
    phrase = review.get("confirmed_spoken_passage", "")
    phrase_words = normalized_words(phrase)
    target, trim, replacement = (review.get(k) for k in
                                 ("target_segment_index", "trim_trailing_words", "diagnostic_segment_index"))
    if (review.get("decision") != "recognized_passage_was_spoken"
            or review.get("confirmed_by_human") is not True
            or not review.get("reviewer") or not review.get("user_decision")
            or review.get("cache_key") != job["cache_key"] or original.get("cache_key") != job["cache_key"]
            or review.get("audio_sha256") != original.get("audio_sha256")
            or diagnostic.get("audio_sha256") != original.get("audio_sha256")
            or review.get("original_asr_sha256") != original_hash
            or diagnostic.get("original_asr_sha256") != original_hash
            or review.get("span_diagnostic_sha256") != diagnostic_hash
            or diagnostic.get("script_prompt_supplied") is not False
            or diagnostic.get("asr_model") != original.get("asr_model")
            or diagnostic.get("asr_revision") != original.get("asr_revision")
            or " ".join(s["text"] for s in diagnostic.get("segments", [])) != diagnostic.get("recognized_text")
            or len(recognized_check) < 20 or not any(expected[i:i+len(recognized_check)] == recognized_check
                for i in range(len(expected)-len(recognized_check)+1))
            or len(phrase_words) < 8 or phrase not in job["text"]
            or any(type(v) is not int for v in (target,trim,replacement))
            or not 0 <= target < len(original["segments"])-1
            or not 0 <= replacement < len(diagnostic["segments"])):
        raise ValueError("Missing, stale or unsupported human passage review")
    segments = deepcopy(original["segments"])
    previous, following = segments[target], segments[target+1]
    restored = deepcopy(diagnostic["segments"][replacement])
    words = previous.get("words", [])
    if not 0 <= trim < len(words) or normalized_words(restored["text"]) != phrase_words:
        raise ValueError("Invalid reviewed passage or trim")
    removed = words[len(words)-trim:] if trim else []
    if removed and normalized_words(" ".join(w["word"] for w in removed)) != phrase_words[:len(removed)]:
        raise ValueError("May trim only a partial recognized prefix of the restored passage")
    previous["words"] = words[:len(words)-trim] if trim else words
    previous["text"] = "".join(w["word"] for w in previous["words"]).strip()
    previous["end_s"] = previous["words"][-1]["end_s"]
    if (not previous["end_s"] <= restored["start_s"] < restored["end_s"] <= following["start_s"]
            or not restored.get("words") or any(not restored["start_s"] <= w["start_s"] < w["end_s"] <= restored["end_s"]
                                                for w in restored["words"])):
        raise ValueError("Passage timings overlap existing speech or are not positive measured words")
    segments.insert(target+1,restored)
    recognized = " ".join(s["text"] for s in segments)
    result = {**original, "segments": segments, "recognized_text": recognized,
              **compare_text(job["text"],recognized),
              "asr_span_resolution": {"kind": "human_confirmed_spoken_passage_recovered",
                                      "original_asr_sha256": original_hash,
                                      "human_review_sha256": review_hash,
                                      "span_diagnostic_sha256": diagnostic_hash,
                                      "original_audio_unchanged": True,
                                      "word_timing_source": "unprompted excerpt recognition, not estimated",
                                      "listening_approval": "pending"}}
    result["content_findings"] = content_findings(result)
    return result


def effective_asr_path(directory: Path, job: dict) -> Path:
    original = directory / "asr-report.json"
    span_review = directory / "asr-span-human-review.json"
    span_resolved = directory / "asr-report-span-reviewed.json"
    if span_review.exists() or span_resolved.exists():
        diagnostic_path = directory / "asr-span-diagnostic.json"
        expected = human_confirmed_span_report(
            job, read(original), read(span_review), read(diagnostic_path),
            sha(original), sha(span_review), sha(diagnostic_path))
        if (read(span_resolved) != expected
                or sha(directory / "voices-only.wav") != expected["audio_sha256"]):
            raise ValueError("Changed human passage-review evidence; original preserved")
        return span_resolved
    human_path = directory / "asr-outro-human-review.json"
    resolved_path = directory / "asr-report-human-reviewed.json"
    if human_path.exists() or resolved_path.exists():
        diagnostic_path = directory / "asr-ending-diagnostic.json"
        expected = human_confirmed_outro_report(
            job, read(original), read(human_path), read(diagnostic_path),
            sha(original), sha(human_path), sha(diagnostic_path))
        if (read(resolved_path) != expected
                or sha(directory / "voices-only.wav") != expected["audio_sha256"]):
            raise ValueError("Changed human outro-review evidence; original preserved")
        return resolved_path
    checked = directory / "asr-report-tail-checked.json"
    if not checked.exists():
        return original
    check_path = directory / "asr-tail-check.json"
    expected = tail_checked_report(job, read(original), read(check_path), sha(original), sha(check_path))
    if read(checked) != expected or sha(directory / "voices-only.wav") != expected["audio_sha256"]:
        raise ValueError("Changed ASR tail-check evidence; original preserved")
    return checked


class SingleTakeProduction:
    """A project-scoped production session; never a live TouchDesigner worker."""

    def __init__(self, project_config: ProjectConfig, *, model_path: Path | None = None):
        self.project_config = project_config
        self.root = project_config.project_root.resolve()
        self.model_path = (model_path or MODEL_PATH).expanduser().resolve()
        self.settings = dict(SETTINGS)
        self.config()
        targets = (project_config.episodes_dir, project_config.work_dir, project_config.audio_dir)
        if any(not p.resolve().is_relative_to(self.root) or p.resolve() == self.root for p in targets):
            raise ValueError("Story production directories must remain inside the project")
        if len({p.resolve() for p in targets}) != 3:
            raise ValueError("Story production directories must be distinct")

    def paths(self, brief: dict) -> tuple[Path, Path]:
        slug = brief.get("run_id", "")
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{4,100}", slug):
            raise ValueError("Unsafe or missing run_id")
        return (self.project_config.work_dir / "local-audio" / slug,
                self.project_config.audio_dir / slug)


    def config(self):
        result = self.project_config
        if result.production_mode != "self_narrated_storytelling" or result.target_minutes_max != 5:
            raise ValueError("This workflow requires the five-minute storytelling policy")
        return result


    def expected_jobs(self, brief: dict) -> list[dict]:
        jobs, seen_ids, seen_texts = [], set(), set()
        if brief.get("contract_version") != 1 or not brief.get("stories"):
            raise ValueError("Expected a nonempty version-one brief")
        cfg = self.config()
        for card in brief["stories"]:
            story_id = card["narration_id"]
            if not re.fullmatch(NARRATION_ID, story_id) or story_id in seen_ids:
                raise ValueError("Invalid or duplicate story ID")
            seen_ids.add(story_id)
            directory = self.project_config.episodes_dir / story_id
            review = require_personal_story(directory)
            adaptation, source = read(directory / "adaptation.json"), read(directory / "source-job.json")
            validation = validate_storytelling_adaptation_data(adaptation, source)
            if not validation["valid"]:
                raise ValueError(f"Invalid reviewed adaptation: {story_id}")
            if adaptation["perspective_mode"] not in {"first_person_preserved", "attributed_first_person"}:
                raise ValueError("Only established first-person stories may be spoken")
            if adaptation["adaptation_language"] != "en":
                raise ValueError("This production brief supports English adaptations only")
            validate_casting(card, adaptation, source)
            budget = require_story_text_budget(cfg, adaptation)
            text = "\n\n".join(section["text"] for section in adaptation["sections"])
            text_hash = hashlib.sha256(re.sub(r"\s+", " ", text).strip().encode()).hexdigest()
            if text_hash in seen_texts:
                raise ValueError("Duplicate spoken story in the production brief")
            seen_texts.add(text_hash)
            seed = card["speech_seed"]
            if not isinstance(seed, int) or isinstance(seed, bool) or not 0 <= seed < 2**32:
                raise ValueError("Speech seed must be an unsigned 32-bit integer")
            payload = {
                "contract_version": 1, "kind": "whole_story_voicedesign_job",
                "narration_id": story_id, "title": adaptation["title"],
                "adaptation_sha256": content_digest(adaptation), "source_job_sha256": content_digest(source),
                "editorial_review_sha256": content_digest(review), "text": text,
                "sections": adaptation["sections"], "source_identity_constraints": adaptation["identity_constraints"],
                "casting_card": card, "speech_seed": seed,
                "instruct": card["voice_description"] + " " + COMMON_DIRECTION + " " + card["performance_direction"],
                "duration_preflight": budget, "maximum_duration_ms": 300000,
                "model": MODEL, "model_revision": REVISION, "generation_settings": self.settings,
                "non_streaming_mode": True, "generation_calls": 1,
                "internal_audio_edits": False, "automatic_voice_approval": False,
            }
            payload["cache_key"] = content_digest(payload)
            jobs.append(payload)
        return jobs


    def protected_files(self, output: Path) -> list[Path]:
        selected = set()
        for folder in (self.project_config.episodes_dir, self.project_config.audio_dir):
            selected.update(p for p in folder.rglob("*") if p.is_file() and not p.is_relative_to(output))
        selected.update(self.root.glob("*.toe"))
        selected.update((self.root / "config").glob("*.json"))
        selected.update((self.root / "touchdesigner").rglob("*.py"))
        selected.add(self.project_config.config_path)
        if (self.root / "podcast.json").is_file():
            selected.add(self.root / "podcast.json")
        return sorted(selected)


    def validate_plan(self, brief: dict, plan: dict, *, preservation: bool = True) -> None:
        if plan.get("brief_sha256") != content_digest(brief) or plan.get("jobs") != self.expected_jobs(brief):
            raise ValueError("Stale plan: source, text, review, casting or settings changed; use a new run_id")
        if not preservation:
            # Listening approval of an older batch checks its current source/job and
            # audio hashes, not whether unrelated later batches have been added.
            return
        _, output = self.paths(brief)
        baseline = plan["protected_sha256"]
        if set(baseline) != {p.relative_to(self.root).as_posix() for p in self.protected_files(output)}:
            raise ValueError("Protected artifact inventory changed; review before continuing")
        for relative, expected in baseline.items():
            path = (self.root / relative).resolve()
            if not path.is_relative_to(self.root) or sha(path) != expected:
                raise ValueError(f"Protected original changed: {relative}")


    def prepare(self, brief: dict) -> dict:
        work, output = self.paths(brief)
        plan_path = work / "plan.json"
        if plan_path.exists():
            plan = read(plan_path)
            self.validate_plan(brief, plan)
        else:
            plan = {"kind": "single_take_story_production_plan", "contract_version": 1,
                    "run_id": brief["run_id"], "brief_sha256": content_digest(brief),
                    "created_at": datetime.now(timezone.utc).isoformat(), "jobs": self.expected_jobs(brief),
                    "protected_sha256": {p.relative_to(self.root).as_posix(): sha(p) for p in self.protected_files(output)}}
            write_json(plan_path, plan, exclusive=True)
        self.reuse_cached_takes(brief, plan)
        return self.dry_run(brief, plan)


    def job_dir(self, brief: dict, job: dict) -> Path:
        return self.paths(brief)[1] / job["narration_id"] / job["cache_key"][:16]


    def cached(self, brief: dict, job: dict) -> bool:
        directory = self.job_dir(brief, job)
        try:
            receipt = read(directory / "generation.json")
            audio = directory / "voices-only.wav"
            if (receipt.get("status") != "completed" or receipt.get("cache_key") != job["cache_key"]
                    or receipt.get("wav_sha256") != sha(audio)):
                return False
            return require_story_audio_duration(self.config(), audio) == receipt["duration_ms"]
        except (OSError, ValueError, KeyError, wave.Error, EOFError):
            return False


    def dry_run(self, brief: dict, plan: dict) -> dict:
        self.validate_plan(brief, plan)
        rows = []
        for job in plan["jobs"]:
            complete = self.cached(brief, job)
            directory = self.job_dir(brief, job)
            blocked = not complete and directory.exists() and any(directory.iterdir())
            content_state = "pending_audio_or_asr"
            if complete and (directory / "asr-report.json").is_file():
                try:
                    audit_report = read(effective_asr_path(directory, job))
                    content_state = "held_for_content_review" if content_findings(audit_report) else "no_major_asr_difference_detected"
                    if (audit_report.get("cache_key") != job["cache_key"]
                            or audit_report.get("audio_sha256") != read(directory / "generation.json").get("wav_sha256")):
                        content_state = "held_for_content_review"
                except (OSError, ValueError):
                    content_state = "held_for_content_review"
            rows.append({"narration_id": job["narration_id"], "title": job["title"],
                         "spoken_words": job["duration_preflight"]["spoken_words"],
                         "estimated_duration_ms": job["duration_preflight"]["estimated_duration_ms"],
                         "cached": complete, "blocked_prior_attempt": blocked, "content_check": content_state})
        result = {"stories": len(rows), "stories_detail": rows,
                  "local_generation_calls_pending": sum(not row["cached"] and not row["blocked_prior_attempt"] for row in rows),
                  "blocked_attempts": sum(row["blocked_prior_attempt"] for row in rows),
                  "content_holds": sum(row["content_check"] == "held_for_content_review" for row in rows),
                  "paid_calls": 0, "network_calls": 0, "model_loads": 0,
                  "pinned_model_cached": (self.model_path / "model.safetensors").is_file(),
                  "maximum_duration_ms": 300000, "protected_originals": len(plan["protected_sha256"])}
        write_json(self.paths(brief)[0] / "dry-run.json", result)
        return result


    def render(self, brief: dict, plan: dict, *, execute: bool, max_calls: int | None) -> dict:
        report = self.dry_run(brief, plan)
        pending = report["local_generation_calls_pending"]
        if not execute or not pending:
            return report
        if max_calls != pending:
            raise ValueError("Pass the exact dry-run --max-calls ceiling; held attempts are never retried")
        if not report["pinned_model_cached"]:
            raise ValueError("Pinned model missing; automatic model downloads are prohibited")
        hardware = hardware_guard()
        offline()
        from home_podcast.providers.qwen_tts import Qwen3TTSLocalRenderer, _float_audio_to_pcm16
        import torch

        renderer = Qwen3TTSLocalRenderer(model_name=str(self.model_path), mode="voice_design")
        model = None
        outcomes = []
        try:
            print("Loading cached VoiceDesign; sequential whole-story takes only.", flush=True)
            model = renderer._load_model()
            for job in plan["jobs"]:
                if self.cached(brief, job):
                    continue
                existing = self.job_dir(brief, job)
                if existing.exists() and any(existing.iterdir()):
                    continue
                self.validate_plan(brief, plan)
                directory = self.job_dir(brief, job)
                directory.mkdir(parents=True, exist_ok=True)
                attempt = {"status": "generating", "cache_key": job["cache_key"], "narration_id": job["narration_id"],
                           "started_at": datetime.now(timezone.utc).isoformat(), "paid_calls": 0, "network_calls": 0}
                write_json(directory / "attempt.json", attempt, exclusive=True)
                started, progress = time.monotonic(), {"steps": 0, "last_log": time.monotonic()}
                torch.cuda.reset_peak_memory_stats()
                renderer._seed_everything(job["speech_seed"])

                def observe(module, inputs, output):
                    progress["steps"] += 1
                    now = time.monotonic()
                    if now - progress["last_log"] >= 30:
                        progress["last_log"] = now
                        print(json.dumps({"story": job["title"], "codec_steps": progress["steps"],
                                          "elapsed_s": round(now - started)}), flush=True)

                hook = model.model.talker.register_forward_hook(observe)
                try:
                    with torch.inference_mode():
                        wavs, rate = generate_once(model, job)
                    if len(wavs) != 1:
                        raise ValueError("Expected one uninterrupted take")
                    pcm = _float_audio_to_pcm16(wavs[0])
                    audio = directory / "voices-only.wav"
                    with audio.open("xb") as binary, wave.open(binary, "wb") as target:
                        target.setnchannels(1)
                        target.setsampwidth(2)
                        target.setframerate(int(rate))
                        target.writeframes(pcm)
                    # Retain a failed over-length take, but do not accept, crop or accelerate it.
                    require_story_audio_duration(self.config(), audio)
                    metrics = inspect_wave(audio)
                    if progress["steps"] >= job["generation_settings"]["max_new_tokens"]:
                        raise ValueError("Generation may have hit its token ceiling; hold for review")
                    if metrics["clipped_sample_fraction"] > 0.001:
                        raise ValueError("Excessive clipping; hold for review")
                    receipt = {**attempt, **metrics, "status": "completed", "hardware": hardware,
                               "model": MODEL, "model_revision": REVISION, "speech_seed": job["speech_seed"],
                               "generation_settings": self.settings, "forward_steps": progress["steps"],
                               "local_generation_calls": 1, "wall_time_s": round(time.monotonic() - started, 2),
                               "peak_cuda_allocated_gib": round(torch.cuda.max_memory_allocated() / 2**30, 3),
                               "internal_audio_edits": False, "gain_db": 0,
                               "automatic_voice_approval": False, "listening_review": "pending"}
                    write_json(directory / "generation.json", receipt, exclusive=True)
                    attempt = receipt
                    outcomes.append({"title": job["title"], "duration_ms": metrics["duration_ms"]})
                    print(json.dumps(outcomes[-1]), flush=True)
                    del wavs, pcm
                except Exception as error:
                    attempt.update(status="failed", error_type=type(error).__name__, forward_steps=progress["steps"])
                    if isinstance(error, ValueError) and (directory / "voices-only.wav").is_file():
                        attempt.update(status="held_quality", reason=str(error))
                        outcomes.append({"title": job["title"], "status": "held_quality", "reason": str(error)})
                        print(json.dumps(outcomes[-1]), flush=True)
                    else:
                        raise
                finally:
                    hook.remove()
                    write_json(directory / "attempt.json", attempt)
        finally:
            model = None
            renderer.unload()
            gc.collect()
            torch.cuda.empty_cache()
        self.validate_plan(brief, plan)
        return {"rendered": outcomes, "paid_calls": 0, "network_calls": 0, "model_unloaded": True,
                "held_prior_attempts": report["blocked_attempts"]}


    def reuse_cached_takes(self, brief: dict, plan: dict) -> int:
        """Copy only complete, content-checked identical jobs; never reuse a held take."""
        reused = 0
        _, output = self.paths(brief)
        receipts = sorted((self.project_config.audio_dir).rglob("generation.json"))
        for job in plan["jobs"]:
            destination = self.job_dir(brief, job)
            if destination.exists() and any(destination.iterdir()):
                continue
            for receipt_path in receipts:
                source_dir = receipt_path.parent
                if source_dir.is_relative_to(output):
                    continue
                try:
                    receipt = read(receipt_path)
                    report = read(source_dir / "asr-report.json")
                    if (receipt.get("status") != "completed" or receipt.get("cache_key") != job["cache_key"]
                            or report.get("cache_key") != job["cache_key"] or content_findings(report)):
                        continue
                    audio = source_dir / "voices-only.wav"
                    audio_hash = sha(audio)
                    if receipt.get("wav_sha256") != audio_hash or report.get("audio_sha256") != audio_hash:
                        continue
                    if require_story_audio_duration(self.config(), audio) != receipt["duration_ms"]:
                        continue
                except (OSError, ValueError, KeyError, wave.Error, EOFError):
                    continue
                destination.mkdir(parents=True, exist_ok=True)
                for filename in ("voices-only.wav", "generation.json", "asr-report.json"):
                    with (source_dir / filename).open("rb") as original, (destination / filename).open("xb") as target:
                        shutil.copyfileobj(original, target)
                write_json(destination / "reuse.json", {
                    "cache_key": job["cache_key"], "source_directory": source_dir.relative_to(self.root).as_posix(),
                    "audio_sha256": audio_hash, "local_generation_calls_this_run": 0,
                    "paid_calls": 0, "network_calls": 0, "source_files_unchanged": True,
                }, exclusive=True)
                reused += 1
                break
        return reused


    def audit(self, brief: dict, plan: dict) -> dict:
        self.validate_plan(brief, plan)
        ready = [job for job in plan["jobs"] if self.cached(brief, job)]
        if not ready:
            raise ValueError("At least one complete current take is required before ASR audit")
        waiting = len(plan["jobs"]) - len(ready)
        pending = [job for job in ready if not (self.job_dir(brief, job) / "asr-report.json").exists()]
        rechecks = [job for job in ready
                    if (self.job_dir(brief, job) / "asr-report.json").exists()
                    and not (self.job_dir(brief, job) / "asr-tail-check.json").exists()
                    and asr_tail_candidate(job, read(self.job_dir(brief, job) / "asr-report.json"))]
        if not pending and not rechecks:
            return {"asr_calls_pending": 0, "cached": len(ready), "stories_waiting_for_audio": waiting}
        offline()
        sys.path.insert(0, str(self.project_config.work_dir / "local-audio/asr-runtime"))
        from faster_whisper import WhisperModel

        cache = Path.home() / ".cache/huggingface/hub/models--Systran--faster-whisper-small/snapshots"
        candidates = [p for p in cache.iterdir() if (p / "model.bin").is_file()]
        if len(candidates) != 1:
            raise ValueError("Expected exactly one existing cached ASR model; no downloads allowed")
        model = WhisperModel(str(candidates[0]), device="cpu", compute_type="int8", cpu_threads=4, local_files_only=True)
        results = []
        for job in pending:
            directory = self.job_dir(brief, job)
            audio = directory / "voices-only.wav"
            segments, _ = model.transcribe(str(audio), language="en", beam_size=5, vad_filter=False,
                                           condition_on_previous_text=False, word_timestamps=True)
            rows = []
            for segment in segments:
                rows.append({"start_s": segment.start, "end_s": segment.end, "text": segment.text.strip(),
                             "words": [{"word": w.word, "start_s": w.start, "end_s": w.end}
                                       for w in segment.words or []]})
                print(f"ASR {job['title']}: {segment.end:.1f}s", flush=True)
            recognized = " ".join(row["text"] for row in rows)
            report = {"cache_key": job["cache_key"], "audio_sha256": sha(audio), "segments": rows,
                      "recognized_text": recognized, **compare_text(job["text"], recognized),
                      "asr_model": "Systran/faster-whisper-small", "asr_revision": candidates[0].name,
                      "device": "cpu", "paid_calls": 0, "network_calls": 0,
                      "limits": "ASR is diagnostic, not editorial or listening approval. It can mishear names. Emotion, accent, pauses and perceived speaker consistency require listening."}
            report["content_findings"] = content_findings(report)
            write_json(directory / "asr-report.json", report, exclusive=True)
            results.append({"title": job["title"], "sequence_match_ratio": report["sequence_match_ratio"],
                            "differences": report["differences"]})
            if asr_tail_candidate(job, report):
                rechecks.append(job)
        tail_results = []
        for job in rechecks:
            directory = self.job_dir(brief, job)
            original_path = directory / "asr-report.json"
            report = read(original_path)
            candidate = asr_tail_candidate(job, report)
            audio_path = directory / "voices-only.wav"
            if sha(audio_path) != report["audio_sha256"] or report["cache_key"] != job["cache_key"]:
                raise ValueError("Stale audio for ASR tail check")
            from .speech_mastering import read_wave
            from scipy.signal import resample_poly
            samples, rate = read_wave(audio_path)
            divisor = math.gcd(rate, 16000)
            closing_audio = resample_poly(samples[round(candidate["start_s"] * rate):],
                                          16000 // divisor, rate // divisor).astype("float32")
            segments, _ = model.transcribe(closing_audio, language="en", beam_size=5,
                                           vad_filter=False, condition_on_previous_text=False,
                                           word_timestamps=True)
            rows = [{"start_s": s.start + candidate["start_s"],
                     "end_s": s.end + candidate["start_s"], "text": s.text.strip()} for s in segments]
            check = {"audio_sha256": report["audio_sha256"], "cache_key": job["cache_key"],
                     "original_asr_sha256": sha(original_path), "start_s": candidate["start_s"],
                     "segments": rows, "recognized_text": " ".join(s["text"] for s in rows),
                     "asr_model": report["asr_model"], "asr_revision": candidates[0].name,
                     "script_prompt_supplied": False, "device": "cpu", "audio_modified": False,
                     "paid_calls": 0, "network_calls": 0}
            if sha(audio_path) != report["audio_sha256"]:
                raise ValueError("Audio changed during ASR tail check")
            check_path = directory / "asr-tail-check.json"
            write_json(check_path, check, exclusive=True)
            try:
                derived = tail_checked_report(job, report, check, sha(original_path), sha(check_path))
            except ValueError:
                tail_results.append({"title": job["title"], "status": "unresolved_hold_retained"})
                continue
            write_json(directory / "asr-report-tail-checked.json", derived, exclusive=True)
            tail_results.append({"title": job["title"], "status": "exact_closing_passage_recovered",
                                 "original_asr_and_audio_preserved": True})
        return {"audited": results, "tail_rechecks": tail_results, "stories_waiting_for_audio": waiting}


    def package(self, brief: dict, plan: dict) -> dict:
        self.validate_plan(brief, plan)
        from home_podcast.providers.qwen_tts import _write_captions
        from home_podcast.speech_mastering import load_settings, master_speech_for_playback

        _, output = self.paths(brief)
        cards, summaries = [], []
        for job in plan["jobs"]:
            if not self.cached(brief, job):
                raise ValueError("Missing current complete take")
            directory = self.job_dir(brief, job)
            report_path = effective_asr_path(directory, job)
            report = read(report_path)
            receipt = read(directory / "generation.json")
            if report["audio_sha256"] != receipt["wav_sha256"] or report["cache_key"] != job["cache_key"]:
                raise ValueError("Stale ASR audit")
            if content_findings(report):
                raise ValueError(f"Hold {job['title']}: possible missing/repeated speech; review before packaging")
            settings = load_settings(self.root)
            if settings["enabled"]:
                mastered = master_speech_for_playback(directory / "voices-only.wav", directory / "mastered",
                                                      settings, asr_path=report_path)
                listening_path = Path(mastered["audio_path"])
                listening = {**inspect_wave(listening_path), "mastering_cache_key": mastered["cache_key"]}
            else:
                listening = listening_copy(directory)
                listening_path = directory / "listening.wav"
            rows = caption_rows(report["segments"], receipt["duration_ms"])
            _write_captions(directory, rows)
            (directory / "transcript.txt").write_text(job["text"] + "\n", encoding="utf-8")
            (directory / "transcript-asr.txt").write_text(report["recognized_text"] + "\n", encoding="utf-8")
            write_json(directory / "casting-and-performance.json", job["casting_card"])
            write_json(directory / "caption-timing.json", {"audio_sha256": receipt["wav_sha256"],
                       "listening_audio_sha256": listening["wav_sha256"], "identical_audio_frame_timing": True, "captions": rows,
                       "timing_source": "CPU Whisper word timestamps, not estimated script timing",
                       "caption_text_source": (
                           "ASR with human-confirmed passage recovery and measured excerpt timings; remaining wording uncorrected"
                           if report.get("asr_span_resolution") else
                           "ASR with explicit human-confirmed false-outro removal; remaining wording uncorrected"
                           if report.get("asr_tail_resolution", {}).get("kind") == "human_confirmed_unspoken_asr_outro"
                           else "Uncorrected ASR; compare with exact narration transcript"),
                       "manually_verified": False})
            duration = receipt["duration_ms"] / 1000
            display_seconds = round(duration)
            prefix = directory.relative_to(output).as_posix()
            playback_prefix = listening_path.relative_to(output).as_posix()
            e = html.escape
            differences = report["differences"]
            diff_items = "".join(f"<li>{e(d['expected'])} → {e(d['recognized'])} ({e(d['kind'])})</li>" for d in differences)
            if report.get("asr_span_resolution"):
                diff_items += ("<li>You confirmed hearing the sentence missed by full-file recognition. "
                               "An unprompted excerpt check recovered its exact words and measured timings. "
                               "Only the derived ASR/captions are repaired; the original report and full "
                               "recording remain unchanged. Full performance and caption review are still pending.</li>")
            if report.get("asr_tail_resolution"):
                if report["asr_tail_resolution"].get("kind") == "human_confirmed_unspoken_asr_outro":
                    diff_items += ("<li>You confirmed the story stops at its intended ending. "
                                   "An unprompted closing-audio check agrees. The false recognized outro "
                                   "is excluded only from this derived ASR/caption edition. The original "
                                   "recognition and complete recording remain unchanged. This narrow "
                                   "ending check is not full performance or caption approval.</li>")
                else:
                    diff_items += ("<li>The full-file recognizer added an impossible-timed outro. "
                                   "An unprompted closing-audio recheck recovered the exact story ending. "
                                   "Both reports and the unchanged audio are preserved; please still listen.</li>")
            cards.append(f'''<article><h2>{e(job['title'])}</h2>
    <p class="meta">{display_seconds//60}:{display_seconds%60:02d} · {job['duration_preflight']['spoken_words']} words · {e(job['casting_card']['voice_label'])}</p>
    <audio controls preload="metadata" src="{playback_prefix}"></audio>
    <p><a href="{playback_prefix}">Listening WAV</a> · <a href="{prefix}/voices-only.wav">Unchanged original WAV</a> · <a href="{prefix}/transcript.txt">Narration transcript</a> · <a href="{prefix}/captions.srt">SRT</a> · <a href="{prefix}/captions.vtt">VTT</a></p>
    <p>{e(job['casting_card']['casting_note'])}</p>
    <details><summary>Story text</summary><div class="story">{e(job['text'])}</div></details>
    <details><summary>Performance direction</summary><p>{e(job['casting_card']['performance_direction'])}</p></details>
    <details><summary>Speech-recognition check: {report['sequence_match_ratio']:.1%} sequence agreement</summary>
    <p>This compares automatic recognition with the script, not a listening score. Names and punctuation can differ. Captions currently contain the recognized wording.</p><ul>{diff_items}</ul></details></article>''')
            summaries.append({"narration_id": job["narration_id"], "title": job["title"], "duration_ms": receipt["duration_ms"],
                              "audio_sha256": receipt["wav_sha256"], "audio_path": str(directory / "voices-only.wav"),
                              "listening_audio_sha256": listening["wav_sha256"], "listening_audio_path": str(listening_path),
                              "mastering_cache_key": listening.get("mastering_cache_key"),
                              "asr_report_file": report_path.name,
                              "asr_tail_resolution": report.get("asr_tail_resolution"),
                              "asr_span_resolution": report.get("asr_span_resolution"),
                              "sequence_match_ratio": report["sequence_match_ratio"], "caption_cues": len(rows),
                              "listening_approval": "pending", "caption_editorial_approval": "pending"})
        page = '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Recovered Homes — __STORY_COUNT__ complete short stories</title><style>
    body{margin:0;background:#101b21;color:#e8eeee;font:17px/1.65 system-ui,sans-serif}main{max-width:900px;margin:48px auto;padding:0 24px}h1{line-height:1.2}h2{margin-top:0}a{color:#9de1d6}article{padding:26px;margin:28px 0;background:#1c2a32;border:1px solid #334650;border-radius:16px}audio{width:100%;margin:8px 0}.meta{color:#b6c8d2}.story{white-space:pre-wrap;margin-top:18px}summary{cursor:pointer;padding:8px 0}li{overflow-wrap:anywhere}</style>
    <main><h1>__STORY_COUNT__ complete short stories</h1><p>One continuous VoiceDesign take per story. No section stitching, time compression or audio truncation. All recordings are measured under five minutes, including pauses and tail silence.</p>
    <p>The players use listening copies made with the project's speech-level settings. Slow volume automation corrects gradual drift when enabled. Timing, pauses and original unmodified WAVs are preserved.</p>
    <p>Please listen for a consistent person throughout, natural emotion and pauses, comfortable volume, and whether the ending feels complete. These takes await your approval. The exact narration transcript and automatic, audio-timed captions are separate files.</p>'''
        page = page.replace("__STORY_COUNT__", str(len(plan["jobs"])))
        (output / "index.html").write_text(page + "".join(cards) + "</main></html>\n", encoding="utf-8")
        result = {"run_id": brief["run_id"], "stories": summaries, "canonical_assets_replaced": False,
                  "paid_calls": 0, "network_calls": 0, "bulk_production_authorized": False,
                  "preserved_originals": len(plan["protected_sha256"])}
        write_json(output / "manifest.json", result)
        return result


    def verify(self, brief: dict, plan: dict, *, preservation: bool = True, save: bool = True) -> dict:
        from home_podcast.providers.qwen_tts import _timestamp
        self.validate_plan(brief, plan, preservation=preservation)
        _, output = self.paths(brief)
        manifest = read(output / "manifest.json")
        if len(manifest["stories"]) != len(plan["jobs"]):
            raise ValueError("Incomplete package manifest")
        for job, summary in zip(plan["jobs"], manifest["stories"]):
            if summary.get("narration_id") != job["narration_id"]:
                raise ValueError("Package story order or identity changed")
            directory = self.job_dir(brief, job)
            if not self.cached(brief, job) or sha(directory / "voices-only.wav") != summary["audio_sha256"]:
                raise ValueError("Invalid audio package")
            generation = read(directory / "generation.json")
            if summary["duration_ms"] != generation["duration_ms"] or not 0 < summary["duration_ms"] <= 300000:
                raise ValueError("Package duration differs from the complete under-five-minute take")
            report_path = effective_asr_path(directory, job)
            report = read(report_path)
            if summary.get("asr_report_file", "asr-report.json") != report_path.name:
                raise ValueError("Package ASR report identity changed")
            if (content_findings(report) or report.get("audio_sha256") != summary["audio_sha256"]
                    or report.get("cache_key") != job["cache_key"]):
                raise ValueError("Unresolved or stale speech-content audit")
            if (directory / "transcript.txt").read_text(encoding="utf-8").strip() != job["text"]:
                raise ValueError("Transcript is not the exact approved story")
            if summary.get("mastering_cache_key"):
                playback = Path(summary["listening_audio_path"])
                mastering = read(playback.parent / "mastering.json")
                if (mastering.get("cache_key") != summary["mastering_cache_key"]
                        or mastering.get("status") != "ready"
                        or mastering["identity"]["raw_audio_sha256"] != summary["audio_sha256"]
                        or mastering["identity"].get("asr_sha256") != sha(report_path)
                        or mastering["metrics"]["quality_findings"]
                        or sha(playback) != mastering["audio_sha256"]):
                    raise ValueError("Invalid mastered playback copy")
                listening = inspect_wave(playback)
            else:
                listening = listening_copy(directory)
            if listening["wav_sha256"] != summary["listening_audio_sha256"] or listening["duration_ms"] != summary["duration_ms"]:
                raise ValueError("Invalid listening copy")
            caption_data = read(directory / "caption-timing.json")
            if caption_data["audio_sha256"] != summary["audio_sha256"]:
                raise ValueError("Stale caption audio hash")
            if caption_data.get("listening_audio_sha256") != summary["listening_audio_sha256"]:
                raise ValueError("Stale caption listening-copy hash")
            expected_rows = caption_rows(report["segments"], summary["duration_ms"])
            if caption_data["captions"] != expected_rows or summary["caption_cues"] != len(expected_rows):
                raise ValueError("Caption content no longer matches the audited audio")
            last_end = 0
            for row in caption_data["captions"]:
                if not 0 <= last_end <= row["start_ms"] < row["speech_end_ms"] <= summary["duration_ms"]:
                    raise ValueError("Invalid or overlapping caption times")
                last_end = row["speech_end_ms"]
            for filename in ("captions.srt", "captions.vtt", "transcript-asr.txt", "casting-and-performance.json"):
                if not (directory / filename).is_file():
                    raise ValueError("Missing package artifact")
            if ((directory / "transcript-asr.txt").read_text(encoding="utf-8").strip() != report["recognized_text"]
                    or read(directory / "casting-and-performance.json") != job["casting_card"]):
                raise ValueError("Package transcript or casting metadata changed")
            for extension in ("srt", "vtt"):
                vtt = extension == "vtt"
                lines = ["WEBVTT", ""] if vtt else []
                for index, row in enumerate(expected_rows, 1):
                    lines.extend([str(index),
                                  f"{_timestamp(row['start_ms'], vtt=vtt)} --> {_timestamp(row['speech_end_ms'], vtt=vtt)}",
                                  re.sub(r"\s+", " ", row["text"]).strip(), ""])
                if (directory / f"captions.{extension}").read_text(encoding="utf-8") != "\n".join(lines):
                    raise ValueError("Caption file changed; editorial corrections need a separate reviewed edition")
        result = {"stories_verified": len(plan["jobs"]), "maximum_duration_ms": 300000,
                  "all_under_limit": True,
                  "originals_verified_unchanged": len(plan["protected_sha256"]) if preservation else None,
                  "verification_scope": "complete_preservation" if preservation else "current_jobs_and_packaged_audio",
                  "listening_review": "pending", "caption_editorial_review": "pending"}
        if save:
            write_json(self.paths(brief)[0] / "verification.json", result)
        return result

    def approve(self, brief: dict, plan: dict, *, reviewer: str, note: str) -> dict:
        """Record an explicit human listening decision, without altering old assets."""
        if not reviewer.strip() or not note.strip():
            raise ValueError("Listening approval requires a reviewer and the user's decision")
        self.verify(brief, plan, preservation=False, save=False)
        _, output = self.paths(brief)
        manifest_path = output / "manifest.json"
        manifest = read(manifest_path)
        records = []
        for job, item in zip(plan["jobs"], manifest["stories"]):
            records.append({"narration_id": job["narration_id"], "cache_key": job["cache_key"],
                            "adaptation_sha256": job["adaptation_sha256"],
                            "source_job_sha256": job["source_job_sha256"],
                            "editorial_review_sha256": job["editorial_review_sha256"],
                            "raw_audio_sha256": item["audio_sha256"],
                            "listening_audio_sha256": item["listening_audio_sha256"],
                            "listening_audio": Path(item["listening_audio_path"]).relative_to(self.root).as_posix(),
                            "listening_approval": "approved_by_user", "caption_editorial_approval": "pending"})
        identity = {"contract_version": 1, "run_id": brief["run_id"], "reviewer": reviewer,
                    "user_decision": note, "manifest_sha256": sha(manifest_path), "stories": records}
        destination = self.project_config.work_dir / "local-audio/approvals" / (brief["run_id"] + ".json")
        if destination.exists():
            existing = read(destination)
            if any(existing.get(key) != value for key, value in identity.items()):
                raise ValueError("Existing approval differs; preserve it and review explicitly")
            return existing
        result = {**identity, "approved_at": datetime.now(timezone.utc).isoformat(),
                  "originals_modified": False, "model_loads": 0, "paid_calls": 0, "network_calls": 0}
        write_json(destination, result, exclusive=True)
        return result

    def quality(self, brief: dict, plan: dict) -> dict:
        """Incrementally validate and master completed takes; never generate speech."""
        from .speech_mastering import load_settings, master_speech_for_playback
        self.validate_plan(brief, plan)
        settings = load_settings(self.root)
        rows = []
        for job in plan["jobs"]:
            directory = self.job_dir(brief, job)
            row = {"narration_id": job["narration_id"], "title": job["title"]}
            if not self.cached(brief, job):
                attempt = directory / "attempt.json"
                if (directory / "generation.json").exists():
                    row["status"] = "held_invalid_cached_audio"
                elif attempt.exists():
                    state = read(attempt).get("status", "")
                    row["status"] = state if state in {"generating", "failed", "held_quality"} else "held_incomplete_attempt"
                elif directory.exists() and any(directory.iterdir()):
                    row["status"] = "held_partial_output"
                else:
                    row["status"] = "pending_generation"
                rows.append(row)
                continue
            receipt = read(directory / "generation.json")
            row.update(status="pending_asr", duration_ms=receipt["duration_ms"], audio_sha256=receipt["wav_sha256"])
            report_path = effective_asr_path(directory, job)
            if report_path.exists():
                report = read(report_path)
                if report["audio_sha256"] != receipt["wav_sha256"] or report["cache_key"] != job["cache_key"]:
                    raise ValueError("Stale ASR report")
                findings = content_findings(report)
                row.update(status="held_for_content_review" if findings else "content_check_passed",
                           content_findings=findings, sequence_match_ratio=report["sequence_match_ratio"])
                if not findings:
                    try:
                        rows_timed = caption_rows(report["segments"], receipt["duration_ms"])
                        if settings["enabled"]:
                            mastered = master_speech_for_playback(directory / "voices-only.wav", directory / "mastered",
                                                                  settings, asr_path=report_path)
                            metrics = mastered["metrics"]
                            row.update(mastering_cache_key=mastered["cache_key"],
                                       speech_rms_dbfs=metrics["after"]["speech_rms_dbfs"],
                                       end_minus_start_db=metrics["after"]["end_minus_start_db"],
                                       peak_dbfs=metrics["four_times_oversampled_peak_dbfs"])
                        else:
                            listening_copy(directory)
                        row.update(status="ready_for_listening_package", caption_cues=len(rows_timed))
                    except ValueError as error:
                        row.update(status="held_for_finishing_review", reason=str(error))
            rows.append(row)
        result = {"run_id": brief["run_id"], "scope_stories": len(rows), "stories": rows,
                  "generated": sum("duration_ms" in row for row in rows),
                  "ready": sum(row["status"] == "ready_for_listening_package" for row in rows),
                  "held": sum(row["status"].startswith("held") or row["status"] == "failed" for row in rows),
                  "originals_verified_unchanged": len(plan["protected_sha256"]),
                  "listening_review": "pending", "caption_editorial_review": "pending",
                  "tts_calls": 0, "paid_calls": 0, "network_calls": 0}
        write_json(self.paths(brief)[0] / "quality.json", result)
        return result

    def queue(self, production_index: Path, *, limit: int = 25) -> dict:
        """Select reviewed, not-yet-recorded stories; casting is still an editorial task."""
        if limit <= 0:
            raise ValueError("Queue limit must be positive")
        existing_ids = set()
        for path in self.project_config.audio_dir.rglob("generation.json"):
            item = read(path)
            if item.get("narration_id"):
                existing_ids.add(item["narration_id"])
        selected, deferred, seen_text, seen_source, seen_witness = [], [], set(), set(), set()
        for item in read(production_index).get("narrations", []):
            story_id = item["narration_id"]
            if not re.fullmatch(NARRATION_ID, story_id):
                raise ValueError("Invalid story ID in index")
            directory = self.project_config.episodes_dir / story_id
            if item.get("readiness") != "ready_for_voice_audition":
                deferred.append({"narration_id": story_id, "reason": "not_editorially_ready"})
                continue
            try:
                review = require_personal_story(directory)
                adaptation, source = read(directory / "adaptation.json"), read(directory / "source-job.json")
                valid = validate_storytelling_adaptation_data(adaptation, source)
                if not valid["valid"]:
                    raise ValueError("Invalid adaptation")
                budget = require_story_text_budget(self.config(), adaptation)
            except ValueError:
                deferred.append({"narration_id": story_id, "reason": "current_editorial_or_duration_gate"})
                continue
            text = " ".join(section["text"] for section in adaptation["sections"])
            text_key = hashlib.sha256(re.sub(r"\s+", " ", text).strip().encode()).hexdigest()
            source_key = (item.get("source_url"), adaptation["title"].casefold())
            analysis = review["reviewed_analysis"]
            witness_key = (adaptation["title"].casefold(), analysis["narrator_evidence"],
                           analysis["personal_experience_evidence"])
            duplicate = (text_key in seen_text or (source_key[0] and source_key in seen_source)
                         or witness_key in seen_witness)
            seen_text.add(text_key)
            seen_witness.add(witness_key)
            if source_key[0]:
                seen_source.add(source_key)
            if story_id in existing_ids:
                deferred.append({"narration_id": story_id, "reason": "existing_take_preserved"})
            elif duplicate:
                deferred.append({"narration_id": story_id, "reason": "duplicate_candidate_review_separately"})
            elif len(selected) < limit:
                selected.append({"narration_id": story_id, "title": adaptation["title"],
                                 "source_language": adaptation["source_language"],
                                 "spoken_words": budget["spoken_words"],
                                 "source_characters": len(source["story_text"]),
                                 "adaptation_sha256": content_digest(adaptation),
                                 "source_job_sha256": content_digest(source),
                                 "editorial_review_sha256": content_digest(review)})
        result = {"selected": selected, "deferred": deferred, "selected_count": len(selected),
                  "casting_review": "required_before_prepare", "model_loads": 0, "paid_calls": 0,
                  "network_calls": 0, "selection_policy": "Approved index order; existing takes and exact-text, same-source/title or identical reviewed witness/title duplicate candidates are not regenerated."}
        write_json(self.project_config.work_dir / "local-audio/next-queue.json", result)
        return result
