"""Verify the installed .41 audio-only overlay on the 5090 without rebinding it.

This uses the local staging receipt from the separate audio-only transfer, not
the 3080 playback backup. It neither installs assets nor grants new approval.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import stat
import sys
import wave


BASE_TOE = "podcast.5090.25.toe"
BASE_EDITION = "work/storytelling-real-december/continuous-image-hold-136-3080-2026-10-30"
BASE_PLAYLIST = f"{BASE_EDITION}/playlist.json"
OVERLAY = "work/5090-136/ambient-update-41-2026-11-24"
OVERLAY_PLAYLIST = f"{OVERLAY}/playlist.json"
RUNTIME = "work/5090-136/audio41-install-20261124/runtime"
NARRATION = "audio/storytelling-real-december/story-gap-136-3080-2026-10-30/voices-only.wav"
AUDIO = {
    "voices_only": NARRATION,
    "soundscape_only": f"{OVERLAY}/soundscape-only.wav",
    "combined": f"{OVERLAY}/narration-and-ambient.wav",
}
AUDIO_FIELDS = {
    "audio_file": NARRATION,
    "soundscape_audio_file": AUDIO["soundscape_only"],
    "combined_audio_file": AUDIO["combined"],
}
MODES = ("original", "human_figures", "balanced")
STORIES, DURATION_MS, RATE = 136, 11_938_720, 48_000
SCENES, CAPTIONS = 619, 2_862
MODULES = {
    "controller_module": f"{BASE_EDITION}/td_controller.py",
    "sequencer_module": f"{BASE_EDITION}/boundary_sequencer.py",
}


class OverlayError(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise OverlayError(message)


def checked_file(root, logical):
    # Only fixed edition paths constructed by this script reach this function.
    # Use lstat along the path so a linked directory cannot redirect a read.
    path = root
    for part in logical.split("/"):
        path /= part
        try:
            info = path.lstat()
        except OSError:
            raise OverlayError("Missing overlay dependency: " + logical) from None
        require(not stat.S_ISLNK(info.st_mode) and not (getattr(info, "st_file_attributes", 0) & 0x400),
                "Linked paths are not supported: " + logical)
    require(stat.S_ISREG(info.st_mode), "Expected a regular file: " + logical)
    return path


def check_hash(path, expected, label):
    require(isinstance(expected, str) and re.fullmatch(r"[a-f0-9]{64}", expected),
            "Missing recorded SHA-256: " + label)
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    require(digest.hexdigest() == expected, "SHA-256 mismatch: " + label)


def verify_wave(path, stories, mode):
    with wave.open(str(path), "rb") as stream:
        require((stream.getframerate(), stream.getnchannels(), stream.getsampwidth(), stream.getnframes())
                == (RATE, 2, 2, DURATION_MS * RATE // 1000),
                "Wrong PCM format or duration: " + mode)
        silence = bytes(RATE * 4)
        for story in stories:
            stream.setpos(story["content_end_ms"] * RATE // 1000)
            require(stream.readframes(RATE) == silence, "Expected an exact one-second silent gap: " + mode)


def without(document, excluded):
    return {key: value for key, value in document.items() if key not in excluded}


def verify_overlay(root):
    """Read only; compare the installed overlay with its verified .25 base."""
    root = Path(root).resolve()
    try:
        receipt = json.loads(checked_file(root, f"{OVERLAY}/staging-verification.json").read_text(encoding="utf-8-sig"))
        require(receipt.get("verified") is True and receipt.get("staged") is True
                and receipt.get("receiver_overlay_is_data_only") is True
                and receipt.get("receiver_overlay") == OVERLAY_PLAYLIST
                and receipt.get("receiver_base_toe") == BASE_TOE
                and receipt.get("receiver_base_playlist") == BASE_PLAYLIST
                and receipt.get("narration_path_unchanged") == NARRATION
                and (receipt.get("stories"), receipt.get("duration_ms"), receipt.get("audio_files"),
                     receipt.get("exact_silent_gaps_per_track")) == (STORIES, DURATION_MS, 2, STORIES),
                "A complete receiver audio-only staging receipt is required")
        protected = receipt["protected_sha256"]
        require(protected[BASE_TOE] == receipt["receiver_base_toe_sha256"]
                and protected[BASE_PLAYLIST] == receipt["receiver_base_playlist_sha256"],
                "The base hashes disagree in the staging receipt")
        check_hash(checked_file(root, BASE_TOE), protected[BASE_TOE], BASE_TOE)

        def verified_json(logical, expected):
            data = checked_file(root, logical).read_bytes()
            require(hashlib.sha256(data).hexdigest() == expected, "SHA-256 mismatch: " + logical)
            return json.loads(data)

        base = verified_json(BASE_PLAYLIST, protected[BASE_PLAYLIST])
        overlay = verified_json(OVERLAY_PLAYLIST, receipt["overlay_sha256"])
        ignored = {"audio", "audio_sha256", "plans", "native_installed"}
        require(without(overlay, ignored) == without(base, ignored),
                "Receiver overlay changed non-audio playlist data (including story clock)")
        stories = overlay["stories"]
        require(overlay["story_count"] == len(stories) == len({s["narration_id"] for s in stories}) == STORIES
                and overlay["duration_ms"] == DURATION_MS and overlay["profile"] == "3080_safe"
                and overlay["gap_colour_enabled"] is False and overlay["native_installed"] is False,
                "Wrong approved clock or cached-playback edition")
        end = 0
        for number, story in enumerate(stories, 1):
            require(story["number"] == number and story["start_ms"] == end
                    and end < story["content_end_ms"] == story["end_ms"] - 1000,
                    "Story boundary or one-second gap changed")
            end = story["end_ms"]
        require(end == DURATION_MS, "Story clock does not end at the approved duration")

        hashes = overlay["audio_sha256"]
        require(overlay["audio"] == AUDIO and set(hashes) == set(base["audio_sha256"]) == set(AUDIO)
                and base["audio"]["voices_only"] == NARRATION
                and hashes["voices_only"] == base["audio_sha256"]["voices_only"] == protected[NARRATION],
                "Audio routes or the original narration changed")
        require(all(hashes[k] != base["audio_sha256"][k] for k in ("soundscape_only", "combined")),
                "The overlay points to legacy ambient audio")

        require(set(base["plans"]) == set(overlay["plans"]) == set(MODES), "Expected three visual paths")
        for mode in MODES:
            old, new = base["plans"][mode], overlay["plans"][mode]
            old_path, new_path = (f"{folder}/{mode}-visual-scenes.json" for folder in (BASE_EDITION, OVERLAY))
            require((old["path"], new["path"]) == (old_path, new_path)
                    and old["sha256"] == protected[old_path]
                    and without(old, {"path", "sha256"}) == without(new, {"path", "sha256"}),
                    "Unexpected visual plan binding: " + mode)
            before = verified_json(old_path, old["sha256"])
            after = verified_json(new_path, new["sha256"])
            ignored = set(AUDIO_FIELDS) | {"audio_sha256"}
            require(without(before, ignored) == without(after, ignored)
                    and after["visual_path"]["id"] == mode and after["playlist_stories"] == stories
                    and after["duration_ms"] == DURATION_MS and after["hold_visual_gaps_edition"] is True
                    and len(after["scenes"]) == SCENES and len(after["captions"]) == CAPTIONS,
                    "Visuals, captions or timing changed: " + mode)
            require(all(after[key] == path for key, path in (AUDIO_FIELDS | MODULES).items())
                    and after["audio_sha256"] == hashes,
                    "Unexpected audio or controller references: " + mode)
        for logical in MODULES.values():
            checked_file(root, logical)
        for mode, logical in AUDIO.items():
            path = checked_file(root, logical)
            check_hash(path, hashes[mode], mode)
            verify_wave(path, stories, mode)
    except (OSError, KeyError, AttributeError, TypeError, ValueError, EOFError, wave.Error) as error:
        raise OverlayError(f"Cannot verify the receiver overlay ({type(error).__name__}); restore from the private transfer") from None
    return dict(passed=True, edition="canonical-136-audio-overlay", stories=STORIES, duration_ms=DURATION_MS,
                audio_tracks=len(AUDIO), exact_silent_gaps_per_track=STORIES, scenes_per_path=SCENES,
                captions=CAPTIONS, read_only=True)


def _binding_parameters():
    return {
        "Playlistmanifest": OVERLAY_PLAYLIST,
        "Audiofile": NARRATION,
        "Soundscapeaudiofile": AUDIO["soundscape_only"],
        "Combinedaudiofile": AUDIO["combined"],
        "Scenejson": f"{OVERLAY}/original-visual-scenes.json",
        "Canonicalvisuals": f"{OVERLAY}/original-visual-scenes.json",
        "Humanfigurejson": f"{OVERLAY}/human_figures-visual-scenes.json",
        "Canonicalhumanvisuals": f"{OVERLAY}/human_figures-visual-scenes.json",
        "Balancedjson": f"{OVERLAY}/balanced-visual-scenes.json",
        "Controllermodule": MODULES["controller_module"],
        "Sequencermodule": MODULES["sequencer_module"],
        "Livecontroljson": f"{RUNTIME}/control.json",
        "Livestatusjson": f"{RUNTIME}/status.json",
        "Livecurrentjson": f"{RUNTIME}/current.json",
    }


def verify_native_overlay(root, name, build, connector):
    """Check existing 5090 bindings, without running any installer or callback."""
    match = re.fullmatch(r"podcast\.5090\.([1-9]\d*)\.toe", name, re.I)
    require(match and int(match[1]) >= 26 and build == "2025.32820",
            "Open the numbered .26 audio-overlay receiver in TouchDesigner 2025.32820")
    root = Path(root).resolve()

    def expect_path(node, parameter, logical):
        par = getattr(node.par, parameter, None) if node is not None else None
        # Compare only the spelling; do not resolve/read arbitrary paths from TD.
        require(par is not None and root / Path(str(par.eval())) == root / logical,
                "Unexpected " + parameter + " binding; no fallback updater will run")

    for parameter, logical in _binding_parameters().items():
        expect_path(connector, parameter, logical)
    control = connector.op("show_control")
    require(control is not None and str(control.par.Runtimeprofile.eval()) == "3080_safe"
            and str(connector.par.Runtimeprofile.eval()) == "3080_safe" and not control.par.Livevariations.eval(),
            "Keep the 5090 in cached playback with live variations off")
    require(not control.par.Play.eval(), "Pause playback before verifying the full WAVs")
    for node_name in ("StreamDiffusionTD", "StreamDiffusionTD2"):
        node = connector.op(node_name)
        require(node is not None and not node.par.Serveractive.eval() and not node.par.Streamactive.eval(),
                "Both receiver servers and streams must be stopped")
    nodes = []
    for node_name, mode in (("voices_only_audio", "voices_only"), ("soundscape_audio", "soundscape_only"),
                            ("combined_audio", "combined")):
        node = connector.op(node_name)
        expect_path(node, "file", AUDIO[mode])
        require(str(node.par.playmode.eval()) == "locked", "Audio must stay locked to the show clock")
        nodes.append(node)
    switch, device = (connector.op(node_name) for node_name in ("audiosource_switch", "audio_out"))
    source = str(control.par.Audiosource.eval())
    sources = ("voices", "soundscape", "combined")
    require(switch is not None and device is not None and tuple(switch.inputs) == tuple(nodes)
            and tuple(device.inputs) == (switch,) and source in sources
            and str(connector.par.Audiosource.eval()) == source and switch.par.index.eval() == sources.index(source),
            "Unexpected 5090 audio source or device routing")
    return dict(verify_overlay(root), project=name, native_bindings_verified=True, saved=False,
                model_servers_started=False, live_generation=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    try:
        report = verify_overlay(parser.parse_args().root)
    except OverlayError as error:
        print(f"5090 overlay not verified: {error}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
