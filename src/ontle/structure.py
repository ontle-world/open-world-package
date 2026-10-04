"""Document field tables and extension checks (spec sections 8 and 13).

Each table mirrors the JSON Schema of the same document under ``schemas/``;
``tests/test_structure.py`` keeps the two in sync. A closed object accepts only
its listed fields plus an ``extensions`` block; an open object accepts any key.
"""
from __future__ import annotations

import difflib
import re
from typing import Any

EXTENSIONS = "extensions"
EXTENSION_NAME_RE = re.compile(r"^[a-z][a-z0-9-]{0,62}\Z")
RESERVED_EXTENSION_NAMES = {"owp", "openworld"}
EXTENSION_KIND_RE = re.compile(r"^([a-z][a-z0-9-]{0,62}):([A-Z][A-Za-z0-9]*)\Z")


def closed(fields: dict[str, Any], extensions: bool = True) -> dict[str, Any]:
    return {"type": "object", "fields": fields, "extensions": extensions}


def array(items: Any) -> dict[str, Any]:
    return {"type": "array", "items": items}


OPEN: dict[str, Any] = {"type": "object", "open": True}
VALUE = None  # any value; not descended into

# ExternalRef (spec section 5.1).
EXTERNAL_REF = closed({
    "provider": VALUE, "uri": VALUE, "revision": VALUE, "digest": VALUE,
    "mediaType": VALUE, "size": VALUE, "status": VALUE,
})
PROVIDERS = {"huggingface", "oci", "git", "https", "s3", "gcs", "doi"}
COMMIT_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}\Z")
FILELIST_MEDIA_TYPE = "application/vnd.openworld.filelist+json"

ONTOLOGY = closed({
    "description": VALUE,
    "iri": VALUE,
    "prefixes": OPEN,
    "entrypoints": array(closed({"path": VALUE, "format": VALUE, "role": VALUE})),
    "termIndex": VALUE,
    "externalImports": array(closed({"iri": VALUE, "ref": EXTERNAL_REF})),
})


SEMANTIC_PROFILE = closed({"apiVersion": VALUE, "kind": VALUE, "metadata": closed({"name": VALUE, "version": VALUE, "title": VALUE, "description": VALUE}), "spec": closed({
    "types": array(closed({
        "id": VALUE, "label": OPEN, "description": VALUE, "subClassOf": VALUE, "enum": VALUE,
        "properties": array(closed({"id": VALUE, "label": OPEN, "description": VALUE, "range": VALUE, "cardinality": VALUE})),
    })),
    "relations": array(closed({"id": VALUE, "label": OPEN, "description": VALUE, "domain": VALUE, "range": VALUE})),
})}, extensions=False)

TERM_INDEX = closed({"apiVersion": VALUE, "kind": VALUE, "metadata": closed({"name": VALUE, "version": VALUE, "title": VALUE, "description": VALUE}), "spec": closed({
    "terms": array(closed({"iri": VALUE, "type": VALUE, "label": VALUE})),
})}, extensions=False)


MANIFEST = closed({
    "apiVersion": VALUE,
    "kind": VALUE,
    "metadata": closed({
        "namespace": VALUE, "name": VALUE, "version": VALUE,
        "title": VALUE, "description": VALUE, "license": VALUE,
    }),
    "spec": closed({
        "dependencies": array(closed({"ref": VALUE, "source": VALUE, "as": VALUE, "mustUnderstand": VALUE})),
        "assets": array(closed({"kind": VALUE, "path": VALUE, "ref": EXTERNAL_REF})),
        "conformance": closed({"profile": VALUE}),
        "world": closed({
            "definition": VALUE, "description": VALUE, "defaultView": VALUE, "defaultStateCompiler": VALUE, "semanticBinding": VALUE,
            "boundary": closed({"included": VALUE, "excluded": VALUE}),
        }),
        "worldModel": closed({
            "description": VALUE,
            "roles": VALUE,
            "semanticGrounding": closed({"worldRef": VALUE, "compatibleWorldViews": VALUE, "compatibleStateCompilers": VALUE}),
            "representation": closed({"adapterRef": VALUE, "input": VALUE, "internal": VALUE, "mode": VALUE}),
            "inputs": closed({"contract": VALUE}),
            "outputs": VALUE,
            "modalities": closed({"inputs": VALUE, "outputs": VALUE}),
            "temporal": OPEN,
            "validity": OPEN,
        }),
        "ontology": ONTOLOGY,
        "extensionDefinition": closed({"description": VALUE, "kinds": VALUE, "schemas": VALUE}),
        "domains": VALUE,
        "capabilities": VALUE,
        "validity": OPEN,
    }),
}, extensions=False)

