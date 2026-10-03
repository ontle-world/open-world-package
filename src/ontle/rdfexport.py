"""RDF for OWP documents in the OWP vocabulary (vocab/owp): IRIs for packages and assets, and an EWS as Turtle 1.2.

An EWS becomes an owp:EffectiveWorldState. Each of its values (each alternative of an unresolved one, each element
of a list, each subject of a per-subject field) is an owp:StateValue that reifies the triple (subject, bound property,
value) without asserting it, and carries the field, its resolution, the observations it came from
(prov:wasDerivedFrom), and, for a latent field, its derivation. When the World's SemanticBinding gives a field a
single-step path and its subjects IRIs, the triple term names them; otherwise the value is given with rdf:value.
This is tooling output: OWP conformance is about the EWS YAML/JSON document (spec section 12).
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any
from urllib.parse import quote

OWP = "https://w3id.org/owp/ns#"
PACKAGE_BASE = "https://w3id.org/owp/pkg/"
SPEC_BASE = "https://w3id.org/owp/spec/"
_FRAGMENT_SAFE = "/-._~!$&'()*+,;=:@"


def package_iri(identity: str) -> str:
    """`<namespace>/<name>@<version>` -> https://w3id.org/owp/pkg/<namespace>/<name>/<version>."""
    name_part, _, version = identity.rpartition("@")
    namespace, _, name = name_part.partition("/")
    return PACKAGE_BASE + "/".join(quote(p, safe="-._~") for p in (namespace, name, version))


def asset_iri(ref: str) -> str:
    """`<package>#<asset path>` -> the package IRI with the path as its fragment."""
    package, _, path = ref.partition("#")
    return package_iri(package) + ("#" + quote(path, safe=_FRAGMENT_SAFE) if path else "")


def spec_iri(api_version: str) -> str:
    """`openworld/v1alpha1` -> https://w3id.org/owp/spec/v1alpha1 (the value of dct:conformsTo)."""
    return SPEC_BASE + api_version.rpartition("/")[2]


def _literal(v: Any) -> str:
    if isinstance(v, bool):
        return f'"{str(v).lower()}"^^xsd:boolean'
    if isinstance(v, int):
        return f'"{v}"^^xsd:integer'
    if isinstance(v, float):
        if math.isfinite(v) and "e" not in repr(v).lower():
            return f'"{repr(v)}"^^xsd:decimal'
        return f'"{repr(v)}"^^xsd:double'
    if isinstance(v, str):
        return json.dumps(v, ensure_ascii=False)
    return json.dumps(json.dumps(v, sort_keys=True, separators=(",", ":"), ensure_ascii=False)) + "^^rdf:JSON"


def _iri(s: str) -> str:
    return f"<{s}>"


