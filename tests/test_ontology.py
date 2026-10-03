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

    @unittest.skipUnless(HAS_RDFLIB, "rdflib not installed (pip install 'ontle-open-world[rdf]')")
    def test_shared_property_and_standard_prefixes(self):
        from ontle.kgcheck import check_knowledge_graphs
        with tempfile.TemporaryDirectory() as td:
            onto, world = Path(td) / "onto", Path(td) / "world"
            shutil.copytree(EXAMPLE, onto)
            shutil.copytree(ROOT / "examples" / "business" / "manufacturing-quality-world", world)
            core = onto / "semantics" / "core.yaml"
            # q:claimStatus is now also a property of q:Lot (two domains), and the ontology declares an rdfs prefix
            core.write_text(core.read_text(encoding="utf-8").replace("    - {id: q:derivedFrom, range: q:Lot}\n", "    - {id: q:derivedFrom, range: q:Lot}\n    - {id: q:claimStatus}\n", 1), encoding="utf-8")
            manifest = onto / "owp.yaml"
            manifest.write_text(manifest.read_text(encoding="utf-8").replace("      q: https://w3id.org/openworld-examples/quality#",
                                "      q: https://w3id.org/openworld-examples/quality#\n      rdfs: http://www.w3.org/2000/01/rdf-schema#"), encoding="utf-8")
            kg = world / "kg" / "plant.ttl"
            kg.write_text("@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n" + kg.read_text(encoding="utf-8")
                          + 'ex:lot-L-1 q:claimStatus "open" ; rdfs:label "lot 1" .\nex:claim-102 q:claimStatus "open" .\n', encoding="utf-8")
            report = check_knowledge_graphs(world, [str(onto)])
        self.assertEqual(report.findings, [])




def _standard_vocabulary(target: Path, iri: str, prefix: str, rdf: str) -> None:
    """An OntologyPackage that publishes a vocabulary given as RDF/XML (like SKOS or BFO)."""
    (target / "ontology").mkdir(parents=True)
    (target / "ONTOLOGY.md").write_text("# Vocabulary\n", encoding="utf-8")
    (target / "ontology" / "vocab.rdf").write_text(rdf, encoding="utf-8")
    (target / "owp.yaml").write_text(
        "apiVersion: openworld/v1alpha1\nkind: OntologyPackage\n"
        f"metadata: {{namespace: standards, name: {target.name}, version: 1.0.0}}\n"
        f"spec:\n  ontology:\n    description: ONTOLOGY.md\n    iri: \"{iri}\"\n    prefixes: {{{prefix}: \"{iri}\"}}\n"
        "    entrypoints:\n    - {path: ontology/vocab.rdf, format: rdf-xml, role: schema}\n", encoding="utf-8")


