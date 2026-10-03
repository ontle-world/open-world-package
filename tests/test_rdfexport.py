"""RDF output in the OWP vocabulary: package and asset IRIs, and an EWS as Turtle 1.2 (vocab/owp)."""
import importlib.util
import tempfile
import unittest
from pathlib import Path

import yaml

from ontle.ews import compile_ews
from ontle.rdfexport import asset_iri, ews_turtle, package_iri, spec_iri
from ontle.scaffold import init_project

HAS_OXIGRAPH = importlib.util.find_spec("pyoxigraph") is not None


class IriTests(unittest.TestCase):
    def test_package_asset_and_spec_iris(self):
        self.assertEqual(package_iri("acme/plant@1.2.0-rc.1+b5"), "https://w3id.org/owp/pkg/acme/plant/1.2.0-rc.1%2Bb5")
        self.assertEqual(asset_iri("acme/plant@0.1.0#views/task view.yaml"), "https://w3id.org/owp/pkg/acme/plant/0.1.0#views/task%20view.yaml")
        self.assertEqual(spec_iri("openworld/v1alpha1"), "https://w3id.org/owp/spec/v1alpha1")


class EwsTurtleTests(unittest.TestCase):
    def compiled(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        world = init_project("w", "acme", "minimal", Path(td.name) / "w")
        manifest = yaml.safe_load((world / "owp.yaml").read_text(encoding="utf-8"))
        observations = yaml.safe_load((world / "examples" / "observations.yaml").read_text(encoding="utf-8"))
        ews = compile_ews(world, "state/default-compiler.yaml", observations, "2026-01-02T00:00:00Z")
        return world, manifest, ews, observations

    def test_values_without_a_binding_use_rdf_value(self):
        world, manifest, ews, observations = self.compiled()
        ttl = ews_turtle(world, manifest, ews, observations, None, {})
        self.assertTrue(ttl.startswith('VERSION "1.2"'))
        self.assertIn("dct:conformsTo <https://w3id.org/owp/spec/v1alpha1>", ttl)
        self.assertIn('owp:field "item.status" ;\n  owp:subjectKey "item-2" ;\n  owp:resolution owp:resolved ;\n  rdf:value "blocked"', ttl)
        self.assertIn("a owp:Aggregate ;\n  owp:function \"count\" ;\n  owp:window \"PT24H\"", ttl)
        self.assertIn('owp:criterion [ a owp:Criterion ; dct:identifier "attention-threshold" ; dct:hasVersion "0.1.0" ]', ttl)
        self.assertNotIn("rdf:reifies", ttl)

    def test_bound_fields_become_unasserted_triple_terms(self):
        world, manifest, ews, observations = self.compiled()
        binding = {"spec": {"fields": {"item.status": {"class": "ex:Item", "path": ["ex:status"]}},
                            "subjects": {"source.item_status": {"base": "https://example.org/item/"}}}}
        ttl = ews_turtle(world, manifest, ews, observations, binding, {"ex": "https://example.org/ns#"})
        self.assertIn('rdf:reifies <<( <https://example.org/item/item-2> <https://example.org/ns#status> "blocked" )>>', ttl)
        self.assertIn('prov:wasDerivedFrom', ttl)
        if HAS_OXIGRAPH:
            import pyoxigraph
            store = pyoxigraph.Store()
            store.load(ttl.encode("utf-8"), format=pyoxigraph.RdfFormat.TURTLE)
            rows = list(store.query("PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> "
                                    "SELECT (OBJECT(?t) AS ?v) WHERE { ?r rdf:reifies ?t }"))
            self.assertEqual(sorted(str(r[0]) for r in rows), ['"active"', '"blocked"'])


    def test_coded_values_become_concept_iris(self):
        from ontle.core import OWPError
        world, manifest, ews, observations = self.compiled()
        binding = {"spec": {"fields": {"item.status": {"class": "ex:Item", "path": ["ex:status"],
                                                       "values": {"base": "https://example.org/status/", "map": {"blocked": "ex:Blocked"}}}},
                            "subjects": {"source.item_status": {"base": "https://example.org/item/"}}}}
        ttl = ews_turtle(world, manifest, ews, observations, binding, {"ex": "https://example.org/ns#"})
        self.assertIn("<https://example.org/item/item-2> <https://example.org/ns#status> <https://example.org/ns#Blocked>", ttl)  # map
        self.assertIn("<https://example.org/item/item-1> <https://example.org/ns#status> <https://example.org/status/active>", ttl)  # base + code
        binding["spec"]["fields"]["item.status"]["values"] = {"map": {"blocked": "ex:Blocked"}}  # "active" has no IRI now
        with self.assertRaises(OWPError):
            ews_turtle(world, manifest, ews, observations, binding, {"ex": "https://example.org/ns#"})

if __name__ == "__main__":
    unittest.main()
