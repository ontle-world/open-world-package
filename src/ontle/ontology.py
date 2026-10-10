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
from .values import WHITESPACE, dig, normalize_rel_path
from .yamlio import dump_yaml, load_yaml

ONTOLOGY_PROFILES = ["vocabulary", "schema", "constrained", "mapped"]
FORMATS = {"owp-yaml", "turtle", "jsonld", "rdf-xml", "owl-xml", "ntriples", "linkml", "sssom-tsv"}
ROLES = {"schema", "shapes", "mappings", "labels"}
TERM_TYPES = {"class", "property", "individual", "datatype", "concept"}
TERM_STATUSES = ("candidate", "stable", "deprecated")  # experimental (Appendix C.1); absent means stable
PREFIX_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*\Z")
IRI_RE = re.compile(rf"^[A-Za-z][A-Za-z0-9+.-]*:[^{WHITESPACE}]+\Z")
CURIE_RE = re.compile(rf"^([A-Za-z][A-Za-z0-9_-]*):([^{WHITESPACE}/][^{WHITESPACE}]*)\Z")

def inside_package(root: Path, rel: Any) -> bool:
    """rel is a package-relative path (relative POSIX, no leading './') of an existing file inside the package root."""
    if not isinstance(rel, str) or not rel or rel.startswith("./"):
        return False
    norm = normalize_rel_path(rel)
    if norm is None:
        return False
    target = (root / norm).resolve()
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
    if match and isinstance(prefixes.get(match.group(1)), str):
        return prefixes[match.group(1)] + match.group(2)
    if "://" in curie or curie.startswith("urn:"):
        return curie
    return None


def _profile_curies(doc: dict[str, Any]) -> list[tuple[str, str, str]]:
    """(where, value, term type) for every CURIE a SemanticProfile defines or uses. Term type is '' for uses."""
    out: list[tuple[str, str, str]] = []
    spec = doc.get("spec") if isinstance(doc.get("spec"), dict) else {}
    as_list = lambda v: v if isinstance(v, list) else []
    for i, t in enumerate(as_list(spec.get("types"))):
        if not isinstance(t, dict):
            continue
        out.append((f"spec.types[{i}].id", t.get("id"), "class"))
        parent = t.get("subClassOf")
        for parent in parent if isinstance(parent, list) else [parent] if parent not in (None, False, 0, "") else []:
            out.append((f"spec.types[{i}].subClassOf", parent, ""))
        for j, p in enumerate(as_list(t.get("properties"))):
            if isinstance(p, dict):
                out.append((f"spec.types[{i}].properties[{j}].id", p.get("id"), "property"))
                if isinstance(p.get("range"), str) and ":" in p["range"]:
                    out.append((f"spec.types[{i}].properties[{j}].range", p["range"], ""))
    for i, r in enumerate(as_list(spec.get("relations"))):
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
        if not (isinstance(fmt, str) and fmt in FORMATS):
            errors.append(f"ontology.format: spec.ontology.entrypoints[{i}].format {fmt!r} must be one of {sorted(FORMATS)}")
        if not (isinstance(role, str) and role in ROLES):
            errors.append(f"ontology.entrypoint: spec.ontology.entrypoints[{i}].role {role!r} must be one of {sorted(ROLES)}")
        if fmt == "owp-yaml":
            doc = _load(root / path)
            if not isinstance(doc, dict) or doc.get("kind") != "SemanticProfile":
                errors.append(f"ontology.parse: {path} (format owp-yaml) must be a SemanticProfile document")
                continue
            errors.extend(structure_errors(doc, SEMANTIC_PROFILE, path, declared))
            for where, value, _ in _profile_curies(doc):
                declared_prefix = isinstance(value, str) and (m := CURIE_RE.match(value)) is not None and m.group(1) in prefixes  # an invalid one is ontology.prefix
                if not isinstance(value, str) or (expand(value, prefixes) is None and not declared_prefix):
                    errors.append(f"ontology.prefix-undeclared: {path}: {where} {value!r} uses a prefix that spec.ontology.prefixes does not declare")
    term_index = ontology.get("termIndex")
    if term_index is not None:
        doc = _load(root / term_index) if inside_package(root, term_index) else None
        if not isinstance(doc, dict) or doc.get("kind") != "OntologyTermIndex":
            errors.append(f"ontology.term-index: spec.ontology.termIndex {term_index!r} must be an existing OntologyTermIndex document")
        else:
            errors.extend(structure_errors(doc, TERM_INDEX, term_index, declared))
            listed = doc["spec"].get("terms") if isinstance(doc.get("spec"), dict) else None
            for j, term in enumerate(listed if isinstance(listed, list) else []):
                if not (isinstance(term, dict) and isinstance(term.get("iri"), str) and IRI_RE.match(term["iri"])
                        and isinstance(term.get("type"), str) and term["type"] in TERM_TYPES):
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
    warnings.extend(lifecycle_warnings(root, {"spec": spec}))
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
    ontology = manifest.get("spec", {}).get("ontology") if isinstance(manifest.get("spec"), dict) else None
    ontology = ontology if isinstance(ontology, dict) else {}
    prefixes = {k: v for k, v in ontology["prefixes"].items() if isinstance(v, str)} if isinstance(ontology.get("prefixes"), dict) else {}
    out: set[str] = set()
    for entry in ontology.get("entrypoints") if isinstance(ontology.get("entrypoints"), list) else []:
        if (isinstance(entry, dict) and entry.get("format") == "owp-yaml" and entry.get("role") == "schema"
                and inside_package(root, entry.get("path"))):  # never read outside the package
            doc = _load(root / entry["path"])
            if isinstance(doc, dict):
                for _, value, term_type in _profile_curies(doc):
                    if term_type and isinstance(value, str) and expand(value, prefixes):
                        out.add(expand(value, prefixes))  # type: ignore[arg-type]
    index = ontology.get("termIndex")
    if inside_package(root, index):
        doc = _load(root / index)
        listed = doc["spec"].get("terms") if isinstance(doc, dict) and isinstance(doc.get("spec"), dict) else None
        for term in listed if isinstance(listed, list) else []:
            if isinstance(term, dict) and isinstance(term.get("iri"), str):
                out.add(term["iri"])
    return prefixes, out