ASSET_METADATA = closed({"name": VALUE, "version": VALUE, "title": VALUE, "description": VALUE})

COMPATIBILITY_EVIDENCE = closed({
    "apiVersion": VALUE,
    "kind": VALUE,
    "metadata": ASSET_METADATA,
    "spec": closed({
        "subject": VALUE, "subjectDigest": VALUE, "evaluationProfile": VALUE, "verifier": VALUE, "goldenSet": VALUE, "dataset": VALUE,
        "scope": closed({"worldRef": VALUE, "worldView": VALUE, "stateCompiler": VALUE, "environment": VALUE, "task": VALUE}),
        "result": OPEN,
    }),
}, extensions=False)

OBSERVATION_SET = closed({
    "apiVersion": VALUE,
    "kind": VALUE,
    "spec": closed({
        "provenance": closed({"extraction": VALUE, "parameters": OPEN, "snapshot": VALUE}),
        "observations": array(closed({"id": VALUE, "type": VALUE, "observedAt": VALUE, "subject": VALUE, "values": OPEN,
                                       "estimatedBy": VALUE, "uncertainty": OPEN, "units": OPEN})),
    }),
}, extensions=False)

EFFECTIVE_WORLD_STATE = closed({
    "apiVersion": VALUE,
    "kind": VALUE,
    "spec": closed({
        "worldRef": VALUE, "worldView": VALUE, "stateCompiler": VALUE,
        "context": closed({"asOf": VALUE}),
        "state": OPEN, "unresolved": OPEN, "missing": VALUE, "provenance": OPEN, "derivation": OPEN,
    }),
}, extensions=False)

def _standard(spec_fields: dict[str, Any]) -> dict[str, Any]:
    return closed({"apiVersion": VALUE, "kind": VALUE, "metadata": ASSET_METADATA, "spec": closed(spec_fields)}, extensions=False)


# Standard kinds with defined fields (spec sections 8 and 15). Fields marked "experimental" are
# listed in spec Appendix C.1: accepted, and the checks on them produce warnings only.
WORLD_VIEW_PROFILE = _standard({
    "externalWorldRefs": VALUE,
    "specializes": VALUE,                                  # experimental
    "purpose": closed({"task": VALUE, "actorScope": VALUE, "objective": VALUE}),
    "projection": closed({"include": VALUE, "exclude": VALUE, "principle": VALUE,
                          "scale": VALUE, "resolution": VALUE, "timeScope": VALUE}),
    "conditioning": closed({"authorityScope": VALUE,
                            "actorRef": VALUE, "roleRefs": VALUE, "taskRef": VALUE}),   # *Ref*: experimental
    "constraints": VALUE,
    "evidenceRefs": VALUE,
})

EVALUATION_PROFILE = _standard({
    "supersedes": VALUE, "changedBecause": VALUE, "metrics": VALUE, "tasks": VALUE, "checks": VALUE,
    "assessmentKind": VALUE,
    "subject": closed({"kind": VALUE, "ref": VALUE}),
    "objective": VALUE,
    "criteria": array(closed({"metric": VALUE, "rubric": VALUE, "threshold": VALUE})),
    "verifierRef": VALUE,
    "evaluatorRef": VALUE,                                 # experimental
    "evidenceRefs": VALUE,
    "validityScope": OPEN,
    "resultSchemaRef": VALUE,
})

SCENARIO_PROFILE = _standard({
    "description": VALUE, "objective": VALUE, "standardBindings": OPEN,
    "baselineStateRef": VALUE,
    "assumptions": VALUE,
    "intervention": OPEN,
    "engine": closed({"kind": VALUE, "ref": VALUE}),
    "timeHorizon": VALUE,
    "constraints": VALUE,
    "uncertainty": OPEN,
    "confidence": VALUE,
    "expectedOutcome": OPEN,
    "evidenceRefs": VALUE,
})

