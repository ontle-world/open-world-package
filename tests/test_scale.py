"""The toolchain at scale, on a synthetic plant (scripts/make_scale_fixture.py): a T-box of 52 classes and 6 enum types,
an A-box of about 1,000 individuals, and about 1,900 observations of 120 machines and 200 lots.

The EWS is compared with values the generator computes from its own observations, without the State Compiler; both
implementations must give that EWS and the same verdicts; the semantic checks must stay quiet on the correct fixture and
find what is broken on purpose; and nothing may take long.
"""
import contextlib
import importlib.util
import io
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from ontle import cli
from ontle.core import deterministic_pack, verify_archive
from ontle.distribution import build_index
from ontle.ews import check_ews, compile_ews, ews_equal
from ontle.mcp import PackageServer
from ontle.ontology import term_catalog
from ontle.report import package_report
from ontle.resolve import validate_resolved
from ontle.yamlio import dump_yaml, load_yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from make_scale_fixture import make  # noqa: E402

TS_CLI = ROOT / "implementations" / "typescript" / "dist" / "cli.js"
HAS_NODE = bool(shutil.which("node")) and TS_CLI.is_file()
HAS_RDFLIB = importlib.util.find_spec("rdflib") is not None
COMPILERS = {"state/equipment-health.yaml": "equipment.", "state/lot-quality.yaml": "lot."}


