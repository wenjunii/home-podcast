import contextlib
from copy import deepcopy
import importlib.util
import io
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from home_podcast import private_handoff as h


class Show41HandoffTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name) / "sender"
        self.bundle = Path(tmp.name) / "snapshot"
        self.target = Path(tmp.name) / "receiver"
        self.root.mkdir()
        self.make_show()

    def write(self, rel, data):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return h.sha(path)

    def write_json(self, rel, data):
        return self.write(rel, h.canonical(data))

    def make_show(self):
        length = 11938720
        stories = []
        end = 0
        for i in range(1, 137):
            next_end = i * length // 136
            stories.append(dict(number=i, narration_id=f"fixture-{i}", start_ms=end,
                                content_end_ms=next_end - 1000, end_ms=next_end))
            end = next_end
        toe = self.write(h.TOE_41, b"native fixture")
        # Deliberately place older projects and unpublished state alongside it.
        self.write(h.TOE, b"rollback fixture")
        self.write("podcast.5090.25.toe", b"receiver fixture")
        self.write("work/storytelling-real-december/unreviewed.json", b"{}")
        audio = {kind: f"audio/storytelling-real-december/fixture/{kind}.wav"
                 for kind in ("voices_only", "soundscape_only", "combined")}
        audio_sha256 = {kind: self.write(name, kind.encode()) for kind, name in audio.items()}
        captions = "audio/storytelling-real-december/approved-136-five-second-3080-2026-10-30/playlist-captions."
        for extension in ("srt", "vtt"):
            self.write(captions + extension, b"caption export")
        self.write("LICENSE", b"license")
        self.write("home_podcast/private_handoff.py", Path(h.__file__).read_bytes())
        rebinder = Path(h.__file__).resolve().parents[1] / "touchdesigner/rebind_show_41.py"
        self.write("touchdesigner/rebind_show_41.py", rebinder.read_bytes())
        for name in h.RUNTIME_41:
            self.write(name, b"# Owned playback dependency\n")
        controller = "work/fixture/controller.py"
        self.write(controller, b'DEPENDENCY = "work/fixture/child.py"\n')
        self.write("work/fixture/child.py", b"# transitive dependency\n")
        plans = {}
        for mode in ("original", "human_figures", "balanced"):
            plan = dict(visual_path={"id": mode}, playlist_stories=stories, duration_ms=length,
                        scenes=[{}] * 619, captions=[{}] * 2862, hold_visual_gaps_edition=True,
                        audio_file=audio["voices_only"], soundscape_audio_file=audio["soundscape_only"],
                        combined_audio_file=audio["combined"], audio_sha256=audio_sha256,
                        controller_module=controller, sequencer_module=h.RUNTIME_41[-1])
            name = f"{h.EDITION_41}/{mode}-visual-scenes.json"
            plans[mode] = dict(path=name, sha256=self.write_json(name, plan))
        approval = h.EDITION_41 + "/approval.json"
        self.write_json(approval, dict(human_ambient_approval="approved_by_user",
                                      target=h.TOE_41, story_count=136, held_stories=[]))
        self.write_json(h.APPROVED + "/approval.json", {})
        manifest = dict(stories=stories, story_count=136, duration_ms=length,
                        target_toe=h.TOE_41, profile="3080_safe", gap_colour_enabled=False,
                        plans=plans, audio=audio, audio_sha256=audio_sha256,
                        ambient_approval=approval, human_ambient_approval="approved_by_user")
        manifest_sha = self.write_json(h.PLAYLIST_41, manifest)
        self.write_json(h.EDITION_41 + "/assembly-verification.json", dict(
            passed=True, original_narration_unchanged=True, scene_captions_and_timing_unchanged=True,
            audio=audio_sha256, manifest_sha256=manifest_sha, duration_ms=length))
        self.write_json(h.EDITION_41 + "/delivery.json", dict(
            passed=True, project=h.TOE_41, manifest=h.PLAYLIST_41, changes_5090=0, model_servers_started=False,
            touchdesigner_build="2025.32820", sha256=toe, duration_ms=length, native_checks=70))
        self.write_json(h.EDITION_41 + "/native-reopen.json", dict(project=h.TOE_41, passed=70, checks=70, failures=[]))
        self.manifest = manifest

    def body(self):
        return h.inventory(self.root, *h.build_approved_41_selection(self.root))

    def test_playback_selection_and_transitive_closure(self):
        out = self.body()
        paths = {row["path"] for row in out["files"]}
        self.assertEqual({name for name in paths if name.endswith(".toe")}, {h.TOE_41})
        self.assertEqual({name for name in paths if name.endswith(".wav")}, set(self.manifest["audio"].values()))
        self.assertIn("work/fixture/child.py", paths)
        self.assertFalse(out["metadata"]["editable"])
        self.assertNotIn("work/storytelling-real-december/unreviewed.json", paths)

    def test_cli_plan_and_export_dry_run_do_not_create_package(self):
        buf = io.StringIO()
        argv = ["export", "--edition", "3080-41", "--root", str(self.root),
                "--bundle", str(self.bundle)]
        with contextlib.redirect_stdout(buf):
            self.assertEqual(h.main(argv), 0)
        self.assertFalse(self.bundle.exists())
        self.assertIn('"apply": false', buf.getvalue())

    def test_export_verify_restore_and_standalone_verification(self):
        h.export_bundle(self.root, self.bundle, self.body(), apply=True)
        self.assertTrue(h.verify_bundle(self.bundle)["passed"])
        result = h.import_bundle(self.bundle, self.target, apply=True)
        self.assertTrue(result["verified"])
        cli = importlib.util.spec_from_file_location("restored_handoff_tool", self.bundle / "handoff.py")
        restored = importlib.util.module_from_spec(cli)
        cli.loader.exec_module(restored)
        self.assertTrue(restored.verify_target(self.target)["passed"])
        self.assertFalse((self.target / h.TOE).exists())

    def test_no_import_into_existing_native_receiver(self):
        h.export_bundle(self.root, self.bundle, self.body(), apply=True)
        self.target.mkdir()
        receiver = self.target / "podcast.5090.25.toe"
        receiver.write_bytes(b"existing receiver")
        with self.assertRaisesRegex(h.HandoffError, "existing native project"):
            h.import_bundle(self.bundle, self.target, apply=True)
        self.assertEqual(list(self.target.iterdir()), [receiver])
        self.assertEqual(receiver.read_bytes(), b"existing receiver")

    def test_no_switching_an_existing_latest_pointer_between_editions(self):
        old_source = {h.TOE: {"legacy_fixture"}}
        old = h.inventory(self.root, old_source, metadata={"toe": h.TOE, "profile": "3080_safe"})
        h.export_bundle(self.root, self.bundle, old, apply=True)
        pointer = (self.bundle / "latest.json").read_bytes()
        with self.assertRaisesRegex(h.HandoffError, "separate package"):
            h.export_bundle(self.root, self.bundle, self.body(), apply=True)
        self.assertEqual((self.bundle / "latest.json").read_bytes(), pointer)

    def test_no_relabel_of_a_draft_or_a_wrong_native_project(self):
        old = self.body()
        for key, value in (("selection_mode", "other"), ("profile", "5090_live"), ("editable", True)):
            body = deepcopy(old)
            body["metadata"][key] = value
            with self.subTest(key=key), self.assertRaisesRegex(h.HandoffError, "dedicated 3080"):
                h.validate_manifest(body)
        body = deepcopy(old)
        body["files"].append(dict(path=h.TOE, sha256="2"*64, size=0, roles=[]))
        with self.assertRaisesRegex(h.HandoffError, "selected private 3080"):
            h.validate_manifest(body)

    def test_changed_audio_fails_the_approved_file_hash(self):
        self.write(self.manifest["audio"]["combined"], b"different take")
        with self.assertRaisesRegex(h.HandoffError, "Changed approved"):
            self.body()

    def test_sender_cannot_ship_an_incompatible_restore_helper(self):
        self.write("touchdesigner/rebind_show_41.py", b"# Another package format\n")
        with self.assertRaisesRegex(h.HandoffError, "tools must match"):
            self.body()

    def test_pending_listening_gate_fails_closed(self):
        name = h.EDITION_41 + "/approval.json"
        approval = h.read(self.root / name)
        approval["held_stories"] = [1]
        self.write_json(name, approval)
        with self.assertRaisesRegex(h.HandoffError, "complete listening approval"):
            self.body()