class StandardVocabularyTests(unittest.TestCase):
    """Published vocabularies wrapped as OntologyPackages (SKOS, BFO, PROV are tested this way by hand)."""

    VOCAB = ('<?xml version="1.0"?>\n<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" '
             'xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#" xmlns:owl="http://www.w3.org/2002/07/owl#">\n'
             '  <owl:Class rdf:about="http://www.w3.org/2004/02/skos/core#Concept"/>\n'
             '  <owl:ObjectProperty rdf:about="http://www.w3.org/2004/02/skos/core#broader">\n'
             '    <rdfs:domain rdf:resource="http://www.w3.org/2004/02/skos/core#Concept"/></owl:ObjectProperty>\n'
             '  <owl:AnnotationProperty rdf:about="http://www.w3.org/2000/01/rdf-schema#label"/>\n'
             '  <owl:AnnotationProperty rdf:about="http://www.w3.org/2004/02/skos/core#prefLabel"/>\n</rdf:RDF>\n')

    @unittest.skipUnless(HAS_RDFLIB, "rdflib not installed (pip install 'ontle-open-world[rdf]')")
    def test_term_index_keeps_only_the_vocabularys_own_terms(self):
        from ontle.ontology import build_term_index
        with tempfile.TemporaryDirectory() as td:
            pkg = Path(td) / "skos"
            _standard_vocabulary(pkg, "http://www.w3.org/2004/02/skos/core#", "skos", self.VOCAB)
            terms = build_term_index(pkg, yaml.safe_load((pkg / "owp.yaml").read_text(encoding="utf-8")))
        # rdfs:label is borrowed and annotation properties are not domain terms
        self.assertEqual(terms, [{"iri": "http://www.w3.org/2004/02/skos/core#Concept", "type": "class"},
                                 {"iri": "http://www.w3.org/2004/02/skos/core#broader", "type": "property"}])

    @unittest.skipUnless(HAS_RDFLIB, "rdflib not installed (pip install 'ontle-open-world[rdf]')")
    def test_single_superclass_is_exported(self):
        root = ROOT / "conformance" / "resolution" / "ontology-dependency-term" / "root"
        turtle = export_rdf(root, yaml.safe_load((root / "owp.yaml").read_text(encoding="utf-8")), "turtle")
        self.assertIn("<https://example.org/domain#Machine> rdfs:subClassOf <https://example.org/upper#MaterialEntity>", turtle)  # a string
        self.assertIn("<https://example.org/domain#Repair> rdfs:subClassOf <https://example.org/upper#Process>", turtle)  # a list

    @unittest.skipUnless(HAS_RDFLIB, "rdflib not installed (pip install 'ontle-open-world[rdf]')")
    def test_kg_check_covers_a_published_vocabulary_and_reports_unreadable_graphs(self):
        from ontle.kgcheck import check_knowledge_graphs
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            _standard_vocabulary(d / "skos", "http://www.w3.org/2004/02/skos/core#", "skos", self.VOCAB)
            write_term_index(d / "skos", d / "skos" / "owp.yaml")
            world = init_project("w", "test", "minimal", d / "w")
            (world / "kg").mkdir()
            (world / "knowledge.yaml").write_text(
                "apiVersion: openworld/v1alpha1\nkind: KnowledgeAsset\nmetadata: {name: kg}\n"
                "spec: {roles: [graph], representation: graph, format: turtle, conformsTo: {ontology: standards/skos@1.0.0}, content: {path: kg/g.ttl}}\n",
                encoding="utf-8")
            manifest = world / "owp.yaml"
            manifest.write_text(manifest.read_text(encoding="utf-8").replace("spec:\n", "spec:\n  dependencies: [standards/skos@1.0.0]\n", 1), encoding="utf-8")
            kg = world / "kg" / "g.ttl"
            kg.write_text("@prefix skos: <http://www.w3.org/2004/02/skos/core#> .\n@prefix ex: <https://example.org/> .\n"
                          "ex:a a skos:Concept ; skos:broaderr ex:b .\nex:c skos:broader ex:a .\n", encoding="utf-8")
            report = check_knowledge_graphs(world, [str(d)])
            self.assertEqual(sorted(f.code for f in report.findings), ["kg.unknown-property", "kg.untyped"])
            kg.write_text("ex:a a skos:Concept .\n", encoding="utf-8")  # prefixes not declared
            report = check_knowledge_graphs(world, [str(d)])
            self.assertEqual([f.code for f in report.findings], ["kg.parse"])
            self.assertFalse(report.ok)


class OwlExportTests(unittest.TestCase):
    """spec 3.1, RDF meaning of owp-yaml: the export is OWL 2 DL."""

    @unittest.skipUnless(HAS_RDFLIB, "rdflib not installed (pip install 'ontle-open-world[rdf]')")
    def test_export_types_properties_by_their_range_and_unions_shared_domains(self):
        import rdflib
        import rdflib.collection
        from rdflib.namespace import OWL, RDF, RDFS
        with tempfile.TemporaryDirectory() as td:
            p = init_project("o", "test", "ontology", Path(td) / "o")
            (p / "semantics" / "core.yaml").write_text(
                "apiVersion: openworld/v1alpha1\nkind: SemanticProfile\nmetadata: {name: core}\nspec:\n  types:\n"
                "  - {id: ex:Machine, subClassOf: up:Entity, properties: [{id: ex:status, range: ex:Status}, {id: ex:serial, range: xsd:string}]}\n"
                "  - {id: ex:Line, properties: [{id: ex:serial, range: xsd:string}]}\n"
                "  - {id: ex:Status, enum: [running, down]}\n", encoding="utf-8")
            manifest = p / "owp.yaml"
            data = yaml.safe_load(manifest.read_text(encoding="utf-8"))
            data["spec"]["ontology"]["prefixes"].update({"up": "https://example.org/upper#", "xsd": "http://www.w3.org/2001/XMLSchema#"})
            ex = next(v for k, v in data["spec"]["ontology"]["prefixes"].items() if k == "ex") if "ex" in data["spec"]["ontology"]["prefixes"] else None
            if ex is None:
                data["spec"]["ontology"]["prefixes"]["ex"] = "https://example.org/ex#"
            manifest.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
            g = rdflib.Graph()
            g.parse(data=export_rdf(p, data, "turtle"), format="turtle")
        E = rdflib.Namespace(data["spec"]["ontology"]["prefixes"]["ex"])
        self.assertIn((E.status, RDF.type, OWL.DatatypeProperty), g)   # enum range: literal values
        self.assertIn((E.serial, RDF.type, OWL.DatatypeProperty), g)   # xsd range
        self.assertIn((E.Status, RDF.type, RDFS.Datatype), g)
        self.assertIn((rdflib.URIRef("https://example.org/upper#Entity"), RDF.type, OWL.Class), g)  # declared
        (domain,) = g.objects(E.serial, RDFS.domain)
        union = rdflib.collection.Collection(g, g.value(domain, OWL.unionOf))
        self.assertEqual(sorted(union), sorted([E.Line, E.Machine]))  # a union, not two domains (intersection)

if __name__ == "__main__":
    unittest.main()
