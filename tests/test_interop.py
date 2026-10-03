"""Mappings to neighbouring runtime standards (docs/interop/): MCP description, NGSI-LD entities, and the term index."""
import tempfile
import unittest
from pathlib import Path

import yaml

from ontle.core import deterministic_pack
from ontle.distribution import build_index
from ontle.ews import compile_ews
from ontle.interop import ews_ngsi_ld, mcp_description
from ontle.scaffold import init_project

ROOT = Path(__file__).resolve().parents[1]


class McpTests(unittest.TestCase):
    def test_views_compilers_and_actions(self):
        d = mcp_description(ROOT / "examples" / "business" / "manufacturing-quality-world")
        self.assertEqual(d["server"]["name"], "openworld-examples/manufacturing-quality-world@0.1.0")
        names = {r["name"] for r in d["resources"]}
        self.assertTrue({"world", "view:quality-incident-task", "compiler:quality-incident-compiler"} <= names)
        self.assertEqual(d["resourceTemplates"][0]["uriTemplate"],
                         "owp-ews://openworld-examples/manufacturing-quality-world/0.1.0/state/quality-incident-compiler.yaml?asOf={asOf}")
        tool = next(t for t in d["tools"] if t["name"] == "propose_capa")
        self.assertTrue(tool["_meta"]["owp/approvalRequired"])
        self.assertIn("not a committed change", tool["description"])
        self.assertEqual(tool["annotations"], {"readOnlyHint": False, "openWorldHint": True})


class NgsiLdTests(unittest.TestCase):
    def test_subjects_become_entities(self):
        with tempfile.TemporaryDirectory() as td:
            world = init_project("w", "acme", "minimal", Path(td) / "w")
            manifest = yaml.safe_load((world / "owp.yaml").read_text(encoding="utf-8"))
            observations = yaml.safe_load((world / "examples" / "observations.yaml").read_text(encoding="utf-8"))
            ews = compile_ews(world, "state/default-compiler.yaml", observations, "2026-01-02T00:00:00Z")
            binding = {"spec": {"observationTypes": {"source.item_status": "ex:Item"},
                                "fields": {"item.status": {"class": "ex:Item", "path": ["ex:status"],
                                                           "values": {"base": "https://example.org/status/", "map": {"blocked": "ex:Blocked"}}}},
                                "subjects": {"source.item_status": {"base": "https://example.org/item/"}}}}
            entities = {e["id"]: e for e in ews_ngsi_ld(world, manifest, ews, observations, binding, {"ex": "https://example.org/ns#"})}
        item2 = entities["https://example.org/item/item-2"]
        self.assertEqual(item2["type"], "https://example.org/ns#Item")
        self.assertEqual(item2["https://example.org/ns#status"]["type"], "VocabProperty")
        self.assertEqual(item2["https://example.org/ns#status"]["vocab"], "https://example.org/ns#Blocked")
        item1 = entities["https://example.org/item/item-1"]["https://example.org/ns#status"]
        self.assertEqual(item1["vocab"], "https://example.org/status/active")  # base + code
        self.assertIn("observedAt", item1)
        self.assertEqual(item2["@context"][-1], "https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context-v1.8.jsonld")
        # one entity per subject: the event fields of item-2 are on the same entity as its status
        self.assertIn("item_events_24h", item2)
        self.assertFalse(any(k.startswith("urn:ngsi-ld:") for k in entities))

    def test_a_code_without_a_concept_is_refused(self):
        from ontle.core import OWPError
        with tempfile.TemporaryDirectory() as td:
            world = init_project("w", "acme", "minimal", Path(td) / "w")
            manifest = yaml.safe_load((world / "owp.yaml").read_text(encoding="utf-8"))
            observations = yaml.safe_load((world / "examples" / "observations.yaml").read_text(encoding="utf-8"))
            ews = compile_ews(world, "state/default-compiler.yaml", observations, "2026-01-02T00:00:00Z")
            binding = {"spec": {"fields": {"item.status": {"class": "ex:Item", "path": ["ex:status"], "values": {"map": {"blocked": "ex:Blocked"}}}}}}
            with self.assertRaises(OWPError):  # "active" has no concept, as in --rdf
                ews_ngsi_ld(world, manifest, ews, observations, binding, {"ex": "https://example.org/ns#"})


class TermIndexTests(unittest.TestCase):
    def test_defined_used_and_mappings(self):
        with tempfile.TemporaryDirectory() as td:
            archives = [deterministic_pack(ROOT / p, Path(td) / f"{Path(p).name}.owp.zip") for p in ("vocab/owp", "alignments/owp-align-prov")]
            index = build_index([Path(a) for a in archives], base=Path(td), terms=True)
        state_value = index["terms"]["https://w3id.org/owp/ns#StateValue"]
        self.assertEqual(state_value["definedBy"], ["openworld/owp-vocabulary@0.1.0"])
        self.assertIn({"package": "openworld/owp-align-prov@0.1.0", "path": "mappings.sssom.tsv", "format": "sssom-tsv"}, index["mappings"])
        self.assertFalse(any(k.startswith("http://www.w3.org/2001/XMLSchema#") for k in index["terms"]))
        self.assertNotIn("terms", build_index([Path(a) for a in archives[:0]]))

    def test_entrypoints_outside_the_archive_are_not_read(self):
        import zipfile
        with tempfile.TemporaryDirectory() as td:
            archive = deterministic_pack(ROOT / "vocab/owp", Path(td) / "v.owp.zip")
            secret = Path(td) / "secret.yaml"
            secret.write_text("apiVersion: openworld/v1alpha1\nkind: SemanticProfile\nspec: {types: [{name: x, subClassOf: owp:Leak}]}\n", encoding="utf-8")
            with zipfile.ZipFile(archive) as zf:
                files = {n: zf.read(n) for n in zf.namelist()}
            files["owp.yaml"] = files["owp.yaml"].replace(b"entrypoints:", b"entrypoints:\n    - {path: " + str(secret).encode() + b", format: owp-yaml, role: schema}", 1)  # an absolute path
            with zipfile.ZipFile(archive, "w") as zf:
                for n, b in files.items():
                    zf.writestr(n, b)
            from ontle.distribution import _term_index
            index = _term_index([Path(archive)])
        self.assertNotIn("https://w3id.org/owp/ns#Leak", index["terms"])


if __name__ == "__main__":
    unittest.main()
