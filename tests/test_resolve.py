import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml

from ontle.core import deterministic_pack
from ontle.resolve import resolve_package, validate_resolved

REPO = Path(__file__).resolve().parent.parent
SUITE = REPO / "conformance"
EXAMPLES = REPO / "examples"
MODEL = EXAMPLES / "physical-ai" / "multimodal-action-world-model"
WORLD = EXAMPLES / "physical-ai" / "mobile-manipulation-world"
WORLD_REF = "openworld-examples/mobile-manipulation-world@0.1.0"


def rule_ids(errors):
    return {e.split(":", 1)[0] for e in errors}


class ResolveTests(unittest.TestCase):
    def setUp(self):
        self._cache = tempfile.TemporaryDirectory()
        patcher = mock.patch.dict(os.environ, {"ONTLE_CACHE": self._cache.name})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self._cache.cleanup)

    def test_resolution_conformance_cases(self):
        expected = yaml.safe_load((SUITE / "expected.yaml").read_text(encoding="utf-8"))["resolutionCases"]
        on_disk = {p.name for p in (SUITE / "resolution").iterdir() if p.is_dir()}
        self.assertEqual(on_disk, set(expected))
        for case_id, exp in expected.items():
            with self.subTest(case=case_id):
                case = SUITE / "resolution" / case_id
                result, resolution = validate_resolved(case / "root", [str(case / "packages")])
                self.assertEqual(result.valid, exp["valid"], result.errors)
                self.assertLessEqual(set(exp.get("errors", [])), rule_ids(result.errors), result.errors)
                if "resolved" in exp:
                    recorded = {i: p.revision for i, p in resolution.packages.items() if i != resolution.root.identity}
                    self.assertEqual(recorded, exp["resolved"])

    def test_examples_resolve_across_packages(self):
        # The business World depends on the quality ontology, so its model's closure has three packages.
        for model, size in ((MODEL, 2), (EXAMPLES / "business" / "quality-transition-world-model", 3)):
            with self.subTest(model=model.name):
                result, resolution = validate_resolved(model, [str(EXAMPLES)])
                self.assertTrue(result.valid, result.errors)
                self.assertEqual(len(resolution.packages), size)

    def test_unresolved_without_sources(self):
        with mock.patch.dict(os.environ, {"ONTLE_PATH": ""}):
            resolution = resolve_package(MODEL, [])
        self.assertTrue(any("cannot resolve" in e for e in resolution.errors))

    def test_ontle_path_environment_source(self):
        with mock.patch.dict(os.environ, {"ONTLE_PATH": str(EXAMPLES)}):
            resolution = resolve_package(MODEL, [])
        self.assertEqual(resolution.errors, [])
        self.assertIn(WORLD_REF, resolution.packages)

    def test_archive_source(self):
        with tempfile.TemporaryDirectory() as td:
            archive = deterministic_pack(WORLD, Path(td) / "world.owp.zip")
            result, resolution = validate_resolved(MODEL, [str(archive)])
            self.assertTrue(result.valid, result.errors)
            self.assertTrue(resolution.packages[WORLD_REF].revision.startswith("sha256:"))

    def test_tampered_archive_rejected(self):
        import zipfile
        with tempfile.TemporaryDirectory() as td:
            archive = deterministic_pack(WORLD, Path(td) / "world.owp.zip")
            tampered = Path(td) / "tampered.owp.zip"
            with zipfile.ZipFile(archive) as src, zipfile.ZipFile(tampered, "w") as dst:
                for name in src.namelist():
                    data = src.read(name)
                    dst.writestr(name, data + b"\n# tampered\n" if name == "WORLD.md" else data)
            resolution = resolve_package(MODEL, [str(tampered)])
            self.assertTrue(any("failed verification" in e for e in resolution.errors), resolution.errors)

    @unittest.skipUnless(shutil.which("git"), "git not installed")
    def test_git_source_pins_commit(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "world-repo"
            shutil.copytree(WORLD, repo / "packages" / "world")
            env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
                   "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid"}
            for cmd in (["init", "-q"], ["add", "."], ["commit", "-q", "-m", "world"], ["tag", "v0.1.0"]):
                subprocess.run(["git", "-C", str(repo), *cmd], check=True, env=env)
            commit = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
            source = f"git+{repo.as_uri()}@v0.1.0#subdir=packages"
            result, resolution = validate_resolved(MODEL, [source])
            self.assertTrue(result.valid, result.errors)
            self.assertEqual(resolution.packages[WORLD_REF].revision, f"git:{commit}")


if __name__ == "__main__":
    unittest.main()
