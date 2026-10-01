import json
import unittest
from pathlib import Path

import yaml

from ontle.core import OWPError
from ontle.ews import json_equal
from ontle.extraction import transform

SUITE = Path(__file__).resolve().parent.parent / "conformance"


class ExtractionConformanceTests(unittest.TestCase):
    def test_extraction_cases(self):
        expected = yaml.safe_load((SUITE / "expected.yaml").read_text(encoding="utf-8"))["extractionCases"]
        self.assertEqual({p.name for p in (SUITE / "extraction").iterdir() if p.is_dir()}, set(expected))
        for case_id, exp in expected.items():
            with self.subTest(case=case_id):
                case = SUITE / "extraction" / case_id
                profile = yaml.safe_load((case / "profile.yaml").read_text(encoding="utf-8"))
                rows = json.loads((case / "results.json").read_text(encoding="utf-8"))
                if exp.get("error"):
                    with self.assertRaises(OWPError) as ctx:
                        transform(profile, rows, exp.get("parameters", {}), exp.get("snapshot"))
                    self.assertLessEqual(set(exp.get("errors", [])), {str(ctx.exception).split(":", 1)[0]})
                else:
                    out = transform(profile, rows, exp.get("parameters", {}), exp.get("snapshot"))
                    want = yaml.safe_load((case / "expected-observations.yaml").read_text(encoding="utf-8"))
                    self.assertTrue(json_equal(out, want), out)


if __name__ == "__main__":
    unittest.main()
