from __future__ import annotations

import runpy
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).parents[1]
TOUCHDESIGNER = ROOT / "touchdesigner"


class TouchDesigner3080WrapperTests(unittest.TestCase):
    def test_all_wrappers_reject_unrelated_project_names(self) -> None:
        for filename in (
            "update_3080_project.py",
            "audit_3080_controls.py",
            "audit_3080_live_events.py",
            "audit_3080_visuals.py",
        ):
            with self.subTest(filename=filename), self.assertRaisesRegex(
                RuntimeError,
                "non-3080",
            ):
                runpy.run_path(
                    str(TOUCHDESIGNER / filename),
                    init_globals={
                        "project": SimpleNamespace(
                            name="unrelated.toe",
                            folder=str(ROOT),
                        )
                    },
                )

    def test_updater_accepts_active_numbered_3080_filename(self) -> None:
        with self.assertRaisesRegex(
            RuntimeError,
            "Missing /project1/podcast_visualizer in the 3080 project",
        ):
            runpy.run_path(
                str(TOUCHDESIGNER / "update_3080_project.py"),
                init_globals={
                    "project": SimpleNamespace(
                        name="podcast.20.toe",
                        folder=str(ROOT),
                    ),
                    "op": lambda path: None,
                },
            )

    def test_updater_accepts_explicit_3080_filename(self) -> None:
        with self.assertRaisesRegex(
            RuntimeError,
            "Missing /project1/podcast_visualizer in the 3080 project",
        ):
            runpy.run_path(
                str(TOUCHDESIGNER / "update_3080_project.py"),
                init_globals={
                    "project": SimpleNamespace(
                        name="podcast.3080.21.toe",
                        folder=str(ROOT),
                    ),
                    "op": lambda path: None,
                },
            )


if __name__ == "__main__":
    unittest.main()
