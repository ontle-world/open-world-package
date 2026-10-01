"""SemanticBinding: World names, EWS fields, observation types, and actions bound to ontology terms (spec section 14)."""
from __future__ import annotations

from typing import Any

from .ontology import CURIE_RE, expand
from .structure import OPEN, VALUE, closed, structure_errors

FIELD_BINDING = closed({"class": VALUE, "path": VALUE})

SEMANTIC_BINDING = closed({
    "apiVersion": VALUE,
    "kind": VALUE,
    "metadata": closed({"name": VALUE, "version": VALUE, "title": VALUE, "description": VALUE}),
    "spec": closed({"terms": OPEN, "fields": OPEN, "observationTypes": OPEN, "actions": OPEN}),
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
    return out


def binding_issues(spec: dict[str, Any], local_kinds: dict[str, str], docs: dict[str, dict[str, Any]],
                   view_includes: set[str], declared: set[str]) -> tuple[list[str], list[str]]:
    """Single-package checks for every local SemanticBinding and spec.world.semanticBinding."""
    errors: list[str] = []
    warnings: list[str] = []
    world = spec.get("world") if isinstance(spec.get("world"), dict) else {}
    named = world.get("semanticBinding")
    if named is not None and local_kinds.get(named) != "SemanticBinding":
        errors.append(f"binding.asset: spec.world.semanticBinding {named!r} must be a listed local SemanticBinding asset")
    schema_fields: set[str] = set()
    for rel, kind in local_kinds.items():
        if kind == "StateCompilerProfile":
            schema = ((docs.get(rel) or {}).get("spec") or {}).get("outputSchema")
            fields = schema.get("fields") if isinstance(schema, dict) else None
            schema_fields |= {f for f in fields or [] if isinstance(f, str)}
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
                errors.append(f"binding.field-unknown: {rel}: spec.fields.{field} is not in any local State Compiler outputSchema.fields")
        for where, value in binding_curies(doc):
            if not _is_curie(value):
                errors.append(f"binding.curie: {rel}: {where} {value!r} must be a CURIE <prefix>:<local name>")
        if scope:
            for name in (bspec.get("terms") or {}) if isinstance(bspec.get("terms"), dict) else []:
                if name not in scope:
                    warnings.append(f"binding.term-unscoped: {rel}: spec.terms.{name} is neither in spec.world.boundary.included nor in any local View's projection.include")
    return errors, warnings


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
