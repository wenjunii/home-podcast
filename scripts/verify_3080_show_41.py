"""Read-only preflight for the exact approved 3080 .41 show, without TouchDesigner."""

from __future__ import annotations

import argparse
import json
import sys
import wave
from pathlib import Path

from home_podcast import private_handoff as h

ROOT = Path(__file__).resolve().parents[1]
TOE_SHA = "f664af7ac69ea0edc881dd9466673d3497f1d204f1e1598c0c1aea69ee306a21"
PLAYLIST_SHA = "f5ad745b8e36a4406ce6098c4036b88d78d6c31321c7603e41260508ea307326"
RECEIPTS = {
    "approval": "852309aa7dd847dd2b81865a4f5d7841223668a78ab607d49ac76344abddc7d6",
    "assembly-verification": "cf81675b2c57dfede3167b3563b20b6ea37995175093f12f39da161730ecdff6",
    "delivery": "e9cd45f2ddb134d75a6b635c62dbfdeffbde695431b1b033c08ce8e8a199951d",
    "native-reopen": "97f7def3475665aafd320c1a0953f9b52f8ab696a41c32fe81484936028402dc",
}
BUILD = "2025.32820"
STORIES, SCENES, CAPTIONS = 136, 619, 2862
DURATION_MS, GAP_MS, MIN_SCENE_MS = 11_938_720, 1000, 5000
AUDIO_MODES = ("voices_only", "soundscape_only", "combined")
VISUAL_PATHS = ("original", "human_figures", "balanced")
CAPTION_BASE = f"audio/{h.APPROVED.removeprefix('work/')}/playlist-captions"


class CheckError(ValueError):
    """Failure message contains only a fixed check name, never artifact content."""


def require(condition, message):
    if not condition:
        raise CheckError(message)


def asset(root, name, label):
    try:
        path = h.checked_path(root, name)
    except h.HandoffError as error:
        raise CheckError(f"Unsafe {label} path.") from error
    require(path.is_file(), f"Missing {label}.")
    return path


def pinned_json(root, name, digest, label):
    data = asset(root, name, label).read_bytes()
    require(h.digest_bytes(data) == digest, f"{label} does not match the approved hash.")
    value = json.loads(data)
    require(isinstance(value, dict), f"Invalid {label} object.")
    return value


def verify_story_clock(rows, duration_ms):
    """Check the shared interval clock, including the last gap before the loop."""
    by_id = {}
    previous_end = 0
    for index, row in enumerate(rows, 1):
        start, content_end, end = (row[k] for k in ("start_ms", "content_end_ms", "end_ms"))
        require(
            all(type(t) is int for t in (start, content_end, end))
            and row["number"] == index and start == previous_end and start < content_end
            and end - content_end == row["gap_after_ms"] == GAP_MS
            and end - start == row["duration_ms"]
            and content_end - start == row["narration_duration_ms"] <= 300_000,
            f"Story {index} has an invalid content boundary, duration or one-second gap.",
        )
        key = row["narration_id"]
        require(isinstance(key, str) and key and key not in by_id, f"Invalid story ID at {index}.")
        by_id[key] = row
        previous_end = end
    require(by_id and previous_end == duration_ms, "The final gap and playlist loop clocks differ.")
    return by_id


def check_intervals(items, by_id, id_field, label):
    """Ordered, distinct, nonoverlapping cues wholly inside their own narration."""
    last_end = 0
    seen = set()
    covered = set()
    for index, item in enumerate(items, 1):
        key = item["narration_id"]
        ident = item[id_field]
        row = by_id.get(key)
        start, end = item["start_ms"], item["end_ms"]
        require(row is not None and isinstance(ident, str) and ident.startswith(key + "--")
                and ident not in seen and type(start) is int and type(end) is int
                and max(last_end, row["start_ms"]) <= start < end <= row["content_end_ms"],
                f"{label} cue {index} overlaps, is out of order, or leaves its narration.")
        last_end = end
        seen.add(ident)
        covered.add(key)
    require(covered == by_id.keys(), f"{label} does not cover every story.")


