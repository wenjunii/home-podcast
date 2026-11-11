from __future__ import annotations

import runpy
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace


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
                "op": lambda path: connector, "marker": marker,
            })
            self.assertEqual(marker, ["canonical-rebind"])
            self.assertEqual(result["updated_5090_project"]["edition"], "canonical-136")
            self.assertFalse(result["updated_5090_project"]["live_generation"])

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
