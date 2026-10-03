"""Effective World State (EWS) documents and the reference declarative State Compiler.

A State Compiler MAY declare `spec.bindings`: a closed, deterministic mapping from observations to EWS
fields. Runtimes that honour bindings must produce identical EWS for identical observations and context.
Compilers without bindings are opaque; their EWS output is still checkable against the output contract.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
import re
from typing import Any

from .core import EWS, OWPError, load_manifest, local_assets, output_schema_fields
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


def _asset_kind(root: Path, manifest: dict[str, Any], rel: str) -> str | None:
    return local_assets(root, manifest.get("spec") or {})[0].get(rel)


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        data = load_yaml(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise OWPError(f"cannot parse {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise OWPError(f"{path} must contain a YAML mapping")
    return data


def load_compiler(world_root: Path, manifest: dict[str, Any], compiler_path: str) -> dict[str, Any]:
    if _asset_kind(world_root, manifest, compiler_path) != "StateCompilerProfile":
        raise OWPError(f"ews.state-compiler: {compiler_path} is not a StateCompilerProfile asset of {_identity(manifest)}")
    spec = _load_yaml(world_root / compiler_path).get("spec")
    if not isinstance(spec, dict):
        raise OWPError(f"ews.state-compiler: {compiler_path} must declare spec")
    return spec


AGGREGATE_FUNCTIONS = {"count", "distinct_count", "sum", "mean", "min", "max"}
CONDITIONS = {"eq", "in", "gt", "gte", "lt", "lte"}
DURATION_RE = re.compile(r"^P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?$")
SEMVER_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$")


def duration_seconds(value: Any) -> int | None:
    """Seconds in an ISO 8601 duration of days, hours, minutes, and seconds; None if malformed."""
    m = DURATION_RE.match(value) if isinstance(value, str) else None
    if not m or value in ("P", "PT") or value.endswith("T"):
        return None
    d, h, mi, sec = (int(x) if x else 0 for x in m.groups())
    return ((d * 24 + h) * 60 + mi) * 60 + sec


def output_lists(compiler: dict[str, Any]) -> tuple[list[str], list[str]]:
    """`outputSchema.perSubject` and `outputSchema.latent` (sections 12.3, 12.4); malformed lists count as empty."""
    schema = compiler.get("outputSchema") if isinstance(compiler.get("outputSchema"), dict) else {}
    lists = []
    for key in ("perSubject", "latent"):
        v = schema.get(key)
        lists.append([x for x in v if isinstance(x, str)] if isinstance(v, list) else [])
    return lists[0], lists[1]


def binding_form(b: Any) -> str | None:
    """observe, estimate, aggregate, or classify; None when the binding has none or several forms."""
    if not isinstance(b, dict):
        return None
    forms = [k for k in ("estimate", "aggregate", "classify") if k in b]
    if forms:
        return forms[0] if len(forms) == 1 and len(b) == 1 else None
    return "observe"


def _source_errors(b: Any, where: str) -> list[str]:
    if not isinstance(b, dict) or not isinstance(b.get("from"), str) or not isinstance(b.get("value"), str):
        return [f"{where} must declare string from and value"]
    return []


def binding_errors(compiler: dict[str, Any], rel: str, fields: list[str] | None) -> list[str]:
    """Static checks for spec.bindings and the output lists against the compiler's EWS fields (`output_schema_fields`)."""
    errors: list[str] = []
    unknown = fields is None and compiler.get("outputSchemaRef") is not None
    schema = compiler.get("outputSchema") if isinstance(compiler.get("outputSchema"), dict) else {}
    for key, rule in (("perSubject", "compiler.per-subject-field"), ("latent", "compiler.latent-field")):
        if key not in schema:
            continue
        v = schema[key]
        if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
            errors.append(f"{rule}: StateCompilerProfile {rel} spec.outputSchema.{key} must be a list of EWS field names")
            continue
        for name in v if not unknown else []:
            if name not in (fields or []):
                errors.append(f"{rule}: StateCompilerProfile {rel} spec.outputSchema.{key} names {name!r}, which is not one of its EWS fields")
    per_subject, latent = output_lists(compiler)
    bindings = compiler.get("bindings")
    if bindings is None:
        return errors
    if not isinstance(bindings, dict):
        return errors + [f"compiler.binding: StateCompilerProfile {rel} spec.bindings must be a mapping of EWS field to binding"]
    # An outputSchemaRef that does not resolve is already an error; its fields are unknown, so keys are not checked.
    for field, b in bindings.items():
        where = f"compiler.binding: StateCompilerProfile {rel} binding {field!r}"
        if not unknown and field not in (fields or []):
            errors.append(f"compiler.binding: StateCompilerProfile {rel} binds {field!r}, which is not one of its EWS fields")
        form = binding_form(b)
        if form is None:
            errors.append(f"{where} must be an observation binding or exactly one of estimate, aggregate, classify")
            continue
        if form != "observe" and field not in latent:
            errors.append(f"{where} is a {form} binding, so the field must be listed in spec.outputSchema.latent")
        if form == "observe" and field in latent:
            errors.append(f"{where}: a latent field needs an estimate, aggregate, or classify binding")
        if form in ("observe", "estimate"):
            inner = b if form == "observe" else b["estimate"]
            errors += _source_errors(inner, where)
            if isinstance(inner, dict) and inner.get("select", "latest") not in SELECTORS:
                errors.append(f"{where} select must be one of {sorted(SELECTORS)}")
        elif form == "aggregate":
            a = b["aggregate"]
            errors += _source_errors(a, where)
            if isinstance(a, dict):
                if a.get("function") not in AGGREGATE_FUNCTIONS:
                    errors.append(f"{where} aggregate.function must be one of {sorted(AGGREGATE_FUNCTIONS)}")
                if "window" in a and duration_seconds(a["window"]) is None:
                    errors.append(f"{where} aggregate.window must be an ISO 8601 duration such as PT24H or P7D")
        else:
            errors += _classify_errors(b["classify"], field, where, fields, per_subject, unknown)
    # classification inputs must not form a cycle
    graph = {f: b["classify"].get("input") for f, b in bindings.items()
             if binding_form(b) == "classify" and isinstance(b["classify"], dict)}
    for start in graph:
        seen, cur = set(), start
        while cur in graph and cur not in seen:
            seen.add(cur)
            cur = graph[cur]
        if cur == start:
            errors.append(f"compiler.binding: StateCompilerProfile {rel} classification inputs form a cycle through {start!r}")
    return errors


