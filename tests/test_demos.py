"""End-to-end demos (ROADMAP section 4): the committed observations, EWS, and evidence are reproducible."""
import subprocess
import sys
import unittest
from pathlib import Path

DEMOS = Path(__file__).resolve().parent.parent / "demos"


class DemoTests(unittest.TestCase):
    def run_script(self, script):
        result = subprocess.run([sys.executable, str(DEMOS / script), "--check"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_business_records_map_to_committed_observations(self):
        self.run_script("business-ai/map_records.py")

    def test_business_demo_reproduces_ews_and_evidence(self):
        self.run_script("business-ai/run.py")

    def test_physical_demo_reproduces_ews_and_evidence(self):
        self.run_script("physical-ai/run.py")


if __name__ == "__main__":
    unittest.main()
