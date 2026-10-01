from __future__ import annotations

from dataclasses import dataclass
from importlib import resources
from pathlib import Path
import hashlib
import json
import re
import zipfile
from typing import Any

import yaml

from . import binding as binding_module
from . import experimental, structure
from . import ontology as ontology_module

MANIFEST = "owp.yaml"
KINDS = {"WorldPackage", "WorldModelPackage", "OntologyPackage"}
LEGACY_MANIFESTS = {"package.yaml", "world.yaml"}


def _load_vocabulary() -> dict[str, str]:
    """Asset kind -> stability, from vocab/asset-kinds.yaml (packaged as ontle.vocab)."""
    try:
        text = resources.files("ontle.vocab").joinpath("asset-kinds.yaml").read_text(encoding="utf-8")
    except (ModuleNotFoundError, FileNotFoundError):  # editable install: read the repository copy
        text = (Path(__file__).resolve().parents[2] / "vocab" / "asset-kinds.yaml").read_text(encoding="utf-8")
    groups = yaml.safe_load(text)["groups"]
    return {kind: entry["stability"] for group in groups.values() for kind, entry in group.items()}


ASSET_KIND_STABILITY = _load_vocabulary()
KNOWN_ASSET_KINDS = set(ASSET_KIND_STABILITY)
SEMVER_PATTERN = r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?"
SEMVER_RE = re.compile(rf"^{SEMVER_PATTERN}$")
# Exact reference to a versioned asset: <name>@<semver>. Ranges are not allowed.
PINNED_REF_RE = re.compile(rf"^[^@\s]+@{SEMVER_PATTERN}$")
# Exact package reference: <namespace>/<name>@<semver>.
PACKAGE_REF_RE = re.compile(rf"^[^/@#\s]+/[^/@#\s]+@{SEMVER_PATTERN}$")
IDENTITY_PART_RE = re.compile(r"^[^/@#\s]+$")
EWS = "EffectiveWorldState"

# WorldPackage conformance profiles. Each profile includes every requirement of the previous ones.
WORLD_PROFILES = ["descriptive", "viewable", "stateful", "model-ready", "action-ready"]
DEFAULT_WORLD_PROFILE = "descriptive"


class OWPError(Exception):
    pass


@dataclass
class ValidationResult:
    valid: bool
    errors: list[str]
    warnings: list[str]
    manifest: dict[str, Any] | None = None


def package_root(path: str | Path) -> Path:
    p = Path(path).expanduser().resolve()
    if p.is_file():
        p = p.parent
    return p


def load_manifest(path: str | Path) -> tuple[Path, dict[str, Any]]:
    root = package_root(path)
    manifest_path = root / MANIFEST
    if not manifest_path.exists():
        raise OWPError(f"missing {MANIFEST} in {root}")
    try:
        data = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise OWPError(f"cannot parse {MANIFEST}: {exc}") from exc
    if not isinstance(data, dict):
        raise OWPError(f"{MANIFEST} must contain a YAML mapping")
    return root, data