def _classify_errors(c: Any, field: str, where: str, fields: list[str] | None, per_subject: list[str], unknown: bool) -> list[str]:
    if not isinstance(c, dict) or not isinstance(c.get("input"), str):
        return [f"{where} classify.input must name an EWS field"]
    errors: list[str] = []
    inp = c["input"]
    if inp == field or (not unknown and inp not in (fields or [])):
        errors.append(f"{where} classify.input {inp!r} must be another EWS field of the compiler")
    if (field in per_subject) != (inp in per_subject):
        errors.append(f"{where} is per-subject exactly when its input {inp!r} is")
    crit = c.get("criterion")
    if not isinstance(crit, dict) or not isinstance(crit.get("id"), str) or not crit["id"]:
        return errors + [f"{where} classify.criterion must be a mapping with an id"]
    if "version" in crit and not (isinstance(crit["version"], str) and SEMVER_RE.match(crit["version"])):
        errors.append(f"{where} classify.criterion.version must be SemVer")
    if "basis" in crit and not isinstance(crit["basis"], str):
        errors.append(f"{where} classify.criterion.basis must be a string")
    rules = crit.get("rules")
    if not isinstance(rules, list) or not rules:
        return errors + [f"{where} classify.criterion.rules must be a non-empty list"]
    for i, r in enumerate(rules):
        when = r.get("when") if isinstance(r, dict) else None
        if not isinstance(when, dict) or not when or not set(when) <= CONDITIONS or "label" not in r:
            errors.append(f"{where} classify.criterion.rules[{i}] needs when (one or more of {sorted(CONDITIONS)}) and label")
        elif "in" in when and not isinstance(when["in"], list):
            errors.append(f"{where} classify.criterion.rules[{i}].when.in must be a list")
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
        if "subject" in o and not isinstance(o["subject"], str):
            raise OWPError(f"ews.input: observation {o['id']} subject must be a string")
        if "estimatedBy" in o and not (isinstance(o["estimatedBy"], str) and o["estimatedBy"]):
            raise OWPError(f"ews.input: observation {o['id']} estimatedBy must be a non-empty string")
    return obs


