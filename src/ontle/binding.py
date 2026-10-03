"""SemanticBinding: World names, EWS fields, observation types, and actions bound to ontology terms (spec section 14)."""
from __future__ import annotations

import re
from urllib.parse import quote
from typing import Any

from .ontology import CURIE_RE, expand
from .structure import OPEN, VALUE, closed, structure_errors

FIELD_BINDING = closed({"class": VALUE, "path": VALUE, "unit": VALUE, "values": closed({"scheme": VALUE, "base": VALUE, "map": OPEN})})

SEMANTIC_BINDING = closed({
    "apiVersion": VALUE,
    "kind": VALUE,
    "metadata": closed({"name": VALUE, "version": VALUE, "title": VALUE, "description": VALUE}),
    "spec": closed({"terms": OPEN, "fields": OPEN, "observationTypes": OPEN, "actions": OPEN, "subjects": OPEN, "semanticIds": OPEN}),
}, extensions=False)


def _is_curie(value: Any) -> bool:
    return isinstance(value, str) and bool(CURIE_RE.match(value))


def binding_curies(doc: dict[str, Any]) -> list[tuple[str, str]]:
    """(where, CURIE) for every ontology reference in a SemanticBinding."""
    spec = doc.get("spec") if isinstance(doc.get("spec"), dict) else {}
    out: list[tuple[str, str]] = []
    for section in ("terms", "observationTypes", "actions"):
        for key, value in (spec.get(section) or {}).items() if isinstance(spec.get(section), dict) else []:
            out.append((f"spec.{section}.{key}", value))
    for field, value in (spec.get("fields") or {}).items() if isinstance(spec.get("fields"), dict) else []:
        if isinstance(value, dict):
            out.append((f"spec.fields.{field}.class", value.get("class")))
            for i, step in enumerate(value.get("path") or [] if isinstance(value.get("path"), list) else []):
                out.append((f"spec.fields.{field}.path[{i}]", step))
            if "unit" in value:  # a unit term, such as a QUDT unit, of a dependency ontology (section 14)
                out.append((f"spec.fields.{field}.unit", value["unit"]))
            values = value.get("values") if isinstance(value.get("values"), dict) else {}
            if "scheme" in values:  # the concept scheme of coded values
                out.append((f"spec.fields.{field}.values.scheme", values["scheme"]))
            for code, concept in (values.get("map") or {}).items() if isinstance(values.get("map"), dict) else []:
                out.append((f"spec.fields.{field}.values.map.{code}", concept))
    return out


def binding_issues(spec: dict[str, Any], local_kinds: dict[str, str], docs: dict[str, dict[str, Any]],
                   ews_fields: dict[str, list[str] | None], view_includes: set[str], declared: set[str]) -> tuple[list[str], list[str]]:
    """Single-package checks for every local SemanticBinding and spec.world.semanticBinding."""
    errors: list[str] = []
    warnings: list[str] = []
    world = spec.get("world") if isinstance(spec.get("world"), dict) else {}
    named = world.get("semanticBinding")
    if named is not None and local_kinds.get(named) != "SemanticBinding":
        errors.append(f"binding.asset: spec.world.semanticBinding {named!r} must be a listed local SemanticBinding asset")
    schema_fields = {f for fields in ews_fields.values() for f in fields or []}
    boundary = world.get("boundary") if isinstance(world.get("boundary"), dict) else {}
    scope = {x for x in boundary.get("included") or [] if isinstance(x, str)} | view_includes
    for rel, kind in sorted(local_kinds.items()):
        if kind != "SemanticBinding" or rel not in docs:
            continue
        doc = docs[rel]
        errors.extend(structure_errors(doc, SEMANTIC_BINDING, rel, declared))
        bspec = doc.get("spec") if isinstance(doc.get("spec"), dict) else {}
        for section in ("terms", "fields", "observationTypes", "actions"):
            if section in bspec and not isinstance(bspec[section], dict):
                errors.append(f"binding.curie: {rel}: spec.{section} must be a mapping")
        for field, value in (bspec.get("fields") or {}).items() if isinstance(bspec.get("fields"), dict) else []:
            if not isinstance(value, dict):
                errors.append(f"binding.curie: {rel}: spec.fields.{field} must be a mapping with class and path")
                continue
            errors.extend(structure_errors(value, FIELD_BINDING, f"{rel}: spec.fields.{field}", declared))
            if "path" in value and not isinstance(value["path"], list):
                errors.append(f"binding.curie: {rel}: spec.fields.{field}.path must be a list of CURIEs")
            if field not in schema_fields:
                errors.append(f"binding.field-unknown: {rel}: spec.fields.{field} is not an EWS field of any local State Compiler")
        for where, value in binding_curies(doc):
            if not _is_curie(value):
                errors.append(f"binding.curie: {rel}: {where} {value!r} must be a CURIE <prefix>:<local name>")
        errors.extend(subjects_errors(rel, bspec))
        errors.extend(values_errors(rel, bspec))
        errors.extend(semantic_ids_errors(rel, bspec))
        if scope:
            for name in (bspec.get("terms") or {}) if isinstance(bspec.get("terms"), dict) else []:
                if name not in scope:
                    warnings.append(f"binding.term-unscoped: {rel}: spec.terms.{name} is neither in spec.world.boundary.included nor in any local View's projection.include")
    return errors, warnings


