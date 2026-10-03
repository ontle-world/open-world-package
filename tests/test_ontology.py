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

    def test_export_keeps_subclasses(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "onto"
            shutil.copytree(EXAMPLE, root)
            core = root / "semantics" / "core.yaml"
            core.write_text(core.read_text(encoding="utf-8").replace("  relations:", "  - {id: q:CustomerClaim, subClassOf: [q:Claim]}\n  relations:"), encoding="utf-8")
            manifest = yaml.safe_load((root / "owp.yaml").read_text(encoding="utf-8"))
            turtle = export_rdf(root, manifest, "turtle")
        self.assertIn("<https://w3id.org/openworld-examples/quality#CustomerClaim> rdfs:subClassOf <https://w3id.org/openworld-examples/quality#Claim> .", turtle)

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


class KnowledgeGraphCheckTests(unittest.TestCase):
    @unittest.skipUnless(HAS_RDFLIB, "rdflib not installed (pip install 'ontle-open-world[rdf]')")
    def test_example_graph_follows_its_ontology(self):
        from ontle.kgcheck import check_knowledge_graphs
        report = check_knowledge_graphs(ROOT / "examples" / "business" / "manufacturing-quality-world", [str(ROOT / "examples")])
        self.assertEqual(report.checked, ["knowledge/plant-kg.yaml"])
        self.assertEqual(report.findings, [])

    @unittest.skipUnless(HAS_RDFLIB, "rdflib not installed (pip install 'ontle-open-world[rdf]')")
    def test_graph_outside_its_ontology(self):
        from ontle.kgcheck import check_knowledge_graphs
        with tempfile.TemporaryDirectory() as td:
            world = Path(td) / "world"
            shutil.copytree(ROOT / "examples" / "business" / "manufacturing-quality-world", world)
            with (world / "kg" / "plant.ttl").open("a", encoding="utf-8") as f:
                f.write("ex:x a q:Widget .\n"                       # class the ontology does not define
                        "ex:lot-L-1 q:color \"red\" .\n"            # property the ontology does not define
                        "ex:lot-L-1 q:affectsLot ex:lot-L-2 .\n"    # domain is q:Claim
                        "ex:claim-102 q:affectsLot \"L-1\" .\n"     # range is q:Lot, not a literal
                        "ex:claim-207 q:affectsLot ex:orphan .\n"   # object without a type
                        "ex:claim-207 rdfs:seeAlso ex:x .\n")       # other vocabularies are not checked
            text = (world / "kg" / "plant.ttl").read_text(encoding="utf-8")
            (world / "kg" / "plant.ttl").write_text("@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n" + text, encoding="utf-8")
            report = check_knowledge_graphs(world, [str(ROOT / "examples")])
        self.assertEqual(sorted(f.code for f in report.findings),
                         ["kg.domain", "kg.range", "kg.unknown-class", "kg.unknown-property", "kg.untyped"])
        self.assertFalse(report.ok)


if __name__ == "__main__":
    unittest.main()