def _shift(ts: str, seconds: int) -> str:
    return (datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ") - timedelta(seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _is_number(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _resolve(cands: list[dict[str, Any]], value: str, select: str) -> tuple[str, Any, list[str]]:
    """Section 12.2 rules 3 and 4 over candidates in (observedAt, id) order: (placement, value, provenance ids)."""
    if select == "all":
        return "state", [o["values"][value] for o in cands], sorted(o["id"] for o in cands)
    newest = cands[-1]["observedAt"]
    tied = [o for o in cands if o["observedAt"] == newest]
    distinct = _distinct([o["values"][value] for o in tied])
    ids = sorted(o["id"] for o in tied)
    return ("state", distinct[0], ids) if len(distinct) == 1 else ("unresolved", distinct, ids)


def _aggregate(cands: list[dict[str, Any]], value: str, function: str) -> tuple[str, Any, list[str]] | None:
    """Section 12.4 aggregates; None when the result is missing."""
    values = [o["values"][value] for o in cands]
    ids = sorted(o["id"] for o in cands)
    if function == "count":
        return "state", len(values), ids
    if function == "distinct_count":
        return "state", len(_distinct(values)), ids
    if not all(_is_number(v) for v in values):
        raise OWPError(f"ews.input: aggregate {function} needs numeric values")
    if function == "sum":
        total = 0
        for v in values:
            total += v
        return "state", total, ids
    if not values:
        return None
    if function == "mean":
        total = 0
        for v in values:
            total += v
        return "state", total / len(values), ids
    return "state", (min(values) if function == "min" else max(values)), ids


def _holds(op: str, v: Any, x: Any) -> bool:
    if op == "eq":
        return json_equal(v, x)
    if op == "in":
        return isinstance(x, list) and any(json_equal(v, y) for y in x)
    if not (_is_number(v) and _is_number(x)):
        return False
    return {"gt": v > x, "gte": v >= x, "lt": v < x, "lte": v <= x}[op]


def classify_value(criterion: dict[str, Any], v: Any) -> Any:
    """The label a criterion gives a value, or None when no rule matches and there is no `otherwise`."""
    for rule in criterion.get("rules") or []:
        if all(_holds(op, v, x) for op, x in rule["when"].items()):
            return rule["label"]
    return criterion.get("otherwise")


def _classify(result: tuple[str, Any, list[str]], criterion: dict[str, Any]) -> tuple[str, Any, list[str]] | None:
    placement, value, ids = result
    alternatives = [value] if placement == "state" else value
    labels = _distinct([lab for lab in (classify_value(criterion, a) for a in alternatives) if lab is not None])
    if not labels:
        return None
    return ("state", labels[0], list(ids)) if len(labels) == 1 else ("unresolved", labels, list(ids))


def compile_ews(world_path: str | Path, compiler_path: str, observations: dict[str, Any], as_of: str) -> dict[str, Any]:
    """Reference compilation of a declarative State Compiler into an EWS document (sections 12.2-12.4)."""
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
    by_id = {o["id"]: o for o in obs}
    per_subject, latent = output_lists(compiler)

    def candidates(src: dict[str, Any], estimates: bool, since: str | None = None) -> list[dict[str, Any]]:
        return sorted((o for o in obs if o["type"] == src["from"] and o["observedAt"] <= as_of and src["value"] in o["values"]
                       and ("estimatedBy" in o) == estimates and (since is None or o["observedAt"] > since)),
                      key=lambda o: (o["observedAt"], o["id"]))

    def grouped(field: str, cands: list[dict[str, Any]]) -> dict[str | None, list[dict[str, Any]]]:
        if field not in per_subject:
            return {None: cands}
        groups: dict[str | None, list[dict[str, Any]]] = {}
        for o in cands:
            if not isinstance(o.get("subject"), str):
                raise OWPError(f"ews.input: observation {o['id']} has no subject, but {field!r} is a per-subject field")
            groups.setdefault(o["subject"], []).append(o)
        return groups

    # results[field] = {subject or None: (placement, value, ids)}; absent field = missing
    results: dict[str, dict[str | None, tuple[str, Any, list[str]]]] = {}
    for field in fields or []:
        b = bindings.get(field)
        form = binding_form(b) if b is not None else None
        if form in ("observe", "estimate"):
            src = b if form == "observe" else b["estimate"]
            out = {k: _resolve(g, src["value"], src.get("select", "latest"))
                   for k, g in grouped(field, candidates(src, form == "estimate")).items() if g}
        elif form == "aggregate":
            a = b["aggregate"]
            since = _shift(as_of, duration_seconds(a["window"])) if "window" in a else None
            groups = grouped(field, candidates(a, False, since))
            out = {}
            for k, g in groups.items():
                r = _aggregate(g, a["value"], a["function"])
                if r is not None:
                    out[k] = r
        else:
            continue
        if out:
            results[field] = out
    pending = [f for f in fields or [] if binding_form(bindings.get(f)) == "classify"]
    while pending:  # inputs first; cycles are rejected by binding_errors
        for field in list(pending):
            c = bindings[field]["classify"]
            if c["input"] in pending:
                continue
            pending.remove(field)
            out = {}
            for k, r in (results.get(c["input"]) or {}).items():
                labelled = _classify(r, c["criterion"])
                if labelled is not None:
                    out[k] = labelled
            if out:
                results[field] = out

    state: dict[str, Any] = {}
    unresolved: dict[str, Any] = {}
    provenance: dict[str, Any] = {}
    derivation: dict[str, Any] = {}
    missing = [f for f in fields or [] if f not in results]
    for field in fields or []:
        if field not in results:
            continue
        for subject, (placement, value, ids) in results[field].items():
            target = state if placement == "state" else unresolved
            if subject is None:
                target[field] = value
                provenance[field] = ids
            else:
                target.setdefault(field, {})[subject] = value
                provenance.setdefault(field, {})[subject] = ids
        if field in latent:
            derivation[field] = _derivation(bindings[field], results[field], by_id)

    world_ref = _identity(manifest)
    spec: dict[str, Any] = {
        "worldRef": world_ref,
        "worldView": f"{world_ref}#{compiler.get('worldViewRef')}",
        "stateCompiler": f"{world_ref}#{compiler_path}",
        "context": {"asOf": as_of},
        "state": state,
        "unresolved": unresolved,
        "missing": missing,
        "provenance": provenance,
    }
    if derivation:
        spec["derivation"] = derivation
    return {"apiVersion": "openworld/v1alpha1", "kind": EWS, "spec": spec}


def _derivation(b: dict[str, Any], result: dict[str | None, tuple[str, Any, list[str]]], by_id: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Section 12.4 derivation record of one latent field."""
    form = binding_form(b)
    if form == "estimate":
        def by(ids: list[str]) -> list[str]:
            return sorted({str(by_id[i]["estimatedBy"]) for i in ids})
        if None in result:
            return {"kind": "estimate", "by": by(result[None][2])}
        return {"kind": "estimate", "by": {k: by(r[2]) for k, r in result.items()}}
    if form == "aggregate":
        a = b["aggregate"]
        return {"kind": "aggregate", **{k: a[k] for k in ("from", "value", "function", "window") if k in a}}
    c = b["classify"]
    return {"kind": "classify", "input": c["input"], "criterion": {k: c["criterion"][k] for k in ("id", "version", "basis") if k in c["criterion"]}}


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
    per_subject, latent = output_lists(compiler)
    derivation = spec.get("derivation", {}) if isinstance(spec.get("derivation", {}), dict) else None
    if derivation is None:
        return errors + ["ews.shape: spec.derivation must be a mapping when present"]
    for field in fields or []:
        if field in per_subject and field in state and field in unresolved and field not in missing:
            continue  # subjects split between state and unresolved (section 12.3)
        placements = (field in state) + (field in unresolved) + (field in missing)
        if placements != 1:
            errors.append(f"ews.field-placement: field {field!r} must appear in exactly one of state, unresolved, missing (found {placements})")
    for field in [f for f in fields or [] if f in per_subject]:
        parts = [(name, sec[field]) for name, sec in (("state", state), ("unresolved", unresolved), ("provenance", provenance)) if field in sec]
        for name, value in parts:
            if not isinstance(value, dict):
                errors.append(f"ews.per-subject-shape: per-subject field {field!r} in {name} must be a mapping from subject to value")
        if isinstance(state.get(field), dict) and isinstance(unresolved.get(field), dict):
            for subject in sorted(set(state[field]) & set(unresolved[field])):
                errors.append(f"ews.per-subject-overlap: subject {subject!r} of {field!r} is in both state and unresolved")
    for field in latent:
        if (field in state or field in unresolved) and field not in derivation:
            errors.append(f"ews.derivation: latent field {field!r} has a value but no spec.derivation entry")
    for field, record in derivation.items():
        if field not in latent:
            errors.append(f"ews.derivation: {field!r} is not a latent field of the State Compiler")
        elif not isinstance(record, dict) or record.get("kind") not in ("estimate", "aggregate", "classify"):
            errors.append(f"ews.derivation: derivation of {field!r} must have kind estimate, aggregate, or classify")
        elif field not in state and field not in unresolved:
            errors.append(f"ews.derivation: derivation for {field!r}, which has no value")
    for field in list(state) + list(unresolved) + list(missing) if fields is not None else []:
        if field not in fields:
            errors.append(f"ews.field-unknown: field {field!r} is not an EWS field of the State Compiler")
    for field, alternatives in unresolved.items():
        groups = alternatives.items() if field in per_subject and isinstance(alternatives, dict) else [(None, alternatives)]
        for subject, alts in groups:
            if not isinstance(alts, list) or len(_distinct(alts)) < 2:
                where = f"{field!r}" if subject is None else f"{field!r} subject {subject!r}"
                errors.append(f"ews.unresolved-alternatives: unresolved field {where} must retain at least two distinct alternatives")
    for field in provenance:
        if field not in state and field not in unresolved:
            errors.append(f"ews.provenance-orphan: provenance for {field!r} which has no value")
    if compiler.get("traceRequired"):
        for field in list(state) + list(unresolved):
            # an aggregate over no observations (a count of 0) has an empty provenance list (section 12.4)
            empty_ok = isinstance(derivation.get(field), dict) and derivation[field].get("kind") == "aggregate"
            if field in per_subject and isinstance(provenance.get(field), dict):
                subjects = set(state.get(field) or {}) | set(unresolved.get(field) or {})
                for subject in sorted(subjects):
                    ids = provenance[field].get(subject)
                    if ids is None or (not ids and not empty_ok):
                        errors.append(f"ews.provenance-required: traceRequired: field {field!r} subject {subject!r} has no provenance")
            elif field not in provenance or (not provenance[field] and not empty_ok):
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
        "provenance": {k: ({s: sorted(i) for s, i in v.items()} if isinstance(v, dict) else sorted(v))
                       for k, v in (spec.get("provenance") or {}).items()},
        "derivation": spec.get("derivation") or {},
    }


def ews_equal(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """Spec 12.2 equality of two EWS documents."""
    return json_equal(canonical(a), canonical(b))