IRI_SAFE_CODE = re.compile(r"^[A-Za-z0-9._~-]+\Z")  # a code that can be appended to `base` as is
IRDI_RE = re.compile(r"^[0-9]{4}[-/][^#\s]+#(?:[0-9A-Z]{2}-)?[0-9A-Z]{3,}#[0-9]{1,3}\Z")  # ISO 29002-5, e.g. 0173-1#02-AAO677#002


def _absolute_iri(value: Any) -> bool:
    return isinstance(value, str) and " " not in value and ("://" in value or value.startswith("urn:"))


def values_errors(rel: str, bspec: dict[str, Any]) -> list[str]:
    """Section 14: a field's coded values tied to concepts: {scheme?, base?, map?} with base or map."""
    errors: list[str] = []
    for field, value in (bspec.get("fields") or {}).items() if isinstance(bspec.get("fields"), dict) else []:
        if not isinstance(value, dict) or "values" not in value:
            continue
        v = value["values"]
        where = f"binding.values: {rel}: spec.fields.{field}.values"
        if not isinstance(v, dict) or not ({"base", "map"} & set(v)):
            errors.append(f"{where} must be a mapping with base, map, or both (and optionally scheme)")
            continue
        if "base" in v and not _absolute_iri(v["base"]):
            errors.append(f"{where}.base must be an absolute IRI prefix")
        if "map" in v and not (isinstance(v["map"], dict) and v["map"] and all(isinstance(k, str) and k for k in v["map"])):
            errors.append(f"{where}.map must be a non-empty mapping from code to concept CURIE")
    return errors


def semantic_ids_errors(rel: str, bspec: dict[str, Any]) -> list[str]:
    """Section 14: external dictionary identifiers (IRDIs or IRIs) attached to bound names, by section."""
    ids = bspec.get("semanticIds")
    if ids is None:
        return []
    where = f"binding.semantic-ids: {rel}: spec.semanticIds"
    if not isinstance(ids, dict):
        return [f"{where} must be a mapping of section (terms, fields, observationTypes, actions) to name to identifiers"]
    errors: list[str] = []
    for section, names in ids.items():
        if section not in ("terms", "fields", "observationTypes", "actions") or not isinstance(names, dict):
            errors.append(f"{where}.{section} must be terms, fields, observationTypes, or actions, mapping names to identifier lists")
            continue
        bound = bspec.get(section) if isinstance(bspec.get(section), dict) else {}
        for name, values in names.items():
            if name not in bound:
                errors.append(f"{where}.{section}.{name} is not bound in spec.{section}")
            if not (isinstance(values, list) and values):
                errors.append(f"{where}.{section}.{name} must be a non-empty list of IRDIs or absolute IRIs")
                continue
            for x in values:
                if not (isinstance(x, str) and (IRDI_RE.match(x) or _absolute_iri(x))):
                    errors.append(f"{where}.{section}.{name}: {x!r} is neither an IRDI (ISO 29002-5, such as 0173-1#02-AAO677#002) nor an absolute IRI")
    return errors


def value_iri(values: dict[str, Any], code: Any, prefixes: dict[str, str]) -> str | None:
    """The concept IRI of a coded value: its `map` entry, else `base` + code when the code is IRI-safe; None otherwise."""
    if isinstance(code, float) and code.is_integer():
        code = int(code)  # EWS equality treats 3 and 3.0 as one value, so they map alike
    if isinstance(code, int) and not isinstance(code, bool):
        code = str(code)  # a numeric code is looked up by its decimal text, so map: {"3": ...} covers the value 3
    if not isinstance(code, str):
        return None
    mapped = (values.get("map") or {}).get(code) if isinstance(values.get("map"), dict) else None
    if isinstance(mapped, str):
        return expand(mapped, prefixes)
    if isinstance(values.get("base"), str) and IRI_SAFE_CODE.match(code):
        return values["base"] + code
    return None


