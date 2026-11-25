from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import wave

from touchdesigner import verify_5090_audio_overlay as v


class OverlayDataTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        tiny = patch.multiple(v, STORIES=3, DURATION_MS=6000, RATE=1000, SCENES=2, CAPTIONS=1)
        tiny.start()
        self.addCleanup(tiny.stop)
        stories = [
            dict(number=i + 1, narration_id=f"fixture-{i}", start_ms=i * 2000,
                 content_end_ms=i * 2000 + 1000, end_ms=(i + 1) * 2000)
            for i in range(3)
        ]
        for name in (v.BASE_TOE, *v.MODULES.values()):
            self.write(name, b"fixture")
        audio_hashes = {mode: self.make_wav(name, i + 1) for i, (mode, name) in enumerate(v.AUDIO.items())}
        old_audio = dict(v.AUDIO, soundscape_only="fixture/old-ambient.wav", combined="fixture/old-mix.wav")
        old_hashes = dict(audio_hashes, soundscape_only="a" * 64, combined="b" * 64)
        self.base = dict(stories=stories, story_count=3, duration_ms=6000, profile="3080_safe",
                         gap_colour_enabled=False, native_installed=True, audio=old_audio,
                         audio_sha256=old_hashes, plans={})
        self.overlay = dict(deepcopy(self.base), native_installed=False, audio=v.AUDIO, audio_sha256=audio_hashes)
        self.original_plans = {}
        self.overlay_plans = {}
        for mode in v.MODES:
            plan = dict(visual_path={"id": mode}, playlist_stories=stories, duration_ms=6000,
                        scenes=[{}, {}], captions=[{"text": "fixture"}], hold_visual_gaps_edition=True,
                        audio_file=v.NARRATION, soundscape_audio_file=old_audio["soundscape_only"],
                        combined_audio_file=old_audio["combined"], audio_sha256=old_hashes, **v.MODULES)
            self.original_plans[mode] = plan
            self.overlay_plans[mode] = dict(deepcopy(plan), **v.AUDIO_FIELDS, audio_sha256=audio_hashes)
        self.base["plans"] = self.write_plans(v.BASE_EDITION, self.original_plans)
        self.receipt = dict(verified=True, staged=True, receiver_overlay_is_data_only=True,
                            receiver_base_toe=v.BASE_TOE, receiver_base_playlist=v.BASE_PLAYLIST,
                            receiver_overlay=v.OVERLAY_PLAYLIST, narration_path_unchanged=v.NARRATION,
                            stories=3, duration_ms=6000, audio_files=2, exact_silent_gaps_per_track=3)
        self.receipt["receiver_base_toe_sha256"] = self.digest(v.BASE_TOE)
        self.receipt["receiver_base_playlist_sha256"] = self.write_json(v.BASE_PLAYLIST, self.base)
        self.receipt["protected_sha256"] = {
            v.BASE_TOE: self.receipt["receiver_base_toe_sha256"],
            v.BASE_PLAYLIST: self.receipt["receiver_base_playlist_sha256"],
            v.NARRATION: audio_hashes["voices_only"],
            **{entry["path"]: entry["sha256"] for entry in self.base["plans"].values()},
        }
        self.reseal()

    def write(self, name, data):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return self.digest(name)

    def digest(self, name):
        return hashlib.sha256((self.root / name).read_bytes()).hexdigest()

    def write_json(self, name, data):
        return self.write(name, json.dumps(data).encode("utf-8"))

    def make_wav(self, name, class_marker, silent_gap=True):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        sample = bytes((class_marker, 0, class_marker, 0))
        gap = bytes(4) if silent_gap else sample
        with wave.open(str(path), "wb") as stream:
            stream.setparams((2, 2, v.RATE, 0, "NONE", "not compressed"))
            stream.writeframes((sample * v.RATE + gap * v.RATE) * v.STORIES)
        return self.digest(name)

    def write_plans(self, folder, plans):
        result = {}
        for mode, plan in plans.items():
            name = f"{folder}/{mode}-visual-scenes.json"
            result[mode] = {"path": name, "sha256": self.write_json(name, plan)}
        return result

    def reseal(self):
        self.overlay["plans"] = self.write_plans(v.OVERLAY, self.overlay_plans)
        self.receipt["overlay_sha256"] = self.write_json(v.OVERLAY_PLAYLIST, self.overlay)
        self.write_json(f"{v.OVERLAY}/staging-verification.json", self.receipt)

    def test_verifies_existing_overlay_without_writing_files(self):
        def hashes():
            return {p: hashlib.sha256(p.read_bytes()).digest() for p in self.root.rglob("*") if p.is_file()}
        before = hashes()
        self.assertTrue(v.verify_overlay(self.root)["read_only"])
        self.assertEqual(hashes(), before)

    def test_interrupted_stage_has_no_verification_receipt(self):
        (self.root / v.OVERLAY / "staging-verification.json").unlink()
        with self.assertRaisesRegex(v.OverlayError, "Missing overlay dependency"):
            v.verify_overlay(self.root)

    def test_changed_rollback_toe_fails_preflight(self):
        self.write(v.BASE_TOE, b"different TOE")
        with self.assertRaisesRegex(v.OverlayError, "SHA-256 mismatch: podcast"):
            v.verify_overlay(self.root)

    def test_resealed_story_clock_change_is_refused(self):
        self.overlay["stories"][0]["end_ms"] += 1
        self.reseal()
        with self.assertRaisesRegex(v.OverlayError, "story clock"):
            v.verify_overlay(self.root)

    def test_resealed_visual_or_caption_edit_is_refused(self):
        for key, value in (("captions", [{"text": "different"}]), ("scenes", [{"different": True}, {}])):
            with self.subTest(key=key):
                plan = self.overlay_plans["balanced"]
                original, plan[key] = plan[key], value
                self.reseal()
                with self.assertRaisesRegex(v.OverlayError, "Visuals, captions or timing changed: balanced"):
                    v.verify_overlay(self.root)
                plan[key] = original

    def test_resealed_narration_hash_change_is_refused(self):
        self.overlay["audio_sha256"]["voices_only"] = "c" * 64
        self.reseal()
        with self.assertRaisesRegex(v.OverlayError, "original narration changed"):
            v.verify_overlay(self.root)

    def test_resealed_legacy_audio_is_refused(self):
        self.overlay["audio_sha256"]["combined"] = self.base["audio_sha256"]["combined"]
        self.reseal()
        with self.assertRaisesRegex(v.OverlayError, "legacy ambient audio"):
            v.verify_overlay(self.root)

    def test_corrupt_copied_wav_is_refused(self):
        self.write(v.AUDIO["combined"], b"changed audio")
        with self.assertRaisesRegex(v.OverlayError, "SHA-256 mismatch: combined"):
            v.verify_overlay(self.root)

    def test_resealed_wav_without_silence_is_refused(self):
        self.overlay["audio_sha256"]["combined"] = self.make_wav(v.AUDIO["combined"], 4, silent_gap=False)
        self.reseal()
        with self.assertRaisesRegex(v.OverlayError, "exact one-second silent gap: combined"):
            v.verify_overlay(self.root)