CAPABILITY_CONTRACT = _standard({
    "description": VALUE, "effect": VALUE,
    "outcomeRefs": VALUE,                                  # experimental
    "context": OPEN,
    "requiredInputs": VALUE,
    "evidenceRefs": VALUE,
    "capacity": OPEN,
    "maturity": VALUE,
    "validityScope": OPEN,
})

# Asset kinds whose document fields are defined; other kinds are checked only for
# top-level metadata/spec extension blocks.

# Standard kinds that had a name but no schema (spec section 8): description, standard bindings, and the fields in use.
DATASET = _standard({"description": VALUE, "standardBindings": OPEN, "worldViewRef": VALUE, "structure": VALUE})
AGENT_PROFILE = _standard({"description": VALUE, "standardBindings": OPEN})
ENVIRONMENT_PROFILE = _standard({"description": VALUE, "standardBindings": OPEN, "exposes": OPEN, "runtimeBinding": VALUE})
MODEL_ARTIFACT = _standard({"description": VALUE, "standardBindings": OPEN, "implementationStatus": VALUE, "bundled": VALUE, "artifactRef": EXTERNAL_REF, "supportedProviders": VALUE, "entrypoint": VALUE})
SOURCE_SYSTEM_SCHEMA_PROFILE = _standard({"description": VALUE, "standardBindings": OPEN, "systems": OPEN})
OBSERVATION_ACQUISITION_PROFILE = _standard({"description": VALUE, "standardBindings": OPEN, "inputs": VALUE, "rule": VALUE, "modalities": VALUE})
ACTION_BINDING_PROFILE = _standard({"description": VALUE, "standardBindings": OPEN, "actions": VALUE, "execution": VALUE, "actionSpace": OPEN})
COMMIT_CONTRACT = _standard({"description": VALUE, "standardBindings": OPEN, "approvalRequired": VALUE, "commitExamples": VALUE, "rule": VALUE, "commitSemantics": OPEN})
EFFECT_VERIFICATION_PROFILE = _standard({"description": VALUE, "standardBindings": OPEN, "verifies": VALUE, "rule": VALUE, "observationSources": VALUE})
VERIFIER_PROFILE = _standard({"description": VALUE, "standardBindings": OPEN, "verifies": VALUE, "basis": VALUE})

ASSET_STRUCTURES = {
    "CompatibilityEvidence": COMPATIBILITY_EVIDENCE,
    "SemanticProfile": SEMANTIC_PROFILE,
    "OntologyTermIndex": TERM_INDEX,
    "WorldViewProfile": WORLD_VIEW_PROFILE,
    "EvaluationProfile": EVALUATION_PROFILE,
    "ScenarioProfile": SCENARIO_PROFILE,
    "CapabilityContract": CAPABILITY_CONTRACT,
    "Dataset": DATASET,
    "AgentProfile": AGENT_PROFILE,
    "EnvironmentProfile": ENVIRONMENT_PROFILE,
    "ModelArtifact": MODEL_ARTIFACT,
    "SourceSystemSchemaProfile": SOURCE_SYSTEM_SCHEMA_PROFILE,
    "ObservationAcquisitionProfile": OBSERVATION_ACQUISITION_PROFILE,
    "ActionBindingProfile": ACTION_BINDING_PROFILE,
    "CommitContract": COMMIT_CONTRACT,
    "EffectVerificationProfile": EFFECT_VERIFICATION_PROFILE,
    "VerifierProfile": VERIFIER_PROFILE,
}


def structure_errors(doc: Any, table: dict[str, Any], where: str, declared: set[str] | None) -> list[str]:
    """Unknown fields and extension-block errors. ``declared`` is None when names are not checked (runtime documents)."""
    errors: list[str] = []
    _walk(doc, table, "", where, declared, errors)
    return errors


def _walk(value: Any, node: Any, path: str, where: str, declared: set[str] | None, errors: list[str]) -> None:
    if node is None or not isinstance(node, dict):
        return
    if node["type"] == "array":
        if isinstance(value, list):
            for i, item in enumerate(value):
                _walk(item, node["items"], f"{path}[{i}]", where, declared, errors)
        return
    if not isinstance(value, dict) or node.get("open"):
        return
    fields = node["fields"]
    for key, sub in value.items():
        child = f"{path}.{key}" if path else str(key)
        if key == EXTENSIONS and node["extensions"]:
            errors.extend(extension_block_errors(sub, child, where, declared))
        elif key in fields:
            _walk(sub, fields[key], child, where, declared, errors)
        else:
            close = difflib.get_close_matches(str(key), list(fields), n=1, cutoff=0.75)
            hint = f"; did you mean {close[0]!r}?" if close else " (extension data belongs in an extensions block)"
            errors.append(f"schema.unknown-field: {where}: {child} is not a defined field{hint}")


