from __future__ import annotations

import runpy
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from touchdesigner import verify_5090_audio_overlay as overlay


SCRIPT_PATH = (
    Path(__file__).parents[1]
    / "touchdesigner"
    / "update_5090_project.py"
)


class Update5090ProjectTests(unittest.TestCase):
    def test_canonical_edition_dispatch_does_not_rebind_to_pilot(self):
        marker = []
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "touchdesigner").mkdir()
            (root / "touchdesigner/rebind_5090_136.py").write_text(
                "marker.append('canonical-rebind')\n", encoding="utf-8")
            (root / "touchdesigner/install_show_control.py").write_text(
                "raise RuntimeError('pilot must not run')\n", encoding="utf-8")
            connector = SimpleNamespace(par=SimpleNamespace(Playlistmanifest=SimpleNamespace(
                eval=lambda: str(root / "work/storytelling-real-december/continuous-image-hold-136-3080-2026-10-30/playlist.json"))))
            result = runpy.run_path(str(SCRIPT_PATH), init_globals={
                "project": SimpleNamespace(name="podcast.5090.25.toe", folder=directory),
                "app": SimpleNamespace(build="2025.32820"),
                "op": lambda path: connector if path == "/project1/podcast_visualizer" else None,
                "marker": marker,
            })
            self.assertEqual(marker, ["canonical-rebind"])
            self.assertEqual(result["updated_5090_project"]["edition"], "canonical-136")
            self.assertFalse(result["updated_5090_project"]["live_generation"])

    def run_update(self, revision, playlist, helpers):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root / "touchdesigner").mkdir()
            for name in ("install_show_control.py", "rebind_5090_136.py", "rebind_project_paths.py"):
                (root / "touchdesigner" / name).write_text(
                    "raise AssertionError('legacy writer must not run')\n", encoding="utf-8")
            for name, source in helpers.items():
                (root / "touchdesigner" / name).write_text(source, encoding="utf-8")
            parms = {"Streamdiffusionpath": SimpleNamespace(eval=lambda: "StreamDiffusionTD;StreamDiffusionTD2")}
            if playlist is not None:
                parms["Playlistmanifest"] = SimpleNamespace(eval=lambda: playlist)
            connector = SimpleNamespace(par=SimpleNamespace(**parms))
            return runpy.run_path(str(SCRIPT_PATH), init_globals={
                "project": SimpleNamespace(name=f"podcast.5090.{revision}.toe", folder=str(root)),
                "app": SimpleNamespace(build="2025.32820"),
                "op": lambda path: connector if path == "/project1/podcast_visualizer" else None,
            })["updated_5090_project"]

    def test_mcp_test_folder_is_refused_before_operator_access(self):
        with tempfile.TemporaryDirectory() as directory:
            test_root = Path(directory) / "home-podcast-5090-mcp-test"
            with self.assertRaisesRegex(RuntimeError, "isolated MCP test copy"):
                runpy.run_path(str(SCRIPT_PATH), init_globals={
                    "project": SimpleNamespace(name="podcast.5090.27.toe", folder=test_root),
                })

    def test_mcp_identity_marker_is_refused_even_if_the_copy_is_renamed(self):
        def op(path):
            self.assertEqual(path, "/rh_podcast_5090_27_mcp_guard")
            return object()

        with self.assertRaisesRegex(RuntimeError, "isolated MCP test copy"):
            runpy.run_path(str(SCRIPT_PATH), init_globals={
                "project": SimpleNamespace(name="podcast.5090.25.toe", folder="."),
                "op": op,
            })

    def test_26_dispatches_to_read_only_verifier(self):
        result = self.run_update(26, overlay.OVERLAY_PLAYLIST, {
            "verify_5090_audio_overlay.py": (
                "def verify_native_overlay(root, name, build, connector):\n"
                "    assert name == 'podcast.5090.26.toe' and build == '2025.32820'\n"
                "    return {'read_only': True, 'native_bindings_verified': True}\n"
            ),
        })
        self.assertTrue(result["read_only"])
        self.assertTrue(result["native_bindings_verified"])

    def test_absent_verifier_does_not_fall_back(self):
        with self.assertRaisesRegex(RuntimeError, "Missing 5090 audio-overlay verifier"):
            self.run_update(26, overlay.OVERLAY_PLAYLIST, {})

    def test_later_numbered_projects_never_fall_back_with_stale_or_missing_playlist(self):
        helper = SCRIPT_PATH.with_name("verify_5090_audio_overlay.py").read_text(encoding="utf-8")
        for number in (26, 27):
            for playlist in (None, overlay.BASE_PLAYLIST, "not-an-edition/playlist.json"):
                with self.subTest(number=number, playlist=playlist):
                    with self.assertRaisesRegex(RuntimeError, "Unexpected Playlistmanifest binding"):
                        self.run_update(number, playlist, {"verify_5090_audio_overlay.py": helper})

    def test_25_does_not_replace_overlay_or_guess_pilot_paths(self):
        for playlist in (None, overlay.OVERLAY_PLAYLIST, "archive/" + overlay.BASE_PLAYLIST + ".bak"):
            with self.subTest(playlist=playlist), self.assertRaisesRegex(RuntimeError, "original canonical playlist"):
                self.run_update(25, playlist, {})

    def test_older_numbered_receiver_with_edition_does_not_run_pilot(self):
        with self.assertRaisesRegex(RuntimeError, "refusing to run the pilot"):
            self.run_update(24, overlay.OVERLAY_PLAYLIST, {})

    def test_pilot_can_still_dispatch_without_an_edition_playlist(self):
        with self.assertRaisesRegex(RuntimeError, "pilot dispatched"):
            self.run_update(24, None, {
                "install_show_control.py": "raise RuntimeError('pilot dispatched')\n",
            })

    def test_direct_legacy_rebinder_refuses_26_before_operator_access(self):
        with self.assertRaisesRegex(RuntimeError, "only for podcast.5090.25.toe"):
            runpy.run_path(str(SCRIPT_PATH.with_name("rebind_5090_136.py")), init_globals={
                "project": SimpleNamespace(name="podcast.5090.26.toe"),
                "app": SimpleNamespace(build="2025.32820"),
            })

    def test_direct_legacy_rebinder_refuses_overlay_even_on_25(self):
        connector = SimpleNamespace(
            par=SimpleNamespace(Playlistmanifest=SimpleNamespace(eval=lambda: overlay.OVERLAY_PLAYLIST)),
        )
        with self.assertRaisesRegex(RuntimeError, "unknown or newer 5090 playlist"):
            runpy.run_path(str(SCRIPT_PATH.with_name("rebind_5090_136.py")), init_globals={
                "project": SimpleNamespace(name="podcast.5090.25.toe", folder="."),
                "app": SimpleNamespace(build="2025.32820"),
                "op": lambda path: connector,
            })

    def test_refuses_3080_project_before_accessing_the_operator_graph(
        self,
    ) -> None:
        with self.assertRaisesRegex(
            RuntimeError,
            "Refusing to update a non-5090 project",
        ):
            runpy.run_path(
                str(SCRIPT_PATH),
                init_globals={
                    "project": SimpleNamespace(
                        name="podcast.3080.20.toe",
                    )
                },
            )


if __name__ == "__main__":
    unittest.main()