def fake_op(**parameters):
    return SimpleNamespace(par=SimpleNamespace(**{
        key: SimpleNamespace(eval=lambda current=value: current)
        for key, value in parameters.items()
    }))


class NativeBindingTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parent
        self.owner = fake_op(**v._binding_parameters(), Runtimeprofile="3080_safe", Audiosource="combined")
        self.nodes = {
            "show_control": fake_op(Play=False, Runtimeprofile="3080_safe", Livevariations=False, Audiosource="combined"),
            **{name: fake_op(Serveractive=False, Streamactive=False) for name in ("StreamDiffusionTD", "StreamDiffusionTD2")},
            **{name: fake_op(file=v.AUDIO[mode], playmode="locked") for name, mode in (
                ("voices_only_audio", "voices_only"), ("soundscape_audio", "soundscape_only"), ("combined_audio", "combined"))},
            "audiosource_switch": fake_op(index=2),
            "audio_out": fake_op(),
        }
        self.nodes["audiosource_switch"].inputs = [self.nodes[n] for n in ("voices_only_audio", "soundscape_audio", "combined_audio")]
        self.nodes["audio_out"].inputs = [self.nodes["audiosource_switch"]]
        self.owner.op = self.nodes.get
        verification = patch.object(v, "verify_overlay", return_value={"passed": True, "read_only": True})
        self.verify_data = verification.start()
        self.addCleanup(verification.stop)

    def run_native(self, name="podcast.5090.26.toe", build="2025.32820"):
        return v.verify_native_overlay(self.root, name, build, self.owner)

    def test_check_accepts_all_three_locked_audio_modes(self):
        for index, mode in enumerate(("voices", "soundscape", "combined")):
            with self.subTest(mode=mode):
                self.owner.par.Audiosource = self.nodes["show_control"].par.Audiosource = SimpleNamespace(eval=lambda: mode)
                self.nodes["audiosource_switch"].par.index = SimpleNamespace(eval=lambda: index)
                report = self.run_native()
                self.assertTrue(report["read_only"])
                self.assertTrue(report["native_bindings_verified"])
                self.assertFalse(report["saved"])
                self.assertFalse(report["model_servers_started"])

    def test_wrong_build_or_donor_never_reaches_data_verification(self):
        for name, build in (("podcast.41.toe", "2025.32820"), ("podcast.5090.26.toe", "2025.32460")):
            with self.subTest(name=name, build=build), self.assertRaisesRegex(v.OverlayError, "numbered .26"):
                self.run_native(name, build)
        self.verify_data.assert_not_called()

    def test_stale_combined_operator_is_refused_even_if_connector_binding_is_correct(self):
        self.nodes["combined_audio"].par.file = SimpleNamespace(eval=lambda: "legacy.wav")
        with self.assertRaisesRegex(v.OverlayError, "Unexpected file binding"):
            self.run_native()
        self.verify_data.assert_not_called()

    def test_legacy_visual_alias_cannot_pass(self):
        self.owner.par.Canonicalhumanvisuals = SimpleNamespace(eval=lambda: f"{v.BASE_EDITION}/human_figures-visual-scenes.json")
        with self.assertRaisesRegex(v.OverlayError, "Unexpected Canonicalhumanvisuals binding"):
            self.run_native()
        self.verify_data.assert_not_called()

    def test_server_or_stream_active_is_refused(self):
        for field in ("Serveractive", "Streamactive"):
            with self.subTest(field=field):
                self.nodes["StreamDiffusionTD2"] = fake_op(Serveractive=False, Streamactive=False)
                setattr(self.nodes["StreamDiffusionTD2"].par, field, SimpleNamespace(eval=lambda: True))
                with self.assertRaisesRegex(v.OverlayError, "servers and streams must be stopped"):
                    self.run_native()
        self.verify_data.assert_not_called()

    def test_live_playback_or_miswired_audio_device_is_refused(self):
        control = self.nodes["show_control"].par
        control.Livevariations = SimpleNamespace(eval=lambda: True)
        with self.assertRaisesRegex(v.OverlayError, "live variations off"):
            self.run_native()
        control.Livevariations = SimpleNamespace(eval=lambda: False)
        control.Play = SimpleNamespace(eval=lambda: True)
        with self.assertRaisesRegex(v.OverlayError, "Pause playback"):
            self.run_native()
        control.Play = SimpleNamespace(eval=lambda: False)
        self.nodes["audio_out"].inputs = []
        with self.assertRaisesRegex(v.OverlayError, "device routing"):
            self.run_native()
        self.verify_data.assert_not_called()
