"""Mappings from OWP to neighbouring runtime standards (docs/interop/). Tooling output, informative.

- mcp_description: what a Model Context Protocol server built on a World exposes. Its Views and State Compilers
  are resources, the EWS of a State Compiler at a time is a resource template, and its actions are tools.
- ews_ngsi_ld: an EWS as NGSI-LD entities. Each per-subject field becomes an attribute of the subject's entity, named
  by its bound property IRI. An unresolved field gives one attribute instance per alternative (datasetId), and a coded
  value gives a VocabProperty. Fields that are not per subject go on one entity for the EWS.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .core import load_manifest, local_assets
from .rdfexport import asset_iri, package_iri

NGSI_LD_CORE_CONTEXT = "https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context-v1.8.jsonld"


def _identity(manifest: dict[str, Any]) -> str:
    md = manifest.get("metadata") or {}
    return f"{md.get('namespace')}/{md.get('name')}@{md.get('version')}"


def ews_uri(identity: str, compiler_path: str) -> str:
    """owp-ews://<namespace>/<name>/<version>/<compiler path>: the EWS a State Compiler produces (an MCP resource URI;
    the asOf goes in the query). Not a package IRI: the fragment of a package IRI cannot carry a query."""
    return package_iri(identity).replace("https://w3id.org/owp/pkg/", "owp-ews://", 1) + "/" + compiler_path


def mcp_description(world_path: str | Path) -> dict[str, Any]:
    """Resources, resource templates, and tools an MCP server for this World exposes (MCP 2025-06-18 shapes)."""
    root, manifest = load_manifest(world_path)
    identity = _identity(manifest)
    spec = manifest.get("spec") or {}
    kinds, docs = local_assets(root, spec)
    md = manifest.get("metadata") or {}
    resources: list[dict[str, Any]] = [{
        "uri": package_iri(identity), "name": "world", "title": md.get("title") or identity, "mimeType": "application/yaml",
        "description": ((spec.get("world") or {}).get("definition") or "The World package manifest."),
    }]
    templates: list[dict[str, Any]] = []
    for rel, kind in sorted(kinds.items()):
        dspec = (docs.get(rel) or {}).get("spec") or {}
        if kind == "WorldViewProfile":
            purpose = dspec.get("purpose") or {}
            what = ", ".join(f"{k} {purpose[k]}" for k in ("task", "objective") if purpose.get(k)) or "a projection of the World"
            resources.append({"uri": asset_iri(f"{identity}#{rel}"), "name": f"view:{Path(rel).stem}", "mimeType": "application/yaml",
                              "description": f"World View ({what}): what the World looks like for this purpose."})
        elif kind == "StateCompilerProfile":
            resources.append({"uri": asset_iri(f"{identity}#{rel}"), "name": f"compiler:{Path(rel).stem}", "mimeType": "application/yaml",
                              "description": f"State Compiler for {dspec.get('worldViewRef')}: how observations become its EWS."})
            templates.append({
                "uriTemplate": ews_uri(identity, rel) + "?asOf={asOf}", "name": f"ews:{Path(rel).stem}", "mimeType": "application/yaml",
                "description": (f"Effective World State of {dspec.get('worldViewRef')} at asOf (UTC, YYYY-MM-DDTHH:MM:SSZ). "
                                "Values the newest observations disagree on are under unresolved, fields without observations under "
                                "missing, and every value lists the observations it came from."),
            })
    commits = [(rel, (docs.get(rel) or {}).get("spec") or {}) for rel, k in sorted(kinds.items()) if k == "CommitContract"]
    verifications = [rel for rel, k in sorted(kinds.items()) if k == "EffectVerificationProfile"]
    tools: list[dict[str, Any]] = []
    for rel, kind in sorted(kinds.items()):
        if kind != "ActionBindingProfile":
            continue
        dspec = (docs.get(rel) or {}).get("spec") or {}
        names = list(dspec.get("actions") or []) + list((dspec.get("actionSpace") or {}).get("commands") or [])
        for name in names:
            if not isinstance(name, str):
                continue
            meta: dict[str, Any] = {"owp/actionBinding": asset_iri(f"{identity}#{rel}")}
            if dspec.get("execution"):
                meta["owp/execution"] = dspec["execution"]
            if commits:
                meta["owp/commitContracts"] = [asset_iri(f"{identity}#{c}") for c, _ in commits]
                meta["owp/approvalRequired"] = any(bool(c.get("approvalRequired")) for _, c in commits)
            if verifications:
                meta["owp/effectVerification"] = [asset_iri(f"{identity}#{v}") for v in verifications]
            tools.append({
                "name": name,
                "description": (f"Action {name} of {identity}. A successful call is not a committed change: the World's commit "
                                "contract and effect verification decide that." if commits or verifications else f"Action {name} of {identity}."),
                "inputSchema": {"type": "object"},
                "annotations": {"readOnlyHint": False, "openWorldHint": True},
                "_meta": meta,
            })
    return {"server": {"name": identity, "title": md.get("title") or identity},
            "resources": resources, "resourceTemplates": templates, "tools": tools}


def ews_ngsi_ld(world_root: Path, world_manifest: dict[str, Any], ews: dict[str, Any], observations: dict[str, Any],
                binding: dict[str, Any] | None, prefixes: dict[str, str]) -> list[dict[str, Any]]:
    """NGSI-LD entities for an EWS (normalized form). Field names are mapped to IRIs by the binding's @context."""
    from .binding import jsonld_context, subject_iri, value_iri
    from .ews import binding_form, output_lists
    from .ontology import expand
    from .yamlio import load_yaml

    spec = ews.get("spec") or {}
    compiler_path = (spec.get("stateCompiler") or "").partition("#")[2]
    try:
        compiler = ((load_yaml((world_root / compiler_path).read_text(encoding="utf-8")) or {}).get("spec") or {}) if compiler_path else {}
    except OSError:
        compiler = {}
    bindings = compiler.get("bindings") if isinstance(compiler.get("bindings"), dict) else {}
    per_subject, _ = output_lists(compiler)
    bspec = (binding or {}).get("spec") or {}
    fields_b = bspec.get("fields") if isinstance(bspec.get("fields"), dict) else {}
    subjects = bspec.get("subjects") if isinstance(bspec.get("subjects"), dict) else {}
    otypes = bspec.get("observationTypes") if isinstance(bspec.get("observationTypes"), dict) else {}
    observed_at = {o.get("id"): o.get("observedAt") for o in ((observations.get("spec") or {}).get("observations") or []) if isinstance(o, dict)}
    context = [jsonld_context(binding, prefixes) if binding else {}, NGSI_LD_CORE_CONTEXT]
    identity = _identity(world_manifest)

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

    def entity_id(otype: str | None, subject: str) -> str:
        rule = subjects.get(otype) if otype else None
        if isinstance(rule, dict):
            return subject_iri(rule, subject)
        return f"urn:ngsi-ld:{(otype or 'Subject').replace(':', '-')}:{subject}"

    def attribute(field: str, value: Any, ids: list[str], dataset: str | None) -> dict[str, Any]:
        fb = fields_b.get(field)
        coded = fb.get("values") if isinstance(fb, dict) and isinstance(fb.get("values"), dict) else None
        concept = value_iri(coded, value, prefixes) if coded else None
        attr: dict[str, Any] = {"type": "VocabProperty", "vocab": concept} if concept else {"type": "Property", "value": value}
        times = sorted(t for t in (observed_at.get(i) for i in ids) if isinstance(t, str))
        if times:
            attr["observedAt"] = times[-1]
        if dataset:
            attr["datasetId"] = dataset
        if ids:
            attr["provenance"] = {"type": "Property", "value": ids}
        derivation = (spec.get("derivation") or {}).get(field)
        if isinstance(derivation, dict):
            attr["derivation"] = {"type": "Property", "value": derivation.get("kind")}
        return attr

    entities: dict[str, dict[str, Any]] = {}
    view_entity = f"urn:ngsi-ld:EffectiveWorldState:{identity.replace('/', ':').replace('@', ':')}:{Path((spec.get('worldView') or '').partition('#')[2]).stem}"
    provenance = spec.get("provenance") or {}

    def attribute_name(field: str) -> str:
        """The bound property's IRI; otherwise the field name with '.' as '_' (NGSI-LD names exclude '.')."""
        fb = fields_b.get(field)
        path = fb.get("path") if isinstance(fb, dict) and isinstance(fb.get("path"), list) else []
        iri = expand(path[-1], prefixes) if path and isinstance(path[-1], str) else None
        return iri or field.replace(".", "_")

    def put(eid: str, etype: str, field: str, attr: Any) -> None:
        field = attribute_name(field)
        e = entities.setdefault(eid, {"id": eid, "type": etype})
        if field in e:  # several alternatives: an array of attribute instances
            e[field] = (e[field] if isinstance(e[field], list) else [e[field]]) + [attr]
        else:
            e[field] = attr

    for section in ("state", "unresolved"):
        for field, value in (spec.get(section) or {}).items():
            prov = provenance.get(field)
            otype = source_type(field)
            etype_iri = expand(otypes[otype], prefixes) if otype and isinstance(otypes.get(otype), str) else None
            etype = etype_iri or (otypes.get(otype) if otype else None) or "Subject"
            groups = value.items() if field in per_subject and isinstance(value, dict) else [(None, value)]
            for subject, v in groups:
                ids = list((prov or {}).get(subject) or []) if subject is not None and isinstance(prov, dict) else list(prov or []) if isinstance(prov, list) else []
                eid, et = (entity_id(otype, subject), etype) if subject is not None else (view_entity, "EffectiveWorldState")
                if section == "unresolved":
                    for n, alt in enumerate(v, start=1):
                        put(eid, et, field, attribute(field, alt, ids, f"urn:ngsi-ld:Dataset:alternative-{n}"))
                else:
                    put(eid, et, field, attribute(field, v, ids, None))
    out = []
    for eid in sorted(entities):
        out.append({**entities[eid], "@context": context})
    return out
