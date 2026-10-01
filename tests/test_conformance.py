import unittest
from pathlib import Path

import yaml

from ontle.core import inspect_package, validate_package

SUITE = Path(__file__).resolve().parent.parent / "conformance"


def rule_ids(errors):
    return {e.split(":", 1)[0] for e in errors}


class ConformanceSuiteTests(unittest.TestCase):
    def test_reference_validator_matches_expected_outcomes(self):
        expected = yaml.safe_load((SUITE / "expected.yaml").read_text(encoding="utf-8"))["cases"]
        on_disk = {p.name for p in (SUITE / "cases").iterdir() if p.is_dir()}
        self.assertEqual(on_disk, set(expected))
        for case_id, exp in expected.items():
            with self.subTest(case=case_id):
                root = SUITE / "cases" / case_id
                result = validate_package(root)
                self.assertEqual(result.valid, exp["valid"], result.errors)
                self.assertLessEqual(set(exp.get("errors", [])), rule_ids(result.errors), result.errors)
                self.assertLessEqual(set(exp.get("warnings", [])), rule_ids(result.warnings), result.warnings)
                if "satisfiedProfile" in exp:
                    self.assertEqual(inspect_package(root)["conformance"]["satisfied"], exp["satisfiedProfile"])


if __name__ == "__main__":
    unittest.main()