def extension_block_errors(block: Any, path: str, where: str, declared: set[str] | None) -> list[str]:
    if not isinstance(block, dict) or not all(isinstance(v, dict) for v in block.values()):
        return [f"extension.block: {where}: {path} must map extension names to mappings"]
    errors = []
    for name in block:
        if not isinstance(name, str) or not EXTENSION_NAME_RE.match(name):
            errors.append(f"extension.block: {where}: {path} key {name!r} is not an extension name")
        elif declared is not None and name not in declared:
            errors.append(f"extension.undeclared: {where}: {path} uses extension {name!r}, which spec.dependencies does not declare with 'as'")
    return errors


def declared_extensions(spec: dict[str, Any]) -> tuple[set[str], list[str]]:
    """Extension names declared by spec.dependencies entries with 'as' (spec 13.1), and declaration errors."""
    names: set[str] = set()
    errors: list[str] = []
    deps = spec.get("dependencies")
    for i, dep in enumerate(deps) if isinstance(deps, list) else []:
        if not isinstance(dep, dict):
            continue
        where = f"spec.dependencies[{i}]"
        if "mustUnderstand" in dep:
            if "as" not in dep:
                errors.append(f"extension.declaration: {where} declares mustUnderstand without as")
            elif not isinstance(dep["mustUnderstand"], bool):
                errors.append(f"extension.declaration: {where}.mustUnderstand must be true or false")
        if "as" not in dep:
            continue
        name = dep["as"]
        if not isinstance(name, str) or not EXTENSION_NAME_RE.match(name):
            errors.append(f"extension.name: {where}.as {name!r} must match [a-z][a-z0-9-]* (at most 63 characters)")
        elif name in RESERVED_EXTENSION_NAMES:
            errors.append(f"extension.name: {where}.as {name!r} is a reserved extension name")
        elif name in names:
            errors.append(f"extension.duplicate: {where}.as {name!r} declares an extension name that is already declared")
        else:
            names.add(name)
    return names, errors


def extension_definition_errors(spec: dict[str, Any]) -> list[str]:
    """Spec 13.2: spec.extensionDefinition {description, kinds, schemas}. Whether each schema file exists is checked by the caller."""
    if "extensionDefinition" not in spec:
        return []
    definition = spec["extensionDefinition"]
    if not isinstance(definition, dict):
        return ["extension.definition: spec.extensionDefinition must be a mapping"]
    errors = []
    if "description" in definition and not isinstance(definition["description"], str):
        errors.append("extension.definition: spec.extensionDefinition.description must be a string")
    kinds = definition.get("kinds")
    if "kinds" in definition and not (isinstance(kinds, list) and all(isinstance(k, str) and re.match(r"^[A-Z][A-Za-z0-9]*\Z", k) for k in kinds)):
        errors.append("extension.definition: spec.extensionDefinition.kinds must be a list of PascalCase kind names without a prefix")
    schemas = definition.get("schemas")
    if "schemas" not in definition:
        return errors
    if not isinstance(schemas, list):
        return errors + ["extension.definition: spec.extensionDefinition.schemas must be a list of package-relative paths"]
    from .values import nonempty_str, normalize_rel_path
    for i, rel in enumerate(schemas):
        if not nonempty_str(rel) or normalize_rel_path(rel) is None or rel.startswith("./"):
            errors.append(f"extension.definition: spec.extensionDefinition.schemas[{i}] {rel!r} must be a package-relative path")
    return errors