def run_cli(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli.main(argv)
    return code, out.getvalue(), err.getvalue()


class ScaleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.dir = Path(cls._tmp.name)
        cls.facts = make(cls.dir)
        cls.onto, cls.world, cls.model = (cls.dir / n for n in ("plant-ontology", "plant-world", "plant-model"))
        cls.observations = load_yaml((cls.world / "examples" / "observations.yaml").read_text(encoding="utf-8"))

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def compile(self, compiler):
        return compile_ews(self.world, compiler, self.observations, self.facts["asOf"])

    def test_fixture_is_at_scale(self):
        manifest = load_yaml((self.onto / "owp.yaml").read_text(encoding="utf-8"))
        classes = [t for t in term_catalog(self.onto, manifest) if t["type"] == "class"]
        self.assertGreaterEqual(len(classes), 40)
        abox = (self.world / "kg" / "plant.ttl").read_text(encoding="utf-8")
        individuals = set(re.findall(r"^<([^>]+)> a p:", abox, re.M))
        self.assertGreaterEqual(len(individuals), 400)
        self.assertGreaterEqual(len(self.observations["spec"]["observations"]), 400)

    def test_every_package_validates_with_resolution(self):
        for package in (self.onto, self.world, self.model):
            with self.subTest(package=package.name):
                result, resolution = validate_resolved(str(package), [str(self.dir)])
                self.assertTrue(result.valid, result.errors[:5])
                self.assertEqual(result.warnings, [])

    def test_fixture_has_the_cases_where_compilers_go_wrong(self):
        """Not only the happy path: ties, observations after asOf, at the window start and at asOf, estimates, a field
        without observations, and subjects whose candidates the filter removes."""
        obs = self.observations["spec"]["observations"]
        self.assertGreaterEqual(len(self.facts["unresolved"]["equipment.state"]), 10)
        self.assertTrue(any(o["observedAt"] > self.facts["asOf"] for o in obs))
        self.assertTrue(any(o["observedAt"] == self.facts["asOf"] for o in obs))
        self.assertTrue(any(o["observedAt"] == "2026-09-09T00:00:00Z" and o["type"] == "OT.alarm" for o in obs))
        self.assertTrue(any("estimatedBy" in o for o in obs))
        self.assertIn("normal", self.facts["expected"]["equipment.temp_band"].values())  # a classification's otherwise
        self.assertTrue(any(o["type"] == "OT.temperature" and "sensor" not in o["values"] for o in obs))  # no `where` key
        e = self.facts["expected"]
        self.assertTrue(any(n > 0 and e["equipment.critical_alarms_24h"][k] == 0 for k, n in e["equipment.alarms_24h"].items()))  # alarms, none critical
        self.assertIn(0, e["equipment.alarms_24h"].values())  # a machine of the subject set without alarms: 0, not absent
        self.assertIn("normal", e["equipment.risk"].values())
        self.assertEqual(len(e["equipment.risk"]), len(self.facts["equipment"]))  # every machine is classified

    def test_ews_equals_the_values_computed_from_the_observations(self):
        for compiler, prefix in COMPILERS.items():
            ews = self.compile(compiler)
            self.assertEqual(check_ews(self.world, ews), [])
            spec = ews["spec"]
            for field, want in self.facts["expected"].items():
                if field.startswith(prefix):
                    with self.subTest(field=field):
                        self.assertEqual(spec["state"].get(field, {}), want)
            for field, want in self.facts["unresolved"].items():
                if field.startswith(prefix):
                    with self.subTest(unresolved=field):
                        self.assertEqual(spec["unresolved"].get(field), want)
            for field, want in self.facts["provenance"].items():
                if field.startswith(prefix):
                    with self.subTest(provenance=field):
                        self.assertEqual({k: sorted(v) for k, v in spec["provenance"].get(field, {}).items()}, want)
            self.assertEqual(sorted(spec["missing"]), self.facts["missing"][compiler])

    def test_cli_round_trip_by_value_and_against_the_ontology(self):
        ews_path = self.dir / "equipment-ews.yaml"
        ews_path.write_text(dump_yaml(self.compile("state/equipment-health.yaml")), encoding="utf-8")
        obs = str(self.world / "examples" / "observations.yaml")
        code, out, err = run_cli(["ews", "check", str(ews_path), "--world", str(self.world), "--observations", obs, "--source", str(self.dir)])
        self.assertEqual((code, out.strip(), err), (0, "VALID", ""))
        broken = load_yaml(ews_path.read_text(encoding="utf-8"))
        first = sorted(broken["spec"]["state"]["equipment.state"])[0]  # a resolved subject
        broken["spec"]["state"]["equipment.state"][first] = "exploded"
        ews_path.write_text(dump_yaml(broken), encoding="utf-8")
        code, out, err = run_cli(["ews", "check", str(ews_path), "--world", str(self.world), "--source", str(self.dir)])
        self.assertIn(f"state.equipment.state subject {first!r} is 'exploded'", out)
        code, _, err = run_cli(["ews", "check", str(ews_path), "--world", str(self.world), "--observations", obs])
        self.assertEqual(code, 1)
        self.assertIn('state.equipment.state: expected', err)

    def test_report_counts(self):
        report = package_report(self.world)
        self.assertTrue(report["valid"])
        self.assertEqual(report["state"], {"stateCompilers": 2, "fields": 13, "withBinding": 13})
        self.assertEqual(report["semanticCoverage"], {"boundToTerms": 13, "fields": 13})
        self.assertEqual(report["hints"], [])
        self.assertEqual(package_report(self.onto)["ontology"]["terms"], self.facts["classes"] + self.facts["enums"] + self.facts["properties"])

    def test_binding_checks_stay_quiet_and_find_a_wrong_path(self):
        with tempfile.TemporaryDirectory() as td:
            shutil.copytree(self.dir, td, dirs_exist_ok=True)
            binding = Path(td) / "plant-world" / "semantics" / "plant-terms.yaml"
            doc = load_yaml(binding.read_text(encoding="utf-8"))
            doc["spec"]["fields"]["lot.status"] = {"class": "p:Lot", "path": ["p:operatingState"]}  # an Equipment property
            binding.write_text(dump_yaml(doc), encoding="utf-8")
            result, _ = validate_resolved(str(Path(td) / "plant-world"), [td])
            self.assertTrue(result.valid)
            self.assertEqual([w.split(":")[0] for w in result.warnings], ["binding.path-domain"])

    @unittest.skipUnless(HAS_RDFLIB, "rdflib not installed (pip install 'ontle[rdf]')")
    def test_knowledge_graph_conforms_and_violations_are_found(self):
        code, out, _ = run_cli(["kg", "check", str(self.world), "--source", str(self.dir)])
        self.assertEqual(code, 0, out)
        with tempfile.TemporaryDirectory() as td:
            shutil.copytree(self.dir, td, dirs_exist_ok=True)
            kg = Path(td) / "plant-world" / "kg" / "plant.ttl"
            bad = [f'<https://w3id.org/scale-fixture/plant/id/lot-LOT-{i:04d}> p:operatingState "running" .' for i in range(1, 6)]
            bad.append("<https://w3id.org/scale-fixture/plant/id/x> a p:NoSuchClass .")
            kg.write_text(kg.read_text(encoding="utf-8") + "\n".join(bad) + "\n", encoding="utf-8")
            code, _, err = run_cli(["kg", "check", str(Path(td) / "plant-world"), "--source", td])
            self.assertEqual(code, 1)
            self.assertIn("(5x)", err)  # the five domain violations are counted as one finding
            self.assertIn("NoSuchClass", err)

    def test_pack_index_and_resolve_through_the_index(self):
        with tempfile.TemporaryDirectory() as td:
            archives = [deterministic_pack(p, Path(td) / f"{p.name}.owp.zip") for p in (self.onto, self.world, self.model)]
            for a in archives:
                self.assertEqual(verify_archive(a), (True, []))
            index = Path(td) / "index.json"
            index.write_text(json.dumps(build_index(archives, Path(td), terms=True)), encoding="utf-8")
            result, resolution = validate_resolved(str(self.model), [f"index:{index}"])
            self.assertTrue(result.valid, result.errors[:5])
            self.assertEqual(len(resolution.packages), 3)

    def test_mcp_finds_terms_of_a_large_ontology(self):
        server = PackageServer(self.world, self.world, sources=[str(self.dir)])
        matches = server.lookup("CncMachine")["matches"]
        self.assertIn("p:CncMachine", [m.get("curie") for m in matches])

    def test_time_budget(self):
        """Generous limits: they catch a quadratic step, not a slow machine."""
        start = time.monotonic()
        validate_resolved(str(self.model), [str(self.dir)])
        for compiler in COMPILERS:
            self.compile(compiler)
        package_report(self.world)
        self.assertLess(time.monotonic() - start, 30)

    @unittest.skipUnless(HAS_NODE, "needs node and the built TypeScript implementation")
    def test_typescript_gives_the_same_verdicts_and_ews(self):
        for package in (self.onto, self.world, self.model):
            with self.subTest(package=package.name):
                run = subprocess.run(["node", str(TS_CLI), "--json", "--resolve", "--source", str(self.dir), str(package)],
                                     capture_output=True, text=True, timeout=120)
                ts = json.loads(run.stdout)
                py, _ = validate_resolved(str(package), [str(self.dir)])
                self.assertEqual(ts["valid"], py.valid)
                self.assertEqual(sorted({e["code"] for e in ts["errors"]}), sorted({e.split(":")[0] for e in py.errors}))
                self.assertEqual(sorted({w["code"] for w in ts["warnings"]}), sorted({w.split(":")[0] for w in py.warnings}))
        for compiler in COMPILERS:
            with self.subTest(compiler=compiler):
                run = subprocess.run(["node", str(TS_CLI), "ews", "compile", str(self.world), "--compiler", compiler,
                                      "--observations", str(self.world / "examples" / "observations.yaml"), "--as-of", self.facts["asOf"]],
                                     capture_output=True, text=True, timeout=120)
                self.assertEqual(run.returncode, 0, run.stderr)
                self.assertTrue(ews_equal(load_yaml(run.stdout), self.compile(compiler)))


if __name__ == "__main__":
    unittest.main()