def _defining_entries(doc: Any) -> list[tuple[str, dict[str, Any]]]:
    """(where, entry) for every type, property, and relation a SemanticProfile defines."""
    spec = doc.get("spec") if isinstance(doc, dict) and isinstance(doc.get("spec"), dict) else {}
    out: list[tuple[str, dict[str, Any]]] = []
    for i, t in enumerate(_list(spec.get("types"))):
        if isinstance(t, dict):
            out.append((f"spec.types[{i}]", t))
            out += [(f"spec.types[{i}].properties[{j}]", p) for j, p in enumerate(_list(t.get("properties"))) if isinstance(p, dict)]
    out += [(f"spec.relations[{i}]", r) for i, r in enumerate(_list(spec.get("relations"))) if isinstance(r, dict)]
    return out


def _lifecycle_docs(root: Path, ontology: dict[str, Any]) -> list[tuple[str, str, list[tuple[str, dict[str, Any]]]]]:
    """(file, format, [(where, entry)]) for the owp-yaml entrypoints and the term index: where `status` and `replacedBy` live."""
    out = []
    for entry in _list(ontology.get("entrypoints")):
        if isinstance(entry, dict) and entry.get("format") == "owp-yaml" and inside_package(root, entry.get("path")):
            out.append((entry["path"], "owp-yaml", _defining_entries(_load(root / entry["path"]))))
    index = ontology.get("termIndex")
    if inside_package(root, index):
        listed = dig(_load(root / index), "spec", "terms")
        out.append((index, "term-index", [(f"spec.terms[{j}]", t) for j, t in enumerate(_list(listed)) if isinstance(t, dict)]))
    return out


