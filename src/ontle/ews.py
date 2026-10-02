"""Effective World State (EWS) documents and the reference declarative State Compiler.

A State Compiler MAY declare `spec.bindings`: a closed, deterministic mapping from observations to EWS
fields. Runtimes that honour bindings must produce identical EWS for identical observations and context.
Compilers without bindings are opaque; their EWS output is still checkable against the output contract.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re
from typing import Any

from .core import EWS, OWPError, load_manifest, output_schema_fields
from .structure import EFFECTIVE_WORLD_STATE, OBSERVATION_SET, structure_errors
from .yamlio import YAMLError, load_yaml

SELECTORS = {"latest", "all"}
TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def load_document(path: str | Path) -> Any:
    """Load an ObservationSet or EWS document (YAML 1.2 core schema: timestamps stay text)."""
    try:
        return load_yaml(Path(path).read_text(encoding="utf-8"))
    except YAMLError as exc:
        raise OWPError(f"cannot parse {path}: {exc}") from exc


def _valid_timestamp(value: Any) -> bool:
    if not (isinstance(value, str) and TIMESTAMP_RE.match(value)):
        return False
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return False
    return True


def json_equal(a: Any, b: Any) -> bool:
    """Equality in the JSON data model: a boolean never equals a number; numbers compare numerically."""
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return a == b
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(json_equal(x, y) for x, y in zip(a, b))
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(json_equal(a[k], b[k]) for k in a)
    return type(a) is type(b) and a == b


def _distinct(values: list[Any]) -> list[Any]:
    out: list[Any] = []
    for v in values:
        if not any(json_equal(v, seen) for seen in out):
            out.append(v)
    return out


def _identity(manifest: dict[str, Any]) -> str:
    md = manifest.get("metadata") or {}
    return f"{md.get('namespace')}/{md.get('name')}@{md.get('version')}"


def _asset_kind(manifest: dict[str, Any], rel: str) -> str | None:
    for item in (manifest.get("spec") or {}).get("assets", []) or []:
        if isinstance(item, dict) and item.get("path") == rel:
            return item.get("kind")
    return None


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        data = load_yaml(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise OWPError(f"cannot parse {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise OWPError(f"{path} must contain a YAML mapping")
    return data


def load_compiler(world_root: Path, manifest: dict[str, Any], compiler_path: str) -> dict[str, Any]:
    if _asset_kind(manifest, compiler_path) != "StateCompilerProfile":
        raise OWPError(f"ews.state-compiler: {compiler_path} is not a StateCompilerProfile asset of {_identity(manifest)}")
    spec = _load_yaml(world_root / compiler_path).get("spec")
    if not isinstance(spec, dict):
        raise OWPError(f"ews.state-compiler: {compiler_path} must declare spec")
    return spec


def binding_errors(compiler: dict[str, Any], rel: str, fields: list[str] | None) -> list[str]:
    """Static checks for spec.bindings against the compiler's EWS fields (`output_schema_fields`)."""
    bindings = compiler.get("bindings")
    if bindings is None:
        return []
    if not isinstance(bindings, dict):
        return [f"compiler.binding: StateCompilerProfile {rel} spec.bindings must be a mapping of EWS field to binding"]
    errors: list[str] = []
    for field, b in bindings.items():
        if field not in (fields or []):
            errors.append(f"compiler.binding: StateCompilerProfile {rel} binds {field!r}, which is not one of its EWS fields")
        if not isinstance(b, dict) or not isinstance(b.get("from"), str) or not isinstance(b.get("value"), str):
            errors.append(f"compiler.binding: StateCompilerProfile {rel} binding {field!r} must declare string from and value")
        elif b.get("select", "latest") not in SELECTORS:
            errors.append(f"compiler.binding: StateCompilerProfile {rel} binding {field!r} select must be one of {sorted(SELECTORS)}")
    return errors