def subjects_errors(rel: str, bspec: dict[str, Any]) -> list[str]:
    """Section 14: spec.subjects maps observation types listed in observationTypes to {base: <IRI>} or {iri: true}."""
    subjects = bspec.get("subjects")
    if subjects is None:
        return []
    if not isinstance(subjects, dict):
        return [f"binding.subjects: {rel}: spec.subjects must be a mapping of observation type to {{base}} or {{iri: true}}"]
    types = bspec.get("observationTypes") if isinstance(bspec.get("observationTypes"), dict) else {}
    errors: list[str] = []
    for otype, rule in subjects.items():
        if otype not in types:
            errors.append(f"binding.subjects: {rel}: spec.subjects.{otype} is not listed in spec.observationTypes")
        ok = isinstance(rule, dict) and len(rule) == 1 and (
            (isinstance(rule.get("base"), str) and re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", rule["base"])) or rule.get("iri") is True)
        if not ok:
            errors.append(f"binding.subjects: {rel}: spec.subjects.{otype} must be {{base: <absolute IRI prefix>}} or {{iri: true}}")
    return errors


IRI_FORBIDDEN = re.compile(r'[\x00-\x20<>"{}|^`\\]')  # characters an IRI never contains (RFC 3987)


def subject_iri(rule: dict[str, Any], subject: str) -> str:
    """The IRI of a subject key under a `subjects` rule: base + the percent-encoded key, or the key itself (which must be an IRI)."""
    from .core import OWPError  # local import: core imports this module
    if rule.get("iri") is True:
        if IRI_FORBIDDEN.search(subject) or not re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", subject):
            raise OWPError(f"binding.subjects: subject {subject!r} is not an absolute IRI, but its rule is {{iri: true}}")
        return subject
    return f"{rule['base']}{quote(subject, safe='')}"


def concept_iris(field: str, values: dict[str, Any], value: Any, prefixes: dict[str, str]) -> list[str]:
    """Concept IRIs of a coded value, or of each element of a list value; refuses a code without one."""
    from .core import OWPError  # local import: core imports this module
    out = []
    for v in value if isinstance(value, list) else [value]:
        iri = value_iri(values, v, prefixes)
        if iri is None:
            raise OWPError(f"binding.values: {field}: value {v!r} has no map entry and cannot be appended to base as an IRI")
        out.append(iri)
    return out


def grounding_issues(package_identity: str, binding_docs: dict[str, dict[str, Any]],
                     ontologies: list[tuple[str, dict[str, str], set[str]]]) -> list[str]:
    """Cross-package checks: prefixes come from dependency OntologyPackages; every CURIE names a term they define."""
    errors: list[str] = []
    prefixes: dict[str, str] = {}
    owners: dict[str, str] = {}
    for ref, ont_prefixes, _ in ontologies:
        for name, iri in ont_prefixes.items():
            if name in prefixes and prefixes[name] != iri:
                errors.append(f"grounding.prefix-conflict: {package_identity}: prefix {name!r} is {prefixes[name]} in {owners[name]} and {iri} in {ref}")
            else:
                prefixes.setdefault(name, iri)
                owners.setdefault(name, ref)
    known = set().union(*(t for _, _, t in ontologies)) if ontologies else set()
    for rel, doc in sorted(binding_docs.items()):
        for where, value in binding_curies(doc):
            if not _is_curie(value):
                continue  # reported by binding.curie
            iri = expand(value, prefixes)
            if iri is None:
                errors.append(f"grounding.prefix-unknown: {package_identity}: {rel}: {where} {value!r} uses a prefix that no dependency OntologyPackage declares")
            elif iri not in known:
                errors.append(f"grounding.ontology-term: {package_identity}: {rel}: {where} {value!r} ({iri}) is not a term of any dependency OntologyPackage")
    return errors


def jsonld_context(binding_doc: dict[str, Any], prefixes: dict[str, str]) -> dict[str, Any]:
    """JSON-LD context mapping each bound EWS field to the IRI of its last path step (or its class)."""
    context: dict[str, Any] = dict(prefixes)
    for field, value in ((binding_doc.get("spec") or {}).get("fields") or {}).items():
        if isinstance(value, dict):
            path = value.get("path") if isinstance(value.get("path"), list) else []
            target = path[-1] if path else value.get("class")
            iri = expand(target, prefixes) if isinstance(target, str) else None
            if iri:
                context[field] = {"@id": iri}
    return context