def _removed_docs(root: Path, ontology: dict[str, Any]) -> list[tuple[str, str, list[tuple[str, Any]]]]:
    """(file, format, [(where, entry)]) for the `removed` lists (tombstones) of the owp-yaml entrypoints and the term index."""
    out = []
    for entry in _list(ontology.get("entrypoints")):
        if isinstance(entry, dict) and entry.get("format") == "owp-yaml" and inside_package(root, entry.get("path")):
            listed = dig(_load(root / entry["path"]), "spec", "removed")
            if listed is not None:
                out.append((entry["path"], "owp-yaml", [(f"spec.removed[{i}]", e) for i, e in enumerate(_list(listed))] if isinstance(listed, list) else [("spec.removed", listed)]))
    index = ontology.get("termIndex")
    if inside_package(root, index):
        listed = dig(_load(root / index), "spec", "removed")
        if listed is not None:
            out.append((index, "term-index", [(f"spec.removed[{i}]", e) for i, e in enumerate(_list(listed))] if isinstance(listed, list) else [("spec.removed", listed)]))
    return out


def _replaced_by_values(value: Any) -> list[Any] | None:
    """The identifiers of a `replacedBy`: a non-empty string or a non-empty list of them; None when malformed."""
    values = value if isinstance(value, list) else [value]
    return values if values and all(isinstance(v, str) and v.strip(WHITESPACE) for v in values) else None


def _identifier(fmt: str, value: Any, prefixes: dict[str, Any]) -> str | None:
    """An identifier as an IRI: a term index lists absolute IRIs; owp-yaml uses CURIEs or absolute IRIs."""
    if not isinstance(value, str):
        return None
    return (value if IRI_RE.match(value) else None) if fmt == "term-index" else expand(value, prefixes)


def replaced_by_refs(root: Path, manifest: dict[str, Any]) -> list[tuple[str, str, str, str]]:
    """(file, where, value, IRI) for every well-formed `replacedBy` identifier of an OntologyPackage (Appendix C.1)."""
    ontology = _ontology(manifest)
    prefixes = ontology.get("prefixes") if isinstance(ontology.get("prefixes"), dict) else {}
    out = []
    for file, fmt, entries in _lifecycle_docs(root, ontology) + _removed_docs(root, ontology):
        for where, entry in entries:
            if not isinstance(entry, dict):
                continue
            for value in _replaced_by_values(entry.get("replacedBy")) or [] if "replacedBy" in entry else []:
                iri = _identifier(fmt, value, prefixes)
                if iri:
                    out.append((file, f"{where}.replacedBy", value, iri))
    return out


def term_statuses(root: Path, manifest: dict[str, Any], index: bool = True) -> dict[str, tuple[str, list[str]]]:
    """Term IRI -> (status, replacedBy IRIs) for the terms an OntologyPackage marks candidate or deprecated
    (Appendix C.1), in its owp-yaml entrypoints and, with `index`, its term index. A term marked in several places
    takes the strongest mark: deprecated, then candidate."""
    ontology = _ontology(manifest)
    prefixes = ontology.get("prefixes") if isinstance(ontology.get("prefixes"), dict) else {}
    out: dict[str, tuple[str, list[str]]] = {}
    for _, fmt, entries in _lifecycle_docs(root, ontology):
        if fmt == "term-index" and not index:
            continue
        for _, entry in entries:
            status, iri = entry.get("status"), _identifier(fmt, entry.get("iri" if fmt == "term-index" else "id"), prefixes)
            if iri is None or status not in ("candidate", "deprecated"):
                continue
            replaced = []
            for value in _replaced_by_values(entry.get("replacedBy")) or [] if status == "deprecated" else []:
                full = _identifier(fmt, value, prefixes)
                if full:
                    replaced.append(full)
            old_status, old_replaced = out.get(iri, ("stable", []))
            if status == "deprecated" or old_status != "deprecated":
                out[iri] = (status, list(dict.fromkeys(old_replaced + replaced)) if old_status == status else replaced)
    return out


