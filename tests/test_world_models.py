"""The reference World Models in examples/business/quality-scenario-world-model."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "examples" / "business" / "quality-scenario-world-model"
RUN = PACKAGE / "models" / "run.py"
OUTCOME = PACKAGE / "examples" / "observed-outcome.yaml"


def run(*args: str, cwd: Path | None = None) -> dict:
    out = subprocess.run([sys.executable, str(RUN), *args], check=True, capture_output=True, text=True, cwd=cwd)
    return yaml.safe_load(out.stdout)


class ReferenceWorldModelTests(unittest.TestCase):
    def test_baselines_reproduce_the_packaged_outputs(self):
        packaged = yaml.safe_load((PACKAGE / "examples" / "baseline-outputs.yaml").read_text(encoding="utf-8"))
        self.assertEqual(run("--baselines", "--evaluate", str(OUTCOME)), packaged)

    def test_results_list_what_they_provide(self):
        for result in run("--baselines")["results"]:
            with self.subTest(model=result["model"]):
                self.assertIn("uncertainty", result["provides"])
                self.assertEqual(set(result["provides"]), set(result) & {"expected_outcome", "range", "risk", "uncertainty", "predicted_transition"})

    def test_own_model_runs_next_to_the_baselines_on_another_ews(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "mine.py").write_text("def predict(ews, scenario, observations, compiler):\n"
                                       "    return {'expected_outcome': {'late': 1}}\n", encoding="utf-8")
            (d / "scenario.yaml").write_text("spec: {timeHorizon: P7D, uncertainty: {late: {low: 0, high: 4}}}\n", encoding="utf-8")
            (d / "ews.yaml").write_text("spec: {context: {asOf: '2026-01-02T00:00:00Z'}, state: {item.status: {item-1: active}}}\n", encoding="utf-8")
            out = run("--model", "persistence", "--entrypoint", "mine.py#predict", "--ews", "ews.yaml", "--scenario", "scenario.yaml", cwd=d)
        persistence, mine = out["results"]
        self.assertEqual(persistence["predicted_transition"]["item.status[item-1]"]["at_horizon"], {"active": 1.0})
        self.assertEqual((mine["model"], mine["provides"], mine["expected_outcome"]), ("mine.py#predict", ["expected_outcome"], {"late": 1}))

    def test_three_point_and_monte_carlo_stay_in_range(self):
        scenario = yaml.safe_load((ROOT / "examples" / "business" / "manufacturing-quality-world" / "scenarios" / "quality-hold.yaml").read_text())
        bounds = scenario["spec"]["uncertainty"]
        for result in run("--baselines")["results"]:
            for name, value in result.get("expected_outcome", {}).items():
                with self.subTest(model=result["model"], variable=name):
                    self.assertLessEqual(bounds[name]["low"], value)
                    self.assertLessEqual(value, bounds[name]["high"])

    def test_markov_rows_are_distributions_and_horizon_sums_to_one(self):
        params = yaml.safe_load((PACKAGE / "models" / "markov-transitions.yaml").read_text(encoding="utf-8"))
        for field, spec in params["fields"].items():
            for state, row in spec["rows"].items():
                with self.subTest(field=field, state=state):
                    self.assertTrue(set(row) <= set(spec["states"]))
                    self.assertAlmostEqual(sum(row.values()), 1.0)
        markov = next(r for r in run("--baselines")["results"] if r["model"] == "markov")
        self.assertEqual(markov["uncertainty"]["steps"], 14)
        for field, out in markov["predicted_transition"].items():
            with self.subTest(field=field):
                self.assertAlmostEqual(sum(out["at_horizon"].values()), 1.0, places=2)
        self.assertEqual(markov["predicted_transition"]["capa.status"]["from"], {"proposed": 0.5, "approved": 0.5})

    def test_every_model_artifact_points_at_a_function(self):
        source = RUN.read_text(encoding="utf-8")
        for path in sorted((PACKAGE / "models").glob("*.yaml")):
            doc = yaml.safe_load(path.read_text(encoding="utf-8"))
            if doc.get("kind") != "ModelArtifact":
                continue
            file, _, name = doc["spec"]["entrypoint"].partition("#")
            with self.subTest(artifact=path.name):
                self.assertEqual(file, "models/run.py")
                self.assertIn(f"\ndef {name}(", source)


if __name__ == "__main__":
    unittest.main()
