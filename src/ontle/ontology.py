"""OntologyPackage contract (spec section 3.1): entrypoints, prefixes, term index, and ontology profiles.

Verdicts depend only on the manifest, OWP YAML files (SemanticProfile, OntologyTermIndex), and file
existence (DD-1). RDF and LinkML content is read only by tooling (`ontle ontology index`, `ontle export`).
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .structure import SEMANTIC_PROFILE, TERM_INDEX, external_ref_issues, structure_errors
from .yamlio import dump_yaml, load_yaml

ONTOLOGY_PROFILES = ["vocabulary", "schema", "constrained", "mapped"]
FORMATS = {"owp-yaml", "turtle", "jsonld", "rdf-xml", "owl-xml", "ntriples", "linkml", "sssom-tsv"}
ROLES = {"schema", "shapes", "mappings", "labels"}
TERM_TYPES = {"class", "property", "individual", "datatype", "concept"}
PREFIX_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")
IRI_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:\S+$")
CURIE_RE = re.compile(r"^([A-Za-z][A-Za-z0-9_-]*):([^\s/][^\s]*)$")

def inside_package(root: Path, rel: Any) -> bool:
    """rel is a package-relative path of an existing file inside the package root."""
    if not isinstance(rel, str) or not rel or rel.startswith("./") or "\\" in rel:
        return False
    target = (root / rel).resolve()
    try:
        target.relative_to(root.resolve())
    except ValueError:
        return False
    return target.is_file()


def _load(path: Path) -> Any:
    try:
        return load_yaml(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def expand(curie: str, prefixes: dict[str, str]) -> str | None:
    """Expand a CURIE with declared prefixes; a full IRI is returned unchanged; None if the prefix is undeclared."""
    match = CURIE_RE.match(curie)
    if match and match.group(1) in prefixes:
        return prefixes[match.group(1)] + match.group(2)
    if "://" in curie or curie.startswith("urn:"):
        return curie
    return None


def _profile_curies(doc: dict[str, Any]) -> list[tuple[str, str, str]]:
    """(where, value, term type) for every CURIE a SemanticProfile defines or uses. Term type is '' for uses."""
    out: list[tuple[str, str, str]] = []
    spec = doc.get("spec") if isinstance(doc.get("spec"), dict) else {}
    for i, t in enumerate(spec.get("types") or []):
        if not isinstance(t, dict):
            continue
        out.append((f"spec.types[{i}].id", t.get("id"), "class"))
        for parent in t.get("subClassOf") or [] if isinstance(t.get("subClassOf"), list) else [t.get("subClassOf")] if t.get("subClassOf") else []:
            out.append((f"spec.types[{i}].subClassOf", parent, ""))
        for j, p in enumerate(t.get("properties") or []):
            if isinstance(p, dict):
                out.append((f"spec.types[{i}].properties[{j}].id", p.get("id"), "property"))
                if isinstance(p.get("range"), str) and ":" in p["range"]:
                    out.append((f"spec.types[{i}].properties[{j}].range", p["range"], ""))
    for i, r in enumerate(spec.get("relations") or []):
        if isinstance(r, dict):
            out.append((f"spec.relations[{i}].id", r.get("id"), "property"))
            for key in ("domain", "range"):
                if isinstance(r.get(key), str):
                    out.append((f"spec.relations[{i}].{key}", r[key], ""))
    return out


def ontology_issues(root: Path, spec: dict[str, Any], declared: set[str]) -> tuple[list[str], list[str]]:
    """Single-package checks of spec.ontology (always applied, independent of the declared profile)."""
    errors: list[str] = []
    warnings: list[str] = []
    ontology = spec.get("ontology")
    if not isinstance(ontology, dict):
        return errors, warnings
    iri = ontology.get("iri")
    if iri is not None and not (isinstance(iri, str) and IRI_RE.match(iri)):
        errors.append(f"ontology.iri: spec.ontology.iri {iri!r} must be an absolute IRI")
    prefixes = ontology.get("prefixes")
    if prefixes is not None:
        if not isinstance(prefixes, dict):
            errors.append("ontology.prefix: spec.ontology.prefixes must map prefix names to IRIs")
            prefixes = {}
        for name, value in prefixes.items():
            if not (isinstance(name, str) and PREFIX_RE.match(name)) or not (isinstance(value, str) and IRI_RE.match(value)):
                errors.append(f"ontology.prefix: prefix {name!r} -> {value!r} must be a name and an absolute IRI")
    prefixes = prefixes if isinstance(prefixes, dict) else {}
    entrypoints = ontology.get("entrypoints")
    if entrypoints is not None and not isinstance(entrypoints, list):
        errors.append("ontology.entrypoint: spec.ontology.entrypoints must be a list")
        entrypoints = []
    for i, entry in enumerate(entrypoints or []):
        if not isinstance(entry, dict):
            errors.append(f"ontology.entrypoint: spec.ontology.entrypoints[{i}] must be a mapping with path, format, and role")
            continue
        path, fmt, role = entry.get("path"), entry.get("format"), entry.get("role")
        if not inside_package(root, path):
            errors.append(f"ontology.entrypoint: spec.ontology.entrypoints[{i}].path {path!r} must be an existing file inside the package")
            continue
        if fmt not in FORMATS:
            errors.append(f"ontology.format: spec.ontology.entrypoints[{i}].format {fmt!r} must be one of {sorted(FORMATS)}")
        if role not in ROLES:
            errors.append(f"ontology.entrypoint: spec.ontology.entrypoints[{i}].role {role!r} must be one of {sorted(ROLES)}")
        if fmt == "owp-yaml":
            doc = _load(root / path)
            if not isinstance(doc, dict) or doc.get("kind") != "SemanticProfile":
                errors.append(f"ontology.parse: {path} (format owp-yaml) must be a SemanticProfile document")
                continue
            errors.extend(structure_errors(doc, SEMANTIC_PROFILE, path, declared))
            for where, value, _ in _profile_curies(doc):
                if not isinstance(value, str) or expand(value, prefixes) is None:
                    errors.append(f"ontology.prefix-undeclared: {path}: {where} {value!r} uses a prefix that spec.ontology.prefixes does not declare")
    term_index = ontology.get("termIndex")
    if term_index is not None:
        doc = _load(root / term_index) if inside_package(root, term_index) else None
        if not isinstance(doc, dict) or doc.get("kind") != "OntologyTermIndex":
            errors.append(f"ontology.term-index: spec.ontology.termIndex {term_index!r} must be an existing OntologyTermIndex document")
        else:
            errors.extend(structure_errors(doc, TERM_INDEX, term_index, declared))
            for j, term in enumerate((doc.get("spec") or {}).get("terms") or []):
                if not (isinstance(term, dict) and isinstance(term.get("iri"), str) and IRI_RE.match(term["iri"]) and term.get("type") in TERM_TYPES):
                    errors.append(f"ontology.term-index: {term_index}: spec.terms[{j}] needs an absolute iri and a type in {sorted(TERM_TYPES)}")
    for i, imp in enumerate(ontology.get("externalImports") or [] if isinstance(ontology.get("externalImports"), list) else []):
        if not isinstance(imp, dict) or not (isinstance(imp.get("iri"), str) and IRI_RE.match(imp["iri"])):
            errors.append(f"ontology.external-import: spec.ontology.externalImports[{i}] needs an absolute iri")
            continue
        if "ref" not in imp:
            errors.append(f"ontology.external-import: spec.ontology.externalImports[{i}] needs a ref (spec section 5.1)")
            continue
        ref_errors, ref_warnings = external_ref_issues(imp["ref"], f"spec.ontology.externalImports[{i}].ref", declared)
        errors.extend(ref_errors)
        warnings.extend(ref_warnings)
    return errors, warnings


def ontology_profile_errors(profile: str, root: Path, spec: dict[str, Any]) -> list[str]:
    """Errors preventing an OntologyPackage from satisfying one profile (cumulative)."""
    level = ONTOLOGY_PROFILES.index(profile)
    ontology = spec.get("ontology") if isinstance(spec.get("ontology"), dict) else {}
    entries = [e for e in ontology.get("entrypoints") or [] if isinstance(e, dict)] if isinstance(ontology.get("entrypoints"), list) else []
    errors: list[str] = []
    if not isinstance(ontology.get("iri"), str) or not entries:
        errors.append("profile.ontology.vocabulary: requires spec.ontology.iri and at least one entrypoint")
    if level < 1:
        return errors
    schema = [e for e in entries if e.get("role") == "schema"]
    if not schema:
        errors.append("profile.ontology.schema: requires an entrypoint with role schema")
    elif not any(e.get("format") == "owp-yaml" for e in schema) and not ontology.get("termIndex"):
        errors.append("profile.ontology.schema: a schema that is not owp-yaml requires spec.ontology.termIndex (generate it with `ontle ontology index`)")
    if level < 2:
        return errors
    if not any(e.get("role") == "shapes" for e in entries):
        errors.append("profile.ontology.constrained: requires an entrypoint with role shapes")
    if level < 3:
        return errors
    if not any(e.get("role") == "mappings" for e in entries):
        errors.append("profile.ontology.mapped: requires an entrypoint with role mappings")
    return errors


def satisfied_ontology_profile(root: Path, spec: dict[str, Any]) -> str | None:
    satisfied = None
    for profile in ONTOLOGY_PROFILES:
        if ontology_profile_errors(profile, root, spec):
            break
        satisfied = profile
    return satisfied


def terms(root: Path, manifest: dict[str, Any]) -> tuple[dict[str, str], set[str]]:
    """(prefixes, term IRIs) an OntologyPackage defines: owp-yaml schema entrypoints plus its term index."""
    ontology = (manifest.get("spec") or {}).get("ontology") or {}
    prefixes = ontology.get("prefixes") if isinstance(ontology.get("prefixes"), dict) else {}
    out: set[str] = set()
    for entry in ontology.get("entrypoints") or []:
        if isinstance(entry, dict) and entry.get("format") == "owp-yaml" and entry.get("role") == "schema" and isinstance(entry.get("path"), str):
            doc = _load(root / entry["path"])
            if isinstance(doc, dict):
                for _, value, term_type in _profile_curies(doc):
                    if term_type and isinstance(value, str) and expand(value, prefixes):
                        out.add(expand(value, prefixes))  # type: ignore[arg-type]
    index = ontology.get("termIndex")
    if isinstance(index, str):
        doc = _load(root / index)
        for term in ((doc or {}).get("spec") or {}).get("terms") or [] if isinstance(doc, dict) else []:
            if isinstance(term, dict) and isinstance(term.get("iri"), str):
                out.add(term["iri"])
    return prefixes, out


# --- tooling (T): index generation and export -------------------------------

RDF_NS = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
RDFS_NS = "http://www.w3.org/2000/01/rdf-schema#"
RDF_FORMATS = {"turtle": "turtle", "jsonld": "json-ld", "rdf-xml": "xml", "ntriples": "nt"}  # OWL/XML (owl-xml) needs an OWL API tool


def build_term_index(root: Path, manifest: dict[str, Any]) -> list[dict[str, str]]:
    """Terms from every schema entrypoint. RDF formats need the optional rdflib dependency (pip install ontle-open-world[rdf])."""
    ontology = (manifest.get("spec") or {}).get("ontology") or {}
    prefixes = ontology.get("prefixes") if isinstance(ontology.get("prefixes"), dict) else {}
    found: dict[str, str] = {}
    for entry in ontology.get("entrypoints") or []:
        if not isinstance(entry, dict) or entry.get("role") != "schema":
            continue
        path = root / str(entry.get("path"))
        fmt = entry.get("format")
        if fmt == "owp-yaml":
            doc = _load(path) or {}
            for _, value, term_type in _profile_curies(doc):
                if term_type and isinstance(value, str) and expand(value, prefixes):
                    found.setdefault(expand(value, prefixes), term_type)  # type: ignore[arg-type]
        elif fmt in RDF_FORMATS:
            # Only the terms this ontology defines: those in its own namespace (an RDF file also declares terms
            # it borrows, such as rdfs:label or Dublin Core annotations).
            namespace = ontology.get("iri") if isinstance(ontology.get("iri"), str) else ""
            found.update({iri: t for iri, t in _rdf_terms(path, RDF_FORMATS[fmt]).items() if iri not in found and iri.startswith(namespace)})
        else:
            from .core import OWPError
            raise OWPError(f"cannot build a term index from format {fmt!r}; write spec.ontology.termIndex by hand")
    return [{"iri": iri, "type": found[iri]} for iri in sorted(found)]


def _rdf_terms(path: Path, rdf_format: str) -> dict[str, str]:
    try:
        import rdflib
        from rdflib.namespace import OWL, RDF, RDFS, SKOS
    except ImportError as exc:
        from .core import OWPError
        raise OWPError("RDF entrypoints need rdflib: pip install 'ontle-open-world[rdf]'") from exc
    if not path.is_file():
        from .core import OWPError
        raise OWPError(f"schema entrypoint {path.name} does not exist; run ontle validate on the package")
    graph = rdflib.Graph()
    try:
        graph.parse(path, format=rdf_format)
    except Exception as exc:  # rdflib raises parser-specific errors
        from .core import OWPError
        raise OWPError(f"cannot read {path.name} as {rdf_format}: {' '.join(str(exc).split())[:200]}") from exc
    types = {OWL.Class: "class", RDFS.Class: "class", OWL.ObjectProperty: "property", OWL.DatatypeProperty: "property",
             RDF.Property: "property", OWL.NamedIndividual: "individual",
             RDFS.Datatype: "datatype", SKOS.Concept: "concept"}
    out: dict[str, str] = {}
    for subject, rdf_type in graph.subject_objects(RDF.type):
        if isinstance(subject, rdflib.URIRef) and rdf_type in types:
            out.setdefault(str(subject), types[rdf_type])
    return out


def write_term_index(root: Path, manifest_path: Path) -> Path:
    manifest = load_yaml(manifest_path.read_text(encoding="utf-8"))
    ontology = manifest.setdefault("spec", {}).setdefault("ontology", {})
    rel = ontology.get("termIndex") or "semantics/terms.yaml"
    target = root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    md = manifest.get("metadata") or {}
    target.write_text(dump_yaml({
        "apiVersion": "openworld/v1alpha1",
        "kind": "OntologyTermIndex",
        "metadata": {"name": f"{md.get('name')}-terms", "description": "Generated by `ontle ontology index`; do not edit by hand."},
        "spec": {"terms": build_term_index(root, manifest)},
    }), encoding="utf-8")
    if ontology.get("termIndex") != rel:
        ontology["termIndex"] = rel
        from .core import write_manifest  # local import: core imports this module
        write_manifest(manifest_path, manifest)
    return target


def export_rdf(root: Path, manifest: dict[str, Any], fmt: str) -> str:
    """Turtle or JSON-LD for the owp-yaml schema entrypoints, as OWL 2 DL (spec section 3.1, "RDF meaning").

    A type is an owl:Class, or, with `enum`, an rdfs:Datatype enumerating its literal values. A property whose
    range is a datatype (xsd:, rdf:langString, rdfs:Literal, an enum type, or none) is an owl:DatatypeProperty,
    otherwise an owl:ObjectProperty. A property declared under several types has their union as its domain.
    """
    ontology = (manifest.get("spec") or {}).get("ontology") or {}
    prefixes = dict(ontology.get("prefixes") or {})
    triples: list[tuple[str, str, str, bool]] = []  # subject, predicate, object, object-is-literal

    def iri(value: Any) -> str | None:
        return expand(value, prefixes) if isinstance(value, str) else None

    specs = []
    for entry in ontology.get("entrypoints") or []:
        if isinstance(entry, dict) and entry.get("format") == "owp-yaml" and entry.get("role") == "schema":
            specs.append((_load(root / entry["path"]) or {}).get("spec") or {})
    enums: dict[str, list[Any]] = {}
    for spec in specs:
        for t in spec.get("types") or []:
            if isinstance(t, dict) and iri(t.get("id")) and isinstance(t.get("enum"), list):
                enums[iri(t.get("id"))] = t["enum"]  # type: ignore[index]
    literal_ranges = ("http://www.w3.org/2001/XMLSchema#", RDF_NS + "langString", RDFS_NS + "Literal")
    props: dict[str, dict[str, set[str]]] = {}  # property -> {"domains": ..., "ranges": ...}

    def declare(prop: str, domain: str | None, rng: str | None) -> None:
        entry = props.setdefault(prop, {"domains": set(), "ranges": set()})
        if domain:
            entry["domains"].add(domain)
        if rng:
            entry["ranges"].add(rng)

    for spec in specs:
        for t in spec.get("types") or []:
            cls = iri(t.get("id")) if isinstance(t, dict) else None
            if not cls:
                continue
            if cls in enums:
                triples.append((cls, "rdf:type", "rdfs:Datatype", False))
            else:
                triples.append((cls, "rdf:type", "owl:Class", False))
            parents = t.get("subClassOf")
            for parent in parents if isinstance(parents, list) else [parents] if parents else []:
                if iri(parent) and cls not in enums:
                    triples.append((cls, "rdfs:subClassOf", iri(parent), False))  # type: ignore[arg-type]
            for lang, text in (t.get("label") or {}).items() if isinstance(t.get("label"), dict) else []:
                triples.append((cls, "rdfs:label", f"{text}@{lang}", True))
            for p in t.get("properties") or []:
                if isinstance(p, dict) and iri(p.get("id")):
                    declare(iri(p["id"]), cls, iri(p.get("range")))  # type: ignore[arg-type]
        for r in spec.get("relations") or []:
            if isinstance(r, dict) and iri(r.get("id")):
                declare(iri(r["id"]), iri(r.get("domain")), iri(r.get("range")))  # type: ignore[arg-type]
                props[iri(r["id"])].setdefault("relation", set()).add("yes")  # type: ignore[index]
    # Classes used but defined elsewhere (a dependency ontology) are declared, as OWL 2 DL requires.
    defined = {s for s, p, o, _ in triples if p == "rdf:type"}
    used = {o for s, p, o, lit in triples if p == "rdfs:subClassOf" and not lit}
    used |= {r for info in props.values() for key in ("domains", "ranges") for r in info[key] if r not in enums and not r.startswith(literal_ranges)}
    for cls in sorted(used - defined):
        triples.append((cls, "rdf:type", "owl:Class", False))
    unions: list[tuple[str, list[str], bool]] = []  # (subject, members, members-are-literals) for owl:unionOf / owl:oneOf
    for cls, values in enums.items():
        unions.append((cls, [json.dumps(v if isinstance(v, str) else json.dumps(v), ensure_ascii=False) for v in values], True))
    for prop, info in sorted(props.items()):
        ranges = sorted(info["ranges"])
        is_data = not info.get("relation") and (not ranges or all(r in enums or r.startswith(literal_ranges) for r in ranges))
        triples.append((prop, "rdf:type", "owl:DatatypeProperty" if is_data else "owl:ObjectProperty", False))
        domains = sorted(info["domains"])
        if len(domains) == 1:
            triples.append((prop, "rdfs:domain", domains[0], False))
        elif domains:
            unions.append((f"{prop}#domain", domains, False))  # several declaring types: the union, not the intersection
            triples.append((prop, "rdfs:domain", f"_:{len(unions) - 1}", False))
        if len(ranges) == 1:
            triples.append((prop, "rdfs:range", ranges[0], False))
        elif ranges:
            unions.append((f"{prop}#range", ranges, False))
            triples.append((prop, "rdfs:range", f"_:{len(unions) - 1}", False))
    std = {"rdf": RDF_NS, "rdfs": RDFS_NS, "owl": "http://www.w3.org/2002/07/owl#"}

    def ref(o: str) -> str:
        if o.startswith("_:"):
            return f"_:u{o[2:]}"
        return o if o.split(":", 1)[0] in std and "://" not in o else f"<{o}>"

    lines = [f"@prefix {k}: <{v}> ." for k, v in {**std, **prefixes}.items()] + [""]
    if isinstance(ontology.get("iri"), str):
        lines.append(f"<{ontology['iri'].rstrip('#/')}> rdf:type owl:Ontology .")
    for s, p, o, lit in triples:
        if lit:
            text, _, lang = o.rpartition("@")
            obj = json.dumps(text, ensure_ascii=False) + f"@{lang}"
        else:
            obj = ref(o)
        lines.append(f"<{s}> {p} {obj} .")
    for i, (subject, members, literals) in enumerate(unions):
        items = " ".join(members if literals else [ref(m) for m in members])
        if literals:  # an enum type: the datatype of exactly these literal values
            lines.append(f"<{subject}> owl:equivalentClass [ rdf:type rdfs:Datatype ; owl:oneOf ( {items} ) ] .")
        else:
            lines.append(f"_:u{i} rdf:type owl:Class ; owl:unionOf ( {items} ) .")
    turtle = "\n".join(lines) + "\n"
    if fmt != "jsonld":
        return turtle
    # JSON-LD of the same graph, built directly (no RDF library needed).
    def node_ref(o: str) -> dict[str, Any]:
        return {"@id": f"_:u{o[2:]}"} if o.startswith("_:") else {"@id": o}

    nodes: dict[str, dict[str, Any]] = {}
    if isinstance(ontology.get("iri"), str):
        nodes[ontology["iri"].rstrip("#/")] = {"@id": ontology["iri"].rstrip("#/"), "@type": ["owl:Ontology"]}
    for s, p, o, lit in triples:
        node = nodes.setdefault(s, {"@id": s})
        if p == "rdf:type":
            node.setdefault("@type", []).append(o)
        elif lit:
            text, _, lang = o.rpartition("@")
            node.setdefault(p, []).append({"@value": text, "@language": lang})
        else:
            node.setdefault(p, []).append(node_ref(o))
    for i, (subject, members, literals) in enumerate(unions):
        if literals:
            values = [{"@value": json.loads(m)} for m in members]
            nodes.setdefault(subject, {"@id": subject}).setdefault("owl:equivalentClass", []).append(
                {"@type": "rdfs:Datatype", "owl:oneOf": {"@list": values}})
        else:
            nodes[f"_:u{i}"] = {"@id": f"_:u{i}", "@type": ["owl:Class"], "owl:unionOf": {"@list": [{"@id": m} for m in members]}}
    return json.dumps({"@context": {**std, **prefixes}, "@graph": list(nodes.values())}, indent=2, ensure_ascii=False) + "\n"
