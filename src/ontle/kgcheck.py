"""`ontle kg check`: does a knowledge graph (A-box) use only what its ontology (T-box) defines? (tooling, spec Appendix C)

A local KnowledgeAsset with RDF content and `spec.conformsTo.ontology` is checked against that OntologyPackage and
the OntologyPackages it depends on. Only terms in those ontologies' namespaces are checked; other vocabularies
(rdfs, skos, schema.org, external imports) are left alone. When those ontologies have `shapes` entrypoints, the graph
is also validated against them with SHACL (the shacl extra). Validation never parses RDF (spec section 3.1), so these
findings are reported by the tool and do not change a package's verdict.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .core import OWPError, load_manifest, local_assets
from .ontology import DCTERMS_NS, RDF_FORMATS, VS_NS, _load, expand, export_rdf, inside_package, removed_terms, term_statuses

KG_FORMATS = {"turtle": "turtle", "jsonld": "json-ld", "ntriples": "nt", "rdf-xml": "xml", "nquads": "nquads"}


@dataclass
class KgFinding:
    code: str
    asset: str
    message: str
    count: int

    def line(self) -> str:
        return f"{self.code}: {self.asset}: {self.message} ({self.count}x)"


ADVICE = {"kg.untyped", "kg.shape-warning", "kg.deprecated", "kg.candidate", "kg.query-terms"}  # reported, but the check still passes


@dataclass
class KgReport:
    findings: list[KgFinding] = field(default_factory=list)
    checked: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)  # what the check could not do: unread entrypoints, shapes not run
    graphs: dict[str, dict[str, Any]] = field(default_factory=dict)  # checked graph -> its ontology and snapshot

    @property
    def ok(self) -> bool:  # advice aside, every finding, including kg.parse, fails the check
        return not any(f.code not in ADVICE for f in self.findings)

    def to_dict(self) -> dict[str, Any]:
        """The report as JSON: counted findings per graph and snapshot, the input for evidence that a term is used."""
        return {"ok": self.ok, "checked": self.checked, "skipped": self.skipped, "graphs": self.graphs,
                "findings": [{"code": f.code, "asset": f.asset, "message": f.message, "count": f.count, "advice": f.code in ADVICE}
                             for f in self.findings],
                "notes": self.notes}


def _rdflib():
    try:
        import rdflib
    except ImportError as exc:
        raise OWPError("checking a knowledge graph needs rdflib: pip install 'ontle[rdf]'") from exc
    return rdflib


def _identity(manifest: dict[str, Any]) -> str:
    md = manifest.get("metadata") or {}
    return f"{md.get('namespace')}/{md.get('name')}@{md.get('version')}"


def _rdf_entrypoints(root: Path, manifest: dict[str, Any], role: str, unread: list[str] | None) -> list[tuple[Path, str]]:
    """The RDF entrypoints of one role, as (file, rdflib format). Others of that role, which the tools cannot read
    (owl-xml needs an OWL API tool, linkml its own toolchain), are added to `unread`; owp-yaml schemas are read by export_rdf."""
    out = []
    for entry in ((manifest.get("spec") or {}).get("ontology") or {}).get("entrypoints") or []:
        if not isinstance(entry, dict) or entry.get("role") != role:
            continue
        fmt = entry.get("format")
        if fmt in RDF_FORMATS:
            if not inside_package(root, entry.get("path")):  # never read outside the package (validate reports it)
                raise OWPError(f"{root.name}: {role} entrypoint {entry['path']} does not exist; run ontle validate on the package")
            out.append((root / entry["path"], RDF_FORMATS[fmt]))
        elif not (role == "schema" and fmt == "owp-yaml") and unread is not None:
            unread.append(f"{_identity(manifest)}: {role} entrypoint {entry.get('path')} ({fmt}) was not read")
    return out


def tbox_graph(root: Path, manifest: dict[str, Any], unread: list[str] | None = None):
    """The T-box of one OntologyPackage as an RDF graph: owp-yaml schema entrypoints, RDF schema entrypoints, and the
    term index. Schema entrypoints in other formats are listed in `unread`; their terms come from the term index alone."""
    rdflib = _rdflib()
    from rdflib.namespace import OWL, RDF
    graph = rdflib.Graph()
    graph.parse(data=export_rdf(root, manifest, "turtle"), format="turtle")
    ontology = (manifest.get("spec") or {}).get("ontology") or {}
    for path, fmt in _rdf_entrypoints(root, manifest, "schema", unread):
        graph.parse(path, format=fmt)
    index = ontology.get("termIndex")
    doc = _load(root / index) if inside_package(root, index) else None
    for term in ((doc or {}).get("spec") or {}).get("terms") or [] if isinstance(doc, dict) else []:
        kind = {"class": OWL.Class, "property": RDF.Property}.get(term.get("type")) if isinstance(term, dict) else None
        if kind is not None and isinstance(term.get("iri"), str):
            graph.add((rdflib.URIRef(term["iri"]), RDF.type, kind))
    for iri, (status, replaced) in term_statuses(root, manifest).items():  # Appendix C.1, as `ontle export` writes it
        if status == "deprecated":
            graph.add((rdflib.URIRef(iri), OWL.deprecated, rdflib.Literal(True)))
            for r in replaced:
                graph.add((rdflib.URIRef(iri), rdflib.URIRef(DCTERMS_NS + "isReplacedBy"), rdflib.URIRef(r)))
        else:
            graph.add((rdflib.URIRef(iri), rdflib.URIRef(VS_NS + "term_status"), rdflib.Literal("testing")))
    return graph


def shapes_graph(root: Path, manifest: dict[str, Any], unread: list[str] | None = None):
    """The SHACL shapes of one OntologyPackage: its `shapes` entrypoints in RDF formats, merged."""
    graph = _rdflib().Graph()
    for path, fmt in _rdf_entrypoints(root, manifest, "shapes", unread):
        try:
            graph.parse(path, format=fmt)
        except Exception as exc:  # rdflib raises parser-specific errors
            raise OWPError(f"{_identity(manifest)}: cannot read shapes {path.name}: {' '.join(str(exc).split())[:200]}") from exc
    return graph


def shape_findings(graph, shapes, tbox) -> Counter[tuple[str, str]]:
    """SHACL validation of a graph (spec 3.1 `shapes` role): one finding per shape, path, and message, counted over
    focus nodes. The T-box is mixed in, so a shape that targets a class also targets instances of its subclasses."""
    import rdflib
    from pyshacl import validate
    from rdflib.namespace import RDF
    sh = rdflib.Namespace("http://www.w3.org/ns/shacl#")
    data = rdflib.Graph()
    for t in graph.triples((None, None, None)):  # a Dataset (nquads) as one graph: named graphs count too
        data.add(t)
    _, results, _ = validate(data, shacl_graph=shapes, ont_graph=tbox, inference="none", allow_warnings=True)
    nn = lambda t: graph.namespace_manager.normalizeUri(t) if isinstance(t, rdflib.URIRef) else str(t)
    found: Counter[tuple[str, str]] = Counter()
    first: dict[tuple[str, str], str] = {}
    for r in results.subjects(RDF.type, sh.ValidationResult):
        code = "kg.shape" if results.value(r, sh.resultSeverity) == sh.Violation else "kg.shape-warning"
        shape = results.value(r, sh.sourceShape)
        if isinstance(shape, rdflib.BNode):  # a property shape: name the node shape it belongs to
            shape = shapes.value(None, sh.property, shape) or shape
        path = results.value(r, sh.resultPath)
        # The constraint by name (sh:minCount 1), not pyshacl's message, which names the focus node and would not aggregate.
        component = str(results.value(r, sh.sourceConstraintComponent) or "")
        param = component.rsplit("#", 1)[-1].removesuffix("ConstraintComponent")
        param = param[:1].lower() + param[1:]
        value = shapes.value(results.value(r, sh.sourceShape), sh[param]) if param else None
        detail = f"sh:{param}" + (f" {nn(value)}" if isinstance(value, (rdflib.URIRef, rdflib.Literal)) else "") + " not met"
        key = (code, f"shape {nn(shape)}" + (f" on {nn(path)}" if isinstance(path, rdflib.URIRef) else "") + f": {detail}")
        found[key] += 1
        first.setdefault(key, nn(results.value(r, sh.focusNode)))
    return Counter({(code, f"{message}, e.g. {first[(code, message)]}"): n for (code, message), n in found.items()})


def _enum_types(root: Path, manifest: dict[str, Any]) -> set[str]:
    """IRIs of owp-yaml types declared with `enum`: their values are literals, not instances."""
    ontology = (manifest.get("spec") or {}).get("ontology") or {}
    prefixes = ontology.get("prefixes") if isinstance(ontology.get("prefixes"), dict) else {}
    out: set[str] = set()
    for entry in ontology.get("entrypoints") or []:
        if isinstance(entry, dict) and entry.get("format") == "owp-yaml" and entry.get("role") == "schema" and inside_package(root, entry.get("path")):
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
    import rdflib.collection
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

        tbox, shapes, namespaces, enums, todo, seen = rdflib.Graph(), rdflib.Graph(), set(), set(), [onto], set()
        removed: dict[Any, tuple[list[Any], str]] = {}  # Appendix C.1 tombstones: term -> (replacements, where it went)
        prefixes: dict[str, str] = {}
        package_graphs: list[Any] = []  # one T-box per package: domains and ranges are read per package
        while todo:  # the ontology and the OntologyPackages it builds on
            pkg = todo.pop()
            if pkg.identity in seen or pkg.kind != "OntologyPackage":
                continue
            seen.add(pkg.identity)
            package_graphs.append(tbox_graph(pkg.root, pkg.manifest, report.notes))
            tbox += package_graphs[-1]
            shapes += shapes_graph(pkg.root, pkg.manifest, report.notes)
            namespaces |= _namespaces(pkg.manifest)
            enums |= {rdflib.URIRef(e) for e in _enum_types(pkg.root, pkg.manifest)}
            for iri, (replaced, version) in removed_terms(pkg.root, pkg.manifest).items():
                where = f"removed from {pkg.identity.rsplit('@', 1)[0]} in {version}" if version else f"removed in {pkg.identity}"
                removed.setdefault(rdflib.URIRef(iri), ([rdflib.URIRef(r) for r in replaced], where))
            for name, ns in (((pkg.manifest.get("spec") or {}).get("ontology") or {}).get("prefixes") or {}).items():
                if isinstance(ns, str):
                    prefixes.setdefault(name, ns)
            for dep in (pkg.manifest.get("spec") or {}).get("dependencies") or []:
                ref = dep if isinstance(dep, str) else dep.get("ref") if isinstance(dep, dict) else None
                if ref in resolution.packages:
                    todo.append(resolution.packages[ref])

        classes = set(tbox.subjects(RDF.type, OWL.Class)) | set(tbox.subjects(RDF.type, RDFS.Class))
        properties = {s for t in (OWL.ObjectProperty, OWL.DatatypeProperty, RDF.Property, OWL.AnnotationProperty)
                      for s in tbox.subjects(RDF.type, t)}
        lifecycle: dict[Any, tuple[str, list[Any]]] = {}  # Appendix C.1: term -> (candidate or deprecated, replacements)
        for t in tbox.subjects(rdflib.URIRef(VS_NS + "term_status"), rdflib.Literal("testing")):
            lifecycle[t] = ("candidate", [])
        for t, value in tbox.subject_objects(OWL.deprecated):
            if str(value).lower() == "true":
                lifecycle[t] = ("deprecated", sorted(tbox.objects(t, rdflib.URIRef(DCTERMS_NS + "isReplacedBy"))))
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
        def mark(term, what: str) -> None:
            status, replaced = lifecycle.get(term, ("stable", []))
            nn = graph.namespace_manager.normalizeUri
            if status == "candidate":
                found[("kg.candidate", f"{what} {nn(term)} is a candidate term, not yet stable")] += 1
            elif status == "deprecated":
                instead = f"; replaced by {', '.join(map(nn, replaced))}" if replaced else ""
                found[("kg.deprecated", f"{what} {nn(term)} is deprecated{instead}")] += 1

        def gone(term, nn) -> str:
            """Why an undefined term is undefined, when an ontology keeps its tombstone."""
            if term not in removed:
                return ""
            replaced, where = removed[term]
            return f"; {where}" + (f", replaced by {', '.join(map(nn, replaced))}" if replaced else "")

        for o in graph.objects(None, RDF.type):
            if ours(o) and o not in classes:
                nn = graph.namespace_manager.normalizeUri
                found[("kg.unknown-class", f"class {nn(o)} is not defined by the ontology{gone(o, nn)}")] += 1
            else:
                mark(o, "class")
        for s, p, o in graph.triples((None, None, None)):
            if p == RDF.type or not ours(p):
                continue
            name = graph.namespace_manager.normalizeUri(p)
            if p not in properties:
                found[("kg.unknown-property", f"property {name} is not defined by the ontology{gone(p, graph.namespace_manager.normalizeUri)}")] += 1
                continue
            mark(p, "property")
            # Within one package, each rdfs:domain must hold (RDFS reads several as an intersection), and within an
            # owl:unionOf domain (a property several types declare) any member is enough. Packages that each declare a
            # domain for a shared property extend it: one package's domains holding is enough. Ranges likewise.
            nn = graph.namespace_manager.normalizeUri

            def requirements(axis) -> list[list[list[Any]]]:
                """Per package that states `axis` for p: its groups (one per triple) of accepted classes."""
                out = []
                for g in package_graphs:
                    groups = []
                    for d in g.objects(p, axis):
                        union = g.value(d, OWL.unionOf)
                        ms = list(rdflib.collection.Collection(g, union)) if union is not None else [d]
                        if axis == RDFS.range:
                            ms = [m for m in ms if m in classes and m not in enums]  # datatypes and enumerations are not checked
                        if ms:
                            groups.append(sorted(ms))
                    if groups:
                        out.append(sorted(groups))
                return out

            def label_of(reqs) -> str:
                group = lambda g: "(" + " or ".join(map(nn, g)) + ")" if len(g) > 1 else nn(g[0])
                alt = lambda gs: " and ".join(map(group, gs))
                return " or ".join(f"({alt(gs)})" if len(gs) > 1 and len(reqs) > 1 else alt(gs) for gs in reqs)

            holds = lambda reqs, have: any(all(any(m in have for m in g) for g in gs) for gs in reqs)
            domains = requirements(RDFS.domain)
            if domains and s not in types:
                found[("kg.untyped", f"subject of {name} has no rdf:type, so domain {label_of(domains)} cannot be checked")] += 1
            elif domains and not holds(domains, types[s]):
                found[("kg.domain", f"subject of {name} is not a {label_of(domains)}")] += 1
            ranges = requirements(RDFS.range)
            if not ranges:
                continue
            if isinstance(o, rdflib.Literal):
                found[("kg.range", f"object of {name} is a literal, not a {label_of(ranges)}")] += 1
            elif o not in types:
                found[("kg.untyped", f"object of {name} has no rdf:type, so range {label_of(ranges)} cannot be checked")] += 1
            elif not holds(ranges, types[o]):
                found[("kg.range", f"object of {name} is not a {label_of(ranges)}")] += 1
        if len(shapes):
            import importlib.util
            if importlib.util.find_spec("pyshacl") is None:
                report.notes.append(f"{rel}: the ontology has SHACL shapes, which were not run: pip install 'ontle[shacl]'")
            else:
                found += shape_findings(graph, shapes, tbox)
        report.checked.append(rel)
        report.graphs[rel] = {"ontology": onto_ref, "asOf": (spec.get("snapshot") or {}).get("asOf") if isinstance(spec.get("snapshot"), dict) else None}
        report.findings += [KgFinding(code, rel, message, n) for (code, message), n in sorted(found.items())]
        defined = set(tbox.subjects(RDF.type, None))
        for prof in sorted(r for r, k in kinds.items() if k == "KnowledgeExtractionProfile" and ((docs.get(r) or {}).get("spec") or {}).get("source") == rel):
            report.findings += _query_findings(prof, (docs.get(prof) or {}).get("spec") or {}, ours, defined, lifecycle, removed, prefixes)
            report.checked.append(prof)
    report.notes = list(dict.fromkeys(report.notes))  # an ontology shared by several graphs is noted once
    return report


def _query_terms(query) -> set[Any]:
    """The IRIs a parsed SPARQL query names: in its patterns, property paths, filters, and values."""
    import rdflib
    from rdflib.paths import Path as RdfPath
    out: set[Any] = set()
    todo, seen = [query.algebra], set()
    while todo:
        node = todo.pop()
        if isinstance(node, rdflib.URIRef):
            out.add(node)
        elif isinstance(node, dict):  # algebra nodes (CompValue) are mappings
            todo.extend(node.values())
        elif isinstance(node, (list, tuple, set, frozenset)):
            todo.extend(node)
        elif isinstance(node, RdfPath) and id(node) not in seen:
            seen.add(id(node))
            todo.extend(v for k, v in vars(node).items() if k in ("arg", "args", "path"))
    return out


def _query_findings(rel: str, spec: dict[str, Any], ours, defined: set[Any], lifecycle: dict[Any, tuple[str, list[Any]]],
                    removed: dict[Any, tuple[list[Any], str]], prefixes: dict[str, str]) -> list[KgFinding]:
    """A SPARQL KnowledgeExtractionProfile over a checked graph: the ontology terms its query names are defined, and not
    candidate or deprecated (advice), and they match the experimental `query.terms` when it is declared (Appendix C.1)."""
    import rdflib
    from rdflib.plugins.sparql import prepareQuery
    query = spec.get("query") if isinstance(spec.get("query"), dict) else {}
    if query.get("language") != "sparql" or not isinstance(query.get("text"), str):
        return []
    try:
        parsed = prepareQuery(query["text"])
    except Exception as exc:  # pyparsing and rdflib raise their own errors
        return [KgFinding("kg.parse", rel, f"spec.query.text is not valid SPARQL: {' '.join(str(exc).split())[:200]}", 1)]
    nm = parsed.prologue.namespace_manager
    for name, ns in prefixes.items():
        nm.bind(name, ns, override=False)
    nn = nm.normalizeUri
    used = {t for t in _query_terms(parsed) if ours(t)}
    found: list[KgFinding] = []
    for term in sorted(used):
        if term not in defined:
            hint = ""
            if term in removed:
                replaced, where = removed[term]
                hint = f"; {where}" + (f", replaced by {', '.join(map(nn, replaced))}" if replaced else "")
            found.append(KgFinding("kg.query-unknown", rel, f"the query names {nn(term)}, which the ontology does not define{hint}", 1))
            continue
        status, replaced = lifecycle.get(term, ("stable", []))
        if status == "candidate":
            found.append(KgFinding("kg.candidate", rel, f"query term {nn(term)} is a candidate term, not yet stable", 1))
        elif status == "deprecated":
            instead = f"; replaced by {', '.join(map(nn, replaced))}" if replaced else ""
            found.append(KgFinding("kg.deprecated", rel, f"query term {nn(term)} is deprecated{instead}", 1))
    if isinstance(query.get("terms"), list):
        declared = {rdflib.URIRef(e) for e in (expand(t, prefixes) if isinstance(t, str) else None for t in query["terms"]) if e}
        for term in sorted(used - declared):
            found.append(KgFinding("kg.query-terms", rel, f"the query names {nn(term)}, which spec.query.terms does not list", 1))
        for term in sorted(t for t in declared - used if ours(t)):
            found.append(KgFinding("kg.query-terms", rel, f"spec.query.terms lists {nn(term)}, which the query does not name", 1))
    return found


def rdf_schema_model(graph) -> dict[str, Any]:
    """The binding-check model of spec 14 (binding.schema_model's shape) from an RDF T-box: classes, rdfs:subClassOf,
    rdfs:domain (an owl:unionOf domain counts each member), rdfs:range, and datatypes enumerated with owl:oneOf."""
    import rdflib
    import rdflib.collection
    from rdflib.namespace import OWL, RDF, RDFS
    model: dict[str, Any] = {"classes": set(), "parents": {}, "declaredOn": {}, "range": {}, "enums": {}}

    def members(node) -> list:
        lst = graph.value(node, OWL.unionOf)
        return list(rdflib.collection.Collection(graph, lst)) if lst is not None else [node]

    for cls in set(graph.subjects(RDF.type, OWL.Class)) | set(graph.subjects(RDF.type, RDFS.Class)):
        if isinstance(cls, rdflib.URIRef):
            model["classes"].add(str(cls))
            model["parents"].setdefault(str(cls), set()).update(str(p) for p in graph.objects(cls, RDFS.subClassOf) if isinstance(p, rdflib.URIRef))
    for prop in set(graph.subjects(RDFS.domain, None)) | set(graph.subjects(RDFS.range, None)):
        if not isinstance(prop, rdflib.URIRef):
            continue
        owners = model["declaredOn"].setdefault(str(prop), set())
        for d in graph.objects(prop, RDFS.domain):
            owners.update(str(m) for m in members(d) if isinstance(m, rdflib.URIRef))
        rng = graph.value(prop, RDFS.range)
        if isinstance(rng, rdflib.URIRef):
            model["range"][str(prop)] = str(rng)
    for dt in set(graph.subjects(OWL.equivalentClass, None)) | set(graph.subjects(OWL.oneOf, None)):
        nodes = [dt] + list(graph.objects(dt, OWL.equivalentClass))
        for n in nodes:
            lst = graph.value(n, OWL.oneOf)
            if lst is not None and isinstance(dt, rdflib.URIRef):
                model["enums"][str(dt)] = {str(v) for v in rdflib.collection.Collection(graph, lst) if isinstance(v, rdflib.Literal)}
    return model


def check_bindings(package: str | Path, sources: list[str] | None = None, notes: list[str] | None = None) -> list[str]:
    """binding.path-domain and binding.value-range (spec 14) for a World's SemanticBinding, judged against the RDF T-box of
    its dependency ontologies: their owp-yaml schemas and their RDF schema entrypoints. Validation judges the owp-yaml
    part only; this tool also covers ontologies published as RDF. Schema entrypoints it cannot read go to `notes`."""
    from .binding import merge_models, semantic_warnings
    from .ontology import terms as ontology_terms
    from .resolve import _dependency_refs, resolve_package
    root, manifest = load_manifest(package)
    kinds, docs = local_assets(root, manifest.get("spec") or {})
    binding_docs = {rel: docs.get(rel) or {} for rel, kind in kinds.items() if kind == "SemanticBinding"}
    if not binding_docs:
        return []
    resolution = resolve_package(root, sources)
    prefixes: dict[str, str] = {}
    models = []
    for ref, _ in _dependency_refs(manifest):
        dep = resolution.packages.get(ref)
        if dep is None or dep.kind != "OntologyPackage":
            continue
        for name, iri in ontology_terms(dep.root, dep.manifest)[0].items():
            prefixes.setdefault(name, iri)
        models.append(rdf_schema_model(tbox_graph(dep.root, dep.manifest, notes)))
    if not models:
        raise OWPError("no dependency OntologyPackage resolves: pass --source or set ONTLE_PATH")
    md = manifest.get("metadata") or {}
    return semantic_warnings(f"{md.get('namespace')}/{md.get('name')}@{md.get('version')}", binding_docs, prefixes, merge_models(models))
