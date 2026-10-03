"""Experimental asset kinds (spec Appendix C).

Every check here produces warnings, so experimental kinds never change whether
a package is valid. Extension rules (section 13) still apply and stay errors.
The field tables mirror ``schemas/experimental/*.schema.json``.
"""
from __future__ import annotations

from importlib import resources
from pathlib import Path
from typing import Any

from . import structure
from .structure import EXTERNAL_REF, OPEN, VALUE, array, closed
from .yamlio import load_yaml

ASSET_METADATA = structure.ASSET_METADATA


def _document(spec_fields: dict[str, Any]) -> dict[str, Any]:
    return closed({"apiVersion": VALUE, "kind": VALUE, "metadata": ASSET_METADATA, "spec": closed(spec_fields)}, extensions=False)


CONTENT = closed({"path": VALUE, "ref": EXTERNAL_REF})

TABLES: dict[str, dict[str, Any]] = {
    "TaskSetProfile": _document({
        "task": closed({"objectiveRefs": VALUE, "workPatterns": VALUE}),
        "requires": closed({"worldRefs": VALUE, "worldViews": VALUE, "knowledge": VALUE, "actors": VALUE}),
        "workPatternRefs": VALUE,
        "mayUse": closed({"worldModels": VALUE, "capabilities": VALUE, "workflows": VALUE,
                          "scenarios": VALUE, "skills": VALUE, "tools": VALUE}),
        "produces": closed({"artifacts": VALUE}),
        "evaluationRefs": VALUE,
    }),
    "WorkPatternProfile": _document({
        "pattern": closed({"kind": VALUE, "family": VALUE}),
        "objective": VALUE,
        "inputs": closed({"semanticRoles": VALUE}),
        "outputs": closed({"semanticRoles": VALUE}),
        "inputContracts": VALUE,
        "outputContracts": VALUE,
        "requiredContracts": VALUE,
        "optionalCapabilities": VALUE,
        "graph": closed({
            "nodes": array(closed({"id": VALUE, "family": VALUE, "patternKind": VALUE, "description": VALUE})),
            "transitions": array(closed({"from": VALUE, "to": VALUE, "guard": VALUE, "event": VALUE})),
            "guards": array(closed({"id": VALUE, "description": VALUE})),
            "events": array(closed({"id": VALUE, "triggers": VALUE, "description": VALUE})),
            "loops": array(closed({"nodes": VALUE, "maxIterations": VALUE, "until": VALUE})),
        }),
        "worldRef": VALUE,
        "worldViewRef": VALUE,
        "governanceRefs": VALUE,
        "evaluationRefs": VALUE,
    }),
    "ArtifactContract": _document({
        "artifact": closed({"type": VALUE, "representation": VALUE}),
        "purposeRef": VALUE,
        "audienceRef": VALUE,
        "inputs": VALUE,
        "sourceBindings": VALUE,
        "structure": closed({"required": VALUE, "optional": VALUE}),
        "serialization": closed({"formats": VALUE}),
        "delivery": closed({"destinations": VALUE}),
        "governance": closed({"approvalRequired": VALUE, "policyRefs": VALUE}),
        "schemaRef": VALUE,
        "sourceRefs": VALUE,
        "evidenceRefs": VALUE,
        "allowedOperations": VALUE,
        "storage": closed({"kind": VALUE, "uri": VALUE}),
        "supersedes": VALUE,
        "validationRefs": VALUE,
        "evaluationRefs": VALUE,
    }),
    "ArtifactTemplate": _document({
        "artifactContractRef": VALUE,
        "format": VALUE,
        "content": CONTENT,
    }),
    "ConsumerRepresentationProfile": _document({
        "actor": closed({"kind": VALUE, "ref": VALUE}),
        "worldViewRef": VALUE,
        "representation": closed({"mode": VALUE, "freshness": OPEN, "provenance": VALUE}),
        "human": closed({"artifactContractRefs": VALUE, "presentation": VALUE, "locale": VALUE,
                         "decisionRights": VALUE, "notification": OPEN}),
        "agent": closed({"toolScope": closed({"capabilityRefs": VALUE}), "memoryScope": OPEN,
                         "feasibleActions": VALUE, "contextBudget": OPEN, "includes": VALUE}),
        "model": closed({"adapterRef": VALUE, "modalities": VALUE, "temporalWindow": OPEN}),
        "system": closed({"interfaceRefs": VALUE, "deliveryMode": VALUE, "serviceLevel": OPEN}),
    }),
    "KnowledgeAsset": _document({
        "roles": VALUE,
        "representation": VALUE,
        "format": VALUE,
        "conformsTo": closed({"ontology": VALUE, "shapes": VALUE}),
        "worldRef": VALUE,
        "snapshot": closed({"asOf": VALUE}),
        "content": CONTENT,
        "delta": closed({"base": VALUE, "format": VALUE}),
        "provenance": VALUE,
        "license": VALUE,
        "access": VALUE,
        "sensitivity": VALUE,
        "evaluationRefs": VALUE,
    }),
    "KnowledgeExtractionProfile": _document({
        "source": VALUE,
        "parameters": OPEN,
        "query": closed({"language": VALUE, "text": VALUE}),
        "observations": array(closed({
            "type": VALUE, "id": VALUE, "values": OPEN, "multi": VALUE,
            "observedAt": closed({"column": VALUE, "default": VALUE}),
        })),
    }),
    "ActorProfile": _document({
        "actorType": VALUE,
        "roleRefs": VALUE,
        "capabilityRefs": VALUE,
        "agentRef": VALUE,
        "memberOf": VALUE,
    }),
    "RoleProfile": _document({
        "permissions": array(closed({"actions": VALUE, "scope": VALUE})),
        "authorities": array(closed({"decisions": VALUE, "scope": VALUE, "ceiling": OPEN})),
        "responsibilities": VALUE,
        "accountabilities": VALUE,
    }),
    "DelegationProfile": _document({
        "delegator": VALUE,
        "delegatee": VALUE,
        "scope": VALUE,
        "permittedActions": VALUE,
        "authorityCeiling": closed({"decisions": VALUE, "limits": OPEN}),
        "validFrom": VALUE,
        "expiresAt": VALUE,
        "revocation": closed({"by": VALUE}),
        "escalation": closed({"to": VALUE, "when": VALUE}),
        "evidenceRefs": VALUE,
    }),
}

