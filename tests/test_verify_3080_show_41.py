import contextlib
import io
import tempfile
import unittest
import wave
from copy import deepcopy
from pathlib import Path

from scripts import verify_3080_show_41 as show


def story(number, key, start, duration):
    end = start + duration + show.GAP_MS
    return {"number": number, "narration_id": key, "start_ms": start,
            "content_end_ms": end - show.GAP_MS, "end_ms": end, "duration_ms": end - start,
            "narration_duration_ms": duration, "gap_after_ms": show.GAP_MS}


def cue(key, index, start, end):
    return {"caption_id": f"{key}--caption-{index}", "narration_id": key, "start_ms": start,
            "end_ms": end, "text": "A short example caption."}


def scene(key, index, start, end, opening=False):
    return {"scene_id": f"{key}--scene-{index}", "narration_id": key, "start_ms": start,
            "end_ms": end, "duration_ms": end - start, "opening_context_exception": opening,
            "material_gates": [{"not_before_ms": start}],
            "prompt": {"chunks": [{"content_token_count": 73}]}}


class StoryClockTests(unittest.TestCase):
    def setUp(self):
        self.rows = [story(1, "first", 0, 11_000), story(2, "second", 12_000, 7000)]

    def test_story_gap_and_loop_use_one_clock(self):
        result = show.verify_story_clock(self.rows, 20_000)
        self.assertEqual(list(result), ["first", "second"])

    def test_bad_gap_or_duplicate_identity_fails(self):
        for key, value, detail in (("gap_after_ms", 999, "one-second gap"),
                                   ("narration_id", "first", "Invalid story ID")):
            with self.subTest(key=key), self.assertRaisesRegex(show.CheckError, detail):
                rows = deepcopy(self.rows)
                rows[1][key] = value
                show.verify_story_clock(rows, 20_000)

    def test_bad_start_or_final_endpoint_fails(self):
        with self.assertRaisesRegex(show.CheckError, "playlist loop clocks differ"):
            show.verify_story_clock(self.rows, 20_001)
        self.rows[1]["start_ms"] = 11_999
        with self.assertRaisesRegex(show.CheckError, "Story 2 has an invalid"):
            show.verify_story_clock(self.rows, 20_000)


class VisualPathTests(unittest.TestCase):
    def setUp(self):
        stories = [story(1, "first", 0, 11_000), story(2, "second", 12_000, 7000)]
        self.by_id = show.verify_story_clock(stories, 20_000)
        self.manifest = {
            "stories": stories, "duration_ms": 20_000, "default_story_crossfade_ms": 3000,
            "audio": {mode: mode + ".wav" for mode in show.AUDIO_MODES}, "audio_sha256": {},
            "plans": {"balanced": {"scenes": 3, "captions": 2}},
        }
        # The intentional one-second visual hold inside story 1 is not a caption/audio gap.
        self.plan = {
            "visual_path": {"id": "balanced"}, "playlist_stories": stories, "duration_ms": 20_000,
            "touchdesigner_version": show.BUILD, "project_variant": "3080", "executable": True,
            "human_visual_approval": "approved_by_user", "audio_file": "voices_only.wav",
            "soundscape_audio_file": "soundscape_only.wav", "combined_audio_file": "combined.wav",
            "audio_sha256": {}, "five_second_opening_edition": True, "hold_visual_gaps_edition": True,
            "abstract_transition_intervals_inactive": True, "all_join_interpolation_edition": True,
            "output_edge_fades": {"default_ms": 0},
            "story_transition_policy": "continuous_post_onset_crossfade",
            "loop_transition_policy": "post_onset_prompt_seed_interpolation", "story_crossfade_ms": 3000,
            "prompt_policy": {"minimum_scene_duration_ms": 5000, "content_token_limit": 75,
                              "crossfade_policy": "post_onset_no_future_preview"},
            "scenes": [scene("first", 1, 0, 5000, True), scene("first", 2, 6000, 11_000),
                       scene("second", 3, 12_000, 19_000, True)],
            "captions": [cue("first", 1, 50, 2000), cue("second", 2, 12_050, 18_900)],
        }

    def verify(self):
        return show.verify_visual_path(self.plan, "balanced", self.manifest, self.by_id)

    def test_accepts_five_seconds_and_checks_story_openings_and_joins(self):
        result = self.verify()
        self.assertEqual(result["under_15_seconds"], 3)
        self.assertEqual(result["story_openings"], 2)
        self.assertEqual(result["within_story_joins"], 1)
        self.assertEqual(result["between_story_joins"], 1)
        self.assertTrue(result["loop_clock_aligned"])

    def test_rejects_shorter_than_five_seconds_and_early_speech_gate(self):
        first = self.plan["scenes"][0]
        first.update(end_ms=4999, duration_ms=4999)
        with self.assertRaisesRegex(show.CheckError, "shorter than five seconds"):
            self.verify()
        first.update(end_ms=5000, duration_ms=5000)
        self.plan["scenes"][1]["material_gates"][0]["not_before_ms"] = 6001
        with self.assertRaisesRegex(show.CheckError, "before recorded speech evidence"):
            self.verify()

    def test_rejects_visuals_or_captions_crossing_a_story_gap(self):
        for key in ("scenes", "captions"):
            with self.subTest(key=key), self.assertRaisesRegex(show.CheckError, "leaves its narration"):
                item = self.plan[key][-2]
                old_end = item["end_ms"]
                try:
                    item["end_ms"] = 11_001
                    self.verify()
                finally:
                    item["end_ms"] = old_end

    def test_rejects_late_opening_or_unapproved_loop_policy(self):
        first = self.plan["scenes"][0]
        first.update(start_ms=1, end_ms=5001)
        with self.assertRaisesRegex(show.CheckError, "opening 1 is not at its boundary"):
            self.verify()
        first.update(start_ms=0, end_ms=5000)
        self.plan["loop_transition_policy"] = "preview_incoming"
        with self.assertRaisesRegex(show.CheckError, "wrong .41 gap, interpolation"):
            self.verify()

    def test_compares_clocks_without_forcing_the_same_visual_prompts(self):
        other = deepcopy(self.plan)
        other["scenes"][0]["prompt"]["chunks"][0]["text"] = "Different framing"
        show.same_visual_clock(self.plan, other, "alternate")
        other["captions"][0]["start_ms"] += 1
        with self.assertRaisesRegex(show.CheckError, "changes the approved scene or caption clock"):
            show.same_visual_clock(self.plan, other, "alternate")


class FileTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)

    def wav(self, *, rate=48_000, noisy_gap=False, signal=1):
        file = self.root / "fixture.wav"
        payload = bytearray(1001 * (rate // 1000) * 4)
        payload[rate // 1000 * 4 if noisy_gap else 0] = signal
        with wave.open(str(file), "wb") as out:
            out.setparams((2, 2, rate, 0, "NONE", "not compressed"))
            out.writeframes(payload)
        return file

    def test_wave_checks_actual_silence_pcm_and_sha(self):
        stories = [story(1, "first", 0, 1)]
        file = self.wav()
        approved = show.h.sha(file)
        report = show.verify_wave(file, "combined", stories, 1001, approved)
        self.assertEqual(report["silent_gaps"], 1)  # The last-to-first separator is included.
        self.assertEqual(report["pcm_frames"], 48_048)
        file = self.wav(noisy_gap=True)
        with self.assertRaisesRegex(show.CheckError, "not exactly one second of silence"):
            show.verify_wave(file, "combined", stories, 1001, show.h.sha(file))
        file = self.wav(rate=24_000)
        with self.assertRaisesRegex(show.CheckError, "format or frame count"):
            show.verify_wave(file, "combined", stories, 1001, show.h.sha(file))
        file = self.wav(signal=2)
        with self.assertRaisesRegex(show.CheckError, "does not match the approved hash"):
            show.verify_wave(file, "combined", stories, 1001, approved)

    def test_caption_exports_match_edge_times_and_wrapped_text(self):
        captions = [cue("first", 1, 4_203_001, 4_204_002)]
        for kind, prefix, sep in (("srt", "", ","), ("vtt", "WEBVTT\n\n", ".")):
            file = self.root / f"fixture.{kind}"
            data = f"{prefix}1\n01:10:03{sep}001 --> 01:10:04{sep}002\nA short\nexample caption.\n"
            file.write_text(data, encoding="utf-8")
            self.assertEqual(show.verify_caption_export(file, kind, captions), 1)
            file.write_text(data.replace("example caption", "altered caption"), encoding="utf-8")
            with self.assertRaisesRegex(show.CheckError, "does not match the approved text and clock"):
                show.verify_caption_export(file, kind, captions)

    def test_cli_does_not_fall_back_to_the_rollback_or_write_output(self):
        old = self.root / "podcast.40.toe"
        old.write_bytes(b"preserve this fixture")
        with contextlib.redirect_stderr(io.StringIO()) as error:
            self.assertEqual(show.main(["--root", str(self.root)]), 2)
        self.assertIn("Missing podcast.41.toe", error.getvalue())
        self.assertEqual(set(self.root.iterdir()), {old})
        self.assertEqual(old.read_bytes(), b"preserve this fixture")

    def test_unapproved_receipt_data_is_not_echoed(self):
        file = self.root / "test-receipt.json"
        file.write_bytes(b'{"body":"ARTIFACT PAYLOAD MUST NOT BE ECHOED"}')
        with self.assertRaisesRegex(show.CheckError, "receipt does not match the approved hash") as err:
            show.pinned_json(self.root, file.name, "0" * 64, "receipt")
        self.assertNotIn("ARTIFACT PAYLOAD", str(err.exception))


if __name__ == "__main__":
    unittest.main()