def external_ref_issues(ref: Any, where: str, declared: set[str]) -> tuple[list[str], list[str]]:
    """Errors and warnings for one ExternalRef (spec section 5.1). Unknown fields are reported by structure_errors."""
    if not isinstance(ref, dict):
        return [f"ref.shape: {where} must be a mapping"], []
    errors: list[str] = []
    warnings: list[str] = []
    status = "bound" if ref.get("status") is None else ref["status"]  # null counts as absent
    if not (isinstance(status, str) and status in {"bound", "unbound"}):
        errors.append(f"ref.shape: {where}.status must be bound or unbound")
        return errors, warnings
    uri = ref.get("uri")
    provider = ref.get("provider")
    if provider is not None:
        if not isinstance(provider, str):
            errors.append(f"ref.provider: {where}.provider must be a string")
        elif ":" in provider:
            name = provider.split(":", 1)[0]
            if not EXTENSION_NAME_RE.match(name) or not provider.split(":", 1)[1]:
                errors.append(f"ref.provider: {where}.provider {provider!r} must be one of {sorted(PROVIDERS)} or <extension>:<provider>")
            elif name not in declared:
                errors.append(f"extension.undeclared: {where}.provider {provider!r} uses extension {name!r}, which spec.dependencies does not declare with 'as'")
        elif provider not in PROVIDERS:
            errors.append(f"ref.provider: {where}.provider {provider!r} must be one of {sorted(PROVIDERS)} or <extension>:<provider>")
    digest = ref.get("digest")
    if digest is not None and not (isinstance(digest, str) and DIGEST_RE.match(digest)):
        errors.append(f"ref.shape: {where}.digest must be sha256:<64 lowercase hex>")
    size = ref.get("size")
    if size is not None and (isinstance(size, bool) or not isinstance(size, int) or size < 0):
        errors.append(f"ref.shape: {where}.size must be a non-negative integer")
    for field in ("revision", "mediaType"):
        if ref.get(field) is not None and not isinstance(ref[field], str):
            errors.append(f"ref.shape: {where}.{field} must be a string")
    if status == "unbound":
        return errors, warnings
    if provider is None:
        errors.append(f"ref.shape: {where} is bound and must declare provider")
    if not isinstance(uri, str) or not uri:
        errors.append(f"ref.shape: {where} is bound and must declare uri")
    if errors or ":" in str(provider):
        return errors, warnings
    revision = ref.get("revision")
    pinned = isinstance(digest, str) or (provider in {"git", "huggingface"} and isinstance(revision, str) and bool(COMMIT_RE.match(revision)))
    if not pinned:
        how = "a commit-hash revision or a digest" if provider in {"git", "huggingface"} else "a digest"
        warnings.append(f"ref.unpinned: {where} ({provider}) is not pinned; declare {how}")
    return errors, warnings


# Standard binding (spec section 5.3): one entry of an asset's spec.standardBindings.
STANDARD_BINDING = closed({"standard": VALUE, "ref": EXTERNAL_REF, "license": VALUE, "terms": OPEN})


def standard_binding_issues(bindings: Any, where: str, declared: set[str]) -> tuple[list[str], list[str]]:
    """Errors and warnings for spec.standardBindings. A bound reference must be pinned and licensed."""
    if not isinstance(bindings, dict):
        return [f"standard.binding: {where} must be a mapping of binding name to binding"], []
    errors: list[str] = []
    warnings: list[str] = []
    for name, entry in bindings.items():
        at = f"{where}.{name}"
        if not isinstance(entry, dict):
            errors.append(f"standard.binding: {at} must be a mapping")
            continue
        errors.extend(structure_errors(entry, STANDARD_BINDING, at, declared))
        if not isinstance(entry.get("standard"), str) or not entry["standard"]:
            errors.append(f"standard.binding: {at}.standard must be a non-empty string")
        terms = entry.get("terms")
        if terms is not None and not (isinstance(terms, dict) and all(isinstance(v, str) for v in terms.values())):
            errors.append(f"standard.binding: {at}.terms must map names to strings")
        if "ref" not in entry and terms is None:
            errors.append(f"standard.binding: {at} must declare ref, terms, or both")
        license_ = entry.get("license")
        if license_ is not None and not (isinstance(license_, str) and license_):
            errors.append(f"standard.binding: {at}.license must be a non-empty SPDX license expression")
        if "ref" not in entry:
            continue
        ref_errors, ref_warnings = external_ref_issues(entry["ref"], f"{at}.ref", declared)
        errors.extend(ref_errors)
        for warning in ref_warnings:
            rule, _, message = warning.partition(":")
            if rule == "ref.unpinned":
                errors.append(f"standard.unpinned: {message.strip()}")
            else:
                warnings.append(warning)
        bound = isinstance(entry["ref"], dict) and entry["ref"].get("status") in (None, "bound")
        if bound and not ref_errors and license_ is None:
            errors.append(f"standard.license: {at} binds an artifact and must declare license")
    return errors, warnings
