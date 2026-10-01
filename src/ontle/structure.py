"""Document field tables and extension checks (spec sections 8 and 13).

Each table mirrors the JSON Schema of the same document under ``schemas/``;
``tests/test_structure.py`` keeps the two in sync. A closed object accepts only
its listed fields plus an ``extensions`` block; an open object accepts any key.
"""
from __future__ import annotations

import re
from typing import Any

EXTENSIONS = "extensions"
EXTENSION_NAME_RE = re.compile(r"^[a-z][a-z0-9-]{0,62}$")
RESERVED_EXTENSION_NAMES = {"owp", "openworld"}
EXTENSION_KIND_RE = re.compile(r"^([a-z][a-z0-9-]{0,62}):([A-Z][A-Za-z0-9]*)$")


def closed(fields: dict[str, Any], extensions: bool = True) -> dict[str, Any]:
    return {"type": "object", "fields": fields, "extensions": extensions}


def array(items: Any) -> dict[str, Any]:
    return {"type": "array", "items": items}


OPEN: dict[str, Any] = {"type": "object", "open": True}
VALUE = None  # any value; not descended into

# ExternalRef (spec section 5.1). `repository` is the deprecated name of `uri`.
EXTERNAL_REF = closed({
    "provider": VALUE, "uri": VALUE, "revision": VALUE, "digest": VALUE,
    "mediaType": VALUE, "size": VALUE, "status": VALUE, "repository": VALUE,
})
PROVIDERS = {"huggingface", "oci", "git", "https", "s3", "gcs", "doi"}
COMMIT_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
FILELIST_MEDIA_TYPE = "application/vnd.openworld.filelist+json"

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
            "definition": VALUE, "description": VALUE, "defaultView": VALUE, "defaultStateCompiler": VALUE,
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
        "ontology": OPEN,
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
        "subject": VALUE, "evaluationProfile": VALUE, "verifier": VALUE, "goldenSet": VALUE, "dataset": VALUE,
        "scope": closed({"worldRef": VALUE, "worldView": VALUE, "stateCompiler": VALUE, "environment": VALUE, "task": VALUE}),
        "result": OPEN,
    }),
}, extensions=False)

OBSERVATION_SET = closed({
    "apiVersion": VALUE,
    "kind": VALUE,
    "spec": closed({
        "observations": array(closed({"id": VALUE, "type": VALUE, "observedAt": VALUE, "subject": VALUE, "values": OPEN})),
    }),
}, extensions=False)

EFFECTIVE_WORLD_STATE = closed({
    "apiVersion": VALUE,
    "kind": VALUE,
    "spec": closed({
        "worldRef": VALUE, "worldView": VALUE, "stateCompiler": VALUE,
        "context": closed({"asOf": VALUE}),
        "state": OPEN, "unresolved": OPEN, "missing": VALUE, "provenance": OPEN,
    }),
}, extensions=False)

# Asset kinds whose document fields are defined; other kinds are checked only for
# top-level metadata/spec extension blocks.
ASSET_STRUCTURES = {"CompatibilityEvidence": COMPATIBILITY_EVIDENCE}


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
            errors.append(f"schema.unknown-field: {where}: {child} is not a defined field (extension data belongs in an extensions block)")


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
    """Extension names declared by spec.dependencies entries with 'as', and declaration errors."""
    names: set[str] = set()
    errors: list[str] = []
    deps = spec.get("dependencies")
    for dep in deps if isinstance(deps, list) else []:
        if not isinstance(dep, dict):
            continue
        if "as" not in dep:
            if "mustUnderstand" in dep:
                errors.append(f"extension.declaration: dependency {dep.get('ref')!r} declares mustUnderstand without as")
            continue
        name = dep["as"]
        if not isinstance(name, str) or not EXTENSION_NAME_RE.match(name):
            errors.append(f"extension.name: dependency {dep.get('ref')!r} as {name!r} must match [a-z][a-z0-9-]* (at most 63 characters)")
            continue
        if name in RESERVED_EXTENSION_NAMES:
            errors.append(f"extension.name: extension name {name!r} is reserved")
            continue
        if name in names:
            errors.append(f"extension.duplicate: extension name {name!r} is declared more than once")
        names.add(name)
        if "mustUnderstand" in dep and not isinstance(dep["mustUnderstand"], bool):
            errors.append(f"extension.declaration: dependency {dep.get('ref')!r} mustUnderstand must be true or false")
    return names, errors


def extension_definition_errors(spec: dict[str, Any]) -> list[str]:
    definition = spec.get("extensionDefinition")
    if definition is None:
        return []
    if not isinstance(definition, dict):
        return ["extension.definition: spec.extensionDefinition must be a mapping"]
    errors = []
    kinds = definition.get("kinds")
    if kinds is not None and not (isinstance(kinds, list) and all(isinstance(k, str) and re.match(r"^[A-Z][A-Za-z0-9]*$", k) for k in kinds)):
        errors.append("extension.definition: spec.extensionDefinition.kinds must be a list of PascalCase kind names without a prefix")
    schemas = definition.get("schemas")
    if schemas is not None and not (isinstance(schemas, list) and all(isinstance(s, str) and s for s in schemas)):
        errors.append("extension.definition: spec.extensionDefinition.schemas must be a list of package-relative paths")
    return errors


def external_ref_issues(ref: Any, where: str, declared: set[str]) -> tuple[list[str], list[str]]:
    """Errors and warnings for one ExternalRef (spec section 5.1). Unknown fields are reported by structure_errors."""
    if not isinstance(ref, dict):
        return [f"ref.shape: {where} must be a mapping"], []
    errors: list[str] = []
    warnings: list[str] = []
    status = ref.get("status", "bound")
    if status not in {"bound", "unbound"}:
        errors.append(f"ref.shape: {where}.status must be bound or unbound")
        return errors, warnings
    uri = ref.get("uri")
    if "repository" in ref:
        if "uri" in ref:
            errors.append(f"ref.shape: {where} declares both uri and its deprecated name repository")
        else:
            warnings.append(f"ref.legacy-shape: {where}.repository is deprecated; use uri")
            uri = ref["repository"]
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
