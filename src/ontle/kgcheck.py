"""`ontle kg check`: does a knowledge graph (A-box) use only what its ontology (T-box) defines? (tooling, spec Appendix C)

A local KnowledgeAsset with RDF content and `spec.conformsTo.ontology` is checked against that OntologyPackage and
the OntologyPackages it depends on. Only terms in those ontologies' namespaces are checked; other vocabularies
(rdfs, skos, schema.org, external imports) are left alone. Validation never parses RDF (spec section 3.1), so these
findings are reported by the tool and do not change a package's verdict.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .core import OWPError, load_manifest, local_assets
from .ontology import RDF_FORMATS, _load, expand, export_rdf

KG_FORMATS = {"turtle": "turtle", "jsonld": "json-ld", "ntriples": "nt", "rdf-xml": "xml", "nquads": "nquads"}


@dataclass
class KgFinding:
    code: str
    asset: str
    message: str
    count: int

    def line(self) -> str:
        return f"{self.code}: {self.asset}: {self.message} ({self.count}x)"


@dataclass
class KgReport:
    findings: list[KgFinding] = field(default_factory=list)
    checked: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:  # kg.untyped is advice; every other finding, including kg.parse, fails the check
        return not any(f.code != "kg.untyped" for f in self.findings)


def _rdflib():
    try:
        import rdflib
    except ImportError as exc:
        raise OWPError("checking a knowledge graph needs rdflib: pip install 'ontle-open-world[rdf]'") from exc
    return rdflib


def tbox_graph(root: Path, manifest: dict[str, Any]):
    """The T-box of one OntologyPackage as an RDF graph: owp-yaml schema entrypoints, RDF schema entrypoints, and the term index."""
    rdflib = _rdflib()
    from rdflib.namespace import OWL, RDF
    graph = rdflib.Graph()
    graph.parse(data=export_rdf(root, manifest, "turtle"), format="turtle")
    ontology = (manifest.get("spec") or {}).get("ontology") or {}
    for entry in ontology.get("entrypoints") or []:
        if isinstance(entry, dict) and entry.get("role") == "schema" and entry.get("format") in RDF_FORMATS:
            graph.parse(root / entry["path"], format=RDF_FORMATS[entry["format"]])
    index = ontology.get("termIndex")
    doc = _load(root / index) if isinstance(index, str) else None
    for term in ((doc or {}).get("spec") or {}).get("terms") or [] if isinstance(doc, dict) else []:
        kind = {"class": OWL.Class, "property": RDF.Property}.get(term.get("type")) if isinstance(term, dict) else None
        if kind is not None and isinstance(term.get("iri"), str):
            graph.add((rdflib.URIRef(term["iri"]), RDF.type, kind))
    return graph


def _enum_types(root: Path, manifest: dict[str, Any]) -> set[str]:
    """IRIs of owp-yaml types declared with `enum`: their values are literals, not instances."""
    ontology = (manifest.get("spec") or {}).get("ontology") or {}
    prefixes = ontology.get("prefixes") if isinstance(ontology.get("prefixes"), dict) else {}
    out: set[str] = set()
    for entry in ontology.get("entrypoints") or []:
        if isinstance(entry, dict) and entry.get("format") == "owp-yaml" and entry.get("role") == "schema":
            for t in ((_load(root / entry["path"]) or {}).get("spec") or {}).get("types") or []:
                if isinstance(t, dict) and "enum" in t and isinstance(t.get("id"), str) and expand(t["id"], prefixes):
                    out.add(expand(t["id"], prefixes))  # type: ignore[arg-type]
    return out


# Vocabularies an ontology may declare a prefix for but does not define (RDF, RDFS, OWL, XSD, SKOS, SHACL, DC, PROV, schema.org).
STANDARD_NAMESPACES = {
    "http://www.w3.org/1999/02/22-rdf-syntax-ns#", "http://www.w3.org/2000/01/rdf-schema#", "http://www.w3.org/2002/07/owl#",
    "http://www.w3.org/2001/XMLSchema#", "http://www.w3.org/2004/02/skos/core#", "http://www.w3.org/ns/shacl#",
    "http://purl.org/dc/terms/", "http://purl.org/dc/elements/1.1/", "http://www.w3.org/ns/prov#", "https://schema.org/", "http://schema.org/",
}


def _namespaces(manifest: dict[str, Any]) -> set[str]:
    """Namespaces whose terms this ontology vouches for: its own `iri`, and its other prefixes except the standard
    vocabularies it merely uses. A package that publishes a standard vocabulary (its `iri` is SKOS, PROV, ...) vouches for it."""
    ontology = (manifest.get("spec") or {}).get("ontology") or {}
    out = {v for v in (ontology.get("prefixes") or {}).values() if isinstance(v, str)} - STANDARD_NAMESPACES
    if isinstance(ontology.get("iri"), str):
        out.add(ontology["iri"])
    return out


def check_knowledge_graphs(package: str | Path, sources: list[str] | None = None) -> KgReport:
    from .resolve import resolve_package
    rdflib = _rdflib()
    from rdflib.namespace import OWL, RDF, RDFS

    root, manifest = load_manifest(package)
    kinds, docs = local_assets(root, manifest.get("spec") or {})
    report = KgReport()
    resolution = None
    for rel in sorted(r for r, k in kinds.items() if k == "KnowledgeAsset"):
        spec = (docs.get(rel) or {}).get("spec") or {}
        content = (spec.get("content") or {}).get("path")
        onto_ref = (spec.get("conformsTo") or {}).get("ontology")
        fmt = KG_FORMATS.get(spec.get("format", "turtle"))
        if spec.get("representation") != "graph" or not isinstance(content, str) or not isinstance(onto_ref, str) or fmt is None:
            report.skipped.append(rel)
            continue
        if resolution is None:
            resolution = resolve_package(root, sources)
        onto = resolution.packages.get(onto_ref)
        if onto is None:
            raise OWPError(f"{rel}: cannot resolve spec.conformsTo.ontology {onto_ref}")

        tbox, namespaces, enums, todo, seen = rdflib.Graph(), set(), set(), [onto], set()
        while todo:  # the ontology and the OntologyPackages it builds on
            pkg = todo.pop()
            if pkg.identity in seen or pkg.kind != "OntologyPackage":
                continue
            seen.add(pkg.identity)
            tbox += tbox_graph(pkg.root, pkg.manifest)
            namespaces |= _namespaces(pkg.manifest)
            enums |= {rdflib.URIRef(e) for e in _enum_types(pkg.root, pkg.manifest)}
            for dep in (pkg.manifest.get("spec") or {}).get("dependencies") or []:
                ref = dep if isinstance(dep, str) else dep.get("ref") if isinstance(dep, dict) else None
                if ref in resolution.packages:
                    todo.append(resolution.packages[ref])

        classes = set(tbox.subjects(RDF.type, OWL.Class)) | set(tbox.subjects(RDF.type, RDFS.Class))
        properties = {s for t in (OWL.ObjectProperty, OWL.DatatypeProperty, RDF.Property, OWL.AnnotationProperty)
                      for s in tbox.subjects(RDF.type, t)}
        parents: dict[Any, set[Any]] = {}
        for c, p in tbox.subject_objects(RDFS.subClassOf):
            parents.setdefault(c, set()).add(p)

        def lineage(c):
            out, todo2 = {c}, [c]
            while todo2:
                for p in parents.get(todo2.pop(), ()):
                    if p not in out:
                        out.add(p)
                        todo2.append(p)
            return out

        def ours(term) -> bool:
            return isinstance(term, rdflib.URIRef) and any(str(term).startswith(ns) for ns in namespaces)

        graph = rdflib.Dataset(default_union=True) if fmt == "nquads" else rdflib.Graph()  # named graphs count too
        try:
            graph.parse(root / content, format=fmt)
        except Exception as exc:  # rdflib raises parser-specific errors
            detail = " ".join(str(exc).split())[:200] or type(exc).__name__
            report.findings.append(KgFinding("kg.parse", rel, f"{content} is not valid {spec.get('format', 'turtle')}: {detail}", 1))
            continue
        types: dict[Any, set[Any]] = {}
        for s, o in graph.subject_objects(RDF.type):
            types.setdefault(s, set()).update(lineage(o))

        found: Counter[tuple[str, str]] = Counter()
        for o in graph.objects(None, RDF.type):
            if ours(o) and o not in classes:
                found[("kg.unknown-class", f"class {graph.namespace_manager.normalizeUri(o)} is not defined by the ontology")] += 1
        for s, p, o in graph.triples((None, None, None)):
            if p == RDF.type or not ours(p):
                continue
            name = graph.namespace_manager.normalizeUri(p)
            if p not in properties:
                found[("kg.unknown-property", f"property {name} is not defined by the ontology")] += 1
                continue
            # A property declared under several types has several domains; any one of them is enough.
            domains = sorted(tbox.objects(p, RDFS.domain))
            label = " or ".join(graph.namespace_manager.normalizeUri(d) for d in domains)
            if domains and s not in types:
                found[("kg.untyped", f"subject of {name} has no rdf:type, so domain {label} cannot be checked")] += 1
            elif domains and not any(d in types[s] for d in domains):
                found[("kg.domain", f"subject of {name} is not a {label}")] += 1
            ranges = sorted(r for r in tbox.objects(p, RDFS.range) if r in classes and r not in enums)  # datatypes and enumerations are not checked
            label = " or ".join(graph.namespace_manager.normalizeUri(r) for r in ranges)
            if not ranges:
                continue
            if isinstance(o, rdflib.Literal):
                found[("kg.range", f"object of {name} is a literal, not a {label}")] += 1
            elif o not in types:
                found[("kg.untyped", f"object of {name} has no rdf:type, so range {label} cannot be checked")] += 1
            elif not any(r in types[o] for r in ranges):
                found[("kg.range", f"object of {name} is not a {label}")] += 1
        report.checked.append(rel)
        report.findings += [KgFinding(code, rel, message, n) for (code, message), n in sorted(found.items())]
    return report
