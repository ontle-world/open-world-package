"""Binding meaning checks (spec 14): binding.path-domain and binding.value-range, in validation (owp-yaml schemas)
and in the tools (kg check --bindings for RDF schemas, ews check --source for EWS values)."""
import contextlib
import importlib.util
import io
import shutil
import tempfile
import unittest
from pathlib import Path

from ontle import cli
from ontle.resolve import validate_resolved

ROOT = Path(__file__).resolve().parent.parent
CASES = ROOT / "conformance" / "resolution"
HAS_RDFLIB = importlib.util.find_spec("rdflib") is not None

TURTLE = """@prefix q: <https://example.org/q#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
q:Claim a owl:Class . q:Lot a owl:Class . q:ProposeCapa a owl:Class .
q:claimStatus a owl:DatatypeProperty ; rdfs:domain q:Claim .
q:derivedFrom a owl:ObjectProperty ; rdfs:domain q:Lot ; rdfs:range q:Lot .
"""


def run_cli(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli.main(argv)
    return code, out.getvalue(), err.getvalue()


def rdf_only_copy(case: str, td: str) -> Path:
    """The case with its ontology published as Turtle only: validation cannot judge it."""
    dest = Path(td) / case
    shutil.copytree(CASES / case, dest)
    onto = dest / "packages" / "onto"
    (onto / "semantics" / "core.yaml").unlink()
    (onto / "semantics" / "core.ttl").write_text(TURTLE, encoding="utf-8")
    (onto / "semantics" / "terms.yaml").write_text(
        "apiVersion: openworld/v1alpha1\nkind: OntologyTermIndex\nmetadata: {name: terms}\nspec:\n  terms:\n"
        + "".join(f"  - {{iri: 'https://example.org/q#{n}', type: {t}}}\n" for n, t in
                  (("Claim", "class"), ("Lot", "class"), ("ProposeCapa", "class"), ("claimStatus", "property"), ("derivedFrom", "property"))),
        encoding="utf-8")
    manifest = onto / "owp.yaml"
    manifest.write_text(manifest.read_text(encoding="utf-8").replace(
        "- {path: semantics/core.yaml, format: owp-yaml, role: schema}",
        "- {path: semantics/core.ttl, format: turtle, role: schema}\n    termIndex: semantics/terms.yaml"), encoding="utf-8")
    return dest


class BindingCheckTests(unittest.TestCase):
    def test_validation_does_not_judge_rdf_only_ontologies(self):
        with tempfile.TemporaryDirectory() as td:
            case = rdf_only_copy("binding-path-domain", td)
            result, _ = validate_resolved(str(case / "root"), [str(case / "packages")])
            self.assertTrue(result.valid, result.errors)
            self.assertFalse([w for w in result.warnings if w.startswith("binding.path-domain")])

    @unittest.skipUnless(HAS_RDFLIB, "rdflib not installed (pip install 'ontle[rdf]')")
    def test_kg_check_bindings_judges_rdf_schemas(self):
        with tempfile.TemporaryDirectory() as td:
            case = rdf_only_copy("binding-path-domain", td)
            code, out, _ = run_cli(["kg", "check", str(case / "root"), "--source", str(case / "packages"), "--bindings"])
            self.assertEqual(code, 0)
            self.assertIn("binding.path-domain", out)
            self.assertIn("1 binding warning", out)
            good = rdf_only_copy("binding-grounded", td)
            self.assertIn("0 binding warnings", run_cli(["kg", "check", str(good / "root"), "--source", str(good / "packages"), "--bindings"])[1])

    def test_ews_check_source_warns_about_values_outside_an_enum(self):
        world = ROOT / "examples" / "business" / "manufacturing-quality-world"
        expected = world / "examples" / "expected-ews.yaml"
        code, out, _ = run_cli(["ews", "check", str(expected), "--world", str(world), "--source", str(ROOT / "examples")])
        self.assertEqual((code, out.strip()), (0, "VALID"))
        with tempfile.TemporaryDirectory() as td:
            wrong = Path(td) / "wrong.yaml"
            wrong.write_text(expected.read_text(encoding="utf-8").replace("quality_incident.status: under_investigation",
                                                                          "quality_incident.status: pending"), encoding="utf-8")
            code, out, _ = run_cli(["ews", "check", str(wrong), "--world", str(world), "--source", str(ROOT / "examples")])
            self.assertEqual(code, 0)  # a warning, not a failure
            self.assertIn("value outside range: state.quality_incident.status is 'pending'", out)


if __name__ == "__main__":
    unittest.main()