def verify_visual_path(plan, mode, manifest, by_id):
    entry = manifest["plans"][mode]
    audio = manifest["audio"]
    require(plan["visual_path"]["id"] == mode and plan["playlist_stories"] == manifest["stories"]
            and plan["duration_ms"] == manifest["duration_ms"]
            and plan["touchdesigner_version"] == BUILD and plan["project_variant"] == "3080"
            and plan["human_visual_approval"] == "approved_by_user" and plan["executable"] is True,
            f"Visual path {mode} is not the approved .41 story clock.")
    require(plan["audio_file"] == audio["voices_only"]
            and plan["soundscape_audio_file"] == audio["soundscape_only"]
            and plan["combined_audio_file"] == audio["combined"]
            and plan["audio_sha256"] == manifest["audio_sha256"],
            f"Visual path {mode} references a different audio edition.")
    policy = plan["prompt_policy"]
    require(policy["minimum_scene_duration_ms"] == MIN_SCENE_MS
            and policy["content_token_limit"] == 75
            and policy["crossfade_policy"] == "post_onset_no_future_preview"
            and plan["five_second_opening_edition"] is True
            and plan["hold_visual_gaps_edition"] is True
            and plan["abstract_transition_intervals_inactive"] is True
            and plan["all_join_interpolation_edition"] is True
            and plan["output_edge_fades"]["default_ms"] == 0
            and plan["story_transition_policy"] == "continuous_post_onset_crossfade"
            and plan["loop_transition_policy"] == "post_onset_prompt_seed_interpolation"
            and plan["story_crossfade_ms"] == manifest["default_story_crossfade_ms"] == 3000,
            f"Visual path {mode} has the wrong .41 gap, interpolation or five-second policy.")

    scenes, captions = plan["scenes"], plan["captions"]
    require(len(scenes) == entry["scenes"] and len(captions) == entry["captions"],
            f"Visual path {mode} has a different scene or caption count.")
    check_intervals(scenes, by_id, "scene_id", f"{mode} scene")
    check_intervals(captions, by_id, "caption_id", f"{mode} caption")
    openings = set()
    short = 0
    for index, scene in enumerate(scenes, 1):
        key = scene["narration_id"]
        start = scene["start_ms"]
        length = scene["end_ms"] - start
        require(length == scene["duration_ms"] >= MIN_SCENE_MS,
                f"{mode} scene {index} is shorter than five seconds or has an inconsistent clock.")
        short += length < 15_000
        if key not in openings:
            require(start == by_id[key]["start_ms"] and scene["opening_context_exception"] is True,
                    f"{mode} story opening {len(openings) + 1} is not at its boundary.")
            openings.add(key)
        require(all(type(gate["not_before_ms"]) is int and gate["not_before_ms"] <= start
                    for gate in scene["material_gates"]),
                f"{mode} scene {index} starts before recorded speech evidence.")
        chunks = scene["prompt"]["chunks"]
        require(chunks and all(type(c["content_token_count"]) is int
                              and 68 <= c["content_token_count"] <= 75 for c in chunks),
                f"{mode} scene {index} has a chunk outside the recorded SDXL token budget.")
    require(all(isinstance(c["text"], str) and c["text"].strip() for c in captions),
            f"Visual path {mode} contains an empty caption.")
    return {
        "scenes": len(scenes), "under_15_seconds": short, "captions": len(captions),
        "story_openings": len(openings), "within_story_joins": len(scenes) - len(openings),
        "between_story_joins": len(openings) - 1, "loop_clock_aligned": True,
    }


def same_visual_clock(reference, candidate, mode):
    def scene_clock(plan):
        return [(s["narration_id"], s["start_ms"], s["end_ms"]) for s in plan["scenes"]]

    require(scene_clock(reference) == scene_clock(candidate)
            and reference["captions"] == candidate["captions"],
            f"Visual path {mode} changes the approved scene or caption clock.")


def timestamp(ms, separator):
    hours, ms = divmod(ms, 3_600_000)
    minutes, ms = divmod(ms, 60_000)
    seconds, ms = divmod(ms, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}{separator}{ms:03d}"


def verify_caption_export(path, kind, cues):
    blocks = path.read_text(encoding="utf-8-sig").strip().split("\n\n")
    if kind == "vtt":
        require(blocks[0] == "WEBVTT", "Missing VTT header.")
        blocks = blocks[1:]
    require(len(blocks) == len(cues), f"{kind.upper()} has a different caption count.")
    separator = "," if kind == "srt" else "."
    for index, (block, cue) in enumerate(zip(blocks, cues, strict=True), 1):
        rows = block.splitlines()
        start, end = (timestamp(cue[k], separator) for k in ("start_ms", "end_ms"))
        require(len(rows) >= 3 and rows[0] == str(index) and rows[1] == f"{start} --> {end}"
                and " ".join(rows[2:]) == cue["text"],
                f"{kind.upper()} caption {index} does not match the approved text and clock.")
    return len(cues)