class Show41RebindTests(unittest.TestCase):
    def setUp(self):
        source = Path(__file__).resolve().parents[1] / "touchdesigner/rebind_show_41.py"
        spec = importlib.util.spec_from_file_location("test_41_rebinder", source)
        self.rebind = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.rebind)

    def test_rebase_owned_python_path_with_spaces_and_apostrophe(self):
        old = r"C:\Sender\Show"
        new = r"D:\Testing\Listener's Show"
        callback = "helper = " + repr(old + r"\work\helper.py")
        rebased = self.rebind.replace_root(callback, old, new)
        result = {}
        exec(compile(rebased, "<test-callback>", "exec"), result)
        self.assertEqual(result["helper"], new + r"\work\helper.py")
        self.assertEqual(self.rebind.saved_root(old + "/" + h.PLAYLIST_41), old)
        with self.assertRaises(RuntimeError):
            self.rebind.saved_root(old + "/" + h.EDITION + "/playlist.json")

    def test_rollback_and_receiver_native_projects_refused(self):
        self.rebind.app = SimpleNamespace(build="2025.32820")
        for name in (h.TOE, "podcast.5090.25.toe"):
            self.rebind.project = SimpleNamespace(name=name)
            with self.subTest(name=name), self.assertRaisesRegex(RuntimeError, "imported podcast.41.toe"):
                self.rebind.rebind_show_41()


if __name__ == "__main__":
    unittest.main()