def _observations(doc: dict[str, Any]) -> list[dict[str, Any]]:
    if doc.get("kind") != "ObservationSet":
        raise OWPError("ews.input: observations document must have kind ObservationSet")
    unknown = structure_errors(doc, OBSERVATION_SET, "ObservationSet", None)
    if unknown:
        raise OWPError("; ".join(unknown))
    obs = (doc.get("spec") or {}).get("observations")
    if not isinstance(obs, list):
        raise OWPError("ews.input: ObservationSet requires spec.observations list")
    seen: set[str] = set()
    for o in obs:
        if not isinstance(o, dict) or not isinstance(o.get("id"), str) or not isinstance(o.get("type"), str):
            raise OWPError("ews.input: each observation requires string id and type")
        if o["id"] in seen:
            raise OWPError(f"ews.input: duplicate observation id {o['id']}")
        seen.add(o["id"])
        if not _valid_timestamp(o.get("observedAt")):
            raise OWPError(f"ews.input: observation {o['id']} observedAt must be UTC YYYY-MM-DDTHH:MM:SSZ")
        if not isinstance(o.get("values"), dict):
            raise OWPError(f"ews.input: observation {o['id']} requires a values mapping")
    return obs


def compile_ews(world_path: str | Path, compiler_path: str, observations: dict[str, Any], as_of: str) -> dict[str, Any]:
    """Reference compilation of a declarative State Compiler into an EWS document."""
    world_root, manifest = load_manifest(world_path)
    compiler = load_compiler(world_root, manifest, compiler_path)
    if not _valid_timestamp(as_of):
        raise OWPError("ews.input: asOf must be UTC YYYY-MM-DDTHH:MM:SSZ")
    bindings = compiler.get("bindings")
    if not isinstance(bindings, dict):
        raise OWPError(f"ews.opaque-compiler: {compiler_path} declares no spec.bindings; opaque compilers cannot be run by the reference compiler")
    fields, errors = output_schema_fields(world_root, compiler, compiler_path)
    errors += binding_errors(compiler, compiler_path, fields)
    if errors:
        raise OWPError("; ".join(errors))
    obs = _observations(observations)

    state: dict[str, Any] = {}
    unresolved: dict[str, list[Any]] = {}
    missing: list[str] = []
    provenance: dict[str, list[str]] = {}
    for field in fields or []:
        b = bindings.get(field)
        if b is None:
            missing.append(field)
            continue
        candidates = sorted(
            (o for o in obs if o["type"] == b["from"] and o["observedAt"] <= as_of and b["value"] in o["values"]),
            key=lambda o: (o["observedAt"], o["id"]),
        )
        if not candidates:
            missing.append(field)
            continue
        if b.get("select", "latest") == "all":
            state[field] = [o["values"][b["value"]] for o in candidates]
            provenance[field] = sorted(o["id"] for o in candidates)
            continue
        newest = candidates[-1]["observedAt"]
        tied = [o for o in candidates if o["observedAt"] == newest]
        distinct = _distinct([o["values"][b["value"]] for o in tied])
        if len(distinct) == 1:
            state[field] = distinct[0]
        else:
            unresolved[field] = distinct
        provenance[field] = sorted(o["id"] for o in tied)

    world_ref = _identity(manifest)
    return {
        "apiVersion": "openworld/v1alpha1",
        "kind": EWS,
        "spec": {
            "worldRef": world_ref,
            "worldView": f"{world_ref}#{compiler.get('worldViewRef')}",
            "stateCompiler": f"{world_ref}#{compiler_path}",
            "context": {"asOf": as_of},
            "state": state,
            "unresolved": unresolved,
            "missing": missing,
            "provenance": provenance,
        },
    }


