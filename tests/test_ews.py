import unittest
from pathlib import Path

import yaml

from ontle.core import OWPError, validate_package
from ontle.ews import check_ews, compile_ews, ews_equal, json_equal, load_document

REPO = Path(__file__).resolve().parent.parent
SUITE = REPO / "conformance"
EXAMPLES = [
    (REPO / "examples" / "business" / "manufacturing-quality-world", "state/quality-incident-compiler.yaml", "2026-09-05T00:00:00Z"),
    (REPO / "examples" / "physical-ai" / "mobile-manipulation-world", "state/pick-place-compiler.yaml", "2026-09-01T12:00:03Z"),
    (REPO / "examples" / "business" / "management-report-world", "state/executive-summary-compiler.yaml", "2026-10-02T09:00:00Z"),
]


def rule_ids(errors):
    return {e.split(":", 1)[0] for e in errors}


def load(path):
    return load_document(path)


class EwsTests(unittest.TestCase):
    def test_ews_compile_conformance_cases(self):
        expected = yaml.safe_load((SUITE / "expected.yaml").read_text(encoding="utf-8"))["ewsCases"]
        self.assertEqual({p.name for p in (SUITE / "ews").iterdir() if p.is_dir()}, set(expected))
        for case_id, exp in expected.items():
            with self.subTest(case=case_id):
                case = SUITE / "ews" / case_id
                observations = load(case / "observations.yaml")
                if exp.get("error"):
                    with self.assertRaises(OWPError) as ctx:
                        compile_ews(case / "world", exp["compiler"], observations, exp["asOf"])
                    self.assertLessEqual(set(exp.get("errors", [])), rule_ids([str(ctx.exception)]))
                    continue
                ews = compile_ews(case / "world", exp["compiler"], observations, exp["asOf"])
                self.assertTrue(ews_equal(ews, load(case / "expected-ews.yaml")), ews)
                self.assertEqual(check_ews(case / "world", ews), [])

    def test_ews_check_conformance_cases(self):
        expected = yaml.safe_load((SUITE / "expected.yaml").read_text(encoding="utf-8"))["ewsCheckCases"]
        self.assertEqual({p.name for p in (SUITE / "ews-check").iterdir() if p.is_dir()}, set(expected))
        for case_id, exp in expected.items():
            with self.subTest(case=case_id):
                case = SUITE / "ews-check" / case_id
                errors = check_ews(case / "world", load(case / "ews.yaml"))
                self.assertEqual(not errors, exp["valid"], errors)
                self.assertLessEqual(set(exp.get("errors", [])), rule_ids(errors), errors)

    def test_examples_compile_to_packaged_expected_ews(self):
        for world, compiler, as_of in EXAMPLES:
            with self.subTest(world=world.name):
                ews = compile_ews(world, compiler, load(world / "examples" / "observations.yaml"), as_of)
                self.assertTrue(ews_equal(ews, load(world / "examples" / "expected-ews.yaml")), ews)
                self.assertEqual(check_ews(world, ews), [])

    def test_json_model_equality(self):
        self.assertFalse(json_equal(True, 1))
        self.assertTrue(json_equal(1, 1.0))
        self.assertTrue(json_equal({"a": [1, {"b": None}]}, {"a": [1.0, {"b": None}]}))
        self.assertFalse(json_equal([1, 2], [2, 1]))

    def test_unquoted_timestamps_are_read_as_text(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "obs.yaml"
            f.write_text("kind: ObservationSet\nspec:\n  observations:\n  - {id: o1, type: t, observedAt: 2026-01-01T09:00:01+09:00, values: {v: 1}}\n", encoding="utf-8")
            self.assertEqual(load(f)["spec"]["observations"][0]["observedAt"], "2026-01-01T09:00:01+09:00")

    def test_opaque_compiler_cannot_be_run(self):
        world = SUITE / "cases" / "world-stateful-satisfies-higher"
        with self.assertRaises(OWPError):
            compile_ews(world, "state/task-compiler.yaml", {"kind": "ObservationSet", "spec": {"observations": []}}, "2026-01-01T00:00:00Z")

    def test_binding_outside_schema_invalidates_package(self):
        import shutil
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            world = Path(td) / "world"
            shutil.copytree(SUITE / "ews" / "latest-picks-newest" / "world", world)
            compiler = world / "state" / "task-compiler.yaml"
            data = load(compiler)
            data["spec"]["bindings"]["z.unknown"] = {"from": "sensor.z", "value": "v"}
            compiler.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
            result = validate_package(world)
            self.assertFalse(result.valid)
            self.assertTrue(any("z.unknown" in e for e in result.errors))


if __name__ == "__main__":
    unittest.main()
