from __future__ import annotations

import ast
import runpy
import unittest
from pathlib import Path
from types import SimpleNamespace


SCRIPT_PATH = (
    Path(__file__).parents[1]
    / "touchdesigner"
    / "audit_5090_visuals.py"
)


class Audit5090VisualsTests(unittest.TestCase):
    def test_status_keys_accept_streamdiffusion_hyphens(self) -> None:
        source = SCRIPT_PATH.read_text(encoding="utf-8")
        module = ast.parse(source, filename=str(SCRIPT_PATH))
        declarations = [
            node
            for node in module.body
            if not (
                isinstance(node, ast.Assign)
                and any(
                    isinstance(target, ast.Name)
                    and target.id == "audit_5090_visual_report"
                    for target in node.targets
                )
            )
        ]
        namespace: dict[str, object] = {}
        exec(
            compile(
                ast.Module(body=declarations, type_ignores=[]),
                str(SCRIPT_PATH),
                "exec",
            ),
            namespace,
        )

        class Cell:
            def __init__(self, value: str) -> None:
                self.value = value

            def __str__(self) -> str:
                return self.value

        class Table:
            numRows = 2

            def __getitem__(self, item: tuple[int, int]) -> Cell:
                values = {
                    (1, 0): Cell(" stream-state "),
                    (1, 1): Cell(" ONLINE "),
                }
                return values[item]

        result = namespace["_table_values"](Table())
        self.assertEqual(result["stream-state"], "ONLINE")
        self.assertEqual(result["stream_state"], "ONLINE")

    def test_current_local_connection_state_overrides_legacy_offline(
        self,
    ) -> None:
        source = SCRIPT_PATH.read_text(encoding="utf-8")
        module = ast.parse(source, filename=str(SCRIPT_PATH))
        declarations = [
            node
            for node in module.body
            if not (
                isinstance(node, ast.Assign)
                and any(
                    isinstance(target, ast.Name)
                    and target.id == "audit_5090_visual_report"
                    for target in node.targets
                )
            )
        ]
        namespace: dict[str, object] = {}
        exec(
            compile(
                ast.Module(body=declarations, type_ignores=[]),
                str(SCRIPT_PATH),
                "exec",
            ),
            namespace,
        )

        active, local_state, legacy_state = namespace[
            "_connection_is_active"
        ](
            {"connection_state": "stream_active"},
            {"stream-state": "OFFLINE", "stream_state": "OFFLINE"},
        )
        self.assertTrue(active)
        self.assertEqual(local_state, "STREAM_ACTIVE")
        self.assertEqual(legacy_state, "OFFLINE")

    def test_refuses_3080_project_before_accessing_the_operator_graph(
        self,
    ) -> None:
        with self.assertRaisesRegex(
            RuntimeError,
            "Refusing to audit visuals in a non-5090 project",
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
