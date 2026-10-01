import importlib.util
import shutil
import tempfile
import unittest
from pathlib import Path

import yaml

from ontle.core import deterministic_pack, inspect_package, validate_package
from ontle.ontology import export_rdf, write_term_index
from ontle.scaffold import init_project

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = ROOT / "examples" / "ontology" / "quality-ontology"
HAS_RDFLIB = importlib.util.find_spec("rdflib") is not None


class OntologyTests(unittest.TestCase):
    def test_template_satisfies_schema_profile(self):
        with tempfile.TemporaryDirectory() as td:
            p = init_project("demo-ontology", "test", "ontology", Path(td) / "demo-ontology")
            result = validate_package(p)
            self.assertTrue(result.valid, result.errors)
            self.assertEqual(inspect_package(p)["conformance"]["satisfied"], "schema")

    def test_example_is_mapped(self):
        self.assertTrue(validate_package(EXAMPLE).valid)
        self.assertEqual(inspect_package(EXAMPLE)["conformance"]["satisfied"], "mapped")

    def test_term_index_from_owp_yaml(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "onto"
            shutil.copytree(EXAMPLE, root)
            target = write_term_index(root, root / "owp.yaml")
            terms = yaml.safe_load(target.read_text(encoding="utf-8"))["spec"]["terms"]
            self.assertIn({"iri": "https://w3id.org/openworld-examples/quality#Claim", "type": "class"}, terms)
            self.assertIn({"iri": "https://w3id.org/openworld-examples/quality#claimStatus", "type": "property"}, terms)
            self.assertEqual(yaml.safe_load((root / "owp.yaml").read_text(encoding="utf-8"))["spec"]["ontology"]["termIndex"], "semantics/terms.yaml")
            self.assertTrue(validate_package(root).valid)

    def test_export_turtle_and_jsonld(self):
        manifest = yaml.safe_load((EXAMPLE / "owp.yaml").read_text(encoding="utf-8"))
        turtle = export_rdf(EXAMPLE, manifest, "turtle")
        self.assertIn("<https://w3id.org/openworld-examples/quality#Claim> rdf:type owl:Class .", turtle)
        jsonld = export_rdf(EXAMPLE, manifest, "jsonld")
        if HAS_RDFLIB:
            import rdflib
            a = rdflib.Graph().parse(data=turtle, format="turtle")
            b = rdflib.Graph().parse(data=jsonld, format="json-ld")
            self.assertEqual(len(a), len(b))
            self.assertGreater(len(a), 0)

    @unittest.skipUnless(HAS_RDFLIB, "rdflib not installed (pip install 'ontle-open-world[rdf]')")
    def test_pack_generates_missing_term_index_for_rdf_schema(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "onto"
            (root / "semantics").mkdir(parents=True)
            (root / "ONTOLOGY.md").write_text("# Onto\n", encoding="utf-8")
            (root / "semantics" / "core.ttl").write_text(
                "@prefix q: <https://example.org/q#> .\n@prefix owl: <http://www.w3.org/2002/07/owl#> .\nq:Claim a owl:Class .\n",
                encoding="utf-8")
            (root / "owp.yaml").write_text(yaml.safe_dump({
                "apiVersion": "openworld/v1alpha1", "kind": "OntologyPackage",
                "metadata": {"namespace": "test", "name": "onto", "version": "0.1.0"},
                "spec": {"ontology": {"description": "ONTOLOGY.md", "iri": "https://example.org/q#",
                                      "entrypoints": [{"path": "semantics/core.ttl", "format": "turtle", "role": "schema"}]},
                         "conformance": {"profile": "schema"}, "assets": []},
            }, sort_keys=False), encoding="utf-8")
            self.assertFalse(validate_package(root).valid)
            deterministic_pack(root, Path(td) / "onto.owp.zip")
            self.assertTrue(validate_package(root).valid)
            terms = yaml.safe_load((root / "semantics" / "terms.yaml").read_text(encoding="utf-8"))["spec"]["terms"]
            self.assertEqual(terms, [{"iri": "https://example.org/q#Claim", "type": "class"}])


class SemanticBindingTests(unittest.TestCase):
    def test_manufacturing_world_is_fully_bound(self):
        from ontle.resolve import ews_jsonld, validate_resolved
        world = ROOT / "examples" / "business" / "manufacturing-quality-world"
        result, _ = validate_resolved(world, [str(ROOT / "examples")])
        self.assertTrue(result.valid, result.errors)
        self.assertEqual(inspect_package(world)["semanticCoverage"], {"boundFields": 9, "fields": 9})
        doc = ews_jsonld(world, {"apiVersion": "openworld/v1alpha1", "kind": "EffectiveWorldState", "spec": {}}, [str(ROOT / "examples")])
        self.assertEqual(doc["@context"]["claim.status"], {"@id": "https://w3id.org/openworld-examples/quality#claimStatus"})


class KnowledgeExtractionTests(unittest.TestCase):
    @unittest.skipUnless(HAS_RDFLIB, "rdflib not installed (pip install 'ontle-open-world[rdf]')")
    def test_example_extraction_runs_sparql_with_parameter(self):
        from ontle.extraction import run_extraction
        world = ROOT / "examples" / "business" / "manufacturing-quality-world"
        out = run_extraction(world, "extraction/claim-context.yaml", {"claimId": "C-102"})
        want = yaml.safe_load((world / "examples" / "kg-observations.yaml").read_text(encoding="utf-8"))
        self.assertEqual(out, want)
        other = run_extraction(world, "extraction/claim-context.yaml", {"claimId": "C-207"})
        self.assertEqual([o["values"] for o in other["spec"]["observations"] if o["type"] == "KG.equipment_part"],
                         [{"part": "https://w3id.org/openworld-examples/plant#die-8"}])


if __name__ == "__main__":
    unittest.main()