def removed_terms(root: Path, manifest: dict[str, Any]) -> dict[str, tuple[list[str], str | None]]:
    """Term IRI -> (replacedBy IRIs, removedIn) for the terms an OntologyPackage lists as removed (Appendix C.1):
    tombstones that keep the replacement known once the term itself is gone."""
    ontology = _ontology(manifest)
    prefixes = ontology.get("prefixes") if isinstance(ontology.get("prefixes"), dict) else {}
    out: dict[str, tuple[list[str], str | None]] = {}
    for _, fmt, entries in _removed_docs(root, ontology):
        for _, entry in entries:
            iri = _identifier(fmt, entry.get("iri" if fmt == "term-index" else "id"), prefixes) if isinstance(entry, dict) else None
            if iri is None:
                continue
            replaced = [r for r in (_identifier(fmt, v, prefixes) for v in _replaced_by_values(entry.get("replacedBy")) or []) if r]
            old_replaced, old_version = out.get(iri, ([], None))
            version = entry.get("removedIn") if isinstance(entry.get("removedIn"), str) else None
            out[iri] = (list(dict.fromkeys(old_replaced + replaced)), old_version or version)
    return out


def compact(iri: str, prefixes: dict[str, Any]) -> str:
    """An IRI as a CURIE with the longest matching prefix, or the IRI itself when none matches."""
    best = None
    for name, ns in prefixes.items():
        if isinstance(ns, str) and ns and iri.startswith(ns) and CURIE_RE.match(f"{name}:{iri[len(ns):]}"):
            if best is None or len(ns) > len(best[1]):
                best = (name, ns)
    return f"{best[0]}:{iri[len(best[1]):]}" if best else iri


def lifecycle_warnings(root: Path, manifest: dict[str, Any]) -> list[str]:
    """Appendix C.1 (experimental, warnings only): `status` and `replacedBy` of the terms an ontology defines."""
    ontology = _ontology(manifest)
    prefixes = ontology.get("prefixes") if isinstance(ontology.get("prefixes"), dict) else {}
    warnings: list[str] = []
    for file, fmt, entries in _lifecycle_docs(root, ontology):
        for where, entry in entries:
            if "status" in entry and entry["status"] not in TERM_STATUSES:
                warnings.append(f"experimental.value: {file}: {where}.status {entry['status']!r} must be one of {', '.join(TERM_STATUSES)}")
            if "replacedBy" not in entry:
                continue
            values = _replaced_by_values(entry["replacedBy"])
            if values is None:
                warnings.append(f"experimental.field: {file}: {where}.replacedBy must be an identifier or a non-empty list of identifiers")
                continue
            if entry.get("status") != "deprecated":
                warnings.append(f"experimental.field: {file}: {where}.replacedBy is only for a term with status deprecated")
            for value in values:
                if _identifier(fmt, value, prefixes) is None:
                    need = "an absolute IRI" if fmt == "term-index" else "a CURIE with a declared prefix or an absolute IRI"
                    warnings.append(f"experimental.field: {file}: {where}.replacedBy {value!r} must be {need}")
    defined = terms(root, manifest)[1]
    for file, fmt, entries in _removed_docs(root, ontology):
        if entries and entries[0][0] == "spec.removed":
            warnings.append(f"experimental.field: {file}: spec.removed must be a list")
            continue
        key = "iri" if fmt == "term-index" else "id"
        for where, entry in entries:
            iri = _identifier(fmt, entry.get(key), prefixes) if isinstance(entry, dict) else None
            if iri is None:
                need = "an absolute IRI" if fmt == "term-index" else "a CURIE with a declared prefix or an absolute IRI"
                warnings.append(f"experimental.field: {file}: {where} needs {key}, {need}")
                continue
            if iri in defined:
                warnings.append(f"experimental.field: {file}: {where} {entry[key]!r} is listed as removed, but the ontology still defines it")
            if "removedIn" in entry and not isinstance(entry["removedIn"], str):
                warnings.append(f"experimental.field: {file}: {where}.removedIn must be a version string")
            if "replacedBy" in entry:
                values = _replaced_by_values(entry["replacedBy"])
                if values is None:
                    warnings.append(f"experimental.field: {file}: {where}.replacedBy must be an identifier or a non-empty list of identifiers")
                for value in values or []:
                    if _identifier(fmt, value, prefixes) is None:
                        need = "an absolute IRI" if fmt == "term-index" else "a CURIE with a declared prefix or an absolute IRI"
                        warnings.append(f"experimental.field: {file}: {where}.replacedBy {value!r} must be {need}")
    namespace = ontology.get("iri")
    if isinstance(namespace, str) and namespace:
        for file, where, value, iri in replaced_by_refs(root, manifest):
            if iri.startswith(namespace) and iri not in defined:
                warnings.append(f"experimental.reference: {file}: {where} {value!r} ({iri}) is not a term this ontology defines")
    return warnings


