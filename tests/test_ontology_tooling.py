"""Ontology tooling (ROADMAP 7): SHACL in `kg check`, unread entrypoints, `ontle diff`, and the public Python API."""
import importlib.util
import json
import shutil
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest import mock

import ontle
from ontle import cli
from ontle.core import deterministic_pack
from ontle.yamlio import load_yaml

ROOT = Path(__file__).resolve().parent.parent
ONTOLOGY = ROOT / "examples" / "ontology" / "quality-ontology"
WORLD = ROOT / "examples" / "business" / "manufacturing-quality-world"
SUITE = ROOT / "conformance"
TS_CLI = ROOT / "implementations" / "typescript" / "dist" / "cli.js"
HAS_RDFLIB = importlib.util.find_spec("rdflib") is not None
HAS_SHACL = HAS_RDFLIB and importlib.util.find_spec("pyshacl") is not None
NEEDS_RDF = unittest.skipUnless(HAS_RDFLIB, "rdflib not installed (pip install 'ontle[rdf]')")


def edit(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    assert old in text, old
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def run(*argv: str) -> tuple[int, str, str]:
    out, err = StringIO(), StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = cli.main(list(argv))
    return code, out.getvalue(), err.getvalue()


# Experimental warnings of the lifecycle conformance cases (Appendix C.1), word for word.
LIFECYCLE_VALIDATION = {
    'ontology-term-status': [],
    'ontology-term-status-unknown': ["experimental.value: semantics/core.yaml: spec.types[0].status 'retired' must be one of candidate, stable, deprecated"],
    'ontology-replaced-by-not-deprecated': ['experimental.field: semantics/core.yaml: spec.types[1].replacedBy is only for a term with status deprecated'],
    'ontology-replaced-by-undefined': ["experimental.reference: semantics/core.yaml: spec.types[1].replacedBy 'q:Defekt' (https://example.org/q#Defekt) is not a term this ontology defines"],
    'ontology-removed-term': [],
    'ontology-removed-still-defined': ["experimental.field: semantics/core.yaml: spec.removed[2] 'q:batchCode' is listed as removed, but the ontology still defines it"],
    'extraction-query-terms-malformed': ["experimental.field: extraction/parts.yaml: spec.query.terms[0] 'has part' must be a CURIE or an absolute IRI"],
    'extraction-query-terms-empty': ['experimental.field: extraction/parts.yaml: spec.query.terms must be a non-empty list of CURIEs or absolute IRIs'],
    'ontology-removed-not-a-list': ['experimental.field: semantics/core.yaml: spec.removed must be a list'],
    'ontology-removed-without-id': ['experimental.field: semantics/core.yaml: spec.removed[2] needs id, a CURIE with a declared prefix or an absolute IRI'],
    'ontology-removed-in-not-string': ['experimental.field: semantics/core.yaml: spec.removed[0].removedIn must be a version string'],
    'ontology-removed-replaced-by-malformed': ['experimental.field: semantics/core.yaml: spec.removed[1].replacedBy must be an identifier or a non-empty list of identifiers'],
    'ontology-removed-replaced-by-undefined': ["experimental.reference: semantics/core.yaml: spec.removed[1].replacedBy 'q:strikes' (https://example.org/q#strikes) is not a term this ontology defines"],
}
LIFECYCLE_RESOLUTION = {
    'ontology-deprecated-term-used': ["experimental.reference: conformance/domain@0.1.0: semantics/core.yaml: spec.types[0].subClassOf 'up:Artifact' (https://example.org/upper#Artifact) is deprecated in conformance/upper@1.0.0; replaced by up:MaterialEntity"],
    'ontology-replaced-by-dependency-unknown': ["experimental.reference: conformance/domain@0.1.0: semantics/core.yaml: spec.types[1].replacedBy 'up:Equipment' (https://example.org/upper#Equipment) is not a term of conformance/upper@1.0.0"],
    'binding-deprecated-term': ["experimental.reference: conformance/world@0.1.0: semantics/terms.yaml: spec.fields.lot.genealogy.path[0] 'q:derivedFrom' (https://example.org/q#derivedFrom) is deprecated in conformance/onto@0.1.0; replaced by q:madeFrom"],
    'binding-removed-term': ["experimental.reference: conformance/world@0.1.0: semantics/terms.yaml: spec.fields.lot.genealogy.path[0] 'q:derivedFrom' (https://example.org/q#derivedFrom) was removed from conformance/onto in 1.0.0; replaced by q:madeFrom"],
    'extraction-query-term-deprecated': ["experimental.reference: conformance/world@0.1.0: extraction/lots.yaml: spec.query.terms[1] 'q:partOf' (https://example.org/q#partOf) is deprecated in conformance/onto@0.1.0; replaced by q:derivedFrom"],
    'extraction-query-term-unknown': ["experimental.reference: conformance/world@0.1.0: extraction/lots.yaml: spec.query.terms[2] 'q:nosuchTerm' (https://example.org/q#nosuchTerm) is not a term of conformance/onto@0.1.0"],
    'extraction-query-term-prefix-unknown': ["experimental.reference: conformance/world@0.1.0: extraction/lots.yaml: spec.query.terms[2] 'x:partOf' uses a prefix that no dependency OntologyPackage declares"],
    'extraction-query-term-removed': ["experimental.reference: conformance/world@0.1.0: extraction/lots.yaml: spec.query.terms[1] 'q:partOf' (https://example.org/q#partOf) was removed from conformance/onto in 0.1.0; replaced by q:derivedFrom"],
    'binding-removed-term-index': ["experimental.reference: conformance/world@0.1.0: semantics/terms.yaml: spec.fields.lot.genealogy.path[0] 'q:derivedFrom' (https://example.org/q#derivedFrom) was removed from conformance/onto in 1.0.0; replaced by q:madeFrom"],
}


class ShapeTests(unittest.TestCase):
    @unittest.skipUnless(HAS_SHACL, "pyshacl not installed (pip install 'ontle[rdf,shacl]')")
    def test_graph_against_the_ontology_shapes(self):
        from ontle.kgcheck import check_knowledge_graphs
        with tempfile.TemporaryDirectory() as td:
            world = Path(td) / "world"
            shutil.copytree(WORLD, world)
            kg = world / "kg" / "plant.ttl"
            edit(kg, 'q:claimStatus "open"', 'q:claimStatus "pending"')   # not in sh:in
            edit(kg, ' q:claimStatus "closed" ;', "")                      # sh:minCount 1
            report = check_knowledge_graphs(world, [str(ROOT / "examples")])
        self.assertFalse(report.ok)
        self.assertEqual([(f.code, f.message) for f in report.findings], [
            ("kg.shape", "shape q:ClaimShape on q:claimStatus: sh:in not met, e.g. ex:claim-102"),
            ("kg.shape", "shape q:ClaimShape on q:claimStatus: sh:minCount 1 not met, e.g. ex:claim-207"),
        ])

    @unittest.skipUnless(HAS_SHACL, "pyshacl not installed (pip install 'ontle[rdf,shacl]')")
    def test_warnings_are_advice_and_subclasses_are_targeted(self):
        from ontle.kgcheck import check_knowledge_graphs
        with tempfile.TemporaryDirectory() as td:
            onto, world = Path(td) / "onto", Path(td) / "world"
            shutil.copytree(ONTOLOGY, onto)
            shutil.copytree(WORLD, world)
            edit(onto / "semantics" / "shapes.ttl", "sh:targetClass q:Claim ;", "sh:targetClass q:Claim ; sh:severity sh:Warning ;")
            edit(onto / "semantics" / "shapes.ttl", "sh:minCount 1 ;", "sh:minCount 1 ; sh:severity sh:Warning ;")
            # q:Complaint is a subclass of q:Claim, so the claim shape applies to its instances too
            (onto / "semantics" / "extra.ttl").write_text(
                "@prefix q: <https://w3id.org/openworld-examples/quality#> .\n"
                "@prefix owl: <http://www.w3.org/2002/07/owl#> .\n@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n"
                "q:Complaint a owl:Class ; rdfs:subClassOf q:Claim .\n", encoding="utf-8")
            edit(onto / "owp.yaml", "    - {path: semantics/shapes.ttl", "    - {path: semantics/extra.ttl, format: turtle, role: schema}\n    - {path: semantics/shapes.ttl")
            with (world / "kg" / "plant.ttl").open("a", encoding="utf-8") as f:
                f.write("ex:complaint-1 a q:Complaint .\n")
            report = check_knowledge_graphs(world, [str(onto)])
        self.assertTrue(report.ok)
        self.assertEqual([(f.code, f.message) for f in report.findings],
                         [("kg.shape-warning", "shape q:ClaimShape on q:claimStatus: sh:minCount 1 not met, e.g. ex:complaint-1")])

    @NEEDS_RDF
    def test_shapes_not_run_without_pyshacl(self):
        from ontle.kgcheck import check_knowledge_graphs
        real = importlib.util.find_spec
        with mock.patch("importlib.util.find_spec", side_effect=lambda name, *a: None if name == "pyshacl" else real(name, *a)):
            report = check_knowledge_graphs(WORLD, [str(ROOT / "examples")])
        self.assertTrue(report.ok)
        self.assertEqual(report.notes, ["knowledge/plant-kg.yaml: the ontology has SHACL shapes, which were not run: pip install 'ontle[shacl]'"])


class UnreadEntrypointTests(unittest.TestCase):
    @NEEDS_RDF
    def test_kg_check_names_the_entrypoints_it_did_not_read(self):
        with tempfile.TemporaryDirectory() as td:
            onto, world = Path(td) / "onto", Path(td) / "world"
            shutil.copytree(ONTOLOGY, onto)
            shutil.copytree(WORLD, world)
            (onto / "semantics" / "extra.owx").write_text("<Ontology/>\n", encoding="utf-8")
            edit(onto / "owp.yaml", "    - {path: semantics/shapes.ttl", "    - {path: semantics/extra.owx, format: owl-xml, role: schema}\n    - {path: semantics/shapes.ttl")
            code, out, _ = run("kg", "check", str(world), "--source", str(onto))
            self.assertEqual(code, 0)
            self.assertIn("NOTE: openworld-examples/quality-ontology@0.1.0: schema entrypoint semantics/extra.owx (owl-xml) was not read", out)
            code, out, _ = run("kg", "check", str(world), "--source", str(onto), "--bindings")
            self.assertIn("NOTE: openworld-examples/quality-ontology@0.1.0: schema entrypoint semantics/extra.owx (owl-xml) was not read", out)
            code, out, _ = run("kg", "check", str(WORLD), "--source", str(ROOT / "examples"))
            self.assertNotIn("NOTE:", out)


@NEEDS_RDF
class DiffTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.new = Path(self.td.name) / "new"
        shutil.copytree(ONTOLOGY, self.new)
        self.core = self.new / "semantics" / "core.yaml"

    def tearDown(self):
        self.td.cleanup()

    def version(self, version: str) -> None:
        edit(self.new / "owp.yaml", "version: 0.1.0", f"version: {version}")

    def diff(self, old: Path = ONTOLOGY):
        return ontle.diff_ontologies(old, self.new)

    def test_no_change(self):
        result = self.diff()
        self.assertEqual((result.changes, result.required, result.enough), ([], None, True))

    def test_levels(self):
        edit(self.core, "    - {id: q:derivedFrom, range: q:Lot}\n", "")                                       # removed
        edit(self.core, "enum: [open, investigating, closed]", "enum: [open, investigating, closed, reopened]")  # value added
        edit(self.core, "label: {en: Production lot, ko: 생산 로트}", "label: {en: Lot, ko: 생산 로트}")         # label
        edit(self.core, "  - id: q:Decision\n", "  - id: q:Decision\n  - id: q:Supplier\n")                     # added
        self.version("0.1.1")
        result = self.diff()
        self.assertEqual([(c.level, c.change) for c in result.changes], [
            ("major", "removed property q:derivedFrom"),
            ("minor", "added class q:Supplier"),
            ("minor", "q:ClaimStatus: values added: reopened"),
            ("patch", "q:Lot: labels or definitions changed"),
        ])
        self.assertEqual((result.required, result.increment, result.enough), ("major", "patch", False))

    def test_zero_major_needs_minor_for_breaking(self):
        edit(self.core, "enum: [open, investigating, closed]", "enum: [open, closed]")
        self.version("0.2.0")
        result = self.diff()
        self.assertEqual([(c.level, c.change) for c in result.changes], [("major", "q:ClaimStatus: values removed: investigating")])
        self.assertTrue(result.enough)  # 0.x: a minor increment carries a breaking change

    def test_after_one_point_zero(self):
        old = Path(self.td.name) / "old"
        shutil.copytree(ONTOLOGY, old)
        edit(old / "owp.yaml", "version: 0.1.0", "version: 1.0.0")
        edit(self.core, "enum: [open, investigating, closed]", "enum: [open, closed]")
        self.version("1.1.0")
        self.assertFalse(self.diff(old).enough)
        edit(self.new / "owp.yaml", "version: 1.1.0", "version: 2.0.0")
        self.assertTrue(self.diff(old).enough)

    def test_domain_and_range(self):
        # q:claimStatus moves from q:Claim to (q:Claim or q:Lot): widened; q:derivedFrom's range changes: narrowed
        edit(self.core, "    - {id: q:derivedFrom, range: q:Lot}\n", "    - {id: q:derivedFrom, range: q:Equipment}\n    - {id: q:claimStatus}\n")
        changes = {(c.level, c.change) for c in self.diff().changes}
        self.assertIn(("minor", "q:claimStatus: domain q:Claim -> (q:Claim, q:Lot)"), changes)
        self.assertIn(("major", "q:derivedFrom: range q:Lot -> q:Equipment"), changes)

    def test_widened(self):
        from ontle.ontodiff import _widened
        f = lambda *groups: frozenset(frozenset(g) for g in groups)
        self.assertTrue(_widened(f({"A"}), f({"A", "B"})))      # union grows
        self.assertTrue(_widened(f({"A"}, {"B"}), f({"A"})))    # a statement dropped
        self.assertTrue(_widened(f({"A"}), f()))                # no domain left
        self.assertFalse(_widened(f(), f({"A"})))               # a domain where there was none
        self.assertFalse(_widened(f({"A", "B"}), f({"A"})))     # union shrinks
        self.assertFalse(_widened(f({"A"}), f({"B"})))

    def test_archives_cli_and_json(self):
        self.version("0.2.0")
        edit(self.core, "    - {id: q:derivedFrom, range: q:Lot}\n", "")
        dist = Path(self.td.name)
        old_zip, new_zip = deterministic_pack(ONTOLOGY, dist / "old.owp.zip"), deterministic_pack(self.new, dist / "new.owp.zip")
        code, out, err = run("diff", str(old_zip), str(new_zip))
        self.assertEqual(code, 0, out + err)
        self.assertIn("major: removed property q:derivedFrom", out)
        self.assertIn("changes call for: major (a minor increment while the major version is 0)", out)
        self.assertIn("OK: the minor increment is enough", out)
        edit(self.new / "owp.yaml", "version: 0.2.0", "version: 0.1.1")
        code, out, _ = run("diff", str(ONTOLOGY), str(self.new), "--json")
        self.assertEqual(code, 1)
        self.assertEqual({k: v for k, v in json.loads(out).items() if k != "changes"},
                         {"old": "openworld-examples/quality-ontology@0.1.0", "new": "openworld-examples/quality-ontology@0.1.1",
                          "required": "major", "increment": "patch", "enough": False,
                          "notes": ["removed without a `removed` entry (Appendix C.1), so users of q:derivedFrom are not told what replaces them"]})

    def test_shapes_changed_is_noted(self):
        edit(self.new / "semantics" / "shapes.ttl", "sh:maxCount 1 ;", "")
        self.assertEqual(self.diff().notes, ["SHACL shapes changed and are not graded: a new or stricter constraint can reject data the old version accepted (major)"])

    def test_refuses_different_packages(self):
        edit(self.new / "owp.yaml", "name: quality-ontology", "name: other-ontology")
        with self.assertRaises(ontle.OWPError):
            self.diff()
        with self.assertRaises(ontle.OWPError):
            ontle.diff_ontologies(ONTOLOGY, WORLD)


class LifecycleTests(unittest.TestCase):
    """Appendix C.1 (experimental) in the tools: candidate, deprecated, and removed terms (tombstones) in export,
    term index, kg check (graphs and extraction queries), and diff."""

    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.onto = Path(self.td.name) / "onto"
        shutil.copytree(ONTOLOGY, self.onto)
        self.core = self.onto / "semantics" / "core.yaml"

    def tearDown(self):
        self.td.cleanup()

    def mark(self) -> None:
        edit(self.core, "  - id: q:Lot\n", "  - id: q:Lot\n    status: candidate\n")
        edit(self.core, "  - {id: q:hasPart, domain: q:Equipment, range: q:Equipment}\n",
             "  - {id: q:hasComponent, domain: q:Equipment, range: q:Equipment}\n"
             "  - {id: q:hasPart, domain: q:Equipment, range: q:Equipment, status: deprecated, replacedBy: q:hasComponent}\n")

    @NEEDS_RDF
    def test_kg_check_reports_candidate_and_deprecated_terms_as_advice(self):
        from ontle.kgcheck import check_knowledge_graphs
        self.mark()
        world = Path(self.td.name) / "world"
        shutil.copytree(WORLD, world)
        report = check_knowledge_graphs(world, [str(self.onto)])
        self.assertTrue(report.ok)
        self.assertEqual([(f.code, f.asset, f.message, f.count) for f in report.findings], [
            ("kg.candidate", "knowledge/plant-kg.yaml", "class q:Lot is a candidate term, not yet stable", 3),
            ("kg.deprecated", "knowledge/plant-kg.yaml", "property q:hasPart is deprecated; replaced by q:hasComponent", 3),
            ("kg.deprecated", "extraction/claim-context.yaml", "query term q:hasPart is deprecated; replaced by q:hasComponent", 1),
        ])

    @NEEDS_RDF
    def test_export_and_term_index_round_trip(self):
        from ontle.core import load_manifest
        from ontle.ontology import build_term_index, export_rdf
        self.mark()
        root, manifest = load_manifest(self.onto)
        turtle = export_rdf(root, manifest, "turtle")
        q = "https://w3id.org/openworld-examples/quality#"
        self.assertIn(f"<{q}Lot> <http://www.w3.org/2003/06/sw-vocab-status/ns#term_status> \"testing\" .", turtle)
        self.assertIn(f"<{q}hasPart> owl:deprecated true .", turtle)
        self.assertIn(f"<{q}hasPart> <http://purl.org/dc/terms/isReplacedBy> <{q}hasComponent> .", turtle)
        expected = [{"iri": f"{q}Lot", "type": "class", "status": "candidate"},
                    {"iri": f"{q}hasPart", "type": "property", "status": "deprecated", "replacedBy": f"{q}hasComponent"}]
        marked = lambda index: [t for t in index if "status" in t]
        self.assertEqual(marked(build_term_index(root, manifest)), expected)
        # the same terms read back from the RDF the export wrote
        (self.onto / "semantics" / "core.ttl").write_text(turtle, encoding="utf-8")
        edit(self.onto / "owp.yaml", "{path: semantics/core.yaml, format: owp-yaml, role: schema}", "{path: semantics/core.ttl, format: turtle, role: schema}")
        root, manifest = load_manifest(self.onto)
        self.assertEqual(marked(build_term_index(root, manifest)), expected)

    @NEEDS_RDF
    def test_diff_grades_status_changes_minor(self):
        self.mark()
        edit(self.onto / "owp.yaml", "version: 0.1.0", "version: 0.1.1")
        result = ontle.diff_ontologies(ONTOLOGY, self.onto)
        self.assertEqual([(c.level, c.change) for c in result.changes], [
            ("minor", "added property q:hasComponent"),
            ("minor", "q:Lot: now a candidate term"),
            ("minor", "q:hasPart: deprecated"),
        ])
        self.assertTrue(result.enough)  # 0.x: a patch increment carries a minor change

    def remove(self) -> Path:
        """1.0.0 removes q:hasPart and keeps its tombstone; returns a World that follows to 1.0.0 without migrating."""
        edit(self.core, "  - {id: q:hasPart, domain: q:Equipment, range: q:Equipment}\n",
             "  - {id: q:hasComponent, domain: q:Equipment, range: q:Equipment}\n")
        with self.core.open("a", encoding="utf-8") as f:
            f.write("  removed:\n  - {id: q:hasPart, replacedBy: q:hasComponent, removedIn: 1.0.0}\n")
        edit(self.onto / "owp.yaml", "version: 0.1.0", "version: 1.0.0")
        world = Path(self.td.name) / "world"
        shutil.copytree(WORLD, world)
        for rel in ("owp.yaml", "knowledge/plant-kg.yaml"):
            edit(world / rel, "quality-ontology@0.1.0", "quality-ontology@1.0.0")
        return world

    @NEEDS_RDF
    def test_diff_names_candidates_and_tombstones(self):
        edit(self.core, "  - id: q:Lot\n", "  - {id: q:Die, status: candidate}\n  - id: q:Lot\n")
        self.remove()
        result = ontle.diff_ontologies(ONTOLOGY, self.onto)
        changes = [(c.level, c.change) for c in result.changes]
        self.assertIn(("minor", "added class q:Die (candidate)"), changes)
        self.assertIn(("major", "removed property q:hasPart (replaced by q:hasComponent)"), changes)
        self.assertEqual(result.notes, [])  # every removed term has a tombstone

    def test_term_index_keeps_tombstones(self):
        from ontle.ontology import write_term_index
        self.remove()
        q = "https://w3id.org/openworld-examples/quality#"
        index = write_term_index(self.onto, self.onto / "owp.yaml")
        tombstone = {"iri": f"{q}hasPart", "replacedBy": f"{q}hasComponent", "removedIn": "1.0.0"}
        self.assertEqual(load_yaml(index.read_text(encoding="utf-8"))["spec"]["removed"], [tombstone])
        # a tombstone written by hand in the index (an RDF schema has no `removed` list) survives regeneration
        edit(index, "  removed:\n", f"  removed:\n  - {{iri: '{q}Widget'}}\n")
        write_term_index(self.onto, self.onto / "owp.yaml")
        self.assertEqual(load_yaml(index.read_text(encoding="utf-8"))["spec"]["removed"], [{"iri": f"{q}Widget"}, tombstone])  # sorted by IRI
        self.assertTrue(ontle.validate_package(self.onto).valid)
        self.assertEqual(ontle.validate_package(self.onto).warnings, [])

    @NEEDS_RDF
    def test_kg_check_follows_a_removed_term_into_queries(self):
        from ontle.kgcheck import check_knowledge_graphs
        world = self.remove()
        report = check_knowledge_graphs(world, [str(self.onto)])
        self.assertFalse(report.ok)
        hint = "removed from openworld-examples/quality-ontology in 1.0.0, replaced by q:hasComponent"
        self.assertEqual([(f.code, f.asset, f.message) for f in report.findings], [
            ("kg.unknown-property", "knowledge/plant-kg.yaml", f"property q:hasPart is not defined by the ontology; {hint}"),
            ("kg.query-unknown", "extraction/claim-context.yaml", f"the query names q:hasPart, which the ontology does not define; {hint}"),
        ])
        # the query migrated, its declared terms not: advice only
        edit(world / "extraction" / "claim-context.yaml", "?equipment q:hasPart ?part", "?equipment q:hasComponent ?part")
        report = check_knowledge_graphs(world, [str(self.onto)])
        self.assertEqual([(f.code, f.asset, f.message) for f in report.findings], [
            ("kg.unknown-property", "knowledge/plant-kg.yaml", f"property q:hasPart is not defined by the ontology; {hint}"),  # the graph is not migrated
            ("kg.query-terms", "extraction/claim-context.yaml", "the query names q:hasComponent, which spec.query.terms does not list"),
            ("kg.query-terms", "extraction/claim-context.yaml", "spec.query.terms lists q:hasPart, which the query does not name"),
        ])

    @NEEDS_RDF
    def test_kg_check_json(self):
        world = self.remove()
        code, out, _ = run("kg", "check", str(world), "--source", str(self.onto), "--json")
        self.assertEqual(code, 1)
        hint = "removed from openworld-examples/quality-ontology in 1.0.0, replaced by q:hasComponent"
        self.assertEqual(json.loads(out), {
            "ok": False,
            "checked": ["knowledge/plant-kg.yaml", "extraction/claim-context.yaml"],
            "skipped": ["knowledge/rca-playbook.yaml"],
            "graphs": {"knowledge/plant-kg.yaml": {"ontology": "openworld-examples/quality-ontology@1.0.0", "asOf": "2026-09-01T00:00:00Z"}},
            "findings": [
                {"code": "kg.unknown-property", "asset": "knowledge/plant-kg.yaml", "count": 3, "advice": False,
                 "message": f"property q:hasPart is not defined by the ontology; {hint}"},
                {"code": "kg.query-unknown", "asset": "extraction/claim-context.yaml", "count": 1, "advice": False,
                 "message": f"the query names q:hasPart, which the ontology does not define; {hint}"},
            ],
            "notes": [],
        })

    @NEEDS_RDF
    def test_kg_check_json_marks_advice(self):
        self.mark()
        world = Path(self.td.name) / "world"
        shutil.copytree(WORLD, world)
        code, out, _ = run("kg", "check", str(world), "--source", str(self.onto), "--json")
        report = json.loads(out)
        self.assertEqual((code, report["ok"]), (0, True))  # advice alone passes
        self.assertEqual([(f["code"], f["advice"]) for f in report["findings"]],
                         [("kg.candidate", True), ("kg.deprecated", True), ("kg.deprecated", True)])

    @NEEDS_RDF
    def test_kg_check_bindings_json(self):
        world = Path(self.td.name) / "world"
        shutil.copytree(WORLD, world)
        edit(world / "semantics" / "quality-terms.yaml", "{class: q:Lot, path: [q:derivedFrom]}", "{class: q:Lot, path: [q:claimStatus]}")
        code, out, _ = run("kg", "check", str(world), "--source", str(self.onto), "--bindings", "--json")
        report = json.loads(out)
        self.assertEqual(code, 0)
        self.assertEqual(sorted(report), ["notes", "warnings"])
        self.assertEqual([w.split(":", 1)[0] for w in report["warnings"]], ["binding.path-domain"])
        self.assertIn("lot.genealogy", report["warnings"][0])

    @NEEDS_RDF
    def test_kg_check_reads_terms_in_property_paths(self):
        """A removed term inside a SPARQL property path is found, as in a plain triple pattern."""
        from ontle.kgcheck import check_knowledge_graphs
        world = self.remove()
        edit(world / "extraction" / "claim-context.yaml", "?lot q:producedOn ?equipment .\n        OPTIONAL { ?equipment q:hasPart ?part }",
             "?lot q:producedOn ?equipment .\n        OPTIONAL { ?equipment q:hasComponent/^q:hasPart ?part }")
        report = check_knowledge_graphs(world, [str(self.onto)])
        self.assertIn(("kg.query-unknown", "the query names q:hasPart, which the ontology does not define; "
                       "removed from openworld-examples/quality-ontology in 1.0.0, replaced by q:hasComponent"),
                      [(f.code, f.message) for f in report.findings if f.asset == "extraction/claim-context.yaml"])

    @NEEDS_RDF
    def test_kg_check_reports_a_query_it_cannot_parse(self):
        from ontle.kgcheck import check_knowledge_graphs
        world = Path(self.td.name) / "world"
        shutil.copytree(WORLD, world)
        edit(world / "extraction" / "claim-context.yaml", "SELECT ?lot ?equipment ?part WHERE {", "SELECT ?lot ?equipment ?part WHERE {{")
        report = check_knowledge_graphs(world, [str(self.onto)])
        self.assertFalse(report.ok)
        self.assertEqual([(f.code, f.asset) for f in report.findings], [("kg.parse", "extraction/claim-context.yaml")])
        self.assertIn("spec.query.text is not valid SPARQL", report.findings[0].message)


@NEEDS_RDF
class QueryTermTests(unittest.TestCase):
    """The IRIs `kg check` reads from a SPARQL query."""

    def terms(self, body: str) -> list[str]:
        from rdflib.plugins.sparql import prepareQuery
        from ontle.kgcheck import _query_terms
        q = "http://x/q#"
        return sorted(str(t)[len(q):] for t in _query_terms(prepareQuery(f"PREFIX q: <{q}> {body}")) if str(t).startswith(q))

    def test_triple_patterns_and_ask(self):
        self.assertEqual(self.terms("SELECT ?a WHERE { ?a a q:C ; q:p ?b OPTIONAL { ?b q:o ?c } }"), ["C", "o", "p"])
        self.assertEqual(self.terms("ASK { ?a q:p ?b }"), ["p"])

    def test_property_paths(self):
        self.assertEqual(self.terms("SELECT ?a WHERE { ?a q:p1/q:p2 ?b . ?b ^q:p3 ?c . ?c q:p4* ?d . ?d (q:p5|q:p6) ?e . ?e !q:p7 ?f }"),
                         ["p1", "p2", "p3", "p4", "p5", "p6", "p7"])

    def test_filters_and_values(self):
        self.assertEqual(self.terms("SELECT ?a WHERE { ?a ?p ?t FILTER(?p = q:p) VALUES ?t { q:C } }"), ["C", "p"])


class LifecycleMessageTests(unittest.TestCase):
    """The exact warnings of the lifecycle conformance cases. The suite compares rule ids only; these pin the text
    (the replacement, written as a CURIE) and the count (one warning per problem)."""

    def test_compact(self):
        from ontle.ontology import compact
        prefixes = {"q": "https://example.org/q#", "qx": "https://example.org/q#x/", "n": 3}
        self.assertEqual(compact("https://example.org/q#Lot", prefixes), "q:Lot")
        self.assertEqual(compact("https://example.org/q#x/Die", prefixes), "qx:Die")  # the longest namespace wins
        self.assertEqual(compact("https://example.org/r#Lot", prefixes), "https://example.org/r#Lot")
        self.assertEqual(compact("https://example.org/q#x//a", {"qx": "https://example.org/q#x/"}), "https://example.org/q#x//a")  # not a CURIE

    def test_validation_cases(self):
        from ontle.core import validate_package
        for case, expected in LIFECYCLE_VALIDATION.items():
            with self.subTest(case=case):
                warnings = validate_package(SUITE / "cases" / case).warnings
                self.assertEqual([w for w in warnings if w.startswith("experimental.")], expected)

    def test_resolution_cases(self):
        from ontle.resolve import validate_resolved
        for case, expected in LIFECYCLE_RESOLUTION.items():
            with self.subTest(case=case):
                d = SUITE / "resolution" / case
                warnings = validate_resolved(d / "root", [str(d / "packages")])[0].warnings
                self.assertEqual([w for w in warnings if w.startswith("experimental.")], expected)


@unittest.skipUnless(shutil.which("node") and TS_CLI.is_file(), "needs node and the built TypeScript implementation")
class LifecycleParityTests(unittest.TestCase):
    """The TypeScript implementation gives the same lifecycle warnings, word for word (quotes aside)."""

    def ts_warnings(self, *args: str) -> list[str]:
        out = subprocess.run(["node", str(TS_CLI), "--json", *args], capture_output=True, text=True).stdout
        return [f"{w['code']}: {w['message']}" for w in json.loads(out)["warnings"] if w["code"].startswith("experimental.")]

    def test_same_warnings(self):
        same = lambda ws: [w.replace("'", '"') for w in ws]  # Python writes values with repr, TypeScript as JSON
        for case, expected in LIFECYCLE_VALIDATION.items():
            with self.subTest(case=case):
                self.assertEqual(self.ts_warnings(str(SUITE / "cases" / case)), same(expected))
        for case, expected in LIFECYCLE_RESOLUTION.items():
            with self.subTest(case=case):
                d = SUITE / "resolution" / case
                self.assertEqual(sorted(self.ts_warnings("--resolve", "--source", str(d / "packages"), str(d / "root"))), sorted(same(expected)))


class PublicApiTests(unittest.TestCase):
    def test_every_name_is_exported(self):
        for name in ontle.__all__:
            self.assertTrue(hasattr(ontle, name), name)
        self.assertEqual(len(set(ontle.__all__)), len(ontle.__all__))

    def test_api_validates_and_compiles(self):
        self.assertTrue(ontle.validate_package(ONTOLOGY).valid)
        root, manifest = ontle.load_manifest(ONTOLOGY)
        self.assertIn({"iri": "https://w3id.org/openworld-examples/quality#Claim", "type": "class"}, ontle.build_term_index(root, manifest))


if __name__ == "__main__":
    unittest.main()
