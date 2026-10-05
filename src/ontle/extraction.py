"""Knowledge extraction (spec section 19.2): query results -> ObservationSet.

The transform is deterministic and covered by the conformance suite. Running the
query is runtime (or tooling) work: the reference CLI runs SPARQL over a local
RDF KnowledgeAsset with the optional rdflib dependency.
"""
from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

from .core import OWPError, load_manifest, local_assets
from .yamlio import YAMLError, load_yaml

PARAMETER_TYPES = {"string": str, "number": (int, float), "boolean": bool}


def _valid_timestamp(value: Any) -> bool:
    from .ews import _valid_timestamp as valid  # local import: ews depends on core
    return valid(value)


def _id_part(value: Any) -> str:
    """Text of one id value: strings as is, booleans as true/false, numbers in shortest form (10.0 -> 10)."""
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        # shortest round-trip digits (repr), written without an exponent: 1e-05 -> 0.00001
        return str(int(value)) if value.is_integer() else format(Decimal(repr(value)), "f")
    raise OWPError(f"extraction.input: id column values must be strings, numbers, or booleans, not {type(value).__name__}")


def check_parameters(profile_spec: dict[str, Any], parameters: dict[str, Any]) -> None:
    declared = profile_spec.get("parameters") or {}
    if not isinstance(declared, dict):
        raise OWPError("extraction.input: spec.parameters must be a mapping")
    for name, value in parameters.items():
        if name not in declared:
            raise OWPError(f"extraction.input: parameter {name!r} is not declared in spec.parameters")
    for name, decl in declared.items():
        if name not in parameters:
            raise OWPError(f"extraction.input: parameter {name!r} has no value")
        expected = PARAMETER_TYPES.get((decl or {}).get("type", "string") if isinstance(decl, dict) else "string")
        value = parameters[name]
        if expected is None or isinstance(value, bool) != (expected is bool) or not isinstance(value, expected):
            raise OWPError(f"extraction.input: parameter {name!r} must be a {(decl or {}).get('type', 'string')}")


def transform(profile: dict[str, Any], rows: list[dict[str, Any]], parameters: dict[str, Any], snapshot: str | None) -> dict[str, Any]:
    """Build an ObservationSet from query result rows (column -> JSON value)."""
    spec = profile.get("spec") if isinstance(profile.get("spec"), dict) else {}
    check_parameters(spec, parameters)
    if not isinstance(rows, list) or not all(isinstance(r, dict) for r in rows):
        raise OWPError("extraction.input: results must be a list of rows (column -> value)")
    templates = spec.get("observations")
    if not isinstance(templates, list) or not templates:
        raise OWPError("extraction.input: spec.observations must be a non-empty list")
    observations: list[dict[str, Any]] = []
    seen: set[str] = set()
    for t_index, template in enumerate(templates):
        if not isinstance(template, dict) or not isinstance(template.get("type"), str) \
                or not isinstance(template.get("id"), list) or not template["id"] \
                or not isinstance(template.get("values"), dict) or not template["values"] \
                or not all(isinstance(c, str) for c in template["id"] + list(template["values"].values())):
            raise OWPError(f"extraction.input: spec.observations[{t_index}] needs type, a non-empty id column list, and a values mapping (column names are strings)")
        observed = template.get("observedAt") or {}
        if not isinstance(observed, dict):
            raise OWPError(f"extraction.input: spec.observations[{t_index}].observedAt must be a mapping")
        produced: list[dict[str, Any]] = []
        for row in rows:
            id_values = [row.get(col) for col in template["id"]]
            if any(v is None for v in id_values):
                continue
            values = {key: row[col] for key, col in template["values"].items() if row.get(col) is not None}
            if not values:
                continue
            at = row.get(observed["column"]) if isinstance(observed.get("column"), str) else None
            if at is None:
                default = observed.get("default", "snapshot")
                at = snapshot if default == "snapshot" else default
            if not _valid_timestamp(at):
                raise OWPError(f"extraction.input: observation time {at!r} for {template['type']} must be UTC YYYY-MM-DDTHH:MM:SSZ")
            obs_id = f"{template['type']}:" + "|".join(_id_part(v) for v in id_values)
            obs = {"id": obs_id, "type": template["type"], "observedAt": at, "values": values}
            subject = row.get(template["subject"]) if isinstance(template.get("subject"), str) else None
            if subject is not None:
                obs["subject"] = _id_part(subject)  # section 12.3: what the observation is about
            produced.append(obs)
        produced.sort(key=lambda o: o["id"])
        unique: list[dict[str, Any]] = []
        for obs in produced:
            if unique and unique[-1]["id"] == obs["id"]:
                if unique[-1] != obs:  # joins repeat rows; identical observations collapse, conflicting ones are invalid
                    raise OWPError(f"extraction.input: observation id {obs['id']} has conflicting values or times")
                continue
            if obs["id"] in seen:
                raise OWPError(f"extraction.input: observation id {obs['id']} is produced by two entries")
            seen.add(obs["id"])
            unique.append(obs)
        observations.extend(unique)
    md = profile.get("metadata") if isinstance(profile.get("metadata"), dict) else {}
    provenance: dict[str, Any] = {"extraction": f"{md.get('name')}@{md.get('version')}" if md.get("version") else str(md.get("name"))}
    if parameters:
        provenance["parameters"] = dict(parameters)
    if snapshot is not None:
        provenance["snapshot"] = snapshot
    return {"apiVersion": "openworld/v1alpha1", "kind": "ObservationSet",
            "spec": {"provenance": provenance, "observations": observations}}


