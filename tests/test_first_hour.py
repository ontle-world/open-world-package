"""What a newcomer does first: init a World, compile its state, ground a World Model in it, pack."""
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

import yaml

from ontle.core import deterministic_pack
from ontle.ews import check_ews, compile_ews
from ontle.scaffold import init_project

ROOT = Path(__file__).resolve().parent.parent


def cli(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    env.pop("ONTLE_PATH", None)
    return subprocess.run([sys.executable, "-m", "ontle.cli", *args], cwd=cwd, env=env, capture_output=True, text=True)


class FirstHourTests(unittest.TestCase):
    def test_world_starters_compile_to_their_expected_ews(self):
        for template in ("minimal", "enterprise"):
            with self.subTest(template=template), tempfile.TemporaryDirectory() as td:
                p = init_project("w", "acme", template, Path(td) / "w")
                observations = yaml.safe_load((p / "examples" / "observations.yaml").read_text(encoding="utf-8"))
                ews = compile_ews(p, "state/default-compiler.yaml", observations, "2026-01-02T00:00:00Z")
                self.assertEqual(ews, yaml.safe_load((p / "examples" / "expected-ews.yaml").read_text(encoding="utf-8")))
                self.assertEqual(ews["spec"]["worldRef"], "acme/w@0.1.0")
                self.assertEqual(ews["spec"]["state"]["item.attention"], {"item-1": "normal", "item-2": "needs_attention"})
                self.assertEqual(check_ews(p, ews), [])

    def test_ews_compile_defaults_to_the_worlds_compiler(self):
        with tempfile.TemporaryDirectory() as td:
            init_project("w", "acme", "minimal", Path(td) / "w")
            r = cli("ews", "compile", "w", "--observations", "w/examples/observations.yaml", "--as-of", "2026-01-02T00:00:00Z", cwd=Path(td))
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("item.events_24h", r.stdout)

    def test_validate_says_whether_grounding_was_checked(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            init_project("w", "acme", "minimal", d / "w")
            init_project("m", "acme", "worldmodel", d / "m", world=str(d / "w"))
            r = cli("validate", "m", cwd=d)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("NOTE: resolved 1 dependency and checked cross-package rules", r.stdout)
            manifest = (d / "m" / "owp.yaml").read_text(encoding="utf-8")
            (d / "m" / "owp.yaml").write_text(manifest.replace("#views/default.yaml", "#views/defalt.yaml"), encoding="utf-8")
            r = cli("validate", "m", cwd=d)
            self.assertEqual(r.returncode, 1)
            self.assertIn("its Views: views/default.yaml", r.stderr)
            (d / "m" / ".ontle" / "project.yaml").unlink()
            r = cli("validate", "m", cwd=d)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("NOTE: checked this package only; dependencies not found: acme/w@0.1.0", r.stdout)

    def test_init_grounds_a_world_model_in_a_chosen_view(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            w = init_project("w", "acme", "minimal", d / "w")
            (w / "views" / "triage.yaml").write_text((w / "views" / "default.yaml").read_text(encoding="utf-8").replace("default-view", "triage"), encoding="utf-8")
            (w / "state" / "triage.yaml").write_text((w / "state" / "default-compiler.yaml").read_text(encoding="utf-8")
                                                     .replace("views/default.yaml", "views/triage.yaml").replace("default-state-compiler", "triage"), encoding="utf-8")
            m = init_project("m", "acme", "worldmodel", d / "m", world=str(w), view="views/triage.yaml")
            grounding = yaml.safe_load((m / "owp.yaml").read_text(encoding="utf-8"))["spec"]["worldModel"]["semanticGrounding"]
            self.assertEqual(grounding["compatibleStateCompilers"], ["acme/w@0.1.0#state/triage.yaml"])

    def test_dot_paths_are_never_packed(self):
        with tempfile.TemporaryDirectory() as td:
            p = init_project("w", "acme", "minimal", Path(td) / "w")
            (p / ".env").write_text("API_KEY=secret\n")
            (p / ".secrets").mkdir()
            (p / ".secrets" / "token").write_text("x\n")
            with zipfile.ZipFile(deterministic_pack(p, Path(td) / "w.owp.zip")) as z:
                names = z.namelist()
            self.assertFalse([n for n in names if any(part.startswith(".") for part in n.split("/"))], names)
            self.assertIn("examples/expected-ews.yaml", names)


if __name__ == "__main__":
    unittest.main()
