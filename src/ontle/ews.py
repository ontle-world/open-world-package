"""Effective World State (EWS) documents and the reference declarative State Compiler.

A State Compiler MAY declare `spec.bindings`: a closed, deterministic mapping from observations to EWS
fields. Runtimes that honour bindings must produce identical EWS for identical observations and context.
Compilers without bindings are opaque; their EWS output is still checkable against the output contract.
"""
from __future__ import annotations

import json

from pathlib import Path
import math
import re
from typing import Any

from .core import EWS, MANIFEST, OWPError, local_assets, output_schema_fields
from .structure import EFFECTIVE_WORLD_STATE, OBSERVATION_SET, structure_errors
from .values import js_string, nonempty_str
from .yamlio import YAMLError, load_yaml

API_VERSION = "openworld/v1alpha1"
MAX_SAFE_INTEGER = 2 ** 53 - 1

SELECTORS = {"latest", "all"}
TIMESTAMP_RE = re.compile(r"^([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})Z\Z")


def load_document(path: str | Path, rule: str = "ews.input") -> Any:
    """Load an ObservationSet or EWS document (YAML 1.2 core schema: timestamps stay text)."""
    try:
        return load_yaml(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, YAMLError) as exc:
        raise OWPError(f"{rule}: cannot parse {path}: {exc}") from exc


def _days_in_month(year: int, month: int) -> int:
    if month == 2:
        return 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28
    return 30 if month in (4, 6, 9, 11) else 31


def _valid_timestamp(value: Any) -> bool:
    """UTC YYYY-MM-DDTHH:MM:SSZ that is a real calendar instant, for any year 0000-9999 (proleptic Gregorian)."""
    m = TIMESTAMP_RE.match(value) if isinstance(value, str) else None
    if not m:
        return False
    year, month, day, hour, minute, second = (int(x) for x in m.groups())
    return 1 <= month <= 12 and 1 <= day <= _days_in_month(year, month) and hour <= 23 and minute <= 59 and second <= 59


def _seconds(ts: str) -> int:
    """Seconds since 0000-01-01T00:00:00Z of a valid timestamp."""
    year, month, day, hour, minute, second = (int(x) for x in TIMESTAMP_RE.match(ts).groups())  # type: ignore[union-attr]
    days = year * 365 + (year + 3) // 4 - (year + 99) // 100 + (year + 399) // 400  # days before Jan 1 of `year`
    days += sum(_days_in_month(year, m) for m in range(1, month)) + day - 1
    return ((days * 24 + hour) * 60 + minute) * 60 + second


