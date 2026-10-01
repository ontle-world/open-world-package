"""OntologyPackage contract (spec section 3.1): entrypoints, prefixes, term index, and ontology profiles.

Verdicts depend only on the manifest, OWP YAML files (SemanticProfile, OntologyTermIndex), and file
existence (DD-1). RDF and LinkML content is read only by tooling (`ontle ontology index`, `ontle export`).
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

from .structure import SEMANTIC_PROFILE, TERM_INDEX, external_ref_issues, structure_errors

ONTOLOGY_PROFILES = ["vocabulary", "schema", "constrained", "mapped"]
FORMATS = {"owp-yaml", "turtle", "jsonld", "owl-xml", "ntriples", "linkml", "sssom-tsv"}
ROLES = {"schema", "shapes", "mappings", "labels"}
TERM_TYPES = {"class", "property", "individual", "datatype", "concept"}
PREFIX_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")
IRI_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:\S+$")
CURIE_RE = re.compile(r"^([A-Za-z][A-Za-z0-9_-]*):([^\s/][^\s]*)$")

def _inside(root: Path, rel: Any) -> bool:
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
        return yaml.safe_load(path.read_text(encoding="utf-8"))
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
        if not _inside(root, path):
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
        doc = _load(root / term_index) if _inside(root, term_index) else None
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

RDF_FORMATS = {"turtle": "turtle", "jsonld": "json-ld", "owl-xml": "xml", "ntriples": "nt"}


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
            found.update({iri: t for iri, t in _rdf_terms(path, RDF_FORMATS[fmt]).items() if iri not in found})
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
    graph = rdflib.Graph()
    graph.parse(path, format=rdf_format)
    types = {OWL.Class: "class", RDFS.Class: "class", OWL.ObjectProperty: "property", OWL.DatatypeProperty: "property",
             RDF.Property: "property", OWL.AnnotationProperty: "property", OWL.NamedIndividual: "individual",
             RDFS.Datatype: "datatype", SKOS.Concept: "concept"}
    out: dict[str, str] = {}
    for subject, rdf_type in graph.subject_objects(RDF.type):
        if isinstance(subject, rdflib.URIRef) and rdf_type in types:
            out.setdefault(str(subject), types[rdf_type])
    return out


def write_term_index(root: Path, manifest_path: Path) -> Path:
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    ontology = manifest.setdefault("spec", {}).setdefault("ontology", {})
    rel = ontology.get("termIndex") or "semantics/terms.yaml"
    target = root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    md = manifest.get("metadata") or {}
    target.write_text(yaml.safe_dump({
        "apiVersion": "openworld/v1alpha1",
        "kind": "OntologyTermIndex",
        "metadata": {"name": f"{md.get('name')}-terms", "description": "Generated by `ontle ontology index`; do not edit by hand."},
        "spec": {"terms": build_term_index(root, manifest)},
    }, sort_keys=False, allow_unicode=True), encoding="utf-8")
    if ontology.get("termIndex") != rel:
        ontology["termIndex"] = rel
        manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return target


def export_rdf(root: Path, manifest: dict[str, Any], fmt: str) -> str:
    """Turtle or JSON-LD for the owp-yaml schema entrypoints (classes, properties, labels, domains, ranges)."""
    ontology = (manifest.get("spec") or {}).get("ontology") or {}
    prefixes = dict(ontology.get("prefixes") or {})
    triples: list[tuple[str, str, str, bool]] = []  # subject, predicate, object, object-is-literal

    def iri(value: Any) -> str | None:
        return expand(value, prefixes) if isinstance(value, str) else None

    for entry in ontology.get("entrypoints") or []:
        if not (isinstance(entry, dict) and entry.get("format") == "owp-yaml" and entry.get("role") == "schema"):
            continue
        spec = (_load(root / entry["path"]) or {}).get("spec") or {}
        for t in spec.get("types") or []:
            cls = iri(t.get("id"))
            if not cls:
                continue
            triples.append((cls, "rdf:type", "owl:Class", False))
            for lang, text in (t.get("label") or {}).items() if isinstance(t.get("label"), dict) else []:
                triples.append((cls, "rdfs:label", f"{text}@{lang}", True))
            for p in t.get("properties") or []:
                prop = iri(p.get("id"))
                if prop:
                    rng = iri(p.get("range"))
                    triples.append((prop, "rdf:type", "owl:ObjectProperty" if rng else "owl:DatatypeProperty", False))
                    triples.append((prop, "rdfs:domain", cls, False))
                    if rng:
                        triples.append((prop, "rdfs:range", rng, False))
        for r in spec.get("relations") or []:
            prop = iri(r.get("id"))
            if prop:
                triples.append((prop, "rdf:type", "owl:ObjectProperty", False))
                for key, pred in (("domain", "rdfs:domain"), ("range", "rdfs:range")):
                    if iri(r.get(key)):
                        triples.append((prop, pred, iri(r.get(key)), False))  # type: ignore[arg-type]
    std = {"rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#", "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
           "owl": "http://www.w3.org/2002/07/owl#"}
    if fmt == "jsonld":
        nodes: dict[str, dict[str, Any]] = {}
        for s, p, o, lit in triples:
            node = nodes.setdefault(s, {"@id": s})
            if p == "rdf:type":
                node.setdefault("@type", []).append(o)
            elif lit:
                text, _, lang = o.rpartition("@")
                node.setdefault(p, []).append({"@value": text, "@language": lang})
            else:
                node.setdefault(p, []).append({"@id": o})
        return json.dumps({"@context": {**std, **prefixes}, "@graph": list(nodes.values())}, indent=2, ensure_ascii=False) + "\n"
    lines = [f"@prefix {k}: <{v}> ." for k, v in {**std, **prefixes}.items()] + [""]
    for s, p, o, lit in triples:
        if lit:
            text, _, lang = o.rpartition("@")
            obj = json.dumps(text, ensure_ascii=False) + f"@{lang}"
        else:
            obj = o if o.split(":", 1)[0] in std and "://" not in o else f"<{o}>"
        lines.append(f"<{s}> {p} {obj} .")
    return "\n".join(lines) + "\n"