def _load(path: Path) -> Any:
    try:
        return load_yaml(path.read_text(encoding="utf-8"))
    except YAMLError as exc:
        raise OWPError(f"cannot parse {path}: {exc}") from exc


def run_extraction(package: str | Path, profile_path: str, parameters: dict[str, Any], results: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Load a KnowledgeExtractionProfile from a package, run its SPARQL query over the source KnowledgeAsset (unless results are given), and transform."""
    root, manifest = load_manifest(package)
    kinds = local_assets(root, _spec(manifest))[0]
    if kinds.get(profile_path) != "KnowledgeExtractionProfile":
        raise OWPError(f"{profile_path} is not a KnowledgeExtractionProfile asset of the package")
    profile = _load(root / profile_path)
    spec = _spec(profile)
    source = spec.get("source")
    if kinds.get(source) != "KnowledgeAsset":
        raise OWPError(f"spec.source {source!r} is not a KnowledgeAsset asset of the package")
    asset = _spec(_load(root / source))
    snapshot = asset["snapshot"].get("asOf") if isinstance(asset.get("snapshot"), dict) else None
    if results is None:
        results = _run_sparql(root, asset, spec, parameters)
    return transform(profile, results, parameters, snapshot)


def _run_sparql(root: Path, asset: dict[str, Any], spec: dict[str, Any], parameters: dict[str, Any]) -> list[dict[str, Any]]:
    query = spec["query"] if isinstance(spec.get("query"), dict) else {}
    if query.get("language") != "sparql":
        raise OWPError("the reference CLI runs only SPARQL queries; pass --results for other languages")
    content = asset["content"].get("path") if isinstance(asset.get("content"), dict) else None
    if not isinstance(content, str):
        raise OWPError("the source KnowledgeAsset has no local content.path; fetch the content first or pass --results")
    try:
        import rdflib
    except ImportError as exc:
        raise OWPError("running SPARQL needs rdflib: pip install 'ontle[rdf]'") from exc
    declared_format = asset.get("format", "turtle")
    fmt = {"turtle": "turtle", "nquads": "nquads", "jsonld": "json-ld", "ntriples": "nt"}.get(declared_format if isinstance(declared_format, str) else "", "turtle")
    graph = rdflib.Dataset(default_union=True) if fmt == "nquads" else rdflib.Graph()  # query named graphs too
    bindings = {name: rdflib.Literal(value) for name, value in parameters.items()}
    rows = []
    try:
        graph.parse(root / content, format=fmt)
        results = graph.query(query.get("text") if isinstance(query.get("text"), str) else "", initBindings=bindings)
    except Exception as exc:  # rdflib raises parser-specific errors
        raise OWPError(f"cannot run the SPARQL query over {content}: {' '.join(str(exc).split())[:200]}") from exc
    for result in results:
        row = {}
        for var in result.labels:
            value = result[var]
            row[str(var)] = None if value is None else value.toPython() if isinstance(value, rdflib.Literal) else str(value)
        rows.append(row)
    return rows


def _spec(doc: Any) -> dict[str, Any]:
    spec = doc.get("spec") if isinstance(doc, dict) else None
    return spec if isinstance(spec, dict) else {}


def multi_latest_warnings(local_kinds: dict[str, str], docs: dict[str, dict[str, Any]]) -> list[str]:
    """compiler.multi-latest: a State Compiler binding reads a multi-valued extracted type with select latest."""
    multi: dict[str, str] = {}
    for rel, kind in sorted(local_kinds.items()):
        templates = _spec(docs.get(rel)).get("observations") if kind == "KnowledgeExtractionProfile" else None
        for template in templates if isinstance(templates, list) else []:
            if isinstance(template, dict) and template.get("multi") is True and isinstance(template.get("type"), str):
                multi[template["type"]] = rel
    warnings: list[str] = []
    for rel, kind in sorted(local_kinds.items()):
        if kind != "StateCompilerProfile":
            continue
        bindings = _spec(docs.get(rel)).get("bindings")
        for field, binding in bindings.items() if isinstance(bindings, dict) else []:
            source = binding.get("from") if isinstance(binding, dict) else None
            select = binding.get("select") if isinstance(binding, dict) else None
            if isinstance(source, str) and source in multi and (select is None or select == "latest"):
                warnings.append(f"compiler.multi-latest: {rel}: binding {field!r} reads {source}, which {multi[source]} marks multi-valued; use select: all")
    return warnings
