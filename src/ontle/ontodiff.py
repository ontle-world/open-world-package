"""`ontle diff`: what changed between two versions of an OntologyPackage, and the SemVer increment the changes call for.

Tooling, like `kg check`: it reads the T-box as RDF (the rdf extra) and changes no verdict. The grading rules are spec
section 3.1 ("Versions"); keep the two in step. Only the terms of the ontology's own namespaces (its `iri` and its
non-standard prefixes) are compared:

- major: a term removed or its type changed; a superclass or superproperty removed; a domain or range narrowed or
  changed; an enumeration value removed. Data that used the old version may no longer fit.
- minor: a term added, deprecated, or undeprecated, or made or no longer a candidate; a superclass or superproperty added; a domain or range widened;
  an enumeration value added.
- patch: labels, definitions, and comments.

A domain or range is compared by the classes it names, without reasoning over subclasses: it is widened when every
statement of the new version is implied by one of the old (each new union contains an old union). Moving a domain to
a superclass is therefore graded major; grade it by hand. While the major version is 0, a breaking change needs a minor
increment and an addition a patch increment (SemVer leaves 0.x open; this is the usual reading).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .core import OWPError, SEMVER_RE, load_manifest
from .kgcheck import _identity, _namespaces, _rdflib, rdf_schema_model, shapes_graph, tbox_graph
from .ontology import VS_NS, removed_terms

LEVELS = ("patch", "minor", "major")
TYPES = {  # the term's type, as `ontology index` names it
    "http://www.w3.org/2002/07/owl#Class": "class", "http://www.w3.org/2000/01/rdf-schema#Class": "class",
    "http://www.w3.org/2002/07/owl#ObjectProperty": "property", "http://www.w3.org/2002/07/owl#DatatypeProperty": "property",
    "http://www.w3.org/2002/07/owl#AnnotationProperty": "property", "http://www.w3.org/1999/02/22-rdf-syntax-ns#Property": "property",
    "http://www.w3.org/2000/01/rdf-schema#Datatype": "datatype", "http://www.w3.org/2002/07/owl#NamedIndividual": "individual",
    "http://www.w3.org/2004/02/skos/core#Concept": "concept", "http://www.w3.org/2004/02/skos/core#ConceptScheme": "concept",
}
TEXT = ("http://www.w3.org/2000/01/rdf-schema#label", "http://www.w3.org/2000/01/rdf-schema#comment",
        "http://www.w3.org/2004/02/skos/core#prefLabel", "http://www.w3.org/2004/02/skos/core#altLabel",
        "http://www.w3.org/2004/02/skos/core#definition")


@dataclass
class Change:
    level: str
    change: str


@dataclass
class OntologyDiff:
    old: str
    new: str
    changes: list[Change] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def required(self) -> str | None:
        """The SemVer increment the changes call for (major, minor, patch), or None when nothing changed."""
        return max((c.level for c in self.changes), key=LEVELS.index, default=None)

    @property
    def increment(self) -> str | None:
        """The increment from the old version to the new one, or None when the new one is not greater."""
        old, new = (_semver(i.rsplit("@", 1)[1]) for i in (self.old, self.new))
        if new <= old:
            return None
        return "major" if new[0] > old[0] else "minor" if new[1] > old[1] else "patch"

    @property
    def enough(self) -> bool:
        need = self.required
        if need is None:
            return True
        if _semver(self.old.rsplit("@", 1)[1])[0] == 0:  # 0.x: breaking -> minor, addition -> patch
            need = {"major": "minor", "minor": "patch"}.get(need, need)
        have = self.increment
        return have is not None and LEVELS.index(have) >= LEVELS.index(need)

    def to_dict(self) -> dict[str, Any]:
        return {"old": self.old, "new": self.new, "required": self.required, "increment": self.increment, "enough": self.enough,
                "changes": [{"level": c.level, "change": c.change} for c in self.changes], "notes": self.notes}


def _semver(version: str) -> tuple[int, int, int, int]:
    m = SEMVER_RE.match(version)
    if not m:
        raise OWPError(f"{version!r} is not a SemVer version")
    pre = 0 if "-" in version.split("+", 1)[0] else 1  # a pre-release sorts before its release
    return int(m.group(1)), int(m.group(2)), int(m.group(3)), pre


def _open(path: str | Path) -> tuple[Path, dict[str, Any]]:
    """A package directory, or a verified .owp.zip (unpacked into the resolver's cache)."""
    p = Path(path)
    if p.suffix == ".zip" and p.is_file():
        from .resolve import ArchiveSource
        pkg = ArchiveSource(str(p), p.resolve())._scan()[0]
        return pkg.root, pkg.manifest
    return load_manifest(p)


def _model(root: Path, manifest: dict[str, Any], notes: list[str]) -> dict[str, Any]:
    rdflib = _rdflib()
    import rdflib.collection
    from rdflib.namespace import OWL, RDF, RDFS
    graph = tbox_graph(root, manifest, notes)
    namespaces = _namespaces(manifest)
    for prefix, iri in (((manifest.get("spec") or {}).get("ontology") or {}).get("prefixes") or {}).items():
        if isinstance(iri, str):
            graph.namespace_manager.bind(prefix, iri, override=True)
    ours = lambda t: isinstance(t, rdflib.URIRef) and any(str(t).startswith(ns) for ns in namespaces)

    def groups(term, axis) -> frozenset[frozenset[str]]:
        out = set()
        for d in graph.objects(term, axis):
            union = graph.value(d, OWL.unionOf)
            members = list(rdflib.collection.Collection(graph, union)) if union is not None else [d]
            out.add(frozenset(str(m) for m in members if isinstance(m, rdflib.URIRef)))
        return frozenset(g for g in out if g)

    terms: dict[str, dict[str, Any]] = {}
    for s, t in graph.subject_objects(RDF.type):
        if ours(s) and str(t) in TYPES:
            terms.setdefault(str(s), {"types": set()})["types"].add(TYPES[str(t)])
    for s, t in graph.subject_objects(RDF.type):  # instances of a class the ontology defines are individuals
        if ours(s) and "class" in terms.get(str(t), {}).get("types", ()):
            terms.setdefault(str(s), {"types": set()})["types"].add("individual")
    enums = rdf_schema_model(graph)["enums"]
    for iri, info in terms.items():
        s = rdflib.URIRef(iri)
        info["parents"] = {str(p) for axis in (RDFS.subClassOf, RDFS.subPropertyOf) for p in graph.objects(s, axis) if isinstance(p, rdflib.URIRef)}
        info["domain"], info["range"] = groups(s, RDFS.domain), groups(s, RDFS.range)
        info["deprecated"] = any(str(v).lower() == "true" for v in graph.objects(s, OWL.deprecated))
        info["candidate"] = any(str(v) in ("testing", "unstable") for v in graph.objects(s, rdflib.URIRef(VS_NS + "term_status")))
        info["text"] = {(str(p), str(o), getattr(o, "language", None)) for p in TEXT for o in graph.objects(s, rdflib.URIRef(p))}
        info["values"] = enums.get(iri)
    return {"terms": terms, "name": graph.namespace_manager.normalizeUri, "shapes": shapes_graph(root, manifest, notes)}


def _widened(old: frozenset[frozenset[str]], new: frozenset[frozenset[str]]) -> bool:
    """Whatever met every old statement meets every new one: each new union contains some old union."""
    return all(any(o <= n for o in old) for n in new)


def diff_ontologies(old_path: str | Path, new_path: str | Path) -> OntologyDiff:
    """Compare two versions of one OntologyPackage (directories or .owp.zip archives)."""
    from rdflib.compare import isomorphic
    (old_root, old_manifest), (new_root, new_manifest) = _open(old_path), _open(new_path)
    for m, p in ((old_manifest, old_path), (new_manifest, new_path)):
        if m.get("kind") != "OntologyPackage":
            raise OWPError(f"{p}: ontle diff compares OntologyPackages")
    old_id, new_id = _identity(old_manifest), _identity(new_manifest)
    if old_id.rsplit("@", 1)[0] != new_id.rsplit("@", 1)[0]:
        raise OWPError(f"{old_id} and {new_id} are different packages")
    result = OntologyDiff(old_id, new_id)
    a, b = _model(old_root, old_manifest, result.notes), _model(new_root, new_manifest, result.notes)
    nn = b["name"]
    names = lambda iris: ", ".join(sorted(nn(i) if "://" in i or i.startswith("urn:") else i for i in iris))
    add = lambda level, text: result.changes.append(Change(level, text))
    old_terms, new_terms = a["terms"], b["terms"]
    tombstones = removed_terms(new_root, new_manifest)
    untold = []
    for iri in sorted(old_terms.keys() - new_terms.keys()):
        replaced = tombstones.get(iri, ([], None))[0]
        instead = f" (replaced by {names(replaced)})" if replaced else ""
        add("major", f"removed {'/'.join(sorted(old_terms[iri]['types']))} {a['name'](iri)}{instead}")
        if iri not in tombstones:
            untold.append(a["name"](iri))
    if untold:
        result.notes.append(f"removed without a `removed` entry (Appendix C.1), so users of {', '.join(untold)} are not told what replaces them")
    for iri in sorted(new_terms.keys() - old_terms.keys()):
        add("minor", f"added {'/'.join(sorted(new_terms[iri]['types']))} {nn(iri)}" + (" (candidate)" if new_terms[iri]["candidate"] else ""))
    for iri in sorted(old_terms.keys() & new_terms.keys()):
        o, n, name = old_terms[iri], new_terms[iri], nn(iri)
        if o["types"] != n["types"]:
            add("major", f"{name}: type {'/'.join(sorted(o['types']))} -> {'/'.join(sorted(n['types']))}")
        if o["parents"] - n["parents"]:
            add("major", f"{name}: no longer a subclass or subproperty of {names(o['parents'] - n['parents'])}")
        if n["parents"] - o["parents"]:
            add("minor", f"{name}: now a subclass or subproperty of {names(n['parents'] - o['parents'])}")
        for axis in ("domain", "range"):
            if o[axis] != n[axis]:
                show = lambda gs: " and ".join(f"({names(g)})" if len(g) > 1 else names(g) for g in sorted(gs, key=sorted)) or "none"
                add("minor" if _widened(o[axis], n[axis]) else "major", f"{name}: {axis} {show(o[axis])} -> {show(n[axis])}")
        if o["values"] is not None and n["values"] is not None:
            if o["values"] - n["values"]:
                add("major", f"{name}: values removed: {', '.join(sorted(o['values'] - n['values']))}")
            if n["values"] - o["values"]:
                add("minor", f"{name}: values added: {', '.join(sorted(n['values'] - o['values']))}")
        if o["deprecated"] != n["deprecated"]:
            add("minor", f"{name}: {'deprecated' if n['deprecated'] else 'no longer deprecated'}")
        if o["candidate"] != n["candidate"]:
            add("minor", f"{name}: {'now a candidate term' if n['candidate'] else 'no longer a candidate term'}")
        if o["text"] != n["text"]:
            add("patch", f"{name}: labels or definitions changed")
    if not isomorphic(a["shapes"], b["shapes"]):
        result.notes.append("SHACL shapes changed and are not graded: a new or stricter constraint can reject data the old version accepted (major)")
    result.notes = list(dict.fromkeys(result.notes))
    return result
