"""Ontology tooling (ROADMAP 7): SHACL in `kg check`, unread entrypoints, `ontle diff`, and the public Python API."""
import importlib.util
import json
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest import mock

import ontle
from ontle import cli
from ontle.core import deterministic_pack

ROOT = Path(__file__).resolve().parent.parent
ONTOLOGY = ROOT / "examples" / "ontology" / "quality-ontology"
WORLD = ROOT / "examples" / "business" / "manufacturing-quality-world"
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
                          "required": "major", "increment": "patch", "enough": False, "notes": []})

    def test_shapes_changed_is_noted(self):
        edit(self.new / "semantics" / "shapes.ttl", "sh:maxCount 1 ;", "")
        self.assertEqual(self.diff().notes, ["SHACL shapes changed and are not graded: a new or stricter constraint can reject data the old version accepted (major)"])

    def test_refuses_different_packages(self):
        edit(self.new / "owp.yaml", "name: quality-ontology", "name: other-ontology")
        with self.assertRaises(ontle.OWPError):
            self.diff()
        with self.assertRaises(ontle.OWPError):
            ontle.diff_ontologies(ONTOLOGY, WORLD)


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