def schema_model(root: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    """What an OntologyPackage's owp-yaml schema entrypoints declare, by expanded IRI, for binding checks (spec 14):
    classes, their parents (subClassOf), the classes each property is declared on (types[].properties and relations'
    domain), each property's range, and the values of each enum type. RDF entrypoints are not read (spec 14)."""
    ontology = _ontology(manifest)
    prefixes = {k: v for k, v in ontology["prefixes"].items() if isinstance(v, str)} if isinstance(ontology.get("prefixes"), dict) else {}
    model: dict[str, Any] = {"classes": set(), "parents": {}, "declaredOn": {}, "range": {}, "enums": {}}

    def iri(value: Any) -> str | None:
        return expand(value, prefixes) if isinstance(value, str) else None

    def declare(prop: str, cls: str | None, rng: Any) -> None:
        model["declaredOn"].setdefault(prop, set())
        if cls:
            model["declaredOn"][prop].add(cls)
        r = iri(rng)
        if r and prop not in model["range"]:
            model["range"][prop] = r

    for entry in _list(ontology.get("entrypoints")):
        if not (isinstance(entry, dict) and entry.get("format") == "owp-yaml" and entry.get("role") == "schema"
                and inside_package(root, entry.get("path"))):
            continue
        doc = _load(root / entry["path"])
        spec = doc.get("spec") if isinstance(doc, dict) and isinstance(doc.get("spec"), dict) else {}
        for t in _list(spec.get("types")):
            cls = iri(t.get("id")) if isinstance(t, dict) else None
            if not cls:
                continue
            if isinstance(t.get("enum"), list):
                model["enums"][cls] = {v for v in t["enum"] if isinstance(v, str)}
                continue
            model["classes"].add(cls)
            parents = t.get("subClassOf")
            parents = parents if isinstance(parents, list) else [parents]
            model["parents"].setdefault(cls, set()).update(p for p in (iri(x) for x in parents) if p)
            for p in _list(t.get("properties")):
                prop = iri(p.get("id")) if isinstance(p, dict) else None
                if prop:
                    declare(prop, cls, p.get("range"))
        for r in _list(spec.get("relations")):
            prop = iri(r.get("id")) if isinstance(r, dict) else None
            if prop:
                declare(prop, iri(r.get("domain")), r.get("range"))
    return model


def term_catalog(root: Path, manifest: dict[str, Any]) -> list[dict[str, str]]:
    """Terms an OntologyPackage defines, for search: iri, curie, type, and label (owp-yaml labels: every language,
    joined). From owp-yaml schema entrypoints and the term index. Tooling, not a conformance rule."""
    ontology = manifest.get("spec", {}).get("ontology") if isinstance(manifest.get("spec"), dict) else None
    ontology = ontology if isinstance(ontology, dict) else {}
    prefixes = {k: v for k, v in ontology["prefixes"].items() if isinstance(v, str)} if isinstance(ontology.get("prefixes"), dict) else {}

    def label_text(label: Any) -> str:
        if isinstance(label, dict):
            return " / ".join(str(v) for v in label.values() if isinstance(v, str))
        return label if isinstance(label, str) else ""

    def curie_of(iri: str) -> str:
        return next((f"{p}:{iri[len(ns):]}" for p, ns in prefixes.items() if iri.startswith(ns)), "")

    found: dict[str, dict[str, str]] = {}
    for entry in ontology.get("entrypoints") if isinstance(ontology.get("entrypoints"), list) else []:
        if not (isinstance(entry, dict) and entry.get("format") == "owp-yaml" and entry.get("role") == "schema"
                and inside_package(root, entry.get("path"))):
            continue
        doc = _load(root / entry["path"])
        spec = doc.get("spec") if isinstance(doc, dict) and isinstance(doc.get("spec"), dict) else {}
        items = [(t, "class") for t in spec.get("types") or [] if isinstance(t, dict)]
        items += [(p, "property") for t in spec.get("types") or [] if isinstance(t, dict) for p in t.get("properties") or [] if isinstance(p, dict)]
        items += [(r, "property") for r in spec.get("relations") or [] if isinstance(r, dict)]
        for item, kind in items:
            iri = expand(item.get("id"), prefixes) if isinstance(item.get("id"), str) else None
            if iri and iri not in found:
                found[iri] = {"iri": iri, "curie": item["id"], "type": kind, "label": label_text(item.get("label"))}
    index = ontology.get("termIndex")
    if inside_package(root, index):
        doc = _load(root / index)
        for term in (doc.get("spec") or {}).get("terms") or [] if isinstance(doc, dict) else []:
            if isinstance(term, dict) and isinstance(term.get("iri"), str) and term["iri"] not in found:
                found[term["iri"]] = {"iri": term["iri"], "curie": curie_of(term["iri"]), "type": str(term.get("type") or ""),
                                      "label": label_text(term.get("label"))}
    return [found[k] for k in sorted(found)]


# --- tooling (T): index generation and export -------------------------------

RDF_NS = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
RDFS_NS = "http://www.w3.org/2000/01/rdf-schema#"
DCTERMS_NS = "http://purl.org/dc/terms/"
VS_NS = "http://www.w3.org/2003/06/sw-vocab-status/ns#"  # term_status "testing" marks a candidate term
RDF_FORMATS = {"turtle": "turtle", "jsonld": "json-ld", "rdf-xml": "xml", "ntriples": "nt"}  # OWL/XML (owl-xml) needs an OWL API tool


def _ontology(manifest: Any) -> dict[str, Any]:
    ontology = dig(manifest, "spec", "ontology")
    return ontology if isinstance(ontology, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def build_term_index(root: Path, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    """Terms from every schema entrypoint, with the lifecycle status of candidate and deprecated terms (Appendix C.1).
    RDF formats need the optional rdflib dependency (pip install ontle[rdf])."""
    ontology = _ontology(manifest)
    prefixes = ontology.get("prefixes") if isinstance(ontology.get("prefixes"), dict) else {}
    found: dict[str, str] = {}
    statuses = term_statuses(root, manifest, index=False)
    for entry in _list(ontology.get("entrypoints")):
        if not isinstance(entry, dict) or entry.get("role") != "schema":
            continue
        path = root / str(entry.get("path"))
        fmt = entry.get("format")
        if not isinstance(fmt, str):
            fmt = repr(fmt)
        if fmt == "owp-yaml":
            doc = _load(path) or {}
            for _, value, term_type in _profile_curies(doc):
                if term_type and isinstance(value, str) and expand(value, prefixes):
                    found.setdefault(expand(value, prefixes), term_type)  # type: ignore[arg-type]
        elif fmt in RDF_FORMATS:
            # Only the terms this ontology defines: those in its own namespace (an RDF file also declares terms
            # it borrows, such as rdfs:label or Dublin Core annotations).
            namespace = ontology.get("iri") if isinstance(ontology.get("iri"), str) else ""
            types, marked = _rdf_terms(path, RDF_FORMATS[fmt])
            found.update({iri: t for iri, t in types.items() if iri not in found and iri.startswith(namespace)})
            for iri, (status, replaced) in marked.items():
                if statuses.get(iri, ("stable",))[0] != "deprecated":
                    statuses[iri] = (status, replaced)
        else:
            from .core import OWPError
            raise OWPError(f"cannot build a term index from format {fmt!r}; write spec.ontology.termIndex by hand")
    out: list[dict[str, Any]] = []
    for iri in sorted(found):
        term: dict[str, Any] = {"iri": iri, "type": found[iri]}
        status, replaced = statuses.get(iri, ("stable", []))
        if status != "stable":
            term["status"] = status
        if replaced:
            term["replacedBy"] = replaced[0] if len(replaced) == 1 else replaced
        out.append(term)
    return out


def build_removed_index(root: Path, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    """The tombstones (Appendix C.1) for a term index: the owp-yaml `removed` lists, and those the current index
    already lists, so that regenerating the index does not lose tombstones written by hand for RDF schemas."""
    out: dict[str, dict[str, Any]] = {}
    for iri, (replaced, version) in removed_terms(root, manifest).items():
        entry: dict[str, Any] = {"iri": iri}
        if replaced:
            entry["replacedBy"] = replaced[0] if len(replaced) == 1 else replaced
        if version:
            entry["removedIn"] = version
        out[iri] = entry
    return [out[iri] for iri in sorted(out)]


def _rdf_terms(path: Path, rdf_format: str) -> tuple[dict[str, str], dict[str, tuple[str, list[str]]]]:
    """(term IRI -> type, term IRI -> (status, replacedBy IRIs)) of an RDF schema. A term is deprecated with
    owl:deprecated true or vs:term_status "archaic", and a candidate with vs:term_status "testing" or "unstable"."""
    try:
        import rdflib
        from rdflib.namespace import OWL, RDF, RDFS, SKOS
    except ImportError as exc:
        from .core import OWPError
        raise OWPError("RDF entrypoints need rdflib: pip install 'ontle[rdf]'") from exc
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
             RDFS.Datatype: "datatype", SKOS.Concept: "concept", SKOS.ConceptScheme: "concept"}
    out: dict[str, str] = {}
    for subject, rdf_type in graph.subject_objects(RDF.type):
        if isinstance(subject, rdflib.URIRef) and rdf_type in types:
            out.setdefault(str(subject), types[rdf_type])
    # Instances of a class the file defines are individuals too, whether or not they are typed owl:NamedIndividual.
    for subject, rdf_type in graph.subject_objects(RDF.type):
        if isinstance(subject, rdflib.URIRef) and out.get(str(rdf_type)) == "class":
            out.setdefault(str(subject), "individual")
    statuses: dict[str, tuple[str, list[str]]] = {}
    for subject, value in graph.subject_objects(rdflib.URIRef(VS_NS + "term_status")):
        if isinstance(subject, rdflib.URIRef) and str(value) in ("testing", "unstable", "archaic"):
            statuses[str(subject)] = ("deprecated" if str(value) == "archaic" else "candidate", [])
    for subject, value in graph.subject_objects(OWL.deprecated):
        if isinstance(subject, rdflib.URIRef) and str(value).lower() == "true":
            statuses[str(subject)] = ("deprecated", [])
    for iri, (status, _) in list(statuses.items()):
        if status == "deprecated":
            replaced = graph.objects(rdflib.URIRef(iri), rdflib.URIRef(DCTERMS_NS + "isReplacedBy"))
            statuses[iri] = (status, sorted(str(r) for r in replaced if isinstance(r, rdflib.URIRef)))
    return out, statuses


def write_term_index(root: Path, manifest_path: Path) -> Path:
    manifest = load_yaml(manifest_path.read_text(encoding="utf-8"))
    ontology = dig(manifest, "spec", "ontology")
    if not isinstance(ontology, dict):
        from .core import OWPError
        raise OWPError("ontle ontology index needs an OntologyPackage manifest with a spec.ontology mapping")
    rel = ontology.get("termIndex") or "semantics/terms.yaml"
    if not isinstance(rel, str) or normalize_rel_path(rel) is None or rel.startswith("./"):
        from .core import OWPError
        raise OWPError(f"spec.ontology.termIndex {rel!r} must be a package-relative path")
    target = root / rel
    removed = build_removed_index(root, manifest)  # before writing: the current index's tombstones are kept
    target.parent.mkdir(parents=True, exist_ok=True)
    md = manifest.get("metadata") if isinstance(manifest.get("metadata"), dict) else {}
    target.write_text(dump_yaml({
        "apiVersion": "openworld/v1alpha1",
        "kind": "OntologyTermIndex",
        "metadata": {"name": f"{md.get('name')}-terms", "description": "Generated by `ontle ontology index`; do not edit by hand."},
        "spec": {"terms": build_term_index(root, manifest), **({"removed": removed} if removed else {})},
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
    ontology = _ontology(manifest)
    prefixes = dict(ontology["prefixes"]) if isinstance(ontology.get("prefixes"), dict) else {}
    triples: list[tuple[str, str, str, Any]] = []  # subject, predicate, object, literal kind: False (IRI), True (text@lang), "boolean", "string"

    def iri(value: Any) -> str | None:
        return expand(value, prefixes) if isinstance(value, str) else None

    specs = []
    for entry in ontology.get("entrypoints") or []:
        if isinstance(entry, dict) and entry.get("format") == "owp-yaml" and entry.get("role") == "schema" and inside_package(root, entry.get("path")):
            doc = _load(root / entry["path"])
            specs.append(doc.get("spec") if isinstance(doc, dict) and isinstance(doc.get("spec"), dict) else {})
    enums: dict[str, list[Any]] = {}
    for spec in specs:
        for t in _list(spec.get("types")):
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
        for t in _list(spec.get("types")):
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
            for p in _list(t.get("properties")):
                if isinstance(p, dict) and iri(p.get("id")):
                    declare(iri(p["id"]), cls, iri(p.get("range")))  # type: ignore[arg-type]
        for r in _list(spec.get("relations")):
            if isinstance(r, dict) and iri(r.get("id")):
                declare(iri(r["id"]), iri(r.get("domain")), iri(r.get("range")))  # type: ignore[arg-type]
                props[iri(r["id"])].setdefault("relation", set()).add("yes")  # type: ignore[index]
    # Classes used but defined elsewhere (a dependency ontology) are declared, as OWL 2 DL requires.
    defined = {s for s, p, o, _ in triples if p == "rdf:type"}
    used = {o for s, p, o, lit in triples if p == "rdfs:subClassOf" and not lit}
    used |= {r for info in props.values() for key in ("domains", "ranges") for r in info[key] if r not in enums and not r.startswith(literal_ranges)}
    for cls in sorted(used - defined):
        triples.append((cls, "rdf:type", "owl:Class", False))
    # Appendix C.1 (experimental): lifecycle status of the terms defined here.
    for term, (status, replaced) in sorted(term_statuses(root, manifest).items()):
        if term not in defined and term not in props:
            continue
        if status == "deprecated":
            triples.append((term, "owl:deprecated", "true", "boolean"))
            triples += [(term, f"<{DCTERMS_NS}isReplacedBy>", r, False) for r in replaced]
        else:
            triples.append((term, f"<{VS_NS}term_status>", "testing", "string"))
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
        if lit is True:
            text, _, lang = o.rpartition("@")
            obj = json.dumps(text, ensure_ascii=False) + f"@{lang}"
        elif lit:
            obj = o if lit == "boolean" else json.dumps(o, ensure_ascii=False)
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
        p = p.strip("<>")  # a full IRI as the key
        if p == "rdf:type":
            node.setdefault("@type", []).append(o)
        elif lit is True:
            text, _, lang = o.rpartition("@")
            node.setdefault(p, []).append({"@value": text, "@language": lang})
        elif lit:
            node.setdefault(p, []).append({"@value": o == "true" if lit == "boolean" else o})
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
