from __future__ import annotations

import runpy
import unittest
from pathlib import Path
from types import SimpleNamespace


SCRIPT_PATH = (
    Path(__file__).parents[1]
    / "touchdesigner"
    / "audit_5090_controls.py"
)


class Audit5090ControlsTests(unittest.TestCase):
    def test_refuses_3080_project_before_accessing_the_operator_graph(
        self,
    ) -> None:
        with self.assertRaisesRegex(
            RuntimeError,
            "Refusing to audit a non-5090 project",
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
