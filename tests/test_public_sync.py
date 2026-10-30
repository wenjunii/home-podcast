from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from scripts.check_public_sync import audit


class PublicSyncTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.git("init", "-q")
        self.write("README.md", "Initial\n");self.git("add", "README.md");self.commit("Initial")
        self.base = self.git("rev-parse", "HEAD").decode().strip()

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.root, capture_output=True, check=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout

    def commit(self, message):
        self.git("-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", message)

    def write(self, name, text):
        path = self.root / name;path.parent.mkdir(parents=True, exist_ok=True);path.write_text(text, encoding="utf-8")

    def memory_git(self, payload, history=False):
        """Synthetic Git protocol in RAM; credential fixtures never touch disk.

        Safe-file tests below still exercise real Git end to end. This seam
        keeps both the staged-blob and deleted-in-a-later-commit regressions
        without materializing credential-shaped bytes in files or Git objects.
        """
        oid, first, second, base = (character*40 for character in "1234")
        name = b"config/key.json\0"
        header = f"{oid} blob {len(payload)}\n".encode("ascii")

        def invoke(root, *args, input_data=None):
            if args[0] == "diff":
                return name
            if args[0] == "ls-files":
                return f"100644 {oid} 0\tconfig/key.json\0".encode("ascii")
            if args[0] == "rev-parse":
                return (base+"\n").encode("ascii")
            if args[0] == "rev-list":
                return (first+"\n"+second+"\n").encode("ascii")
            if args[0] == "diff-tree":
                return name if args[-1] == first else b""
            if args[0] == "ls-tree":
                return f"100644 blob {oid}\tconfig/key.json\0".encode("ascii") if args[-1] == first else b""
            if args[:2] == ("cat-file", "--batch-check"):
                self.assertEqual(input_data, (oid+"\n").encode("ascii"))
                return header
            if args[:2] == ("cat-file", "--batch"):
                self.assertEqual(input_data, (oid+"\n").encode("ascii"))
                return header+payload+b"\n"
            raise AssertionError("Unexpected Git operation")

        with patch("scripts.check_public_sync.git", side_effect=invoke):
            return audit(self.root, "fixture-base" if history else None)

    def test_code_and_docs_are_allowed(self):
        self.write("scripts/example.py", "VALUE = 1\n");self.git("add", "scripts/example.py")
        result = audit(self.root)
        self.assertTrue(result["passed"]);self.assertEqual(result["blobs_scanned"], 1)

    def test_private_assets_blocked_even_if_force_staged(self):
        for name in ("work/bundle/latest.json", "narrations/story/adaptation.json", "data/full_exports/stories_en.md", "audio/file.wav", "podcast.40.toe"):
            self.write(name, "private");self.git("add", "-f", "--", name)
        result = audit(self.root)
        self.assertFalse(result["passed"]);self.assertEqual(len(result["findings"]), 5)

    def test_actual_staged_secret_is_found_after_working_copy_cleaned(self):
        secret = "sk-" + "aB1"*12
        self.write("config/key.json", '{"api_key":null}')
        result = self.memory_git(('{"api_key":"'+secret+'"}').encode("utf-8"))
        self.assertFalse(result["passed"]);self.assertNotIn(secret, str(result))
        self.assertEqual((self.root / "config/key.json").read_text(encoding="utf-8"), '{"api_key":null}')

    def test_clean_index_not_confused_with_secret_unstaged_file(self):
        self.write("config/key.json", '{"api_key":null}');self.git("add", "config/key.json")
        # Invalid but non-sensitive working-copy content must not replace the
        # safe JSON actually in the index.
        self.write("config/key.json", "UNSTAGED CONTENT IS NOT THE INDEX")
        self.assertTrue(audit(self.root)["passed"])

    def test_nonstandard_credential_field_is_blocked(self):
        self.assertFalse(self.memory_git(b'{"client_secret":"synthetic-test-marker"}')["passed"])

    def test_deleted_later_secret_still_blocks_commit_range(self):
        result = self.memory_git(b'{"api_key":"synthetic-test-marker"}', history=True)
        self.assertFalse(result["passed"]);self.assertEqual(result["commits"], 2)

    def test_deleted_private_asset_still_blocks_real_commit_range(self):
        self.write("work/fixture.txt", "Synthetic fixture data")
        self.git("add", "-f", "work/fixture.txt");self.commit("Add fixture")
        self.git("rm", "work/fixture.txt");self.commit("Remove fixture")
        result = audit(self.root, self.base)
        self.assertFalse(result["passed"]);self.assertEqual(result["commits"], 2)

    def test_safe_commit_range(self):
        self.write("README.md", "Updated\n");self.git("add", "README.md");self.commit("Docs")
        self.assertTrue(audit(self.root, self.base)["passed"])

    def test_binary_payload_cannot_hide_in_python_file(self):
        self.write("scripts/not-source.py", "binary\0payload");self.git("add", "scripts/not-source.py")
        self.assertFalse(audit(self.root)["passed"])

    def test_oversized_payload_is_refused_before_batch_read(self):
        self.write("scripts/oversize.py", "x"*(5*1024*1024+1));self.git("add", "scripts/oversize.py")
        with self.assertRaisesRegex(ValueError, "oversized public source"):
            audit(self.root)


if __name__ == "__main__":
    unittest.main()