ACTOR_BLOCKS = ("human", "agent", "model", "system")


def _load_value_sets() -> dict[str, set[str]]:
    try:
        text = resources.files("ontle.vocab").joinpath("value-sets.yaml").read_text(encoding="utf-8")
    except (ModuleNotFoundError, FileNotFoundError):  # editable install: read the repository copy
        text = (Path(__file__).resolve().parents[2] / "vocab" / "value-sets.yaml").read_text(encoding="utf-8")
    return {name: set(entry["values"]) for name, entry in load_yaml(text)["valueSets"].items()}


VALUE_SETS = _load_value_sets()


def _values(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _check_value(value: Any, value_set: str, where: str, rel: str, declared: set[str],
                 errors: list[str], warnings: list[str]) -> None:
    if not isinstance(value, str):
        warnings.append(f"experimental.value: {rel}: {where} must be a string")
    elif ":" in value:
        name = value.split(":", 1)[0]
        if name not in declared:
            errors.append(f"extension.undeclared: {rel}: {where} {value!r} uses extension {name!r}, which spec.dependencies does not declare with 'as'")
    elif value not in VALUE_SETS[value_set]:
        warnings.append(f"experimental.value: {rel}: {where} {value!r} is not in the experimental value set {value_set}")


def _check_standard_value(value: Any, value_set: str, rule: str, where: str, rel: str, declared: set[str], errors: list[str]) -> None:
    """A value of a standard value set: one of its values, or a declared extension value."""
    if not isinstance(value, str):
        errors.append(f"{rule}: {rel}: {where} must be a string")
    elif ":" in value:
        name = value.split(":", 1)[0]
        if name not in declared:
            errors.append(f"extension.undeclared: {rel}: {where} {value!r} uses extension {name!r}, which spec.dependencies does not declare with 'as'")
    elif value not in VALUE_SETS[value_set]:
        errors.append(f"{rule}: {rel}: {where} {value!r} is not one of {sorted(VALUE_SETS[value_set])}")


def _check_local_ref(ref: Any, kinds: tuple[str, ...] | None, where: str, rel: str,
                     local_kinds: dict[str, str], warnings: list[str]) -> None:
    """A package-relative path must name a listed local asset (of one of ``kinds``). Cross-package refs (with '#') are not checked here."""
    if not isinstance(ref, str) or not ref:
        warnings.append(f"experimental.reference: {rel}: {where} must be a package-relative asset path")
        return
    if "#" in ref:
        return
    kind = local_kinds.get(ref)
    if kind is None:
        warnings.append(f"experimental.reference: {rel}: {where} {ref!r} is not a listed local asset")
    elif kinds is not None and kind not in kinds:
        warnings.append(f"experimental.reference: {rel}: {where} {ref!r} is a {kind}, expected {' or '.join(kinds)}")


def _file_in_package(root: Path, rel: Any) -> bool:
    from .ontology import inside_package
    return inside_package(root, rel)


def _valid_timestamp(value: Any) -> bool:
    from .ews import _valid_timestamp as valid  # local import: ews depends on core
    return valid(value)


def _delegator_grants(delegator: Any, local_kinds: dict[str, str], docs: dict[str, dict[str, Any]]) -> tuple[set[str], set[str]] | None:
    """(permitted actions, decisions) the delegator's local roles grant, or None when the delegator is not a local ActorProfile."""
    if local_kinds.get(delegator) != "ActorProfile":
        return None
    actions: set[str] = set()
    decisions: set[str] = set()
    for role in _values(((docs.get(delegator) or {}).get("spec") or {}).get("roleRefs")):
        rspec = (docs.get(role) or {}).get("spec") or {}
        for p in rspec.get("permissions") or []:
            actions |= {a for a in _values(p.get("actions") if isinstance(p, dict) else None) if isinstance(a, str)}
        for a in rspec.get("authorities") or []:
            decisions |= {d for d in _values(a.get("decisions") if isinstance(a, dict) else None) if isinstance(d, str)}
    return actions, decisions


def _check_graph(graph: dict[str, Any], rel: str, declared: set[str], errors: list[str], warnings: list[str]) -> None:
    """Work-pattern graph: unique node ids, known families, and references between nodes, guards, and events."""
    if not graph:
        return
    def ids(section: str) -> list[Any]:
        return [x.get("id") for x in graph.get(section) or [] if isinstance(x, dict)]
    nodes = ids("nodes")
    for section, seen_ids in (("nodes", nodes), ("guards", ids("guards")), ("events", ids("events"))):
        duplicates = {i for i in seen_ids if seen_ids.count(i) > 1}
        if duplicates or any(not isinstance(i, str) or not i for i in seen_ids):
            warnings.append(f"experimental.field: {rel}: spec.graph.{section} need unique string ids")
    for i, node in enumerate(graph.get("nodes") or []):
        if isinstance(node, dict):
            if "family" in node:
                _check_value(node["family"], "workNodeFamilies", f"spec.graph.nodes[{i}].family", rel, declared, errors, warnings)
            if "patternKind" in node:
                _check_value(node["patternKind"], "workPatterns", f"spec.graph.nodes[{i}].patternKind", rel, declared, errors, warnings)
    guards, events = set(ids("guards")), set(ids("events"))
    for i, t in enumerate(graph.get("transitions") or []):
        if not isinstance(t, dict):
            continue
        for end in ("from", "to"):
            if t.get(end) not in nodes:
                warnings.append(f"experimental.reference: {rel}: spec.graph.transitions[{i}].{end} {t.get(end)!r} is not a node")
        if t.get("guard") is not None and t["guard"] not in guards:
            warnings.append(f"experimental.reference: {rel}: spec.graph.transitions[{i}].guard {t['guard']!r} is not a declared guard")
        if t.get("event") is not None and t["event"] not in events:
            warnings.append(f"experimental.reference: {rel}: spec.graph.transitions[{i}].event {t['event']!r} is not a declared event")
    for i, e in enumerate(graph.get("events") or []):
        for target in _values(e.get("triggers") if isinstance(e, dict) else None):
            if target not in nodes:
                warnings.append(f"experimental.reference: {rel}: spec.graph.events[{i}].triggers {target!r} is not a node")
    for i, loop in enumerate(graph.get("loops") or []):
        if not isinstance(loop, dict):
            continue
        for node in _values(loop.get("nodes")):
            if node not in nodes:
                warnings.append(f"experimental.reference: {rel}: spec.graph.loops[{i}].nodes {node!r} is not a node")
        if loop.get("until") is not None and loop["until"] not in guards:
            warnings.append(f"experimental.reference: {rel}: spec.graph.loops[{i}].until {loop['until']!r} is not a declared guard")
        bound = loop.get("maxIterations")
        integral = isinstance(bound, int) or (isinstance(bound, float) and bound.is_integer())  # JSON data model: 1.0 == 1
        if bound is not None and (isinstance(bound, bool) or not integral or bound < 1):
            warnings.append(f"experimental.field: {rel}: spec.graph.loops[{i}].maxIterations must be a positive integer")


def experimental_issues(doc: dict[str, Any], kind: str, rel: str, root: Path, spec_manifest: dict[str, Any],
                        local_kinds: dict[str, str], declared: set[str],
                        docs: dict[str, dict[str, Any]] | None = None) -> tuple[list[str], list[str]]:
    """Errors (extension rules only) and warnings for one experimental asset document."""
    docs = docs or {}
    errors: list[str] = []
    warnings: list[str] = []
    for issue in structure.structure_errors(doc, TABLES[kind], rel, declared):
        if issue.startswith("schema.unknown-field: "):
            warnings.append("experimental.field: " + issue[len("schema.unknown-field: "):])
        else:
            errors.append(issue)
    spec = doc.get("spec") if isinstance(doc.get("spec"), dict) else {}

    def sub(name: str) -> dict[str, Any]:
        value = spec.get(name)
        return value if isinstance(value, dict) else {}

    if kind == "TaskSetProfile":
        for v in _values(sub("task").get("workPatterns")):
            _check_value(v, "workPatterns", "spec.task.workPatterns", rel, declared, errors, warnings)
        for ref in _values(sub("requires").get("worldViews")):
            _check_local_ref(ref, ("WorldViewProfile",), "spec.requires.worldViews", rel, local_kinds, warnings)
        for ref in _values(sub("requires").get("knowledge")):
            _check_local_ref(ref, ("KnowledgeAsset",), "spec.requires.knowledge", rel, local_kinds, warnings)
        for ref in _values(sub("produces").get("artifacts")):
            _check_local_ref(ref, ("ArtifactContract",), "spec.produces.artifacts", rel, local_kinds, warnings)
        for ref in _values(sub("requires").get("actors")):
            _check_local_ref(ref, ("ActorProfile", "RoleProfile"), "spec.requires.actors", rel, local_kinds, warnings)
        for ref in _values(spec.get("workPatternRefs")):
            _check_local_ref(ref, ("WorkPatternProfile",), "spec.workPatternRefs", rel, local_kinds, warnings)
        for field, kinds in (("scenarios", ("ScenarioProfile",)), ("skills", ("SkillProfile",)), ("tools", ("ToolProfile",))):
            for ref in _values(sub("mayUse").get(field)):
                _check_local_ref(ref, kinds, f"spec.mayUse.{field}", rel, local_kinds, warnings)
    elif kind == "WorkPatternProfile":
        if "kind" not in sub("pattern"):
            warnings.append(f"experimental.field: {rel}: spec.pattern.kind is required")
        else:
            _check_value(sub("pattern")["kind"], "workPatterns", "spec.pattern.kind", rel, declared, errors, warnings)
        if "family" in sub("pattern"):
            _check_value(sub("pattern")["family"], "workNodeFamilies", "spec.pattern.family", rel, declared, errors, warnings)
        for field in ("inputContracts", "outputContracts"):
            for ref in _values(spec.get(field)):
                _check_local_ref(ref, ("ArtifactContract",), f"spec.{field}", rel, local_kinds, warnings)
        if spec.get("worldViewRef") is not None:
            _check_local_ref(spec["worldViewRef"], ("WorldViewProfile",), "spec.worldViewRef", rel, local_kinds, warnings)
        _check_graph(sub("graph"), rel, declared, errors, warnings)
    elif kind == "ArtifactContract":
        artifact = sub("artifact")
        if "type" not in artifact:
            warnings.append(f"experimental.field: {rel}: spec.artifact.type is required")
        else:
            _check_value(artifact["type"], "artifactTypes", "spec.artifact.type", rel, declared, errors, warnings)
        if "representation" in artifact:
            _check_value(artifact["representation"], "artifactRepresentations", "spec.artifact.representation", rel, declared, errors, warnings)
        for v in _values(spec.get("allowedOperations")):
            _check_value(v, "artifactOperations", "spec.allowedOperations", rel, declared, errors, warnings)
        if spec.get("schemaRef") is not None and not _file_in_package(root, spec["schemaRef"]):
            warnings.append(f"experimental.reference: {rel}: spec.schemaRef {spec['schemaRef']!r} must be a file in the package")
        from .core import PINNED_REF_RE  # local import: core imports this module
        supersedes = spec.get("supersedes")
        if supersedes is not None and not (isinstance(supersedes, str) and PINNED_REF_RE.match(supersedes)):
            warnings.append(f"experimental.field: {rel}: spec.supersedes must be a pinned <name>@<version> reference")
    elif kind == "ArtifactTemplate":
        _check_local_ref(spec.get("artifactContractRef"), ("ArtifactContract",), "spec.artifactContractRef", rel, local_kinds, warnings)
        _check_content(sub("content"), rel, root, declared, errors, warnings)
    elif kind == "ConsumerRepresentationProfile":
        actor = sub("actor").get("kind")
        if actor is None:
            warnings.append(f"experimental.field: {rel}: spec.actor.kind is required")
        else:
            _check_value(actor, "actorKinds", "spec.actor.kind", rel, declared, errors, warnings)
        _check_local_ref(spec.get("worldViewRef"), ("WorldViewProfile",), "spec.worldViewRef", rel, local_kinds, warnings)
        if sub("actor").get("ref") is not None:
            _check_local_ref(sub("actor")["ref"], ("ActorProfile",), "spec.actor.ref", rel, local_kinds, warnings)
        present = [b for b in ACTOR_BLOCKS if b in spec]
        if isinstance(actor, str) and actor in ACTOR_BLOCKS and present not in ([], [actor]):
            warnings.append(f"experimental.field: {rel}: only the spec.{actor} block may be present for actor kind {actor} (found {', '.join(present)})")
        for ref in _values(sub("human").get("artifactContractRefs")):
            _check_local_ref(ref, ("ArtifactContract",), "spec.human.artifactContractRefs", rel, local_kinds, warnings)
        agent = sub("agent")
        tool_scope = agent.get("toolScope") if isinstance(agent.get("toolScope"), dict) else {}
        for ref in _values(tool_scope.get("capabilityRefs")):
            _check_local_ref(ref, None, "spec.agent.toolScope.capabilityRefs", rel, local_kinds, warnings)
        if "model" in spec:
            _check_local_ref(sub("model").get("adapterRef"), ("RepresentationAdapterProfile",), "spec.model.adapterRef", rel, local_kinds, warnings)
        for ref in _values(sub("system").get("interfaceRefs")):
            _check_local_ref(ref, None, "spec.system.interfaceRefs", rel, local_kinds, warnings)
    elif kind == "KnowledgeAsset":
        for v in _values(spec.get("roles")):
            _check_value(v, "knowledgeRoles", "spec.roles", rel, declared, errors, warnings)
        if "representation" in spec:
            _check_value(spec["representation"], "knowledgeRepresentations", "spec.representation", rel, declared, errors, warnings)
        ontology = sub("conformsTo").get("ontology")
        if ontology is None and spec.get("representation") == "graph":
            warnings.append(f"experimental.graph-ontology: {rel}: a graph KnowledgeAsset is an A-box; declare the OntologyPackage "
                            "that is its T-box in spec.conformsTo.ontology")
        if ontology is not None:
            dependency_refs = {d.get("ref") if isinstance(d, dict) else d for d in spec_manifest.get("dependencies") or []}
            if ontology not in dependency_refs:
                warnings.append(f"experimental.reference: {rel}: spec.conformsTo.ontology {ontology!r} must also be listed in spec.dependencies")
        _check_content(sub("content"), rel, root, declared, errors, warnings)
    elif kind == "ActorProfile":
        if "actorType" not in spec:
            warnings.append(f"experimental.field: {rel}: spec.actorType is required")
        else:
            _check_value(spec["actorType"], "actorTypes", "spec.actorType", rel, declared, errors, warnings)
        for ref in _values(spec.get("roleRefs")):
            _check_local_ref(ref, ("RoleProfile",), "spec.roleRefs", rel, local_kinds, warnings)
        for ref in _values(spec.get("capabilityRefs")):
            _check_local_ref(ref, ("CapabilityContract",), "spec.capabilityRefs", rel, local_kinds, warnings)
        if spec.get("agentRef") is not None:
            _check_local_ref(spec["agentRef"], ("AgentProfile",), "spec.agentRef", rel, local_kinds, warnings)
        for ref in _values(spec.get("memberOf")):
            _check_local_ref(ref, ("ActorProfile",), "spec.memberOf", rel, local_kinds, warnings)
    elif kind == "DelegationProfile":
        for field in ("delegator", "delegatee"):
            _check_local_ref(spec.get(field), ("ActorProfile",), f"spec.{field}", rel, local_kinds, warnings)
        for field in ("by",):
            for ref in _values(sub("revocation").get(field)):
                _check_local_ref(ref, ("ActorProfile",), "spec.revocation.by", rel, local_kinds, warnings)
        for ref in _values(sub("escalation").get("to")):
            _check_local_ref(ref, ("ActorProfile",), "spec.escalation.to", rel, local_kinds, warnings)
        start, end = spec.get("validFrom"), spec.get("expiresAt")
        for field, value in (("validFrom", start), ("expiresAt", end)):
            if value is not None and not _valid_timestamp(value):
                warnings.append(f"experimental.field: {rel}: spec.{field} must be UTC YYYY-MM-DDTHH:MM:SSZ")
        if _valid_timestamp(start) and _valid_timestamp(end) and not start < end:
            warnings.append(f"experimental.field: {rel}: spec.validFrom must be before spec.expiresAt")
        granted = _delegator_grants(spec.get("delegator"), local_kinds, docs)
        if granted is not None:
            actions, decisions = granted
            over = [a for a in _values(spec.get("permittedActions")) if a not in actions | decisions]
            over += [d for d in _values(sub("authorityCeiling").get("decisions")) if d not in decisions]
            if over:
                warnings.append(f"experimental.delegation-exceeds-authority: {rel}: delegates {', '.join(map(str, over))}, which the delegator's roles do not grant")
    elif kind == "KnowledgeExtractionProfile":
        _check_local_ref(spec.get("source"), ("KnowledgeAsset",), "spec.source", rel, local_kinds, warnings)
        if "language" not in sub("query"):
            warnings.append(f"experimental.field: {rel}: spec.query.language is required")
        else:
            _check_value(sub("query")["language"], "queryLanguages", "spec.query.language", rel, declared, errors, warnings)
        templates = spec.get("observations")
        if not isinstance(templates, list) or not templates:
            warnings.append(f"experimental.field: {rel}: spec.observations must be a non-empty list")
        for i, template in enumerate(templates if isinstance(templates, list) else []):
            if not (isinstance(template, dict) and isinstance(template.get("type"), str) and isinstance(template.get("id"), list)
                    and template["id"] and isinstance(template.get("values"), dict) and template["values"]):
                warnings.append(f"experimental.field: {rel}: spec.observations[{i}] needs type, a non-empty id column list, and a values mapping")
    return errors, warnings


def _check_content(content: dict[str, Any], rel: str, root: Path, declared: set[str],
                   errors: list[str], warnings: list[str]) -> None:
    if not content:
        return
    if ("path" in content) == ("ref" in content):
        warnings.append(f"experimental.field: {rel}: spec.content must declare exactly one of path or ref")
        return
    if "path" in content:
        path = content["path"]
        if not isinstance(path, str) or not (root / path).is_file():
            warnings.append(f"experimental.reference: {rel}: spec.content.path {path!r} does not exist in the package")
        return
    ref_errors, ref_warnings = structure.external_ref_issues(content["ref"], f"{rel}: spec.content.ref", declared)
    for issue in ref_errors:
        if issue.startswith("extension.undeclared: "):
            errors.append(issue)
        else:
            warnings.append("experimental.field: " + issue.split(": ", 1)[1])
    warnings.extend(ref_warnings)


# --- experimental fields of standard kinds (spec Appendix C.4) ------------------

def standard_kind_checks(doc: dict[str, Any], kind: str, rel: str, root: Path, local_kinds: dict[str, str],
                           declared: set[str]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    spec = doc.get("spec") if isinstance(doc.get("spec"), dict) else {}

    def sub(name: str) -> dict[str, Any]:
        value = spec.get(name)
        return value if isinstance(value, dict) else {}

    if kind == "WorldViewProfile":
        for field, kinds in (("actorRef", ("ActorProfile",)), ("taskRef", ("TaskSetProfile",))):
            if sub("conditioning").get(field) is not None:
                _check_local_ref(sub("conditioning")[field], kinds, f"spec.conditioning.{field}", rel, local_kinds, warnings)
        for ref in _values(sub("conditioning").get("roleRefs")):
            _check_local_ref(ref, ("RoleProfile",), "spec.conditioning.roleRefs", rel, local_kinds, warnings)
    elif kind == "EvaluationProfile":
        # Standard fields (spec section 15.1): errors.
        if "assessmentKind" in spec:
            _check_standard_value(spec["assessmentKind"], "assessmentKinds", "evaluation.assessment-kind", "spec.assessmentKind", rel, declared, errors)
        if "kind" in sub("subject"):
            _check_standard_value(sub("subject")["kind"], "evaluationSubjects", "evaluation.subject", "spec.subject.kind", rel, declared, errors)
        subject_ref = sub("subject").get("ref")
        if subject_ref is not None and "#" not in str(subject_ref) and "@" not in str(subject_ref) and subject_ref not in local_kinds:
            errors.append(f"evaluation.subject: {rel}: spec.subject.ref {subject_ref!r} is neither a listed local asset nor a package or asset reference")
        verifier = spec.get("verifierRef")
        if verifier is not None:
            from .core import PINNED_REF_RE  # local import: core imports this module
            if not (isinstance(verifier, str) and ("@" in verifier and PINNED_REF_RE.match(verifier) or local_kinds.get(verifier) == "VerifierProfile")):
                errors.append(f"evaluation.verifier-ref: {rel}: spec.verifierRef must be a local VerifierProfile or a pinned <name>@<version>")
        if spec.get("resultSchemaRef") is not None and not _file_in_package(root, spec["resultSchemaRef"]):
            errors.append(f"evaluation.result-schema: {rel}: spec.resultSchemaRef {spec['resultSchemaRef']!r} must be a file in the package")
        # Experimental field (Appendix C.4): warning.
        if spec.get("evaluatorRef") is not None:
            _check_local_ref(spec["evaluatorRef"], ("ActorProfile",), "spec.evaluatorRef", rel, local_kinds, warnings)
    elif kind == "ScenarioProfile":
        # Standard fields (spec section 15.2): errors.
        if "kind" in sub("engine"):
            _check_standard_value(sub("engine")["kind"], "scenarioEngines", "scenario.engine-kind", "spec.engine.kind", rel, declared, errors)
        baseline = spec.get("baselineStateRef")
        if baseline is not None and "://" not in str(baseline) and "#" not in str(baseline) and not _file_in_package(root, baseline):
            errors.append(f"scenario.baseline-ref: {rel}: spec.baselineStateRef {baseline!r} must be a file in the package or a URI")
        confidence = spec.get("confidence")
        if confidence is not None and (isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1):
            errors.append(f"scenario.confidence: {rel}: spec.confidence must be a number from 0 to 1")
    return errors, warnings


# --- World View specialization (experimental fields of WorldViewProfile) -----

def view_specialization_warnings(local_kinds: dict[str, str], docs: dict[str, dict[str, Any]]) -> list[str]:
    warnings: list[str] = []
    for rel, kind in sorted(local_kinds.items()):
        if kind != "WorldViewProfile":
            continue
        spec = (docs.get(rel) or {}).get("spec") or {}
        base = spec.get("specializes") if isinstance(spec, dict) else None
        if base is None:
            continue
        if local_kinds.get(base) != "WorldViewProfile":
            warnings.append(f"experimental.reference: {rel}: spec.specializes {base!r} must be a local WorldViewProfile asset")
            continue
        seen = [rel]
        current = base
        while current is not None:
            if current in seen:
                warnings.append(f"experimental.reference: {rel}: spec.specializes forms a cycle: {' -> '.join(seen + [current])}")
                break
            seen.append(current)
            nxt = ((docs.get(current) or {}).get("spec") or {}).get("specializes")
            current = nxt if local_kinds.get(nxt) == "WorldViewProfile" else None
    return warnings


def resolve_view(rel: str, docs: dict[str, dict[str, Any]], local_kinds: dict[str, str], _seen: tuple[str, ...] = ()) -> dict[str, Any]:
    """The View's spec with `specializes` applied: include = base ∪ include − exclude; purpose and conditioning override key by key."""
    spec = dict((docs.get(rel) or {}).get("spec") or {})
    base = spec.pop("specializes", None)
    if base is None or local_kinds.get(base) != "WorldViewProfile" or base in _seen + (rel,):
        projection = dict(spec.get("projection") or {})
        exclude = set(projection.pop("exclude", []) or [])
        projection["include"] = [x for x in projection.get("include", []) or [] if x not in exclude]
        spec["projection"] = projection
        return spec
    parent = resolve_view(base, docs, local_kinds, _seen + (rel,))
    merged: dict[str, Any] = dict(parent)
    for key, value in spec.items():
        if key in {"purpose", "conditioning"} and isinstance(value, dict):
            merged[key] = {**(parent.get(key) or {}), **value}
        elif key == "projection" and isinstance(value, dict):
            projection = {**(parent.get("projection") or {}), **{k: v for k, v in value.items() if k not in {"include", "exclude"}}}
            include = list(parent.get("projection", {}).get("include", []) or [])
            include += [x for x in value.get("include", []) or [] if x not in include]
            exclude = set(value.get("exclude", []) or [])
            projection["include"] = [x for x in include if x not in exclude]
            merged["projection"] = projection
        else:
            merged[key] = value
    return merged


# --- Reference graph (relation names are informative; spec section 13 does not standardize them) ---

def reference_graph(manifest: dict[str, Any], docs: dict[str, dict[str, Any]], local_kinds: dict[str, str]) -> dict[str, Any]:
    md = manifest.get("metadata") or {}
    spec = manifest.get("spec") or {}
    identity = f"{md.get('namespace')}/{md.get('name')}@{md.get('version')}"
    nodes: list[dict[str, Any]] = [{"id": identity, "type": "package", "kind": manifest.get("kind")}]
    edges: list[dict[str, str]] = []

    def edge(source: str, relation: str, target: Any) -> None:
        item = {"from": source, "relation": relation, "to": target}
        if isinstance(target, str) and target and item not in edges:
            edges.append(item)

    for dep in spec.get("dependencies") or []:
        ref = dep.get("ref") if isinstance(dep, dict) else dep
        edge(identity, "uses_extension" if isinstance(dep, dict) and dep.get("as") else "depends_on", ref)
    for rel, kind in sorted(local_kinds.items()):
        nodes.append({"id": rel, "type": "asset", "kind": kind})
        edge(identity, "contains", rel)
        s = (docs.get(rel) or {}).get("spec") or {}
        if not isinstance(s, dict):
            continue
        if kind == "StateCompilerProfile":
            edge(rel, "compiles_view", s.get("worldViewRef"))
        elif kind == "WorldViewProfile":
            edge(rel, "specializes", s.get("specializes"))
            conditioning = s.get("conditioning") or {}
            edge(rel, "for_actor", conditioning.get("actorRef"))
            for v in _values(conditioning.get("roleRefs")):
                edge(rel, "for_role", v)
            edge(rel, "for_task", conditioning.get("taskRef"))
        elif kind == "ActorProfile":
            for v in _values(s.get("roleRefs")):
                edge(rel, "occupies_role", v)
            for v in _values(s.get("capabilityRefs")):
                edge(rel, "has_capability", v)
            edge(rel, "implemented_by", s.get("agentRef"))
            for v in _values(s.get("memberOf")):
                edge(rel, "member_of", v)
        elif kind == "DelegationProfile":
            edge(rel, "delegated_by", s.get("delegator"))
            edge(rel, "delegated_to", s.get("delegatee"))
        elif kind == "WorkPatternProfile":
            for v in _values(s.get("inputContracts")):
                edge(rel, "consumes_contract", v)
            for v in _values(s.get("outputContracts")):
                edge(rel, "produces_contract", v)
        elif kind == "EvaluationProfile":
            subject = s.get("subject") or {}
            edge(rel, "evaluates", subject.get("ref") if isinstance(subject, dict) else None)
            edge(rel, "evaluated_by_actor", s.get("evaluatorRef"))
        elif kind == "ScenarioProfile":
            edge(rel, "baseline", s.get("baselineStateRef"))
            engine = s.get("engine") or {}
            edge(rel, "uses_engine", engine.get("ref") if isinstance(engine, dict) else None)
        elif kind == "TaskSetProfile":
            for v in _values((s.get("task") or {}).get("workPatterns")):
                for prel, pkind in local_kinds.items():
                    if pkind == "WorkPatternProfile" and (((docs.get(prel) or {}).get("spec") or {}).get("pattern") or {}).get("kind") == v:
                        edge(rel, "uses_pattern", prel)
            for v in _values((s.get("requires") or {}).get("worldViews")):
                edge(rel, "requires_view", v)
            for v in _values((s.get("requires") or {}).get("knowledge")):
                edge(rel, "requires_knowledge", v)
            for v in _values((s.get("requires") or {}).get("actors")):
                edge(rel, "performed_by", v)
            for v in _values(s.get("workPatternRefs")):
                edge(rel, "uses_pattern", v)
            for v in _values((s.get("mayUse") or {}).get("scenarios")):
                edge(rel, "may_use_scenario", v)
            for v in _values((s.get("produces") or {}).get("artifacts")):
                edge(rel, "produces_artifact", v)
            for v in _values(s.get("evaluationRefs")):
                edge(rel, "evaluated_by", v)
        elif kind == "ArtifactTemplate":
            edge(rel, "template_for", s.get("artifactContractRef"))
        elif kind == "ConsumerRepresentationProfile":
            edge(rel, "represents_view", s.get("worldViewRef"))
            edge(rel, "for_actor", (s.get("actor") or {}).get("ref") if isinstance(s.get("actor"), dict) else None)
            for v in _values((s.get("human") or {}).get("artifactContractRefs")):
                edge(rel, "consumes_contract", v)
            edge(rel, "uses_adapter", (s.get("model") or {}).get("adapterRef"))
        elif kind == "KnowledgeAsset":
            edge(rel, "conforms_to", (s.get("conformsTo") or {}).get("ontology"))
        elif kind == "CompatibilityEvidence":
            edge(rel, "evidences", s.get("subject"))
    world_model = spec.get("worldModel") or {}
    grounding = world_model.get("semanticGrounding") or {}
    edge(identity, "grounded_in", grounding.get("worldRef"))
    for v in grounding.get("compatibleWorldViews") or []:
        edge(identity, "valid_for_view", v)
    for v in grounding.get("compatibleStateCompilers") or []:
        edge(identity, "valid_for_compiler", v)
    edge(identity, "uses_adapter", (world_model.get("representation") or {}).get("adapterRef"))
    return {"nodes": nodes, "edges": edges}


EXPERIMENTAL_FIELDS = {  # spec Appendix C.4
    "WorldViewProfile": [("specializes",), ("projection", "exclude"), ("conditioning", "actorRef"), ("conditioning", "roleRefs"), ("conditioning", "taskRef")],
    "EvaluationProfile": [("evaluatorRef",)],
    "CapabilityContract": [("outcomeRefs",)],
}


def usage(local_kinds: dict[str, str], docs: dict[str, dict[str, Any]], stability: dict[str, str]) -> dict[str, Any]:
    """Experimental kinds and fields a package uses, for `ontle inspect`."""
    kinds = sorted({k for k in local_kinds.values() if stability.get(k) == "experimental"})
    fields = []
    for rel, kind in sorted(local_kinds.items()):
        for path in EXPERIMENTAL_FIELDS.get(kind, []):
            node: Any = (docs.get(rel) or {}).get("spec") or {}
            for part in path:
                node = node.get(part) if isinstance(node, dict) else None
            if node is not None:
                fields.append(f"{rel}: spec.{'.'.join(path)}")
    return {"kinds": kinds, "fields": fields}
