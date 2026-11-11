import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("build_5090_136", ROOT / "scripts/build_5090_136_native.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class Build5090Tests(unittest.TestCase):
    def test_renderer_descendants_and_settings_are_never_donor_owned(self):
        for name in ("StreamDiffusionTD.parm", "StreamDiffusionTD2.cparm", "StreamDiffusionTD/secret.text",
                     "StreamDiffusionTD_callbacks.text", "StreamDiffusionTD_callbacks2.text", "audio_out.parm", "syphonspoutout2.n"):
            name = module.PREFIX + "/" + name
            self.assertTrue(module.protected(name))
            self.assertFalse(module.own(name))
        self.assertTrue(module.own(module.PREFIX + "/show_control/playlist_callbacks.text"))
        self.assertFalse(module.own("project1.parm"))

    def test_text_dat_utf8_length_is_recomputed(self):
        payload = b"print('old')\n"
        original = b"2\n*" + struct.pack(">6I", 1, 1, 1, 1, 2, len(payload)) + payload
        changed = module.encode_dat(original, "print('new \u2014 5090')\n")
        self.assertEqual(module.decode_dat(changed), "print('new \u2014 5090')\n")
        with self.assertRaises(ValueError):
            module.decode_dat(changed[:-1])

    def test_path_rebase_is_one_pass_and_does_not_rewrite_neighbor_roots(self):
        old = r"C:\sender\home-podcast"
        new = Path(r"C:\receiver\home-podcast")
        text = old + "|" + old.replace("\\", "\\\\") + "|" + old.replace("\\", "/")
        result = module.replace_root(text, old, new)
        self.assertNotIn("sender", result)
        self.assertIn(str(new), result)

    def test_parameter_update_retains_other_device_settings(self):
        result = module.set_parameter("?\nplay 0 1\ndevice 0 RECEIVER_DEVICE\n?\n", "play", "0", "0")
        self.assertIn("play 0 0", result)
        self.assertIn("device 0 RECEIVER_DEVICE", result)
        self.assertEqual(result.count("play 0"), 1)

    def test_wrong_native_target_refused_before_io(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(ValueError):
                module.build(root, root / "podcast.3080.20.toe", root / "podcast.40.toe",
                             root / "podcast.5090.25.toe", root / "scratch", root)
            self.assertFalse((root / "scratch").exists())


if __name__ == "__main__":
    unittest.main()
