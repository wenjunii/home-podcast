import hashlib
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scripts import prepare_5090_preflight_handoff as handoff


@unittest.skipUnless(shutil.which("git"), "Git executable required")
class HandoffTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.git("init", "-q")
        self.write(".gitignore", "work/\n")
        self.write("README.md", "Base docs.\n")
        self.commit("Base")
        self.base = self.git("rev-parse", "HEAD").decode("ascii").strip()
        self.write("README.md", "Base docs.\n\nPreflight instructions.\n")
        self.write("scripts/verify_3080_show_41.py", "# Reviewed verifier fixture\n")
        self.write("tests/test_verify_3080_show_41.py", "# Reviewed tests fixture\n")
        self.commit("Reviewed code-only update")
        self.head = self.git("rev-parse", "HEAD").decode("ascii").strip()
        self.patch = self.git("diff", *handoff.DIFF_OPTIONS, self.base, self.head, "--")
        self.digest = hashlib.sha256(self.patch).hexdigest()
        bindings = patch.multiple(handoff, BASE=self.base, HEAD=self.head, PATCH_SHA256=self.digest)
        self.addCleanup(bindings.stop)
        bindings.start()

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.root, capture_output=True, check=True,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def commit(self, message):
        self.git("add", "-A")
        self.git("-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", message)

    def test_preview_reads_commits_not_uncommitted_files(self):
        self.write("README.md", "ONLY ON THE SENDER.\n")
        before = self.git("status", "--porcelain")
        result = handoff.prepare(self.root, "valid-preview")
        self.assertFalse((self.root / "work").exists())
        self.assertFalse(result["apply"])
        self.assertFalse(result["receiver_contacted"])
        self.assertEqual(result["patch_sha256"], self.digest)
        self.assertEqual(result["local_files_written"], 0)
        self.assertEqual(self.git("status", "--porcelain"), before)

    def test_apply_creates_only_exact_patch_and_note_and_never_overwrites(self):
        result = handoff.prepare(self.root, "single-copy", apply=True)
        target = self.root / result["bundle"]
        self.assertEqual({item.name for item in target.iterdir()}, {handoff.PATCH_NAME, handoff.NOTE_NAME})
        self.assertEqual((target / handoff.PATCH_NAME).read_bytes(), self.patch)
        note = (target / handoff.NOTE_NAME).read_text(encoding="utf-8")
        self.assertIn(self.digest, note)
        self.assertIn("Wait for the user", note)
        self.assertIn("touchdesigner.verify_5090_audio_overlay", note)
        self.git("apply", "--reverse", "--check", "--", str(target / handoff.PATCH_NAME))
        self.assertEqual(self.git("status", "--porcelain"), b"")
        with self.assertRaisesRegex(handoff.PreparationError, "output already exists"):
            handoff.prepare(self.root, "single-copy", apply=True)
        self.assertEqual((target / handoff.PATCH_NAME).read_bytes(), self.patch)

    def test_unreviewed_hash_or_extra_path_is_not_exported(self):
        with (patch.object(handoff, "PATCH_SHA256", "0" * 64),
              self.assertRaisesRegex(handoff.PreparationError, "differs from the exact reviewed")):
            handoff.prepare(self.root, "wrong-digest", apply=True)
        self.git("checkout", "-qb", "extra-path-fixture", self.base)
        self.write("other.txt", "Outside the approved scope.\n")
        self.commit("Unexpected file")
        other = self.git("rev-parse", "HEAD").decode("ascii").strip()
        with (patch.object(handoff, "HEAD", other),
              self.assertRaisesRegex(handoff.PreparationError, "exactly the three expected")):
            handoff.prepare(self.root, "wrong-scope", apply=True)
        self.assertFalse((self.root / "work").exists())

    def test_missing_commit_nonignored_output_and_bad_label_fail_no_write(self):
        with (patch.object(handoff, "HEAD", "0" * 40),
              self.assertRaisesRegex(handoff.PreparationError, "No automatic fetch")):
            handoff.prepare(self.root, "missing", apply=True)
        with self.assertRaisesRegex(handoff.PreparationError, "short, non-secret label"):
            handoff.prepare(self.root, "../outside", apply=True)
        self.write(".gitignore", "# not ignored\n")
        with self.assertRaisesRegex(handoff.PreparationError, "ignored output path"):
            handoff.prepare(self.root, "would-be-visible", apply=True)
        self.assertFalse((self.root / "work").exists())


class LocalGitTests(unittest.TestCase):
    def test_subprocess_has_no_fetch_or_external_protocol(self):
        with patch.object(subprocess, "run", return_value=SimpleNamespace(returncode=0, stdout=b"")) as run:
            handoff.local_git(Path.cwd(), "rev-parse", "HEAD")
        self.assertEqual(run.call_args.kwargs["env"]["GIT_NO_LAZY_FETCH"], "1")
        self.assertEqual(run.call_args.kwargs["env"]["GIT_ALLOW_PROTOCOL"], "")
        self.assertEqual(run.call_args.kwargs["env"]["GIT_TERMINAL_PROMPT"], "0")


if __name__ == "__main__":
    unittest.main()