def check_ews(world_path: str | Path, ews: dict[str, Any]) -> list[str]:
    """Check an EWS document produced by any runtime against the State Compiler's output contract."""
    world_root, manifest = load_manifest(world_path)
    world_ref = _identity(manifest)
    if ews.get("kind") != EWS:
        return [f"ews.kind: EWS document must have kind {EWS}"]
    spec = ews.get("spec") if isinstance(ews.get("spec"), dict) else {}
    errors: list[str] = structure_errors(ews, EFFECTIVE_WORLD_STATE, "EffectiveWorldState", None)
    if spec.get("worldRef") != world_ref:
        errors.append(f"ews.world-ref: spec.worldRef must be {world_ref}")
    compiler_ref = spec.get("stateCompiler")
    view_ref = spec.get("worldView")
    if not isinstance(compiler_ref, str) or compiler_ref.partition("#")[0] != world_ref:
        return errors + [f"ews.state-compiler: spec.stateCompiler must have the form {world_ref}#<asset path>"]
    try:
        compiler = load_compiler(world_root, manifest, compiler_ref.partition("#")[2])
    except OWPError as exc:
        return errors + [str(exc)]
    if view_ref != f"{world_ref}#{compiler.get('worldViewRef')}":
        errors.append("ews.world-view: spec.worldView must be the View compiled by spec.stateCompiler")
    as_of = (spec.get("context") or {}).get("asOf") if isinstance(spec.get("context"), dict) else None
    if not _valid_timestamp(as_of):
        errors.append("ews.as-of: spec.context.asOf must be UTC YYYY-MM-DDTHH:MM:SSZ")

    fields, field_errors = output_schema_fields(world_root, compiler, compiler_ref.partition("#")[2])
    errors += field_errors
    state = spec.get("state") if isinstance(spec.get("state"), dict) else None
    unresolved = spec.get("unresolved", {}) if isinstance(spec.get("unresolved", {}), dict) else None
    missing = spec.get("missing", []) if isinstance(spec.get("missing", []), list) else None
    provenance = spec.get("provenance", {}) if isinstance(spec.get("provenance", {}), dict) else None
    if state is None or unresolved is None or missing is None or provenance is None:
        return errors + ["ews.shape: spec.state must be a mapping; unresolved/provenance mappings and missing list when present"]
    for field in fields or []:
        placements = (field in state) + (field in unresolved) + (field in missing)
        if placements != 1:
            errors.append(f"ews.field-placement: field {field!r} must appear in exactly one of state, unresolved, missing (found {placements})")
    for field in list(state) + list(unresolved) + list(missing) if fields is not None else []:
        if field not in fields:
            errors.append(f"ews.field-unknown: field {field!r} is not an EWS field of the State Compiler")
    for field, alternatives in unresolved.items():
        if not isinstance(alternatives, list) or len(_distinct(alternatives)) < 2:
            errors.append(f"ews.unresolved-alternatives: unresolved field {field!r} must retain at least two distinct alternatives")
    for field in provenance:
        if field not in state and field not in unresolved:
            errors.append(f"ews.provenance-orphan: provenance for {field!r} which has no value")
    if compiler.get("traceRequired"):
        for field in list(state) + list(unresolved):
            if not provenance.get(field):
                errors.append(f"ews.provenance-required: traceRequired: field {field!r} has no provenance")
    return errors


def canonical(ews: dict[str, Any]) -> dict[str, Any]:
    """Comparable form of an EWS document: the parts two conforming runtimes must agree on."""
    spec = ews.get("spec") or {}
    return {
        "worldRef": spec.get("worldRef"),
        "worldView": spec.get("worldView"),
        "stateCompiler": spec.get("stateCompiler"),
        "asOf": (spec.get("context") or {}).get("asOf"),
        "state": spec.get("state") or {},
        "unresolved": spec.get("unresolved") or {},
        "missing": sorted(spec.get("missing") or []),
        "provenance": {k: sorted(v) for k, v in (spec.get("provenance") or {}).items()},
    }


def ews_equal(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """Spec 12.2 equality of two EWS documents."""
    return json_equal(canonical(a), canonical(b))
