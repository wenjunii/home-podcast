import importlib.util
from pathlib import Path
import runpy
import tempfile
from types import SimpleNamespace
import unittest

from test_show_control_callbacks import FakePar, FakePars

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("control_audit_5090_test", ROOT / "touchdesigner/control_audit_5090_136.py")
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class FullControlAuditTests(unittest.TestCase):
    def test_inventory_is_exhaustive_and_rejects_unknown_controls(self):
        self.assertEqual(len(audit.EXPECTED), 40)
        self.assertFalse(audit.coverage(audit.EXPECTED)["unknown"])
        result = audit.coverage((audit.EXPECTED - {"Play"}) | {"Mysteryslider"})
        self.assertEqual(result["missing"], ["Play"])
        self.assertEqual(result["unknown"], ["Mysteryslider"])

    def test_cases_cover_every_editable_control_and_never_enable_generation(self):
        cases = audit.cases()
        exercised = {v if n == "pulse" else n for n, v in cases}
        self.assertEqual(exercised, audit.ACTIVE | audit.DORMANT)
        self.assertFalse(exercised & audit.LOCKED)
        self.assertFalse(exercised & audit.DISABLED)
        for field, minimum, maximum in (("Gamma", .1, 4), ("Hue", -180, 180),
                                         ("Brightness", 0, 2), ("Crossfadesec", 0, 30)):
            values = [v for n, v in cases if n == field]
            self.assertEqual(min(values), minimum)
            self.assertEqual(max(values), maximum)

    def test_missing_duplicate_failed_or_unrestored_case_cannot_pass(self):
        good = [dict(id=0, passed=True), dict(id=1, passed=True)]
        self.assertTrue(audit.terminal_result(2, good, True)["passed"])
        for details, restored in ((good[:1], True), (good + good[:1], True),
                                   ([dict(id=0, passed=False), good[1]], True), (good, False)):
            self.assertFalse(audit.terminal_result(2, details, restored)["passed"])

    def test_signed_hue_limits_have_equivalent_cyclic_rotations(self):
        self.assertEqual(audit.downstream_value("Hue", -180), 180)
        self.assertEqual(audit.downstream_value("Hue", -90), 270)
        self.assertEqual(audit.downstream_value("Hue", 180), 180)
        self.assertEqual(audit.downstream_value("Hue", 0), 0)
        self.assertEqual(audit.downstream_value("Brightness", 2), 2)

    def test_3080_audit_refused_before_graph_access(self):
        original_project = getattr(audit, "project", None)
        audit.project = SimpleNamespace(name="podcast.40.toe")
        try:
            with self.assertRaisesRegex(RuntimeError, "5090 .25"):
                audit.guard()
        finally:
            audit.project = original_project

    def test_canonical_writer_forces_live_off_and_does_not_regenerate(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "control.json"
            connector = SimpleNamespace(par=FakePars(
                Livecontroljson=FakePar("Livecontroljson", str(output)), Runtimeprofile=FakePar("Runtimeprofile", "5090_live")))
            control = SimpleNamespace(par=FakePars(**{name: FakePar(name, value) for name, value in dict(
                Runtimeprofile="5090_live", Livevariations=True, Narrationvariation=True,
                Speechvariation=True, Visualvariation=True, Interpretivecasting=True,
                Randomvariationseeds=False, Variationseed=77).items()}), parent=lambda: connector)
            namespace = runpy.run_path(str(ROOT / "touchdesigner/canonical_5090_callbacks.py"), init_globals={
                "project": SimpleNamespace(folder=str(ROOT)), "parent": lambda: control})
            value = namespace["_write_live_control"](regenerate=True)
            self.assertEqual(value["profile"], "3080_safe")
            self.assertFalse(value["enabled"])
            self.assertFalse(control.par.Livevariations.eval())
            self.assertEqual(control.par.Runtimeprofile.eval(), "3080_safe")
            self.assertEqual(value["regeneration_nonce"], 0)
            self.assertEqual(value["fixed_seed"], 77)
            for field in ("Runtimeprofile", "Livevariations"):
                control.par.Runtimeprofile = "5090_live"
                control.par.Livevariations = True
                namespace["onValueChange"](getattr(control.par, field), None)
                self.assertFalse(control.par.Livevariations.eval())
                self.assertEqual(control.par.Runtimeprofile.eval(), "3080_safe")
            namespace["onPulse"](FakePar("Regeneratenext", True))
            import json
            self.assertEqual(json.loads(output.read_text(encoding="utf-8"))["regeneration_nonce"], 0)


if __name__ == "__main__":
    unittest.main()