def ews_turtle(world_root: Path, world_manifest: dict[str, Any], ews: dict[str, Any], observations: dict[str, Any],
               binding: dict[str, Any] | None, prefixes: dict[str, str]) -> str:
    """The EWS as Turtle 1.2. `binding` and `prefixes` come from the World's SemanticBinding and its dependency ontologies."""
    from .binding import subject_iri
    from .ews import binding_form, output_lists
    from .ontology import expand
    from .yamlio import load_yaml

    spec = ews.get("spec") or {}
    compiler_path = (spec.get("stateCompiler") or "").partition("#")[2]
    try:
        compiler = (load_yaml((world_root / compiler_path).read_text(encoding="utf-8")) or {}).get("spec") or {} if compiler_path else {}
    except OSError:
        compiler = {}
    bindings = compiler.get("bindings") if isinstance(compiler.get("bindings"), dict) else {}
    per_subject, _ = output_lists(compiler)
    bspec = (binding or {}).get("spec") or {}
    field_bindings = bspec.get("fields") if isinstance(bspec.get("fields"), dict) else {}
    subject_rules = bspec.get("subjects") if isinstance(bspec.get("subjects"), dict) else {}
    obs_by_id = {o.get("id"): o for o in ((observations.get("spec") or {}).get("observations") or []) if isinstance(o, dict)}

    def source_type(field: str, seen: tuple[str, ...] = ()) -> str | None:
        b = bindings.get(field)
        form = binding_form(b) if b is not None else None
        if form == "observe":
            return b.get("from")
        if form in ("estimate", "aggregate"):
            return b[form].get("from")
        if form == "classify" and field not in seen:
            return source_type(b["classify"].get("input"), seen + (field,))
        return None

    def property_of(field: str) -> str | None:
        fb = field_bindings.get(field)
        path = fb.get("path") if isinstance(fb, dict) and isinstance(fb.get("path"), list) else []
        return expand(path[0], prefixes) if len(path) == 1 and isinstance(path[0], str) else None

    lines = ['VERSION "1.2"',
             "@prefix owp: <https://w3id.org/owp/ns#> .",
             "@prefix prov: <http://www.w3.org/ns/prov#> .",
             "@prefix dct: <http://purl.org/dc/terms/> .",
             "@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .",
             "@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .", ""]
    api = ews.get("apiVersion") or world_manifest.get("apiVersion") or ""
    ews_lines = ["_:ews a owp:EffectiveWorldState"]
    if api:
        ews_lines.append(f"dct:conformsTo {_iri(spec_iri(api))}")
    for key, prop in (("worldRef", "owp:worldRef"), ("worldView", "owp:worldView"), ("stateCompiler", "owp:stateCompiler")):
        if isinstance(spec.get(key), str):
            ews_lines.append(f"{prop} {_iri(asset_iri(spec[key]))}")
    as_of = (spec.get("context") or {}).get("asOf")
    if isinstance(as_of, str):
        ews_lines.append(f'owp:asOf "{as_of}"^^xsd:dateTimeStamp')
    for field in spec.get("missing") or []:
        ews_lines.append(f"owp:missingField {_literal(field)}")
    ews_lines.append("prov:wasGeneratedBy _:run")
    lines.append(" ;\n  ".join(ews_lines) + " .")
    if compiler_path and isinstance(spec.get("stateCompiler"), str):
        lines.append(f"_:run a owp:Compilation ; prov:qualifiedAssociation [ a prov:Association ; prov:hadPlan {_iri(asset_iri(spec['stateCompiler']))} ] .")
    else:
        lines.append("_:run a owp:Compilation .")

    obs_nodes: dict[str, str] = {}

    def obs_node(oid: str) -> str:
        if oid not in obs_nodes:
            obs_nodes[oid] = f"_:o{len(obs_nodes) + 1}"
        return obs_nodes[oid]

    derivations = spec.get("derivation") or {}
    derivation_nodes: dict[str, str] = {}
    for i, (field, d) in enumerate(sorted(derivations.items())):
        node = f"_:d{i + 1}"
        derivation_nodes[field] = node
        kind = d.get("kind") if isinstance(d, dict) else None
        parts = [f"{node} a owp:{ {'estimate': 'Estimate', 'aggregate': 'Aggregate', 'classify': 'Classification'}.get(kind, 'Derivation') }"]
        if kind == "aggregate":
            parts.append(f"owp:function {_literal(d.get('function'))}")
            if "window" in d:
                parts.append(f"owp:window {_literal(d['window'])}")
        if kind == "classify" and isinstance(d.get("criterion"), dict):
            crit = d["criterion"]
            cparts = ["a owp:Criterion", f"dct:identifier {_literal(crit.get('id'))}"]
            if "version" in crit:
                cparts.append(f"dct:hasVersion {_literal(crit['version'])}")
            if "basis" in crit:
                cparts.append(f"dct:source {_literal(crit['basis'])}")
            parts.append("owp:criterion [ " + " ; ".join(cparts) + " ]")
        lines.append(" ;\n  ".join(parts) + " .")

    counter = 0

    def emit(field: str, subject: str | None, value: Any, resolution: str, ids: list[str]) -> None:
        nonlocal counter
        values = value if isinstance(value, list) and resolution == "resolved" and not isinstance(value, dict) else [value]
        for v in values:
            counter += 1
            node = f"_:v{counter}"
            parts = [f"{node} a owp:StateValue", "owp:inState _:ews", f"owp:field {_literal(field)}"]
            if subject is not None:
                parts.append(f"owp:subjectKey {_literal(subject)}")
            parts.append(f"owp:resolution owp:{resolution}")
            prop = property_of(field)
            otype = source_type(field)
            rule = subject_rules.get(otype) if otype else None
            if prop and subject is not None and isinstance(rule, dict):
                parts.append(f"rdf:reifies <<( {_iri(subject_iri(rule, subject))} {_iri(prop)} {_literal(v)} )>>")
            else:
                parts.append(f"rdf:value {_literal(v)}")
            if ids:
                parts.append("prov:wasDerivedFrom " + " , ".join(obs_node(i) for i in ids))
            if field in derivation_nodes:
                parts.append(f"owp:derivation {derivation_nodes[field]}")
            lines.append(" ;\n  ".join(parts) + " .")

    provenance = spec.get("provenance") or {}
    for section, resolution in (("state", "resolved"), ("unresolved", "unresolved")):
        for field, value in (spec.get(section) or {}).items():
            prov = provenance.get(field)
            if field in per_subject and isinstance(value, dict):
                for subject, v in value.items():
                    ids = list((prov or {}).get(subject) or []) if isinstance(prov, dict) else []
                    for alt in (v if resolution == "unresolved" else [v]):
                        emit(field, subject, alt, resolution, ids)
            else:
                ids = list(prov or []) if isinstance(prov, list) else []
                for alt in (value if resolution == "unresolved" else [value]):
                    emit(field, None, alt, resolution, ids)

    for oid, node in obs_nodes.items():
        o = obs_by_id.get(oid) or {}
        parts = [f"{node} a owp:Observation", f"dct:identifier {_literal(oid)}"]
        if isinstance(o.get("type"), str):
            parts.append(f"owp:observationType {_literal(o['type'])}")
        if isinstance(o.get("observedAt"), str):
            parts.append(f'owp:observedAt "{o["observedAt"]}"^^xsd:dateTimeStamp')
        if isinstance(o.get("estimatedBy"), str):
            parts.append(f"owp:estimatedBy {_literal(o['estimatedBy'])}")
        lines.append(" ;\n  ".join(parts) + " .")
    if obs_nodes:
        lines.append("_:run prov:used " + " , ".join(obs_nodes.values()) + " .")
    return "\n".join(lines) + "\n"