def _timestamp(seconds: int) -> str:
    """The UTC timestamp `seconds` after 0000-01-01T00:00:00Z (inverse of _seconds within years 0000-9999)."""
    days, rest = divmod(seconds, 86400)
    year = max(0, min(9999, days * 400 // 146097))
    while year > 0 and _seconds(f"{year:04d}-01-01T00:00:00Z") // 86400 > days:
        year -= 1
    while year < 9999 and _seconds(f"{year + 1:04d}-01-01T00:00:00Z") // 86400 <= days:
        year += 1
    days -= _seconds(f"{year:04d}-01-01T00:00:00Z") // 86400
    month = 1
    while days >= _days_in_month(year, month):
        days -= _days_in_month(year, month)
        month += 1
    return f"{year:04d}-{month:02d}-{days + 1:02d}T{rest // 3600:02d}:{rest // 60 % 60:02d}:{rest % 60:02d}Z"


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
    """<namespace>/<name>@<version> as written in the World's metadata; a missing part reads `undefined`, as in TypeScript."""
    md = manifest.get("metadata") if isinstance(manifest.get("metadata"), dict) else {}
    return "{}/{}@{}".format(*(js_string(md[k]) if k in md else "undefined" for k in ("namespace", "name", "version")))


def load_world(world_path: str | Path) -> tuple[Path, dict[str, Any], str]:
    """The World's root, manifest, and identity. A World that is not a readable WorldPackage manifest raises a message without a rule id."""
    root = Path(world_path).expanduser().resolve()
    if root.is_file():
        root = root.parent
    try:
        manifest = load_yaml((root / MANIFEST).read_text(encoding="utf-8"))
    except Exception as exc:
        raise OWPError(f"cannot read World manifest in {world_path}: {exc}") from exc
    if not isinstance(manifest, dict):
        raise OWPError(f"cannot read World manifest in {world_path}")
    if manifest.get("kind") != "WorldPackage":
        raise OWPError(f"{world_path} is not a WorldPackage")
    return root, manifest, _identity(manifest)


def load_compiler(world_root: Path, manifest: dict[str, Any], compiler_path: str) -> dict[str, Any]:
    """The spec of a local StateCompilerProfile asset of the World; refusals are ews.state-compiler."""
    if local_assets(world_root, manifest.get("spec") if isinstance(manifest.get("spec"), dict) else {})[0].get(compiler_path) != "StateCompilerProfile":
        raise OWPError(f"ews.state-compiler: {compiler_path} is not a local StateCompilerProfile asset of {_identity(manifest)}")
    try:
        doc = load_yaml((world_root / compiler_path).read_text(encoding="utf-8"))
    except Exception as exc:
        raise OWPError(f"ews.state-compiler: cannot read State Compiler {compiler_path}: {exc}") from exc
    spec = doc.get("spec") if isinstance(doc, dict) else None
    if not isinstance(spec, dict):
        raise OWPError(f"ews.state-compiler: State Compiler {compiler_path} has no spec")
    return spec


AGGREGATE_FUNCTIONS = {"count", "distinct_count", "sum", "mean", "min", "max"}
CONDITIONS = {"eq", "in", "gt", "gte", "lt", "lte"}
DURATION_RE = re.compile(r"^P(?:([0-9]+)D)?(?:T(?:([0-9]+)H)?(?:([0-9]+)M)?(?:([0-9]+)S)?)?\Z")
SEMVER_RE = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?\Z")


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
    units = output_units(compiler)
    if "units" in schema:
        if units is None:
            errors.append(f"compiler.unit: StateCompilerProfile {rel} spec.outputSchema.units must map EWS fields to UCUM codes (printable ASCII, no spaces)")
        else:
            for name in units if not unknown else []:
                if name not in (fields or []):
                    errors.append(f"compiler.unit: StateCompilerProfile {rel} spec.outputSchema.units names {name!r}, which is not one of its EWS fields")
    units = units or {}
    if "bindings" not in compiler:
        return errors
    bindings = compiler["bindings"]
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
            if isinstance(inner, dict) and "select" in inner and not (isinstance(inner["select"], str) and inner["select"] in SELECTORS):
                errors.append(f"{where} select must be one of {sorted(SELECTORS)}")
        elif form == "aggregate":
            a = b["aggregate"]
            errors += _source_errors(a, where)
            if isinstance(a, dict):
                if not (isinstance(a.get("function"), str) and a["function"] in AGGREGATE_FUNCTIONS):
                    errors.append(f"{where} aggregate.function must be one of {sorted(AGGREGATE_FUNCTIONS)}")
                if "window" in a and duration_seconds(a["window"]) is None:
                    errors.append(f"{where} aggregate.window must be an ISO 8601 duration such as PT24H or P7D")
                if "where" in a:
                    errors += _where_errors(a["where"], where)
                if a.get("function") in ("count", "distinct_count") and field in units and not dimensionless(units[field]):
                    errors.append(f"compiler.unit: StateCompilerProfile {rel} field {field!r} is a {a['function']}, so its unit must be dimensionless (1 or an annotation such as {{alarm}}), not {units[field]!r}")
        else:
            errors += _classify_errors(b["classify"], field, where, fields, per_subject, unknown)
            c = b["classify"] if isinstance(b["classify"], dict) else {}
            crit = c.get("criterion") if isinstance(c.get("criterion"), dict) else {}
            if field in units:
                errors.append(f"compiler.unit: StateCompilerProfile {rel} field {field!r} is a classification; a label has no unit")
            input_unit = units.get(c["input"]) if isinstance(c.get("input"), str) else None
            if crit.get("unit") is not None and crit["unit"] != input_unit:
                errors.append(f"compiler.unit: StateCompilerProfile {rel} binding {field!r} criterion.unit {crit['unit']!r} must equal the unit of its input {c.get('input')!r} ({input_unit!r})")
    # classification inputs must not form a cycle
    graph = {f: b["classify"]["input"] for f, b in bindings.items()
             if binding_form(b) == "classify" and isinstance(b["classify"], dict) and isinstance(b["classify"].get("input"), str)}
    for start in graph:
        seen, cur = set(), start
        while cur in graph and cur not in seen:
            seen.add(cur)
            cur = graph[cur]
        if cur == start:
            errors.append(f"compiler.binding: StateCompilerProfile {rel} classification inputs form a cycle through {start!r}")
    return errors


UCUM_CODE_RE = re.compile(r"^[!-~]+\Z")  # a UCUM code: printable ASCII without spaces (compared as text, never converted)


def output_units(compiler: dict[str, Any]) -> dict[str, str] | None:
    """spec.outputSchema.units (section 12.5): EWS field -> UCUM code; {} when absent, None when malformed."""
    schema = compiler.get("outputSchema") if isinstance(compiler.get("outputSchema"), dict) else {}
    units = schema.get("units")
    if units is None:  # absent or null: no units declared
        return {}
    if not isinstance(units, dict) or not all(isinstance(k, str) and isinstance(v, str) and UCUM_CODE_RE.match(v) for k, v in units.items()):
        return None
    return units


def dimensionless(unit: str) -> bool:
    """UCUM unity: `1`, or an annotation only, such as `{alarm}`."""
    return unit == "1" or bool(re.fullmatch(r"\{[^{}]*\}", unit))


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


def _where_errors(w: Any, where: str) -> list[str]:
    """Section 12.4: aggregate.where maps a values key to conditions, the same conditions a classify rule uses."""
    if not isinstance(w, dict) or not w:
        return [f"{where} aggregate.where must be a non-empty mapping from a values key to conditions"]
    errors: list[str] = []
    for key, cond in w.items():
        if not isinstance(key, str) or not key:
            errors.append(f"{where} aggregate.where keys must be non-empty strings")
        elif not isinstance(cond, dict) or not cond or not set(cond) <= CONDITIONS:
            errors.append(f"{where} aggregate.where.{key} needs one or more of {sorted(CONDITIONS)}")
        elif "in" in cond and not isinstance(cond["in"], list):
            errors.append(f"{where} aggregate.where.{key}.in must be a list")
    return errors


def _passes(o: dict[str, Any], w: dict[str, Any] | None) -> bool:
    """An observation meets aggregate.where: every condition on every key holds; a missing key fails."""
    return w is None or all(key in o["values"] and all(_holds(op, o["values"][key], x) for op, x in cond.items())
                            for key, cond in w.items())


def _inexact_number(value: Any) -> bool:
    """A number JSON implementations cannot all represent exactly: .inf, .nan, or an integer outside +-(2^53-1)."""
    if isinstance(value, bool):
        return False
    if isinstance(value, float) and not math.isfinite(value):
        return True
    if isinstance(value, (int, float)):
        return (isinstance(value, int) or value.is_integer()) and abs(value) > MAX_SAFE_INTEGER
    if isinstance(value, list):
        return any(_inexact_number(v) for v in value)
    if isinstance(value, dict):
        return any(_inexact_number(v) for v in value.values())
    return False


def observation_errors(doc: Any) -> tuple[list[dict[str, Any]], list[str]]:
    """The observations of an ObservationSet and every reason it is invalid input (`<rule-id>: <message>`)."""
    if not isinstance(doc, dict):
        return [], ["ews.input: ObservationSet must be a mapping"]
    errors = [f"{e.split(': ', 1)[0]}: ObservationSet: {e.split(': ', 1)[1]}" for e in structure_errors(doc, OBSERVATION_SET, "ObservationSet", None)]
    if "apiVersion" in doc and doc["apiVersion"] != API_VERSION:
        errors.append(f"ews.input: ObservationSet apiVersion must be {API_VERSION}")
    if doc.get("kind") != "ObservationSet":
        errors.append("ews.input: observations document must have kind ObservationSet")
    obs = doc["spec"].get("observations") if isinstance(doc.get("spec"), dict) else None
    if not isinstance(obs, list):
        return [], errors + ["ews.input: ObservationSet requires spec.observations list"]
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for i, o in enumerate(obs):
        where = f"ews.input: observations[{i}]"
        if not isinstance(o, dict):
            errors.append(f"{where} must be a mapping")
            continue
        if not nonempty_str(o.get("id")):
            errors.append(f"{where} requires a non-empty string id")
        elif o["id"] in seen:
            errors.append(f"ews.input: duplicate observation id {o['id']}")
        else:
            seen.add(o["id"])
        if not nonempty_str(o.get("type")):
            errors.append(f"{where} requires a non-empty string type")
        if not _valid_timestamp(o.get("observedAt")):
            errors.append(f"{where}.observedAt must be UTC YYYY-MM-DDTHH:MM:SSZ")
        if not isinstance(o.get("values"), dict):
            errors.append(f"{where} requires a values mapping")
        elif _inexact_number(o["values"]):
            errors.append(f"{where} has a value that is not a finite JSON number with an exact value (.inf, .nan, or an integer outside +-(2^53-1))")
        if "subject" in o and not isinstance(o["subject"], str):
            errors.append(f"{where}.subject must be a string")
        if "estimatedBy" in o and not nonempty_str(o["estimatedBy"]):
            errors.append(f"{where}.estimatedBy must be a non-empty string")
        if "units" in o and not (isinstance(o["units"], dict) and all(isinstance(v, str) and UCUM_CODE_RE.match(v) for v in o["units"].values())):
            errors.append(f"{where}.units must map value keys to UCUM codes")
        if not errors:
            out.append(o)
    return out, errors


def _shift(ts: str, seconds: int) -> str:
    """`ts` minus `seconds`; before year 0000 the result sorts before every timestamp."""
    shifted = _seconds(ts) - seconds
    return _timestamp(shifted) if shifted >= 0 else "-"


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
    try:
        world_root, manifest, world_ref = load_world(world_path)
    except OWPError as exc:
        raise OWPError(f"ews.state-compiler: {exc}") from exc
    if not _valid_timestamp(as_of):
        raise OWPError("ews.input: asOf must be UTC YYYY-MM-DDTHH:MM:SSZ")
    compiler = load_compiler(world_root, manifest, compiler_path)
    if "bindings" not in compiler:
        raise OWPError(f"ews.opaque-compiler: {compiler_path} declares no spec.bindings; opaque compilers cannot be run by the reference compiler")
    fields, errors = output_schema_fields(world_root, compiler, compiler_path)
    errors += binding_errors(compiler, compiler_path, fields)
    if errors:
        raise OWPError("; ".join(errors))
    bindings = compiler["bindings"]
    obs, errors = observation_errors(observations)
    if errors:
        raise OWPError("; ".join(errors))
    by_id = {o["id"]: o for o in obs}
    per_subject, latent = output_lists(compiler)

    units = output_units(compiler) or {}

    def candidates(field: str, src: dict[str, Any], estimates: bool, since: str | None = None, same_unit: bool = False,
                   counted: bool = False, where: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        cands = sorted((o for o in obs if o["type"] == src["from"] and o["observedAt"] <= as_of and src["value"] in o["values"]
                        and ("estimatedBy" in o) == estimates and (since is None or o["observedAt"] > since) and _passes(o, where)),
                       key=lambda o: (o["observedAt"], o["id"]))
        # Section 12.5: a reported unit must be the field's declared unit; values are never converted.
        reported = {}
        for o in cands:
            u = (o.get("units") or {}).get(src["value"])
            if u is not None:
                if field in units and not counted and u != units[field]:  # a count's unit is not the unit of what it counts
                    raise OWPError(f"ews.input: observation {o['id']} reports {src['value']!r} in {u!r}, but {field!r} is declared in {units[field]!r}")
                reported[u] = o["id"]
        if same_unit and len(reported) > 1:
            raise OWPError(f"ews.input: {field!r} would combine values in different units ({', '.join(sorted(reported))}); units are not converted")
        return cands

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
                   for k, g in grouped(field, candidates(field, src, form == "estimate")).items() if g}
        elif form == "aggregate":
            a = b["aggregate"]
            since = _shift(as_of, duration_seconds(a["window"])) if "window" in a else None
            groups = grouped(field, candidates(field, a, False, since, same_unit=a["function"] in ("sum", "mean", "min", "max"),
                                                counted=a["function"] in ("count", "distinct_count"), where=a.get("where")))
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

    spec: dict[str, Any] = {
        "worldRef": world_ref,
        "worldView": f"{world_ref}#{js_string(compiler['worldViewRef']) if 'worldViewRef' in compiler else 'undefined'}",
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
        return {"kind": "aggregate", **{k: a[k] for k in ("from", "value", "function", "window", "where") if k in a}}
    c = b["classify"]
    return {"kind": "classify", "input": c["input"], "criterion": {k: c["criterion"][k] for k in ("id", "version", "basis") if k in c["criterion"]}}


def check_ews(world_path: str | Path, ews: Any) -> list[str]:
    """Check an EWS document produced by any runtime against the State Compiler's output contract (spec 12.1)."""
    try:
        world_root, manifest, world_ref = load_world(world_path)
    except OWPError as exc:
        return [f"ews.world-ref: {exc}"]
    if not isinstance(ews, dict):
        return ["ews.kind: EWS document must be a mapping"]
    errors: list[str] = []
    if ews.get("apiVersion") != API_VERSION:
        errors.append(f"ews.kind: apiVersion must be {API_VERSION}")
    if ews.get("kind") != EWS:
        errors.append(f"ews.kind: EWS document must have kind {EWS}")
    errors += structure_errors(ews, EFFECTIVE_WORLD_STATE, "EffectiveWorldState", None)
    spec = ews.get("spec")
    if not isinstance(spec, dict):
        return errors + ["ews.shape: spec must be a mapping"]
    for key in ("worldRef", "worldView", "stateCompiler"):
        if not nonempty_str(spec.get(key)):
            errors.append(f"ews.shape: spec.{key} is required")
    context = spec.get("context")
    if not _valid_timestamp(context.get("asOf") if isinstance(context, dict) else None):
        errors.append("ews.as-of: spec.context.asOf must be UTC YYYY-MM-DDTHH:MM:SSZ")
    absent = lambda key, default: default if spec.get(key) is None else spec[key]  # null counts as absent
    state = spec.get("state")
    unresolved, missing, provenance, derivation = absent("unresolved", {}), absent("missing", []), absent("provenance", {}), absent("derivation", {})
    if not isinstance(state, dict):
        errors.append("ews.shape: spec.state must be a mapping")
    if not isinstance(unresolved, dict):
        errors.append("ews.shape: spec.unresolved must be a mapping")
    if not (isinstance(missing, list) and all(isinstance(x, str) for x in missing)):
        errors.append("ews.shape: spec.missing must be a list of strings")
    elif len(set(missing)) != len(missing):
        errors.append("ews.shape: spec.missing has duplicate entries")
    id_list = lambda v: isinstance(v, list) and all(isinstance(x, str) for x in v)
    if not isinstance(provenance, dict):
        errors.append("ews.shape: spec.provenance must be a mapping")
    else:
        for key, value in provenance.items():  # a per-subject field maps subjects to id lists (section 12.3)
            if not id_list(value) and not (isinstance(value, dict) and all(id_list(v) for v in value.values())):
                errors.append(f"ews.shape: provenance.{key} must be a list of observation ids")
    if not isinstance(derivation, dict):
        errors.append("ews.shape: spec.derivation must be a mapping")
    structural = ("ews.as-of:", "schema.unknown-field:", "extension.block:")
    if any(not e.startswith(structural) for e in errors) or not (isinstance(state, dict) and isinstance(unresolved, dict) and isinstance(missing, list)
                                                                and isinstance(provenance, dict) and isinstance(derivation, dict)):
        return errors

    if spec["worldRef"] != world_ref:
        errors.append(f"ews.world-ref: spec.worldRef must be {world_ref}")
    prefix = f"{world_ref}#"
    if not spec["stateCompiler"].startswith(prefix):
        return errors + [f"ews.world-ref: spec.stateCompiler must have the form {prefix}<asset path>"]  # a reference to another World
    compiler_rel = spec["stateCompiler"][len(prefix):]
    try:
        compiler = load_compiler(world_root, manifest, compiler_rel)
    except OWPError as exc:
        return errors + [str(exc)]
    view = js_string(compiler["worldViewRef"]) if "worldViewRef" in compiler else "undefined"
    if spec["worldView"] != f"{prefix}{view}":
        errors.append("ews.world-view: spec.worldView must be the View compiled by spec.stateCompiler")

    fields, field_errors = output_schema_fields(world_root, compiler, compiler_rel)
    errors += field_errors
    per_subject, latent = output_lists(compiler)
    for field in fields or []:
        places = (field in state) + (field in unresolved) + missing.count(field)
        if field in per_subject and field in state and field in unresolved and field not in missing:
            continue  # subjects split between state and unresolved (section 12.3)
        if places != 1:
            errors.append(f"ews.field-placement: field {field!r} must appear in exactly one of state, unresolved, missing (found {places})")
    for field in [f for f in fields or [] if f in per_subject]:
        for name, sec in (("state", state), ("unresolved", unresolved), ("provenance", provenance)):
            if field in sec and not isinstance(sec[field], dict):
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
        elif not isinstance(record, dict) or not (isinstance(record.get("kind"), str) and record["kind"] in ("estimate", "aggregate", "classify")):
            errors.append(f"ews.derivation: derivation of {field!r} must have kind estimate, aggregate, or classify")
        elif field not in state and field not in unresolved:
            errors.append(f"ews.derivation: derivation for {field!r}, which has no value")
    for field in dict.fromkeys(list(state) + list(unresolved) + missing) if fields is not None else []:
        if field not in fields:
            errors.append(f"ews.field-unknown: field {field!r} is not an EWS field of the State Compiler")
    for field, alternatives in unresolved.items():
        groups = alternatives.items() if field in per_subject and isinstance(alternatives, dict) else [(None, alternatives)]
        for subject, alts in groups:
            if not isinstance(alts, list) or len(_distinct(alts)) < 2:
                where = f"{field!r}" if subject is None else f"{field!r} subject {subject!r}"
                errors.append(f"ews.unresolved-alternatives: unresolved field {where} must retain at least two distinct alternatives")
    present = list(dict.fromkeys(list(state) + list(unresolved)))
    for field in provenance:
        if field not in present:
            errors.append(f"ews.provenance-orphan: provenance for {field!r} which has no value")
    if compiler.get("traceRequired") is True:
        for field in present:
            ids = provenance.get(field)
            # an aggregate over no observations (a count of 0) has an empty provenance list (section 12.4)
            empty_ok = isinstance(derivation.get(field), dict) and derivation[field].get("kind") == "aggregate"
            traced = lambda v: isinstance(v, list) and (bool(v) or empty_ok)
            if field in per_subject and isinstance(ids, dict):
                subjects = set(state[field] if isinstance(state.get(field), dict) else {}) | set(unresolved[field] if isinstance(unresolved.get(field), dict) else {})
                for subject in sorted(subjects):
                    if not traced(ids.get(subject)):
                        errors.append(f"ews.provenance-required: traceRequired: field {field!r} subject {subject!r} has no provenance")
            elif not traced(ids):
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


def ews_differences(expected: dict[str, Any], actual: dict[str, Any]) -> list[str]:
    """Where two EWS documents differ in their comparable form, one line per field (tooling)."""
    a, b = canonical(expected), canonical(actual)
    out: list[str] = []
    for part in a:
        x, y = a[part], b[part]
        if json_equal(x, y):
            continue
        if isinstance(x, dict) and isinstance(y, dict):
            for key in sorted(set(x) | set(y)):
                if key not in x or key not in y or not json_equal(x[key], y[key]):
                    out.append(f"{part}.{key}: expected {json.dumps(x.get(key), ensure_ascii=False)}, compiled {json.dumps(y.get(key), ensure_ascii=False)}")
        else:
            out.append(f"{part}: expected {json.dumps(x, ensure_ascii=False)}, compiled {json.dumps(y, ensure_ascii=False)}")
    return out
