import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from home_podcast import private_handoff as h


class PrivateHandoffTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.source = self.base / "source"
        self.bundle = self.base / "bundle"
        self.target = self.base / "restored"
        self.source.mkdir()
        self.write("scripts/example.py", b"VALUE = 1\n")
        self.write("data/exports/stories_en.md", b"# One memory\nI came home.\n")

    def write(self, name, data):
        path = self.source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def body(self):
        return h.inventory(self.source, {p.relative_to(self.source).as_posix(): {"fixture"} for p in self.source.rglob("*") if p.is_file()}, metadata={"profile": "3080_safe"})

    def export(self):
        body = self.body()
        h.export_bundle(self.source, self.bundle, body, apply=True)
        return body

    def test_plan_and_export_dry_runs_write_nothing(self):
        result = h.export_bundle(self.source, self.bundle, self.body())
        self.assertEqual(result["new_objects"], 2)
        self.assertFalse(self.bundle.exists())

    def test_complete_export_verify_and_import(self):
        body = self.export()
        result = h.verify_bundle(self.bundle)
        self.assertEqual(result["files"], 2)
        dry = h.import_bundle(self.bundle, self.target)
        self.assertEqual(dry["copy_files"], 2)
        self.assertFalse(self.target.exists())
        result = h.import_bundle(self.bundle, self.target, apply=True)
        self.assertTrue(result["verified"])
        for item in body["files"]:
            self.assertEqual((self.target / item["path"]).read_bytes(), (self.source / item["path"]).read_bytes())

    def test_incremental_second_export_copies_zero_bytes(self):
        body = self.export()
        result = h.export_bundle(self.source, self.bundle, body, apply=True)
        self.assertEqual((result["new_objects"], result["copy_bytes"]), (0, 0))

    def test_new_snapshot_preserves_previous_manifest_and_objects(self):
        first = self.export();first_id = h.digest_bytes(h.canonical(first))
        self.write("scripts/example.py", b"VALUE = 2\n")
        result = h.export_bundle(self.source, self.bundle, self.body(), apply=True)
        self.assertEqual(result["new_objects"], 1)
        self.assertNotEqual(first_id, result["snapshot"])
        self.assertTrue(h.verify_bundle(self.bundle, first_id)["passed"])
        self.assertTrue(h.verify_bundle(self.bundle)["passed"])

    def test_duplicate_contents_share_one_object(self):
        self.write("scripts/same.py", b"VALUE = 1\n")
        body = self.export()
        self.assertEqual(len(body["files"]), 3)
        self.assertEqual(h.verify_bundle(self.bundle)["unique_objects"], 2)

    def test_existing_identical_destination_is_skipped(self):
        self.export();h.import_bundle(self.bundle, self.target, apply=True)
        result = h.import_bundle(self.bundle, self.target, apply=True)
        self.assertEqual(result["copy_files"], 0)
        self.assertEqual(result["unchanged_files"], 2)

    def test_conflict_preflight_copies_nothing(self):
        self.export()
        conflict = self.target / "scripts/example.py"
        conflict.parent.mkdir(parents=True);conflict.write_text("my other PC changes")
        with self.assertRaisesRegex(h.HandoffError, "Import conflicts"):
            h.import_bundle(self.bundle, self.target, apply=True)
        self.assertEqual(conflict.read_text(), "my other PC changes")
        self.assertFalse((self.target / "data").exists())

    def test_corruption_is_detected_before_import(self):
        body = self.export()
        entry = body["files"][0]
        (self.bundle / h.object_name(entry["sha256"])).write_bytes(b"corrupt")
        with self.assertRaises(h.HandoffError):h.import_bundle(self.bundle, self.target, apply=True)
        self.assertFalse(self.target.exists())

    def test_existing_corrupt_package_object_is_not_overwritten(self):
        body = self.export();entry = body["files"][0]
        path = self.bundle / h.object_name(entry["sha256"]);path.write_bytes(b"bad")
        with self.assertRaisesRegex(h.HandoffError, "corrupt"):
            h.export_bundle(self.source, self.bundle, body, apply=True)
        self.assertEqual(path.read_bytes(), b"bad")

    def test_changed_source_after_plan_is_rejected(self):
        body = self.body();self.write("scripts/example.py", b"changed")
        with self.assertRaisesRegex(h.HandoffError, "Source changed"):
            h.export_bundle(self.source, self.bundle, body, apply=True)
        self.assertFalse(self.bundle.exists())

    def test_approved_hash_is_checked(self):
        with self.assertRaisesRegex(h.HandoffError, "Changed approved"):
            h.inventory(self.source, {"scripts/example.py": {"code"}}, {"scripts/example.py": "0"*64})

    def test_secret_content_is_held_without_echoing_value(self):
        secret = "sk-" + "aB1"*12
        self.write("scripts/unsafe.py", ("KEY = " + repr(secret)).encode())
        with self.assertRaises(h.HandoffError) as result:self.body()
        self.assertNotIn(secret, str(result.exception))
        self.assertIn("contents suppressed", str(result.exception))

    def test_nonstandard_nonempty_credential_field_is_held(self):
        self.write("config/unsafe.json", json.dumps({"api_key": "not-a-standard-shaped-key"}).encode())
        with self.assertRaisesRegex(h.HandoffError, "credential field"):self.body()

    def test_filename_and_traversal_guards(self):
        for name in ("../outside", "/absolute", "C:/escape", "a\\b", "a//b", "a/./b", "con.txt", "a/NUL", "a/b.", ".git/config", ".env", "auth.json", "key.pem", "a:stream"):
            with self.subTest(name=name), self.assertRaises(h.HandoffError):h.safe_name(name)

    def test_case_collisions_are_rejected(self):
        body = self.body();entry = dict(body["files"][0]);entry["path"] = entry["path"].upper();body["files"].append(entry)
        with self.assertRaisesRegex(h.HandoffError, "case-colliding"):h.validate_manifest(body)

    def test_other_toe_and_5090_toe_are_rejected(self):
        for name in ("podcast.5090.toe", "podcast.38.toe", "sub/podcast.40.toe"):
            body = self.body();body["files"][0]["path"] = name
            with self.assertRaisesRegex(h.HandoffError, "selected private 3080"):h.validate_manifest(body)

    def test_destination_symlink_parent_is_rejected(self):
        outside = self.base / "outside";outside.mkdir();self.target.mkdir()
        try:(self.target / "scripts").symlink_to(outside, target_is_directory=True)
        except OSError:self.skipTest("Symlink creation unavailable")
        with self.assertRaisesRegex(h.HandoffError, "Symlink/reparse"):
            h.checked_path(self.target, "scripts/example.py")

    def test_target_corruption_is_detected(self):
        self.export();h.import_bundle(self.bundle, self.target, apply=True)
        (self.target / "scripts/example.py").write_bytes(b"bad")
        with self.assertRaisesRegex(h.HandoffError, "Restored file changed"):h.verify_target(self.target)

    def test_manifest_tampering_is_detected(self):
        self.export();pointer = h.read(self.bundle / "latest.json")
        (self.bundle / "snapshots" / (pointer["snapshot"] + ".json")).write_text("{}")
        with self.assertRaisesRegex(h.HandoffError, "Manifest digest mismatch"):h.verify_bundle(self.bundle)

    def test_bundle_lock_does_not_restart_or_steal_export(self):
        self.bundle.mkdir();(self.bundle / "handoff.lock").write_text("existing worker")
        with self.assertRaisesRegex(h.HandoffError, "locked"):
            h.export_bundle(self.source, self.bundle, self.body(), apply=True)
        self.assertEqual((self.bundle / "handoff.lock").read_text(), "existing worker")

    def test_interrupted_unpublished_partial_is_not_an_object(self):
        self.export();(self.bundle / "abandoned.partial").write_bytes(b"partial")
        self.export()
        self.assertTrue(h.verify_bundle(self.bundle)["passed"])
        self.assertEqual((self.bundle / "abandoned.partial").read_bytes(), b"partial")

    def test_import_does_not_execute_transferred_code(self):
        sentinel = self.base / "executed"
        self.write("scripts/example.py", ("open("+repr(str(sentinel))+", 'w').write('bad')").encode())
        self.export();h.import_bundle(self.bundle, self.target, apply=True)
        self.assertFalse(sentinel.exists())

    def test_runtime_closure_is_static_and_fails_on_missing_dependency(self):
        self.write("work/one.py", b"raise RuntimeError('never execute')\nPATH = 'work/two.py'\n")
        self.write("work/two.py", b"VALUE = 2\n")
        self.assertEqual(h.runtime_closure(self.source, {"work/one.py"}), {"work/one.py", "work/two.py"})
        (self.source / "work/two.py").unlink()
        with self.assertRaisesRegex(h.HandoffError, "Missing runtime dependency"):
            h.runtime_closure(self.source, {"work/one.py"})

    def test_import_target_cannot_be_inside_package(self):
        self.export()
        with self.assertRaisesRegex(h.HandoffError, "must not overlap"):
            h.import_bundle(self.bundle, self.bundle / "target", apply=True)

    def test_copy_refuses_a_racing_destination(self):
        source = self.source / "scripts/example.py";target = self.base / "race.py";target.write_bytes(b"keep")
        with self.assertRaisesRegex(h.HandoffError, "Destination appeared"):
            h._copy_verified(source, target, {"path": "scripts/example.py", "sha256": h.sha(source), "size": source.stat().st_size})
        self.assertEqual(target.read_bytes(), b"keep")

    def test_bootstrap_is_included_without_git_or_network_commands(self):
        self.write("home_podcast/private_handoff.py", Path(h.__file__).read_bytes())
        self.export()
        self.assertEqual((self.bundle / "handoff.py").read_bytes(), Path(h.__file__).read_bytes())

    def test_unknown_nonempty_export_folder_is_untouched(self):
        self.bundle.mkdir();(self.bundle / "handoff.py").write_bytes(b"other project")
        with self.assertRaisesRegex(h.HandoffError, "empty folder"):
            h.export_bundle(self.source, self.bundle, self.body(), apply=True)
        self.assertEqual((self.bundle / "handoff.py").read_bytes(), b"other project")

    def test_import_receipt_is_a_reserved_payload_name(self):
        body = self.body();body["files"][0]["path"] = "private-handoff-receipt.json"
        with self.assertRaisesRegex(h.HandoffError, "Reserved import receipt"):h.validate_manifest(body)

    def test_file_directory_collision_rejected_in_manifest(self):
        body = self.body();body["files"][0]["path"] = "folder";body["files"][1]["path"] = "FOLDER/nested.py"
        with self.assertRaisesRegex(h.HandoffError, "File/directory path collision"):h.validate_manifest(body)

    def test_import_parent_file_preflight_copies_nothing(self):
        self.export();self.target.mkdir();(self.target / "scripts").write_text("keep")
        with self.assertRaisesRegex(h.HandoffError, "parent is a file"):
            h.import_bundle(self.bundle, self.target, apply=True)
        self.assertFalse((self.target / "data").exists())

    def test_modified_standalone_tool_is_preserved(self):
        self.write("home_podcast/private_handoff.py", Path(h.__file__).read_bytes());body = self.export()
        (self.bundle / "handoff.py").write_bytes(b"my local tool")
        with self.assertRaisesRegex(h.HandoffError, "locally edited"):
            h.export_bundle(self.source, self.bundle, body, apply=True)
        self.assertEqual((self.bundle / "handoff.py").read_bytes(), b"my local tool")


class HandoffRebindingHelpersTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = Path(__file__).resolve().parents[1] / "touchdesigner/rebind_private_handoff.py"
        spec = importlib.util.spec_from_file_location("rh_test_private_rebind", source)
        cls.module = importlib.util.module_from_spec(spec);spec.loader.exec_module(cls.module)

    def test_literal_repr_and_forward_slash_paths(self):
        old = r"C:\Users\old\home-podcast";new = r"D:\shows\home-podcast"
        for form in (old, old.replace("\\", "\\\\"), old.replace("\\", "/")):
            text = "open(" + form + "/work/callback.py)"
            result = self.module.replace_root(text, old, new)
            self.assertNotIn(form, result)
            self.assertIn("callback.py", result)

    def test_nested_destination_does_not_replace_twice(self):
        result = self.module.replace_root("/old/work/file.py", "/old", "/old/new")
        self.assertEqual(result, "/old/new/work/file.py")

    def test_manifest_suffix_required(self):
        relative = h.EDITION + "/playlist.json"
        self.assertEqual(self.module.old_root_from_manifest("D:/project/"+relative, relative), "D:/project")
        with self.assertRaises(RuntimeError):self.module.old_root_from_manifest("D:/wrong/playlist.json", relative)


if __name__ == "__main__":
    unittest.main()
