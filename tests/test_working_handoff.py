import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from home_podcast import private_handoff as h
from home_podcast import working_handoff as w


class WorkingHandoffTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.root = self.base / "source"
        self.root.mkdir()
        self.bundle = self.base / "private-package"
        self.write("home_podcast/private_handoff.py", Path(h.__file__).read_bytes())
        self.write(w.GUIDE, b"# Synthetic receiver instructions\n")
        self.write("audio/approved.wav", b"synthetic-media-fixture")
        self.write("narrations/real-december/one/adaptation.json", b'{"status":"pending"}')
        self.write("narrations/real-december/two/adaptation.json", b'{"status":"held"}')
        self.write("data/exports/stories_en.md", b"# Synthetic source\nI lived here.\n")
        self.write("work/planning/job.json", b'{"job":"synthetic"}')
        for name in ("catalog.sqlite3", "catalog-real-december.sqlite3"):
            connection = sqlite3.connect(self.root / "data" / name)
            connection.execute("CREATE TABLE stories (story_id TEXT PRIMARY KEY, content TEXT)")
            connection.execute("INSERT INTO stories VALUES (?, ?)", ("fixture-one", "I lived here."))
            connection.commit()
            connection.close()
        def selection(root, editable=True):
            names = ("home_podcast/private_handoff.py", w.GUIDE, "audio/approved.wav")
            return ({name: {"fixture"} for name in names}, {"audio/approved.wav": h.sha(self.root / "audio/approved.wav")},
                {"stories": 1, "profile": "3080_safe", "editable": True})
        mocked = patch.object(h, "build_selection", side_effect=selection)
        mocked.start()
        self.addCleanup(mocked.stop)

    def write(self, name, data):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def run_prepare(self, label="fixture-v1", apply=False):
        return w.prepare(self.root, self.bundle, label, apply)

    def test_default_is_read_only_and_catalogues_stay_unchanged(self):
        before = {p.relative_to(self.root).as_posix(): h.sha(p) for p in self.root.rglob("*") if p.is_file()}
        result = self.run_prepare()
        self.assertEqual(result["writes"], 0)
        self.assertEqual(result["adaptation_records"], 2)
        self.assertFalse(self.bundle.exists())
        self.assertFalse((self.root / w.STATE).exists())
        after = {p.relative_to(self.root).as_posix(): h.sha(p) for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(before, after)

    def test_apply_publishes_verified_payload_and_receiver_notes(self):
        result = self.run_prepare(apply=True)
        verified = h.verify_bundle(self.bundle)
        self.assertEqual(result["snapshot"], verified["snapshot"])
        self.assertTrue((self.bundle / "handoff.py").is_file())
        self.assertEqual(h.read(self.bundle / "SENDER-3080.json")["adaptation_records"], 2)
        self.assertEqual(h.read(self.bundle / "receiver-notes.json")["snapshot"], result["snapshot"])
        self.assertFalse((self.bundle / "receiver-notes.pending.json").exists())

    def test_catalogue_sql_is_data_and_can_restore_in_memory(self):
        plan = w.build_plan(self.root, "fixture-v1")
        data = next(data for name, data in plan["generated"].items() if name.endswith("catalog.sqlite3.sql.txt"))
        restored = sqlite3.connect(":memory:")
        try:
            restored.executescript(data.decode())
            self.assertEqual(restored.execute("SELECT * FROM stories").fetchall(), [("fixture-one", "I lived here.")])
        finally:
            restored.close()
        self.assertFalse(any(entry["path"].endswith(".sqlite3") for entry in plan["body"]["files"]))

    def test_unchanged_checkpoint_reuses_all_objects(self):
        first = self.run_prepare(apply=True)
        second = self.run_prepare(apply=True)
        self.assertEqual(first["snapshot"], second["snapshot"])
        self.assertEqual((second["new_objects"], second["copy_bytes"]), (0, 0))

    def test_same_label_cannot_freeze_changed_data(self):
        first = self.run_prepare(apply=True)
        self.write("work/planning/job.json", b'{"job":"changed"}')
        with self.assertRaisesRegex(h.HandoffError, "label already freezes"):
            self.run_prepare(apply=True)
        self.assertEqual(h.read(self.bundle / "latest.json")["snapshot"], first["snapshot"])

    def test_new_label_preserves_old_snapshot_and_notes(self):
        first = self.run_prepare(apply=True)
        original_notes = (self.bundle / "SENDER-3080.json").read_bytes()
        self.write("work/planning/job.json", b'{"job":"changed"}')
        second = self.run_prepare("fixture-v2", apply=True)
        self.assertNotEqual(first["snapshot"], second["snapshot"])
        self.assertTrue(h.verify_bundle(self.bundle, first["snapshot"])["passed"])
        self.assertEqual((self.bundle / "receiver-notes" / first["snapshot"] / "SENDER-3080.json").read_bytes(), original_notes)

    def test_scope_excludes_old_media_models_credentials_and_active_locks(self):
        omitted = ("audio/old-take.wav", "work/planning/worker-lock.json", "work/planning/data.lock.json",
            "work/planning/.env.json", "data/exports/Matches_test.md",
            "work/storytelling-real-december/ambient-runtime/vendor/model.json",
            "work/storytelling-real-december/ambient-runtime/venv/settings.json",
            "work/storytelling-real-december/local-audio/asr-runtime/settings.json",
            "work/storytelling-real-december/runtime/current.json")
        for name in omitted:
            self.write(name, b"not JSON; must not be read as source state")
        plan = w.build_plan(self.root, "fixture-v1")
        names = {entry["path"] for entry in plan["body"]["files"]}
        self.assertFalse(names.intersection(omitted))
        self.assertIn("narrations/real-december/two/adaptation.json", names)
        self.assertEqual(json.loads((self.root / "narrations/real-december/two/adaptation.json").read_bytes())["status"], "held")

    def test_missing_catalogue_is_a_hold_not_an_empty_substitute(self):
        (self.root / "data/catalog.sqlite3").unlink()
        with self.assertRaisesRegex(h.HandoffError, "Missing source catalogue"):
            self.run_prepare(apply=True)
        self.assertFalse(self.bundle.exists())

    def test_unknown_authorization_value_still_blocks_working_data(self):
        # Use the in-memory gate rather than materializing credential fixtures.
        with patch.object(h, "scan", side_effect=h.HandoffError("Nonempty credential field (contents suppressed)")):
            with self.assertRaises(h.HandoffError):
                self.run_prepare(apply=True)
        self.assertFalse(self.bundle.exists())

    def test_unknown_guide_edits_are_never_overwritten(self):
        first = self.run_prepare(apply=True)
        guide = self.bundle / "START-HERE.md"
        guide.write_text("My local edits", encoding="utf-8")
        with self.assertRaisesRegex(h.HandoffError, "locally edited"):
            self.run_prepare(apply=True)
        self.assertEqual(guide.read_text(), "My local edits")
        self.assertEqual(h.read(self.bundle / "latest.json")["snapshot"], first["snapshot"])

    def test_pending_note_update_resumes_only_known_bytes(self):
        first = self.run_prepare(apply=True)
        content = {name: (self.bundle / name).read_bytes() for name in w.ROOT_NOTES}
        hashes = {name: h.digest_bytes(value) for name, value in content.items()}
        h.atomic_write(self.bundle / "receiver-notes.pending.json", h.canonical(dict(format=w.NOTE_FORMAT,
            snapshot=first["snapshot"], previous_snapshot=first["snapshot"], old=hashes, new=hashes)))
        self.run_prepare(apply=True)
        self.assertFalse((self.bundle / "receiver-notes.pending.json").exists())

    def test_unknown_pending_note_edits_are_held(self):
        first = self.run_prepare(apply=True)
        hashes = {name: h.sha(self.bundle / name) for name in w.ROOT_NOTES}
        h.atomic_write(self.bundle / "receiver-notes.pending.json", h.canonical(dict(format=w.NOTE_FORMAT,
            snapshot=first["snapshot"], previous_snapshot=first["snapshot"], old=hashes, new=hashes)))
        (self.bundle / "START-HERE.md").write_text("Other local work", encoding="utf-8")
        with self.assertRaisesRegex(h.HandoffError, "edited during update"):
            self.run_prepare(apply=True)
        self.assertEqual((self.bundle / "START-HERE.md").read_text(), "Other local work")

    def test_dry_run_refuses_corrupt_existing_object(self):
        self.run_prepare(apply=True)
        body, _ = h.load_bundle(self.bundle)
        path = self.bundle / h.object_name(body["files"][0]["sha256"])
        path.write_bytes(b"corrupt")
        with self.assertRaisesRegex(h.HandoffError, "corrupt"):
            self.run_prepare()
        self.assertEqual(path.read_bytes(), b"corrupt")

    def test_relevant_symlinks_are_refused(self):
        outside = self.base / "outside"
        outside.mkdir()
        try:
            (self.root / "work/planning/other").symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest("Symlink creation unavailable")
        with self.assertRaisesRegex(h.HandoffError, "Symlink/reparse"):
            self.run_prepare()

    def test_checkpoint_label_validation(self):
        for label in ("../outside", "", "with spaces", "A-CAPITAL-LABEL", "a" * 81):
            with self.subTest(label=label), self.assertRaises(h.HandoffError):
                self.run_prepare(label)
        self.assertFalse((self.root / w.STATE).exists())

    def test_narrow_export_cannot_replace_broader_latest_pointer(self):
        result = self.run_prepare(apply=True)
        selected, expected, metadata = h.build_selection(self.root)
        narrow = h.inventory(self.root, selected, expected, metadata)
        with self.assertRaisesRegex(h.HandoffError, "Cannot narrow"):
            h.export_bundle(self.root, self.bundle, narrow, apply=True)
        self.assertEqual(h.read(self.bundle / "latest.json")["snapshot"], result["snapshot"])

    def test_migration_of_original_verified_3080_notes(self):
        # Reproduce the old readable envelope on a synthetic valid package.
        selected, expected, metadata = h.build_selection(self.root)
        old_body = h.inventory(self.root, selected, expected, metadata)
        old = h.export_bundle(self.root, self.bundle, old_body, apply=True)
        (self.bundle / "START-HERE.md").write_bytes((self.root / w.GUIDE).read_bytes())
        (self.bundle / "SENDER-3080.json").write_bytes(h.canonical(dict(snapshot=old["snapshot"], start_here_sha256=h.sha(self.root / w.GUIDE))))
        (self.bundle / "VERIFIED-3080.json").write_bytes(h.canonical(dict(status="ready_for_private_transfer", snapshot=old["snapshot"], files_verified=len(old_body["files"]))))
        newer = self.run_prepare(apply=True)
        self.assertNotEqual(old["snapshot"], newer["snapshot"])
        self.assertTrue((self.bundle / "receiver-notes" / old["snapshot"] / "SENDER-3080.json").exists())


if __name__ == "__main__":
    unittest.main()