def verify_wave(path, mode, stories, duration_ms, digest):
    frames_per_ms = 48
    frames = duration_ms * frames_per_ms
    silent = bytes(GAP_MS * frames_per_ms * 4)  # stereo × 16-bit
    try:
        with wave.open(str(path), "rb") as audio:
            require((audio.getframerate(), audio.getnchannels(), audio.getsampwidth(),
                     audio.getcomptype(), audio.getnframes()) == (48_000, 2, 2, "NONE", frames),
                    f"{mode} WAV format or frame count differs from the approved clock.")
            for index, story in enumerate(stories, 1):
                audio.setpos(story["content_end_ms"] * frames_per_ms)
                require(audio.readframes(GAP_MS * frames_per_ms) == silent,
                        f"{mode} WAV gap after story {index} is not exactly one second of silence.")
    except (wave.Error, EOFError) as error:
        raise CheckError(f"Invalid {mode} WAV header or data.") from error
    require(h.sha(path) == digest, f"{mode} WAV does not match the approved hash.")
    return {"pcm_frames": frames, "silent_gaps": len(stories), "sha256_verified": True}


def verify(root=ROOT):
    require(h.sha(asset(root, h.TOE_41, "podcast.41.toe")) == TOE_SHA,
            "podcast.41.toe does not match the approved native hash.")
    manifest = pinned_json(root, h.PLAYLIST_41, PLAYLIST_SHA, ".41 playlist")
    receipts = {name: pinned_json(root, f"{h.EDITION_41}/{name}.json", digest, f"{name} receipt")
                for name, digest in RECEIPTS.items()}
    reopen = receipts["native-reopen"]
    require(manifest["target_toe"] == h.TOE_41 and manifest["profile"] == "3080_safe"
            and manifest["gap_colour_enabled"] is False and manifest["executable"] is True
            and manifest["human_ambient_approval"] == "approved_by_user"
            and manifest["human_visual_approval"] == "approved_by_user"
            and manifest["story_count"] == len(manifest["stories"]) == STORIES
            and manifest["duration_ms"] == DURATION_MS
            and receipts["delivery"]["sha256"] == TOE_SHA
            and receipts["assembly-verification"]["manifest_sha256"] == PLAYLIST_SHA
            and receipts["approval"]["human_ambient_approval"] == "approved_by_user"
            and not reopen["failures"] and reopen["checks"] == reopen["passed"] == 70,
            "The approval records or active .41 scope do not match the verified delivery.")
    require(set(manifest["plans"]) == set(VISUAL_PATHS)
            and set(manifest["audio"]) == set(manifest["audio_sha256"]) == set(AUDIO_MODES),
            "The approved three visual paths and three audio tracks are required.")
    by_id = verify_story_clock(manifest["stories"], manifest["duration_ms"])

    visuals = {}
    reference = None
    runtime = set(h.RUNTIME_41)
    for mode in VISUAL_PATHS:
        entry = manifest["plans"][mode]
        require((entry["scenes"], entry["captions"]) == (SCENES, CAPTIONS),
                f"Unexpected approved {mode} scene or caption scope.")
        plan = pinned_json(root, entry["path"], entry["sha256"], f"{mode} visual plan")
        visuals[mode] = verify_visual_path(plan, mode, manifest, by_id)
        if reference is None:
            reference = plan
        else:
            same_visual_clock(reference, plan, mode)
        runtime.update((plan["sequencer_module"], plan["controller_module"]))
    captions = {kind: verify_caption_export(asset(root, f"{CAPTION_BASE}.{kind}", f"{kind} captions"),
                                           kind, reference["captions"]) for kind in ("srt", "vtt")}
    try:
        runtime_found = len(h.runtime_closure(Path(root), runtime))
    except h.HandoffError as error:
        raise CheckError("An approved playback script or its local dependency is missing/unsafe.") from error
    audio = {mode: verify_wave(asset(root, manifest["audio"][mode], f"{mode} WAV"), mode,
                              manifest["stories"], DURATION_MS, manifest["audio_sha256"][mode])
             for mode in AUDIO_MODES}
    return {
        "passed": True, "edition": "3080-41", "project": h.TOE_41, "saved_touchdesigner_build": BUILD,
        "stories": len(by_id), "duration_ms": DURATION_MS, "gap_ms": GAP_MS,
        "minimum_scene_ms": MIN_SCENE_MS, "audio": audio, "visual_paths": visuals,
        "caption_exports": captions, "runtime_scripts_present": runtime_found,
        "previous_native_checks_verified": reopen["passed"], "native_playback_retested": False,
        "writes": 0, "models_started": 0, "network_calls": 0,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT, help="Local .41 playback root")
    args = parser.parse_args(argv)
    try:
        print(json.dumps(verify(args.root), indent=2))
    except CheckError as error:
        print(f".41 preflight failed: {error}", file=sys.stderr)
        return 2
    except (OSError, SyntaxError, UnicodeError, ValueError, TypeError, KeyError, IndexError):
        print(".41 preflight failed: an input is unreadable or malformed (contents suppressed).",
              file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
