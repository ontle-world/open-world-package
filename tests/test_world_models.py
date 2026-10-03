"""The reference World Models in examples/business/quality-scenario-world-model."""
import subprocess
import sys
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "examples" / "business" / "quality-scenario-world-model"
RUN = PACKAGE / "models" / "run.py"


def run(*args: str) -> dict:
    out = subprocess.run([sys.executable, str(RUN), *args], check=True, capture_output=True, text=True)
    return yaml.safe_load(out.stdout)


class ReferenceWorldModelTests(unittest.TestCase):
    def test_baselines_reproduce_the_packaged_outputs(self):
        packaged = yaml.safe_load((PACKAGE / "examples" / "baseline-outputs.yaml").read_text(encoding="utf-8"))
        self.assertEqual(run("--baselines"), packaged)

    def test_baselines_answer_in_one_shape(self):
        for result in run("--baselines")["results"]:
            with self.subTest(model=result["model"]):
                self.assertTrue({"expected_outcome", "range", "risk", "uncertainty", "predicted_transition"} <= set(result))
                self.assertIsNotNone(result["uncertainty"])

    def test_three_point_and_monte_carlo_stay_in_range(self):
        scenario = yaml.safe_load((ROOT / "examples" / "business" / "manufacturing-quality-world" / "scenarios" / "quality-hold.yaml").read_text())
        bounds = scenario["spec"]["uncertainty"]
        for result in run("--baselines")["results"]:
            for name, value in result["expected_outcome"].items():
                with self.subTest(model=result["model"], variable=name):
                    self.assertLessEqual(bounds[name]["low"], value)
                    self.assertLessEqual(value, bounds[name]["high"])

    def test_every_model_artifact_points_at_a_function(self):
        source = RUN.read_text(encoding="utf-8")
        for path in sorted((PACKAGE / "models").glob("*.yaml")):
            doc = yaml.safe_load(path.read_text(encoding="utf-8"))
            if doc["kind"] != "ModelArtifact":
                continue
            file, _, name = doc["spec"]["entrypoint"].partition("#")
            with self.subTest(artifact=path.name):
                self.assertEqual(file, "models/run.py")
                self.assertIn(f"\ndef {name}(", source)


if __name__ == "__main__":
    unittest.main()