def _local_asset_paths(spec: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for item in spec.get("assets", []) or []:
        if isinstance(item, str):
            out.append(item)
        elif isinstance(item, dict) and isinstance(item.get("path"), str):
            out.append(item["path"])
    return out


def _spec_of(doc: Any) -> dict[str, Any]:
    spec = doc.get("spec") if isinstance(doc, dict) else None
    return spec if isinstance(spec, dict) else {}


def _world_profile_errors(profile: str, spec: dict[str, Any], asset_kinds: set[str],
                          local_asset_kinds: dict[str, str], local_asset_docs: dict[str, dict[str, Any]],
                          identity: str | None = None) -> list[str]:
    """Errors preventing a WorldPackage from satisfying one conformance profile (cumulative)."""
    level = WORLD_PROFILES.index(profile)
    errors: list[str] = []
    world = spec.get("world") if isinstance(spec.get("world"), dict) else {}
    if not world.get("definition") and "WorldDefinition" not in asset_kinds:
        errors.append("profile.descriptive: requires spec.world.definition or a WorldDefinition asset")
    if level < 1:
        return errors

    if "WorldViewProfile" not in asset_kinds:
        errors.append("profile.viewable: requires at least one WorldViewProfile")
    default_view = world.get("defaultView")
    if not isinstance(default_view, str) or not default_view.strip():
        errors.append("profile.viewable: requires spec.world.defaultView")
    elif local_asset_kinds.get(default_view) != "WorldViewProfile":
        errors.append("profile.viewable: spec.world.defaultView must point to a local WorldViewProfile asset")
    elif _spec_of(local_asset_docs.get(default_view)).get("worldRef") not in {"self", identity}:
        errors.append(f"profile.viewable.world-ref: default WorldViewProfile spec.worldRef must be 'self' or this package's identity {identity}")
    if level < 2:
        return errors

    if "StateCompilerProfile" not in asset_kinds:
        errors.append("profile.stateful: requires at least one StateCompilerProfile")
    default_compiler = world.get("defaultStateCompiler")
    if not isinstance(default_compiler, str) or not default_compiler.strip():
        errors.append("profile.stateful: requires spec.world.defaultStateCompiler")
    elif local_asset_kinds.get(default_compiler) != "StateCompilerProfile":
        errors.append("profile.stateful: spec.world.defaultStateCompiler must point to a local StateCompilerProfile asset")
    elif _spec_of(local_asset_docs.get(default_compiler)).get("worldViewRef") != default_view:
        errors.append("profile.stateful.default-compiler-view: default StateCompilerProfile spec.worldViewRef must reference spec.world.defaultView")
    for rel, kind in sorted(local_asset_kinds.items()):
        if kind != "StateCompilerProfile":
            continue
        cspec = _spec_of(local_asset_docs.get(rel))
        if local_asset_kinds.get(cspec.get("worldViewRef")) != "WorldViewProfile":
            errors.append(f"profile.stateful.compiler-view: StateCompilerProfile {rel} spec.worldViewRef must point to a local WorldViewProfile asset")
        if cspec.get("outputContract") != EWS:
            errors.append(f"profile.stateful.output-contract: StateCompilerProfile {rel} must declare spec.outputContract = {EWS}")
        from .ews import binding_errors  # local import: ews depends on core
        errors.extend(binding_errors(cspec, rel))
        if level >= 3:
            schema = cspec.get("outputSchema")
            fields = schema.get("fields") if isinstance(schema, dict) else None
            if not (isinstance(fields, list) and fields) and not cspec.get("outputSchemaRef"):
                errors.append(f"profile.model-ready.output-schema: StateCompilerProfile {rel} must declare spec.outputSchema.fields or spec.outputSchemaRef")
    if level < 4:
        return errors

    for required in ("ActionBindingProfile", "CommitContract", "EffectVerificationProfile"):
        if required not in asset_kinds:
            errors.append(f"profile.action-ready: requires a {required} asset")
    return errors


def satisfied_world_profile(spec: dict[str, Any], asset_kinds: set[str],
                            local_asset_kinds: dict[str, str], local_asset_docs: dict[str, dict[str, Any]],
                            identity: str | None = None) -> str | None:
    """Highest WorldPackage conformance profile the package satisfies, independent of the declared one."""
    satisfied = None
    for profile in WORLD_PROFILES:
        if _world_profile_errors(profile, spec, asset_kinds, local_asset_kinds, local_asset_docs, identity):
            break
        satisfied = profile
    return satisfied


def _validate_evaluation_lineage(spec: dict[str, Any], kind: Any, identity: str, local_asset_kinds: dict[str, str],
                                 local_asset_docs: dict[str, dict[str, Any]], errors: list[str], warnings: list[str]) -> None:
    """Evaluation lineage and evidence binding. OWP records which exact evaluation produced a result; it does not run or evolve evaluations."""
    local_versions: dict[str, dict[str, str | None]] = {"EvaluationProfile": {}, "VerifierPackage": {}}
    for rel, asset_kind in sorted(local_asset_kinds.items()):
        if asset_kind not in local_versions or rel not in local_asset_docs:
            continue
        doc = local_asset_docs[rel]
        md = doc.get("metadata") if isinstance(doc.get("metadata"), dict) else {}
        version = md.get("version")
        if isinstance(md.get("name"), str):
            if md["name"] in local_versions[asset_kind]:
                errors.append(f"eval.duplicate-name: more than one local {asset_kind} is named {md['name']!r}")
            local_versions[asset_kind].setdefault(md["name"], version if isinstance(version, str) else None)
        if version is None:
            warnings.append(f"eval.version-missing: {asset_kind} {rel} should declare metadata.version so evidence can bind to it")
        elif not isinstance(version, str) or not SEMVER_RE.match(version):
            errors.append(f"eval.version: {asset_kind} {rel} metadata.version must use SemVer")
        supersedes = _spec_of(doc).get("supersedes")
        if supersedes is not None and not (isinstance(supersedes, str) and PINNED_REF_RE.match(supersedes)):
            errors.append(f"eval.supersedes: {asset_kind} {rel} spec.supersedes must be a pinned <name>@<version> reference")

    grounding: dict[str, Any] = {}
    if kind == "WorldModelPackage" and isinstance(spec.get("worldModel"), dict):
        g = spec["worldModel"].get("semanticGrounding")
        grounding = g if isinstance(g, dict) else {}

    for rel, asset_kind in sorted(local_asset_kinds.items()):
        if asset_kind != "CompatibilityEvidence" or rel not in local_asset_docs:
            continue
        espec = _spec_of(local_asset_docs[rel])
        if not espec.get("subject"):
            errors.append(f"evidence.subject: CompatibilityEvidence {rel} must declare spec.subject")
        elif kind == "WorldModelPackage" and espec["subject"] != identity:
            errors.append(f"evidence.subject: CompatibilityEvidence {rel} spec.subject must be this package's identity {identity}")
        for field, bound_kind, required in (("evaluationProfile", "EvaluationProfile", True), ("verifier", "VerifierPackage", False)):
            ref = espec.get(field)
            if ref is None:
                if required:
                    errors.append(f"evidence.required: CompatibilityEvidence {rel} must declare spec.{field}")
                continue
            if not (isinstance(ref, str) and PINNED_REF_RE.match(ref)):
                errors.append(f"evidence.unpinned: CompatibilityEvidence {rel} spec.{field} must be a pinned <name>@<version> reference")
                continue
            name, version = ref.split("@", 1)
            if name in local_versions[bound_kind] and local_versions[bound_kind][name] != version:
                local = local_versions[bound_kind][name] or "unversioned"
                errors.append(f"evidence.version-mismatch: CompatibilityEvidence {rel} binds {ref} but the packaged {bound_kind} {name} is {local}")
        for field in ("goldenSet", "dataset"):
            ref = espec.get(field)
            if ref is not None and not (isinstance(ref, str) and PINNED_REF_RE.match(ref)):
                errors.append(f"evidence.unpinned: CompatibilityEvidence {rel} spec.{field} must be a pinned <name>@<version> reference")
        scope = espec.get("scope")
        if not isinstance(scope, dict) or not scope.get("worldRef") or not scope.get("worldView"):
            errors.append(f"evidence.scope: CompatibilityEvidence {rel} must declare spec.scope.worldRef and spec.scope.worldView")
        elif grounding:
            if grounding.get("worldRef") and scope["worldRef"] != grounding["worldRef"]:
                errors.append(f"evidence.scope.world-ref: CompatibilityEvidence {rel} scope.worldRef differs from semanticGrounding.worldRef")
            if scope["worldView"] not in (grounding.get("compatibleWorldViews") or []):
                errors.append(f"evidence.scope.world-view: CompatibilityEvidence {rel} scope.worldView is outside semanticGrounding.compatibleWorldViews")
            compiler = scope.get("stateCompiler")
            if compiler is not None and compiler not in (grounding.get("compatibleStateCompilers") or []):
                errors.append(f"evidence.scope.state-compiler: CompatibilityEvidence {rel} scope.stateCompiler is outside semanticGrounding.compatibleStateCompilers")
        if not isinstance(espec.get("result"), dict):
            errors.append(f"evidence.result: CompatibilityEvidence {rel} must declare spec.result")


def _asset_structure_errors(doc: dict[str, Any], asset_kind: Any, rel: str, extension_names: set[str]) -> list[str]:
    """Defined fields for kinds with a schema; top-level extension blocks for every kind."""
    table = structure.ASSET_STRUCTURES.get(asset_kind)
    if table is not None:
        return structure.structure_errors(doc, table, rel, extension_names)
    errors: list[str] = []
    for section in ("metadata", "spec"):
        block = doc.get(section)
        if isinstance(block, dict) and structure.EXTENSIONS in block:
            errors.extend(structure.extension_block_errors(block[structure.EXTENSIONS], f"{section}.{structure.EXTENSIONS}", rel, extension_names))
    return errors


def validate_package(path: str | Path) -> ValidationResult:
    errors: list[str] = []
    warnings: list[str] = []
    try:
        root, data = load_manifest(path)
    except OWPError as exc:
        return ValidationResult(False, [f"manifest.load: {exc}"], warnings, None)

    for legacy in sorted(LEGACY_MANIFESTS):
        if (root / legacy).exists():
            errors.append(f"package.legacy-manifest: legacy manifest {legacy} is not allowed; use only {MANIFEST}")

    if data.get("apiVersion") != "openworld/v1alpha1":
        errors.append("manifest.api-version: apiVersion must be openworld/v1alpha1")

    kind = data.get("kind")
    if kind not in KINDS:
        errors.append(f"manifest.kind: kind must be one of {sorted(KINDS)}")

    metadata = data.get("metadata")
    if not isinstance(metadata, dict):
        errors.append("manifest.metadata: metadata must be a mapping")
        metadata = {}
    for key in ("namespace", "name", "version"):
        if not isinstance(metadata.get(key), str) or not metadata.get(key).strip():
            errors.append(f"manifest.identity: metadata.{key} is required")
        elif key != "version" and not IDENTITY_PART_RE.match(metadata[key]):
            errors.append(f"manifest.identity: metadata.{key} must not contain '/', '@', '#', or whitespace")
    version = metadata.get("version")
    if isinstance(version, str) and not SEMVER_RE.match(version):
        errors.append("manifest.version: metadata.version must use SemVer (for example 0.1.0 or 0.1.0-alpha.1)")

    identity = f"{metadata.get('namespace')}/{metadata.get('name')}@{metadata.get('version')}"

    spec = data.get("spec")
    if not isinstance(spec, dict):
        errors.append("manifest.spec: spec must be a mapping")
        spec = {}

    dependencies = spec.get("dependencies", []) or []
    if not isinstance(dependencies, list):
        errors.append("manifest.dependency: spec.dependencies must be a list")
        dependencies = []
    for dep in dependencies:
        ref = dep.get("ref") if isinstance(dep, dict) else dep
        if not (isinstance(ref, str) and PACKAGE_REF_RE.match(ref)):
            errors.append(f"manifest.dependency: dependency {dep!r} must be <namespace>/<name>@<exact-semver> or a mapping with such a ref")

    extension_names, extension_errors = structure.declared_extensions(spec)
    errors.extend(extension_errors)
    errors.extend(structure.structure_errors(data, structure.MANIFEST, MANIFEST, extension_names))
    errors.extend(structure.extension_definition_errors(spec))
    definition = spec.get("extensionDefinition")
    for rel in (definition.get("schemas") or []) if isinstance(definition, dict) and isinstance(definition.get("schemas"), list) else []:
        if isinstance(rel, str) and rel and not ontology_module._inside(root, rel):
            errors.append(f"extension.definition: spec.extensionDefinition.schemas entry {rel} must be an existing file inside the package")

    card = {
        "WorldPackage": "WORLD.md",
        "WorldModelPackage": "WORLDMODEL.md",
        "OntologyPackage": "ONTOLOGY.md",
    }.get(kind)
    if card and not (root / card).exists():
        errors.append(f"package.card: {kind} requires {card}")

    if kind == "WorldPackage":
        world = spec.get("world")
        if not isinstance(world, dict):
            errors.append("world.spec: WorldPackage requires spec.world")
        elif not (world.get("definition") or world.get("description")):
            warnings.append("world.undescribed: spec.world should declare definition or description")

    if kind == "WorldModelPackage":
        wm = spec.get("worldModel")
        if not isinstance(wm, dict):
            errors.append("worldmodel.spec: WorldModelPackage requires spec.worldModel")
        else:
            if not wm.get("roles"):
                errors.append("worldmodel.roles: spec.worldModel.roles must contain at least one role")
            grounding = wm.get("semanticGrounding")
            if not isinstance(grounding, dict) or not isinstance(grounding.get("worldRef"), str) or not grounding.get("worldRef", "").strip():
                errors.append("worldmodel.world-ref: WorldModelPackage requires spec.worldModel.semanticGrounding.worldRef")
                grounding = {}
            views = grounding.get("compatibleWorldViews") if isinstance(grounding, dict) else None
            if not isinstance(views, list) or not views or not all(isinstance(x, str) and x.strip() for x in views):
                errors.append("worldmodel.compatible-views: WorldModelPackage requires at least one semanticGrounding.compatibleWorldViews reference")
            compilers = grounding.get("compatibleStateCompilers") if isinstance(grounding, dict) else None
            if not isinstance(compilers, list) or not compilers or not all(isinstance(x, str) and x.strip() for x in compilers):
                errors.append("worldmodel.compatible-compilers: WorldModelPackage requires at least one semanticGrounding.compatibleStateCompilers reference")
            world_ref = grounding.get("worldRef")
            if isinstance(world_ref, str) and world_ref.strip() and not PACKAGE_REF_RE.match(world_ref):
                errors.append(f"worldmodel.world-ref: semanticGrounding.worldRef {world_ref!r} must be <namespace>/<name>@<exact-semver>")
            for field, refs in (("compatibleWorldViews", views), ("compatibleStateCompilers", compilers)):
                for ref in refs if isinstance(refs, list) and isinstance(world_ref, str) else []:
                    if isinstance(ref, str) and (ref.partition("#")[0] != world_ref or not ref.partition("#")[2]):
                        errors.append(f"worldmodel.grounding-ref: semanticGrounding.{field} entry {ref!r} must have the form <worldRef>#<asset path> with worldRef {world_ref}")

    if kind == "OntologyPackage":
        ontology = spec.get("ontology")
        if not isinstance(ontology, dict):
            errors.append("ontology.spec: OntologyPackage requires spec.ontology")
        else:
            onto_errors, onto_warnings = ontology_module.ontology_issues(root, spec, extension_names)
            errors.extend(onto_errors)
            warnings.extend(onto_warnings)

    assets = spec.get("assets", []) or []
    if not isinstance(assets, list):
        errors.append("asset.list: spec.assets must be a list when present")
        assets = []
    seen_paths: set[str] = set()
    experimental_docs: list[tuple[str, str, dict[str, Any]]] = []
    local_asset_kinds: dict[str, str] = {}
    local_asset_docs: dict[str, dict[str, Any]] = {}
    asset_kinds: set[str] = set()
    for idx, item in enumerate(assets):
        if not isinstance(item, dict):
            errors.append(f"asset.entry: spec.assets[{idx}] must be a mapping")
            continue
        asset_kind = item.get("kind")
        if not isinstance(asset_kind, str) or not asset_kind.strip():
            errors.append(f"asset.kind: spec.assets[{idx}].kind is required")
        else:
            asset_kinds.add(asset_kind)
            if ":" in asset_kind:
                match = structure.EXTENSION_KIND_RE.match(asset_kind)
                if not match:
                    errors.append(f"asset.kind: spec.assets[{idx}].kind {asset_kind!r} must be <extension>:<Kind>")
                elif match.group(1) not in extension_names:
                    errors.append(f"extension.undeclared: spec.assets[{idx}].kind {asset_kind!r} uses extension {match.group(1)!r}, which spec.dependencies does not declare with 'as'")
            elif asset_kind not in KNOWN_ASSET_KINDS:
                warnings.append(f"asset.kind-unknown: unrecognized unqualified asset kind: {asset_kind}")
            elif ASSET_KIND_STABILITY[asset_kind] == "experimental":
                warnings.append(f"asset.kind-experimental: asset kind {asset_kind} is experimental and may change")
        has_path = isinstance(item.get("path"), str) and bool(item.get("path").strip())
        has_ref = "ref" in item
        if has_ref:
            ref_errors, ref_warnings = structure.external_ref_issues(item["ref"], f"spec.assets[{idx}].ref", extension_names)
            errors.extend(ref_errors)
            warnings.extend(ref_warnings)
        if has_path == has_ref:
            errors.append(f"asset.path-or-ref: spec.assets[{idx}] must declare exactly one of path or ref")
            continue
        if has_path:
            rel = item["path"]
            if rel.startswith("./") or "\\" in rel:
                errors.append(f"asset.path-form: local asset path {rel!r} must be a relative POSIX path without a leading './'")
            if rel in seen_paths:
                errors.append(f"asset.duplicate-path: duplicate local asset path: {rel}")
                continue
            seen_paths.add(rel)
            if isinstance(asset_kind, str):
                local_asset_kinds[rel] = asset_kind
            target = (root / rel).resolve()
            try:
                target.relative_to(root)
            except ValueError:
                errors.append(f"asset.path-escape: asset path escapes package root: {rel}")
                continue
            if not target.exists():
                errors.append(f"asset.missing-file: local asset path does not exist: {rel}")
                continue
            if target.suffix.lower() in {".yaml", ".yml"}:
                try:
                    adata = yaml.safe_load(target.read_text(encoding="utf-8"))
                except Exception as exc:
                    errors.append(f"asset.yaml: cannot parse asset YAML {rel}: {exc}")
                    continue
                # Examples may be any document (for example an ObservationSet), so their kind is not checked.
                if asset_kind != "PackageExample" and isinstance(adata, dict) and adata.get("kind") and adata.get("kind") != asset_kind:
                    errors.append(f"asset.kind-mismatch: asset kind mismatch for {rel}: manifest={asset_kind}, file={adata.get('kind')}")
                if isinstance(adata, dict):
                    local_asset_docs[rel] = adata
                    if asset_kind == "SemanticBinding":
                        pass  # checked by binding_issues after the asset loop
                    elif asset_kind in experimental.TABLES:
                        experimental_docs.append((rel, asset_kind, adata))
                    elif asset_kind != "PackageExample":
                        errors.extend(_asset_structure_errors(adata, asset_kind, rel, extension_names))

    for rel, asset_kind, adata in experimental_docs:
        exp_errors, exp_warnings = experimental.experimental_issues(adata, asset_kind, rel, root, spec, local_asset_kinds, extension_names)
        errors.extend(exp_errors)
        warnings.extend(exp_warnings)
    warnings.extend(experimental.view_specialization_warnings(local_asset_kinds, local_asset_docs))
    view_includes = {x for rel, k in local_asset_kinds.items() if k == "WorldViewProfile"
                     for x in (experimental.resolve_view(rel, local_asset_docs, local_asset_kinds).get("projection") or {}).get("include", []) or []
                     if isinstance(x, str)}
    bind_errors, bind_warnings = binding_module.binding_issues(spec, local_asset_kinds, local_asset_docs, view_includes, extension_names)
    errors.extend(bind_errors)
    warnings.extend(bind_warnings)

    if kind == "WorldModelPackage":
        if "ModelArtifact" not in asset_kinds:
            warnings.append("worldmodel.model-artifact-missing: WorldModelPackage should reference a ModelArtifact, even if it is contract-only/unbound")
        if "EvaluationProfile" not in asset_kinds:
            warnings.append("worldmodel.evaluation-profile-missing: WorldModelPackage should reference an EvaluationProfile")
        if "RepresentationAdapterProfile" not in asset_kinds:
            errors.append("worldmodel.adapter: WorldModelPackage requires a RepresentationAdapterProfile (an identity adapter is valid when no transform is needed)")
        wm = spec.get("worldModel") or {}
        inputs = wm.get("inputs") if isinstance(wm, dict) else None
        if not isinstance(inputs, dict) or inputs.get("contract") != "EffectiveWorldState":
            errors.append("worldmodel.input-contract: WorldModelPackage requires spec.worldModel.inputs.contract = EffectiveWorldState")
        representation = wm.get("representation") if isinstance(wm, dict) else None
        adapter_ref = representation.get("adapterRef") if isinstance(representation, dict) else None
        if not isinstance(adapter_ref, str) or not adapter_ref.strip():
            errors.append("worldmodel.adapter-ref: WorldModelPackage requires spec.worldModel.representation.adapterRef")
        elif local_asset_kinds.get(adapter_ref) != "RepresentationAdapterProfile":
            errors.append("worldmodel.adapter-ref: spec.worldModel.representation.adapterRef must point to a local RepresentationAdapterProfile asset")
        else:
            adapter_doc = local_asset_docs.get(adapter_ref) or {}
            adapter_spec = adapter_doc.get("spec") if isinstance(adapter_doc, dict) else None
            if not isinstance(adapter_spec, dict) or adapter_spec.get("source") != "EffectiveWorldState":
                errors.append("worldmodel.adapter-source: RepresentationAdapterProfile referenced by adapterRef must declare spec.source = EffectiveWorldState")

    if kind == "WorldPackage":
        conformance = spec.get("conformance") if spec.get("conformance") is not None else {}
        profile = conformance.get("profile", DEFAULT_WORLD_PROFILE) if isinstance(conformance, dict) else None
        if profile not in WORLD_PROFILES:
            errors.append(f"profile.unknown: spec.conformance.profile must be one of {WORLD_PROFILES}")
        else:
            errors.extend(_world_profile_errors(profile, spec, asset_kinds, local_asset_kinds, local_asset_docs, identity))
    elif kind == "OntologyPackage" and spec.get("conformance") is not None:
        conformance = spec.get("conformance")
        profile = conformance.get("profile") if isinstance(conformance, dict) else None
        if profile not in ontology_module.ONTOLOGY_PROFILES:
            errors.append(f"profile.unknown: spec.conformance.profile must be one of {ontology_module.ONTOLOGY_PROFILES} for an OntologyPackage")
        else:
            errors.extend(ontology_module.ontology_profile_errors(profile, root, spec))
    elif spec.get("conformance") is not None:
        warnings.append("manifest.conformance-ignored: spec.conformance applies to WorldPackage and OntologyPackage only and is ignored")

    _validate_evaluation_lineage(spec, kind, identity, local_asset_kinds, local_asset_docs, errors, warnings)

    return ValidationResult(not errors, errors, warnings, data)


def inspect_package(path: str | Path, graph: bool = False, resolved_views: bool = False) -> dict[str, Any]:
    root, data = load_manifest(path)
    result = validate_package(root)
    md = data.get("metadata") or {}
    spec = data.get("spec") or {}
    summary: dict[str, Any] = {}
    if data.get("kind") == "WorldPackage" and isinstance(spec, dict):
        kinds, docs = _local_assets(root, spec)
        conformance = spec.get("conformance") if isinstance(spec.get("conformance"), dict) else {}
        summary["conformance"] = {
            "declared": conformance.get("profile", DEFAULT_WORLD_PROFILE),
            "satisfied": satisfied_world_profile(spec, {k for k in kinds.values()} | _ref_asset_kinds(spec), kinds, docs,
                                                 f"{md.get('namespace')}/{md.get('name')}@{md.get('version')}"),
        }
    if data.get("kind") == "WorldPackage" and isinstance(spec, dict) and isinstance((spec.get("world") or {}).get("semanticBinding"), str):
        kinds, docs = _local_assets(root, spec)
        bdoc = docs.get(spec["world"]["semanticBinding"]) or {}
        bound = set(((bdoc.get("spec") or {}).get("fields") or {}))
        fields = set()
        for rel, k in kinds.items():
            if k == "StateCompilerProfile":
                fields |= set((((docs.get(rel) or {}).get("spec") or {}).get("outputSchema") or {}).get("fields") or [])
        summary["semanticCoverage"] = {"boundFields": len(bound & fields), "fields": len(fields)}
    if data.get("kind") == "OntologyPackage" and isinstance(spec, dict):
        conformance = spec.get("conformance") if isinstance(spec.get("conformance"), dict) else {}
        summary["conformance"] = {"declared": conformance.get("profile"),
                                  "satisfied": ontology_module.satisfied_ontology_profile(root, spec)}
    if graph or resolved_views:
        kinds, docs = _local_assets(root, spec if isinstance(spec, dict) else {})
        if graph:
            summary["graph"] = experimental.reference_graph(data, docs, kinds)
        if resolved_views:
            summary["resolvedViews"] = {rel: experimental.resolve_view(rel, docs, kinds)
                                        for rel, k in sorted(kinds.items()) if k == "WorldViewProfile"}
    return {
        "root": str(root),
        "identity": f"{md.get('namespace','?')}/{md.get('name','?')}@{md.get('version','?')}",
        "kind": data.get("kind"),
        "valid": result.valid,
        "errors": result.errors,
        "warnings": result.warnings,
        "asset_count": len(spec.get("assets", []) or []),
        "domains": spec.get("domains", []),
        "extensions": [
            {"name": d["as"], "ref": d.get("ref"), "mustUnderstand": bool(d.get("mustUnderstand", False))}
            for d in (spec.get("dependencies") or []) if isinstance(d, dict) and isinstance(d.get("as"), str)
        ],
        **summary,
    }


def _local_assets(root: Path, spec: dict[str, Any]) -> tuple[dict[str, str], dict[str, dict[str, Any]]]:
    """Kinds and parsed YAML documents of local assets, keyed by package-relative path."""
    kinds: dict[str, str] = {}
    docs: dict[str, dict[str, Any]] = {}
    for item in spec.get("assets", []) or []:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str) or not isinstance(item.get("kind"), str):
            continue
        kinds[item["path"]] = item["kind"]
        target = (root / item["path"]).resolve()
        try:
            target.relative_to(root)
            doc = yaml.safe_load(target.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(doc, dict):
            docs[item["path"]] = doc
    return kinds, docs


def _ref_asset_kinds(spec: dict[str, Any]) -> set[str]:
    return {a["kind"] for a in spec.get("assets", []) or [] if isinstance(a, dict) and isinstance(a.get("kind"), str) and isinstance(a.get("ref"), dict)}


def package_files(root: Path) -> list[Path]:
    ignored_parts = {".git", ".ontle", "__pycache__", ".pytest_cache", ".mypy_cache", ".venv", "venv", "dist", "build"}
    files: list[Path] = []
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(root)
        if any(part in ignored_parts for part in rel.parts):
            continue
        if p.name.endswith(".owp.zip"):
            continue
        files.append(p)
    return sorted(files, key=lambda p: p.relative_to(root).as_posix())


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build_lock(root: Path, files: list[Path]) -> dict[str, Any]:
    entries = []
    for p in files:
        data = p.read_bytes()
        entries.append({
            "path": p.relative_to(root).as_posix(),
            "sha256": sha256_bytes(data),
            "size": len(data),
        })
    manifest_bytes = (root / MANIFEST).read_bytes()
    return {
        "format": "owp-lock/v1alpha1",
        "manifest": MANIFEST,
        "manifest_sha256": sha256_bytes(manifest_bytes),
        "files": entries,
    }


def deterministic_pack(path: str | Path, output: str | Path | None = None) -> Path:
    root, manifest = load_manifest(path)
    _ensure_term_index(root, manifest)
    root, manifest = load_manifest(path)
    result = validate_package(root)
    if not result.valid:
        raise OWPError("package is invalid: " + "; ".join(result.errors))
    md = manifest["metadata"]
    if output is None:
        out_dir = root / "dist"
        out_dir.mkdir(exist_ok=True)
        output = out_dir / f"{md['namespace']}-{md['name']}-{md['version']}.owp.zip"
    output = Path(output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    files = package_files(root)
    lock = build_lock(root, files)
    lock_bytes = (json.dumps(lock, indent=2, sort_keys=True) + "\n").encode("utf-8")

    fixed_date = (2020, 1, 1, 0, 0, 0)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for p in files:
            rel = p.relative_to(root).as_posix()
            zi = zipfile.ZipInfo(rel, date_time=fixed_date)
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = (0o644 & 0xFFFF) << 16
            zf.writestr(zi, p.read_bytes())
        zi = zipfile.ZipInfo("owp.lock.json", date_time=fixed_date)
        zi.compress_type = zipfile.ZIP_DEFLATED
        zi.external_attr = (0o644 & 0xFFFF) << 16
        zf.writestr(zi, lock_bytes)
    return output


def _ensure_term_index(root: Path, manifest: dict[str, Any]) -> None:
    """DD-2: an OntologyPackage whose schema is not owp-yaml needs a term index; generate it when it is missing and rdflib is available."""
    if manifest.get("kind") != "OntologyPackage":
        return
    onto = (manifest.get("spec") or {}).get("ontology")
    if not isinstance(onto, dict) or onto.get("termIndex"):
        return
    schema = [e for e in onto.get("entrypoints") or [] if isinstance(e, dict) and e.get("role") == "schema"]
    if schema and not any(e.get("format") == "owp-yaml" for e in schema):
        try:
            import rdflib  # noqa: F401
        except ImportError:
            return  # validation reports the missing index
        ontology_module.write_term_index(root, root / MANIFEST)


def verify_archive(path: str | Path) -> tuple[bool, list[str]]:
    archive = Path(path).expanduser().resolve()
    errors: list[str] = []
    with zipfile.ZipFile(archive, "r") as zf:
        names = set(zf.namelist())
        if "owp.lock.json" not in names:
            return False, ["archive missing owp.lock.json"]
        lock = json.loads(zf.read("owp.lock.json"))
        locked = {entry.get("path") for entry in lock.get("files", []) if isinstance(entry, dict)}
        for name in sorted(names - locked - {"owp.lock.json"}):
            errors.append(f"unlocked archived file: {name}")
        for entry in lock.get("files", []):
            name = entry["path"]
            if name not in names:
                errors.append(f"missing archived file: {name}")
                continue
            data = zf.read(name)
            if sha256_bytes(data) != entry["sha256"]:
                errors.append(f"hash mismatch: {name}")
        if MANIFEST not in names:
            errors.append(f"archive missing {MANIFEST}")
        elif sha256_bytes(zf.read(MANIFEST)) != lock.get("manifest_sha256"):
            errors.append(f"manifest hash mismatch: {MANIFEST}")
    return not errors, errors
