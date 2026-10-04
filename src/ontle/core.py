from __future__ import annotations

from dataclasses import dataclass
from importlib import resources
from pathlib import Path
import hashlib
import json
import posixpath
import re
import tempfile
import zipfile
from typing import Any, Iterator

from . import binding as binding_module
from . import experimental, structure
from . import ontology as ontology_module
from .ignore import IGNORE_FILE, is_ignored, load_ignore
from .values import WHITESPACE, PathMap, dig, js_equal, js_string, nonempty_str, normalize_rel_path
from .yamlio import dump_yaml, load_yaml

MANIFEST = "owp.yaml"
KINDS = {"WorldPackage", "WorldModelPackage", "OntologyPackage"}
LEGACY_MANIFESTS = {"package.yaml", "world.yaml"}


def _load_vocabulary() -> dict[str, str]:
    """Asset kind -> stability, from vocab/asset-kinds.yaml (packaged as ontle.vocab)."""
    try:
        text = resources.files("ontle.vocab").joinpath("asset-kinds.yaml").read_text(encoding="utf-8")
    except (ModuleNotFoundError, FileNotFoundError):  # editable install: read the repository copy
        text = (Path(__file__).resolve().parents[2] / "vocab" / "asset-kinds.yaml").read_text(encoding="utf-8")
    groups = load_yaml(text)["groups"]
    return {kind: entry["stability"] for group in groups.values() for kind, entry in group.items()}


ASSET_KIND_STABILITY = _load_vocabulary()
KNOWN_ASSET_KINDS = set(ASSET_KIND_STABILITY)
DOCUMENT_KINDS = {"ObservationSet", "EffectiveWorldState"}  # OWP documents that are package files, not assets
# ASCII digits only: Python's \d also matches other decimal digits (such as U+0663 or full-width digits).
SEMVER_PATTERN = r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?"
SEMVER_RE = re.compile(rf"^{SEMVER_PATTERN}\Z")
# Exact reference to a versioned asset: <name>@<semver>. Ranges are not allowed.
PINNED_REF_RE = re.compile(rf"^[^@{WHITESPACE}]+@{SEMVER_PATTERN}\Z")
# Exact package reference: <namespace>/<name>@<semver>.
PACKAGE_REF_RE = re.compile(rf"^[^/@#{WHITESPACE}]+/[^/@#{WHITESPACE}]+@{SEMVER_PATTERN}\Z")
IDENTITY_PART_RE = re.compile(rf"^[^/@#{WHITESPACE}]+\Z")
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


MANIFEST_SCHEMA_LINE = "# yaml-language-server: $schema=https://raw.githubusercontent.com/ontle-world/open-world-package/main/schemas/owp-manifest.schema.json\n"


def write_manifest(path: Path, data: dict[str, Any]) -> None:
    """Write owp.yaml, keeping its leading comment lines (or adding the editor schema line to a new file)."""
    head = MANIFEST_SCHEMA_LINE
    if path.exists():
        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
        head = "".join(line for line in lines[:next((i for i, line in enumerate(lines) if not line.startswith("#")), len(lines))])
    path.write_text(head + dump_yaml(data), encoding="utf-8")


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
        data = load_yaml(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise OWPError(f"cannot parse {MANIFEST}: {exc}") from exc
    if not isinstance(data, dict):
        raise OWPError(f"{MANIFEST} must contain a YAML mapping")
    return root, data


def _asset_path_form(path: str) -> bool:
    """A package-relative POSIX path in normal form: no leading './' or '/', no '..', '//', or trailing '/' (spec 3)."""
    return (bool(path) and "\\" not in path and not re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", path)
            and posixpath.normpath(path) == path and not path.startswith(("/", "../")) and path not in {".", ".."})


def _spec_of(doc: Any) -> dict[str, Any]:
    spec = doc.get("spec") if isinstance(doc, dict) else None
    return spec if isinstance(spec, dict) else {}


def _reject_constant(name: str) -> Any:
    raise ValueError(f"{name} is not JSON")


def output_schema_fields(root: Path, cspec: dict[str, Any], rel: str) -> tuple[list[str] | None, list[str]]:
    """EWS fields of a State Compiler (spec section 12.1) and the errors resolving them.

    The fields are `outputSchema.fields`, or the top-level `properties` keys of the JSON Schema named by
    `outputSchemaRef`; both must agree when both are present. None means the compiler declares no field list.
    """
    schema = cspec.get("outputSchema")
    declared = schema.get("fields") if isinstance(schema, dict) else None
    fields = [f for f in declared if isinstance(f, str)] if isinstance(declared, list) else None
    ref = cspec.get("outputSchemaRef")
    if ref is None:
        return fields, []
    bad = f"compiler.output-schema-ref: StateCompilerProfile {rel} spec.outputSchemaRef"
    if not isinstance(ref, str) or not ref or ref.startswith(("./", "/")) or "\\" in ref:
        return fields, [f"{bad} {ref!r} must be a relative POSIX path without a leading './'"]
    if not ontology_module.inside_package(root, ref):
        return fields, [f"{bad} {ref!r} does not name a file in the package"]
    try:
        doc = json.loads((root / ref).read_text(encoding="utf-8"), parse_constant=_reject_constant)
    except (OSError, ValueError) as exc:
        return fields, [f"{bad} {ref!r} is not a readable JSON document: {exc}"]
    properties = doc.get("properties") if isinstance(doc, dict) else None
    if not isinstance(properties, dict) or not properties:
        return fields, [f"{bad} {ref!r} must be a JSON Schema with a non-empty top-level properties object"]
    if fields is not None:  # both declared: they must agree, and outputSchema.fields (with its order) is used
        if set(fields) != set(properties):
            return fields, [f"compiler.output-schema-mismatch: StateCompilerProfile {rel} spec.outputSchema.fields and the properties of {ref!r} list different fields"]
        return fields, []
    return list(properties), []


def compiler_fields(root: Path, local_asset_kinds: dict[str, str],
                    local_asset_docs: dict[str, dict[str, Any]]) -> tuple[dict[str, list[str] | None], list[str]]:
    """EWS fields of every local State Compiler, keyed by asset path, and the errors resolving them."""
    fields: dict[str, list[str] | None] = {}
    errors: list[str] = []
    for rel, kind in sorted(local_asset_kinds.items()):
        if kind == "StateCompilerProfile":
            fields[rel], field_errors = output_schema_fields(root, _spec_of(local_asset_docs.get(rel)), rel)
            errors.extend(field_errors)
    return fields, errors


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


_ABSENT = object()  # a missing key: equal only to another missing key


def _world_profile_errors(profile: str, spec: dict[str, Any], asset_kinds: set[str],
                          local_asset_kinds: dict[str, str], local_asset_docs: dict[str, dict[str, Any]],
                          ews_fields: dict[str, list[str] | None], identity: str | None = None) -> list[str]:
    """Errors preventing a WorldPackage from satisfying one conformance profile (cumulative)."""
    level = WORLD_PROFILES.index(profile)
    errors: list[str] = []
    world = spec.get("world") if isinstance(spec.get("world"), dict) else {}
    if not nonempty_str(world.get("definition")):
        errors.append("profile.descriptive: requires spec.world.definition")
    if level < 1:
        return errors

    if "WorldViewProfile" not in asset_kinds:
        errors.append("profile.viewable: requires at least one WorldViewProfile")
    default_view = world.get("defaultView")
    if "defaultView" not in world:
        errors.append("profile.viewable: requires spec.world.defaultView")
    elif local_asset_kinds.get(default_view) != "WorldViewProfile":
        errors.append("profile.viewable: spec.world.defaultView must point to a local WorldViewProfile asset")
    if level < 2:
        return errors

    if "StateCompilerProfile" not in asset_kinds:
        errors.append("profile.stateful: requires at least one StateCompilerProfile")
    default_compiler = world.get("defaultStateCompiler")
    if "defaultStateCompiler" not in world:
        errors.append("profile.stateful: requires spec.world.defaultStateCompiler")
    elif local_asset_kinds.get(default_compiler) != "StateCompilerProfile":
        errors.append("profile.stateful: spec.world.defaultStateCompiler must point to a local StateCompilerProfile asset")
    elif not js_equal(_spec_of(local_asset_docs.get(default_compiler)).get("worldViewRef", _ABSENT), world.get("defaultView", _ABSENT)):
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
        errors.extend(binding_errors(cspec, rel, ews_fields.get(rel)))
        if level >= 3 and not ews_fields.get(rel):
            errors.append(f"profile.model-ready.output-schema: StateCompilerProfile {rel} must declare spec.outputSchema.fields or a resolvable spec.outputSchemaRef")
    if level < 4:
        return errors

    for required in ("ActionBindingProfile", "CommitContract", "EffectVerificationProfile"):
        if required not in asset_kinds:
            errors.append(f"profile.action-ready: requires a {required} asset")
    return errors


def satisfied_world_profile(spec: dict[str, Any], asset_kinds: set[str],
                            local_asset_kinds: dict[str, str], local_asset_docs: dict[str, dict[str, Any]],
                            ews_fields: dict[str, list[str] | None], identity: str | None = None) -> str | None:
    """Highest WorldPackage conformance profile the package satisfies, independent of the declared one."""
    satisfied = None
    for profile in WORLD_PROFILES:
        if _world_profile_errors(profile, spec, asset_kinds, local_asset_kinds, local_asset_docs, ews_fields, identity):
            break
        satisfied = profile
    return satisfied


def _validate_evaluation_lineage(kind: Any, identity: str | None, grounding: Grounding | None, local_asset_kinds: dict[str, str],
                                 local_asset_docs: dict[str, dict[str, Any]], errors: list[str], warnings: list[str]) -> None:
    """Evaluation lineage and evidence binding (spec 9). OWP records which exact evaluation produced a result; it does not run or evolve evaluations."""
    names: dict[str, set[str]] = {"EvaluationProfile": set(), "VerifierProfile": set()}
    for rel, asset_kind in sorted(local_asset_kinds.items()):
        if asset_kind not in names or not isinstance(local_asset_docs.get(rel), dict):
            continue
        doc = local_asset_docs[rel]
        md = doc.get("metadata") if isinstance(doc.get("metadata"), dict) else {}
        if isinstance(md.get("name"), str):
            if md["name"] in names[asset_kind]:
                errors.append(f"eval.duplicate-name: more than one local {asset_kind} is named {md['name']!r}")
            names[asset_kind].add(md["name"])
        if "version" not in md:
            warnings.append(f"eval.version-missing: {asset_kind} {rel} should declare metadata.version so evidence can bind to it")
        elif not isinstance(md["version"], str) or not SEMVER_RE.match(md["version"]):
            errors.append(f"eval.version: {asset_kind} {rel} metadata.version must use SemVer")
        spec = doc.get("spec")
        if isinstance(spec, dict) and "supersedes" in spec and not (isinstance(spec["supersedes"], str) and PINNED_REF_RE.match(spec["supersedes"])):
            errors.append(f"eval.supersedes: {asset_kind} {rel} spec.supersedes must be a pinned <name>@<version> reference")

    def local_versions(bound_kind: str, name: str) -> list[Any] | None:
        """metadata.version of each local asset of the kind named `name`; None when there is none."""
        found = []
        for rel, k in sorted(local_asset_kinds.items()):
            md = (local_asset_docs.get(rel) or {}).get("metadata") if k == bound_kind else None
            if isinstance(md, dict) and md.get("name") == name and isinstance(md.get("name"), str):
                found.append(md.get("version") if "version" in md else _MISSING)
        return found or None

    for rel, asset_kind in sorted(local_asset_kinds.items()):
        if asset_kind != "CompatibilityEvidence" or not isinstance(local_asset_docs.get(rel), dict):
            continue
        doc = local_asset_docs[rel]
        md = doc.get("metadata")
        if not (isinstance(md, dict) and nonempty_str(md.get("name"))):
            errors.append(f"evidence.required: CompatibilityEvidence {rel} must declare metadata.name")
        espec = doc.get("spec")
        if not isinstance(espec, dict):
            errors.append(f"evidence.required: CompatibilityEvidence {rel} must declare a spec mapping")
            continue
        if not nonempty_str(espec.get("subject")):
            errors.append(f"evidence.subject: CompatibilityEvidence {rel} must declare spec.subject")
        elif kind == "WorldModelPackage" and espec["subject"] != identity:
            errors.append(f"evidence.subject: CompatibilityEvidence {rel} spec.subject must be this package's identity {identity}")
        for field in ("evaluationProfile", "verifier", "goldenSet", "dataset"):
            if field not in espec:
                if field == "evaluationProfile":
                    errors.append(f"evidence.required: CompatibilityEvidence {rel} must declare spec.{field}")
                continue
            ref = espec[field]
            if not (isinstance(ref, str) and PINNED_REF_RE.match(ref)):
                errors.append(f"evidence.unpinned: CompatibilityEvidence {rel} spec.{field} must be a pinned <name>@<version> reference")
        for field, bound_kind in (("evaluationProfile", "EvaluationProfile"), ("verifier", "VerifierProfile")):
            ref = espec.get(field)
            if not (isinstance(ref, str) and PINNED_REF_RE.match(ref)):
                continue
            name, _, version = ref.rpartition("@")
            versions = local_versions(bound_kind, name)
            if versions is not None and version not in [v for v in versions if isinstance(v, str)]:
                errors.append(f"evidence.version-mismatch: CompatibilityEvidence {rel} binds {ref} but the packaged {bound_kind} {name} has a different version")
        scope = espec.get("scope")
        if not isinstance(scope, dict):
            errors.append(f"evidence.scope: CompatibilityEvidence {rel} must declare spec.scope.worldRef and spec.scope.worldView")
        else:
            for field in ("worldRef", "worldView"):
                if not nonempty_str(scope.get(field)):
                    errors.append(f"evidence.scope: CompatibilityEvidence {rel} must declare spec.scope.{field}")
            for field in ("stateCompiler", "environment", "task"):
                if field in scope and not nonempty_str(scope[field]):
                    errors.append(f"evidence.scope: CompatibilityEvidence {rel} spec.scope.{field} must be a non-empty string when present")
            if grounding is not None:
                if nonempty_str(scope.get("worldRef")) and grounding.world_ref is not None and scope["worldRef"] != grounding.world_ref:
                    errors.append(f"evidence.scope.world-ref: CompatibilityEvidence {rel} scope.worldRef differs from semanticGrounding.worldRef")
                if nonempty_str(scope.get("worldView")) and scope["worldView"] not in grounding.views:
                    errors.append(f"evidence.scope.world-view: CompatibilityEvidence {rel} scope.worldView is outside semanticGrounding.compatibleWorldViews")
                if nonempty_str(scope.get("stateCompiler")) and scope["stateCompiler"] not in grounding.compilers:
                    errors.append(f"evidence.scope.state-compiler: CompatibilityEvidence {rel} scope.stateCompiler is outside semanticGrounding.compatibleStateCompilers")
        if not isinstance(espec.get("result"), dict):
            errors.append(f"evidence.result: CompatibilityEvidence {rel} must declare spec.result")


_MISSING = object()


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


def view_external_names(vspec: dict[str, Any]) -> list[tuple[str, str]]:
    """(world ref, name) for each projection.include entry written as <world ref>#<name>."""
    include = (vspec.get("projection") or {}).get("include") if isinstance(vspec.get("projection"), dict) else None
    return [tuple(x.split("#", 1)) for x in include if isinstance(x, str) and "#" in x] if isinstance(include, list) else []  # type: ignore[misc]


def _external_world_errors(rel: str, vspec: dict[str, Any], spec: dict[str, Any]) -> list[str]:
    """Section 6: a View names the other Worlds it reads in spec.externalWorldRefs, and each is a dependency."""
    errors: list[str] = []
    refs = vspec.get("externalWorldRefs")
    if refs is not None and not (isinstance(refs, list) and all(isinstance(r, str) for r in refs)):
        return [f"view.external-world: {rel}: spec.externalWorldRefs must be a list of package references"]
    declared = set(refs or [])
    deps = [d if isinstance(d, str) else d.get("ref") for d in _list(spec.get("dependencies")) if isinstance(d, (str, dict))]
    for ref in refs or []:
        if ref not in deps:
            errors.append(f"view.external-world: {rel}: external World {ref} must also be listed in spec.dependencies")
    for ref, name in view_external_names(vspec):
        if ref not in declared:
            errors.append(f"view.external-world: {rel}: projection.include '{ref}#{name}' names a World that spec.externalWorldRefs does not list")
    return errors


def _containment_warnings(spec: dict[str, Any], local_asset_kinds: dict[str, str], local_asset_docs: dict[str, dict[str, Any]],
                          ews_fields: dict[str, list[str] | None]) -> list[str]:
    """Section 6: a View selects from the World's boundary, and a State Compiler's fields belong to its View's names."""
    warnings: list[str] = []
    world = spec.get("world") if isinstance(spec.get("world"), dict) else {}
    boundary = world.get("boundary") if isinstance(world.get("boundary"), dict) else {}
    included = {x for x in boundary.get("included") or [] if isinstance(x, str)} if isinstance(boundary.get("included"), list) else set()
    includes: dict[str, set[str]] = {}
    for rel, k in sorted(local_asset_kinds.items()):
        if k != "WorldViewProfile":
            continue
        names = dig(experimental.resolve_view(rel, local_asset_docs, local_asset_kinds), "projection", "include")
        own = {x for x in names if isinstance(x, str) and "#" not in x} if isinstance(names, list) else set()
        external = {x.split("#", 1)[1] for x in names if isinstance(x, str) and "#" in x} if isinstance(names, list) else set()
        includes[rel] = own | external  # a compiler field may describe an entity of an external World the View selects
        for name in sorted(own - included) if included else []:
            warnings.append(f"view.outside-world: {rel}: projection.include {name!r} is not in spec.world.boundary.included")
    for rel, k in sorted(local_asset_kinds.items()):
        if k != "StateCompilerProfile":
            continue
        view = _spec_of(local_asset_docs.get(rel)).get("worldViewRef")
        names = includes.get(view) if isinstance(view, str) else None
        for field in ews_fields.get(rel) or [] if names else []:
            entity = field.split(".", 1)[0]
            if field.find(".") > 0 and entity not in names:
                warnings.append(f"compiler.field-outside-view: {rel}: field {field!r} names {entity!r}, which {view}'s projection.include does not list")
    return warnings


def dependency_problems(spec: dict[str, Any]) -> list[str]:
    """Spec 11: spec.dependencies lists exact <namespace>/<name>@<version> strings or {ref, source, as, mustUnderstand} mappings."""
    if "dependencies" not in spec:
        return []
    deps = spec["dependencies"]
    if not isinstance(deps, list):
        return ["spec.dependencies must be a list"]
    problems: list[str] = []
    for i, dep in enumerate(deps):
        if isinstance(dep, dict):
            ref = dep.get("ref")
            if "source" in dep and not nonempty_str(dep["source"]):
                problems.append(f"spec.dependencies[{i}].source must be a non-empty string")
        elif isinstance(dep, str):
            ref = dep
        else:
            problems.append(f"spec.dependencies[{i}] must be a string or a {{ref, source}} mapping")
            continue
        if not isinstance(ref, str):
            problems.append(f"spec.dependencies[{i}] requires ref <namespace>/<name>@<version>")
        elif not PACKAGE_REF_RE.match(ref):
            problems.append(f"spec.dependencies[{i}] {ref!r} must be an exact <namespace>/<name>@<version>; ranges are not allowed")
    return problems


@dataclass
class Grounding:
    """A World Model's semantic grounding as far as it is well-formed: entries that are not <worldRef>#<path> are left out."""
    world_ref: str | None
    views: list[str]
    compilers: list[str]


def contract_ref_path(entry: Any, world_ref: str | None) -> str | None:
    """The asset path of a `<worldRef>#<asset path>` grounding entry, or None when the entry is malformed."""
    if not nonempty_str(entry) or "#" not in entry:
        return None
    ref, _, path = entry.partition("#")
    if world_ref is not None and ref != world_ref:
        return None
    norm = normalize_rel_path(path)
    return norm if norm is not None and norm == path and not path.startswith("./") else None


def _world_model_grounding(spec: dict[str, Any], errors: list[str]) -> Grounding:
    """Spec 3 (WorldModelPackage): roles and semanticGrounding."""
    g = Grounding(None, [], [])
    wm = spec.get("worldModel")
    if not isinstance(wm, dict):
        errors.append("worldmodel.spec: WorldModelPackage requires spec.worldModel")
        return g
    roles = wm.get("roles")
    if not isinstance(roles, list) or not roles or not all(nonempty_str(r) for r in roles):
        errors.append("worldmodel.roles: spec.worldModel.roles must be a non-empty list of non-empty strings")
    sg = wm.get("semanticGrounding")
    if not isinstance(sg, dict):
        errors.append("worldmodel.world-ref: WorldModelPackage requires spec.worldModel.semanticGrounding.worldRef")
        errors.append("worldmodel.compatible-views: WorldModelPackage requires semanticGrounding.compatibleWorldViews")
        errors.append("worldmodel.compatible-compilers: WorldModelPackage requires semanticGrounding.compatibleStateCompilers")
        return g
    world_ref = sg.get("worldRef")
    if not nonempty_str(world_ref):
        errors.append("worldmodel.world-ref: WorldModelPackage requires spec.worldModel.semanticGrounding.worldRef")
    else:
        if not PACKAGE_REF_RE.match(world_ref):
            errors.append(f"worldmodel.world-ref: semanticGrounding.worldRef {world_ref!r} must be <namespace>/<name>@<exact-semver>")
        g.world_ref = world_ref
    for field, into, rule in (("compatibleWorldViews", g.views, "worldmodel.compatible-views"),
                              ("compatibleStateCompilers", g.compilers, "worldmodel.compatible-compilers")):
        refs = sg.get(field)
        if not isinstance(refs, list) or not refs:
            errors.append(f"{rule}: WorldModelPackage requires at least one semanticGrounding.{field} reference")
            continue
        for i, ref in enumerate(refs):
            if contract_ref_path(ref, g.world_ref) is None:
                errors.append(f"worldmodel.grounding-ref: semanticGrounding.{field}[{i}] {ref!r} must have the form <worldRef>#<asset path>"
                              + (f" with worldRef {g.world_ref}" if g.world_ref else ""))
            else:
                into.append(ref)
    return g


def validate_package(path: str | Path) -> ValidationResult:
    errors: list[str] = []
    warnings: list[str] = []
    try:
        root, data = load_manifest(path)
    except OWPError as exc:
        root = package_root(path)
        legacy = [f"package.legacy-manifest: legacy manifest {name} is not allowed; use only {MANIFEST}"
                  for name in sorted(LEGACY_MANIFESTS) if root.is_dir() and (root / name).exists()]
        return ValidationResult(False, legacy + [f"manifest.load: {exc}"], warnings, None)

    for legacy in sorted(LEGACY_MANIFESTS):
        if (root / legacy).exists():
            errors.append(f"package.legacy-manifest: legacy manifest {legacy} is not allowed; use only {MANIFEST}")

    if data.get("apiVersion") != "openworld/v1alpha1":
        errors.append("manifest.api-version: apiVersion must be openworld/v1alpha1")

    kind = data.get("kind") if isinstance(data.get("kind"), str) else None
    if kind not in KINDS:
        errors.append(f"manifest.kind: kind must be one of {sorted(KINDS)}")

    metadata = data.get("metadata")
    raw_identity = None  # <namespace>/<name>@<version> from the raw metadata, for identity comparisons
    if not isinstance(metadata, dict):
        errors.append("manifest.metadata: metadata must be a mapping")
        metadata = {}
    else:
        for key in ("namespace", "name"):
            if not nonempty_str(metadata.get(key)):
                errors.append(f"manifest.identity: metadata.{key} is required")
            elif not IDENTITY_PART_RE.match(metadata[key]):
                errors.append(f"manifest.identity: metadata.{key} must not contain '/', '@', '#', or whitespace")
        version = metadata.get("version")
        if version is None or version == "":
            errors.append("manifest.identity: metadata.version is required")
        elif not isinstance(version, str) or not SEMVER_RE.match(version):
            errors.append("manifest.version: metadata.version must use SemVer (for example 0.1.0 or 0.1.0-alpha.1)")
        if all(key in metadata for key in ("namespace", "name", "version")):
            raw_identity = f"{js_string(metadata['namespace'])}/{js_string(metadata['name'])}@{js_string(metadata['version'])}"
    identity = raw_identity

    spec = data.get("spec")
    if not isinstance(spec, dict):
        errors.append("manifest.spec: spec must be a mapping")
        spec = {}

    errors.extend(f"manifest.dependency: {p}" for p in dependency_problems(spec))

    extension_names, extension_errors = structure.declared_extensions(spec)
    errors.extend(extension_errors)
    errors.extend(structure.structure_errors(data, structure.MANIFEST, MANIFEST, extension_names))
    errors.extend(structure.extension_definition_errors(spec))
    definition = spec.get("extensionDefinition")
    for i, rel in enumerate(definition.get("schemas")) if isinstance(definition, dict) and isinstance(definition.get("schemas"), list) else []:
        if nonempty_str(rel) and normalize_rel_path(rel) is not None and not rel.startswith("./") and not ontology_module.inside_package(root, rel):
            errors.append(f"extension.definition: spec.extensionDefinition.schemas[{i}] {rel} must be an existing file inside the package")

    card = {
        "WorldPackage": "WORLD.md",
        "WorldModelPackage": "WORLDMODEL.md",
        "OntologyPackage": "ONTOLOGY.md",
    }.get(kind or "")
    if card and not (root / card).exists():
        errors.append(f"package.card: {kind} requires {card}")

    if kind == "WorldPackage":
        world = spec.get("world")
        if not isinstance(world, dict):
            errors.append("world.spec: WorldPackage requires spec.world")
        elif not (nonempty_str(world.get("definition")) or nonempty_str(world.get("description"))):
            warnings.append("world.undescribed: spec.world should declare definition or description")

    grounding: Grounding | None = None
    if kind == "WorldModelPackage":
        grounding = _world_model_grounding(spec, errors)

    if kind == "OntologyPackage":
        ontology = spec.get("ontology")
        if not isinstance(ontology, dict):
            errors.append("ontology.spec: OntologyPackage requires spec.ontology")
        else:
            onto_errors, onto_warnings = ontology_module.ontology_issues(root, spec, extension_names)
            errors.extend(onto_errors)
            warnings.extend(onto_warnings)

    assets = spec.get("assets", [])
    if not isinstance(assets, list):  # an absent key is no assets; any other value that is not a list is malformed
        errors.append("asset.list: spec.assets must be a list when present")
        assets = []
    experimental_docs: list[tuple[str, str, dict[str, Any]]] = []
    experimental_kind_counts: dict[str, int] = {}
    reserved_kind_counts: dict[str, int] = {}
    standard_docs: list[tuple[str, str, dict[str, Any]]] = []
    local_asset_kinds: dict[str, str] = PathMap()
    local_asset_docs: dict[str, dict[str, Any]] = PathMap()
    asset_kinds: set[str] = set()

    def kind_issues(asset_kind: str, where: str, discovered: bool) -> bool:
        """Errors and warnings for one asset kind; False when the kind cannot be used."""
        if ":" in asset_kind:
            match = structure.EXTENSION_KIND_RE.match(asset_kind)
            if not match:
                errors.append(f"asset.kind: {where} {asset_kind!r} must be <extension>:<Kind>")
                return False
            if match.group(1) not in extension_names:
                errors.append(f"extension.undeclared: {where} {asset_kind!r} uses extension {match.group(1)!r}, which spec.dependencies does not declare with 'as'")
        elif asset_kind not in KNOWN_ASSET_KINDS:
            if discovered:  # a file that says it is an OWP document must name a kind OWP knows (spec section 5)
                errors.append(f"asset.kind: {where} {asset_kind!r} is not an asset kind of the vocabulary or an extension kind")
                return False
            warnings.append(f"asset.kind-unknown: unrecognized unqualified asset kind: {asset_kind}")
        elif ASSET_KIND_STABILITY[asset_kind] in ("experimental", "reserved"):
            counts = experimental_kind_counts if ASSET_KIND_STABILITY[asset_kind] == "experimental" else reserved_kind_counts
            counts[asset_kind] = counts.get(asset_kind, 0) + 1
        return True

    # The manifest lists external assets (ref) and PackageExample files; other local assets are discovered.
    example_paths: set[str] = set()  # listed PackageExample paths: discovery skips them
    seen_paths: set[str] = set()
    ignore_rules = load_ignore(root)
    for idx, item in enumerate(assets):
        where = f"spec.assets[{idx}]"
        if not isinstance(item, dict):
            errors.append(f"asset.entry: {where} must be a mapping")
            continue
        asset_kind = item.get("kind")
        if not nonempty_str(asset_kind):
            errors.append(f"asset.kind: {where}.kind is required")
            continue
        kind_issues(asset_kind, f"{where}.kind", discovered=False)
        has_path = "path" in item
        has_ref = "ref" in item  # spec 5.1: a present ref key is an ExternalRef, whatever its value
        if has_ref:
            ref_errors, ref_warnings = structure.external_ref_issues(item["ref"], f"{where}.ref", extension_names)
            errors.extend(ref_errors)
            warnings.extend(ref_warnings)
        if has_path and asset_kind != "PackageExample":
            errors.append(f"asset.path-or-ref: {where} lists the local file {item['path']!r}; local assets are found by their "
                          "apiVersion and kind, and only PackageExample files are listed")
            continue
        if has_path == has_ref:
            errors.append(f"asset.path-or-ref: {where} must declare exactly one of path or ref")
            continue
        if has_ref:
            if isinstance(item["ref"], dict):
                asset_kinds.add(asset_kind)
            continue
        rel = item["path"]
        if not nonempty_str(rel):
            errors.append(f"asset.path-form: {where}.path must be a non-empty string")
            continue
        example_paths.add(rel)
        asset_kinds.add(asset_kind)
        absolute = rel.startswith("/") or bool(re.match(r"^[A-Za-z]:", rel))
        form_bad = absolute or "\\" in rel or rel.startswith("./") or "//" in rel or rel.endswith("/")
        if form_bad:
            errors.append(f"asset.path-form: local asset path {rel!r} must be a relative POSIX path without a leading './'")
        norm = None if absolute else normalize_rel_path(rel)
        if norm is None:
            if absolute or posixpath.normpath(rel).startswith(".."):
                errors.append(f"asset.path-escape: asset path escapes package root: {rel}")
            continue
        if form_bad:
            continue
        if rel in seen_paths:
            errors.append(f"asset.duplicate-path: duplicate local asset path: {rel}")
        seen_paths.add(rel)
        local_asset_kinds[rel] = "PackageExample"
        target = root / norm
        if target.is_file():
            try:
                target.resolve().relative_to(root.resolve())
            except ValueError:
                errors.append(f"asset.path-escape: asset path escapes package root: {rel}")
                continue
        if not target.is_file():
            errors.append(f"asset.missing-file: local asset path does not exist: {rel}")
            continue
        if is_ignored(ignore_rules, norm):
            errors.append(f"asset.missing-file: local asset path {rel} is excluded by {IGNORE_FILE}, so it is not a package file")
            continue
        if target.suffix.lower() in {".yaml", ".yml"}:
            try:
                adata = load_yaml(target.read_text(encoding="utf-8"))
            except Exception as exc:
                errors.append(f"asset.yaml: cannot parse asset YAML {rel}: {exc}")
                continue
            if isinstance(adata, dict):
                local_asset_docs[rel] = adata  # examples may be any document; their kind is not checked

    for rel, adata in package_documents(root, skip=example_paths):
        if isinstance(adata, Exception):
            errors.append(f"asset.yaml: cannot parse YAML {rel}: {adata}")
            continue
        if not is_owp_document(adata):
            continue  # not an OWP document: an ordinary package file
        if adata["apiVersion"] != data.get("apiVersion"):
            errors.append(f"asset.api-version: {rel} declares apiVersion {adata['apiVersion']!r}; it must equal the manifest's {data.get('apiVersion')!r}")
        asset_kind = adata.get("kind")
        if isinstance(asset_kind, str) and asset_kind in DOCUMENT_KINDS:
            continue  # an ObservationSet or EWS document, not an asset
        if not nonempty_str(asset_kind):
            errors.append(f"asset.kind: {rel} declares apiVersion {adata['apiVersion']!r} but no kind")
            continue
        if not kind_issues(asset_kind, f"{rel}: kind", discovered=True):
            continue
        asset_kinds.add(asset_kind)
        local_asset_kinds[rel] = asset_kind
        local_asset_docs[rel] = adata
        aspec = adata.get("spec")
        if isinstance(aspec, dict) and "standardBindings" in aspec:
            sb_errors, sb_warnings = structure.standard_binding_issues(aspec["standardBindings"], f"{rel}: spec.standardBindings", extension_names)
            errors.extend(sb_errors)
            warnings.extend(sb_warnings)
        if asset_kind == "SemanticBinding":
            pass  # checked by binding_issues after the asset loop
        elif asset_kind in experimental.TABLES:
            experimental_docs.append((rel, asset_kind, adata))
        elif asset_kind != "PackageExample":
            errors.extend(_asset_structure_errors(adata, asset_kind, rel, extension_names))
            if asset_kind in {"WorldViewProfile", "EvaluationProfile", "ScenarioProfile", "CapabilityContract"}:
                standard_docs.append((rel, asset_kind, adata))

    for asset_kind, count in experimental_kind_counts.items():
        warnings.append(f"asset.kind-experimental: asset kind {asset_kind} is experimental and may change ({count} asset{'s' if count > 1 else ''})")
    for asset_kind, count in reserved_kind_counts.items():
        warnings.append(f"asset.kind-reserved: asset kind {asset_kind} is reserved: it has no schema or rules yet ({count} asset{'s' if count > 1 else ''})")
    for rel, asset_kind, adata in experimental_docs:
        exp_errors, exp_warnings = experimental.experimental_issues(adata, asset_kind, rel, root, spec, local_asset_kinds, extension_names, local_asset_docs)
        errors.extend(exp_errors)
        warnings.extend(exp_warnings)
    for rel, asset_kind, adata in standard_docs:
        std_errors, std_warnings = experimental.standard_kind_checks(adata, asset_kind, rel, root, local_asset_kinds, extension_names)
        errors.extend(std_errors)
        warnings.extend(std_warnings)
    warnings.extend(experimental.view_specialization_warnings(local_asset_kinds, local_asset_docs))
    warnings.extend(experimental.view_composition_warnings(local_asset_kinds, local_asset_docs))
    from .extraction import multi_latest_warnings  # local import: extraction depends on core
    warnings.extend(multi_latest_warnings(local_asset_kinds, local_asset_docs))
    view_includes = {x for rel, k in local_asset_kinds.items() if k == "WorldViewProfile"
                     for x in (lambda inc: inc if isinstance(inc, list) else [])(dig(experimental.resolve_view(rel, local_asset_docs, local_asset_kinds), "projection", "include"))
                     if isinstance(x, str)}
    ews_fields, field_errors = compiler_fields(root, local_asset_kinds, local_asset_docs)
    errors.extend(field_errors)
    bind_errors, bind_warnings = binding_module.binding_issues(spec, local_asset_kinds, local_asset_docs, ews_fields, view_includes, extension_names)
    errors.extend(bind_errors)
    warnings.extend(bind_warnings)
    if kind == "WorldPackage":
        warnings.extend(_containment_warnings(spec, local_asset_kinds, local_asset_docs, ews_fields))
    for rel, k in sorted(local_asset_kinds.items()):
        if k != "WorldViewProfile":
            continue
        if kind != "WorldPackage":
            errors.append(f"view.world-ref: {rel}: a WorldViewProfile belongs to a WorldPackage, not a {kind}")
            continue
        errors.extend(_external_world_errors(rel, _spec_of(local_asset_docs.get(rel)), spec))

    for rel, k in sorted(local_asset_kinds.items()):
        entry = _spec_of(local_asset_docs.get(rel)).get("entrypoint") if k == "ModelArtifact" else None
        if entry is not None and not (isinstance(entry, str) and ontology_module.inside_package(root, entry.partition("#")[0])):
            errors.append(f"model.entrypoint: {rel}: spec.entrypoint {entry!r} must name a file in the package (<path>[#<name>])")

    if kind == "WorldModelPackage":
        if "ModelArtifact" not in asset_kinds:
            warnings.append("worldmodel.model-artifact-missing: WorldModelPackage should reference a ModelArtifact, even if it is contract-only/unbound")
        if "EvaluationProfile" not in asset_kinds:
            warnings.append("worldmodel.evaluation-profile-missing: WorldModelPackage should reference an EvaluationProfile")
        if "RepresentationAdapterProfile" not in local_asset_kinds.values():
            errors.append("worldmodel.adapter: WorldModelPackage requires a RepresentationAdapterProfile (an identity adapter is valid when no transform is needed)")
        wm = spec.get("worldModel") if isinstance(spec.get("worldModel"), dict) else None  # missing: worldmodel.spec only
        inputs = wm.get("inputs") if wm is not None else None
        if wm is not None and (not isinstance(inputs, dict) or inputs.get("contract") != "EffectiveWorldState"):
            errors.append("worldmodel.input-contract: WorldModelPackage requires spec.worldModel.inputs.contract = EffectiveWorldState")
        representation = wm.get("representation") if isinstance(wm, dict) else None
        adapter_ref = representation.get("adapterRef") if isinstance(representation, dict) else None
        if wm is None:
            pass
        elif not nonempty_str(adapter_ref):
            errors.append("worldmodel.adapter-ref: WorldModelPackage requires spec.worldModel.representation.adapterRef")
        elif local_asset_kinds.get(adapter_ref) != "RepresentationAdapterProfile":
            errors.append("worldmodel.adapter-ref: spec.worldModel.representation.adapterRef must point to a local RepresentationAdapterProfile asset")
        else:
            adapter_doc = local_asset_docs.get(adapter_ref) or {}
            adapter_spec = adapter_doc.get("spec") if isinstance(adapter_doc, dict) else None
            if not isinstance(adapter_spec, dict) or adapter_spec.get("source") != "EffectiveWorldState":
                errors.append("worldmodel.adapter-source: RepresentationAdapterProfile referenced by adapterRef must declare spec.source = EffectiveWorldState")

    if kind == "WorldPackage":
        profile = DEFAULT_WORLD_PROFILE
        if "conformance" in spec:
            conformance = spec["conformance"]
            if not isinstance(conformance, dict):
                errors.append("profile.unknown: spec.conformance must be a mapping with a defined profile")
            elif "profile" in conformance:
                if isinstance(conformance["profile"], str) and conformance["profile"] in WORLD_PROFILES:
                    profile = conformance["profile"]
                else:
                    errors.append(f"profile.unknown: spec.conformance.profile must be one of {WORLD_PROFILES}")
        errors.extend(_world_profile_errors(profile, spec, asset_kinds, local_asset_kinds, local_asset_docs, ews_fields, identity))
    elif kind == "OntologyPackage" and spec.get("conformance") is not None:
        conformance = spec.get("conformance")
        profile = conformance.get("profile") if isinstance(conformance, dict) else None
        if profile not in ontology_module.ONTOLOGY_PROFILES:
            errors.append(f"profile.unknown: spec.conformance.profile must be one of {ontology_module.ONTOLOGY_PROFILES} for an OntologyPackage")
        else:
            errors.extend(ontology_module.ontology_profile_errors(profile, root, spec))
    elif "conformance" in spec and kind not in ("WorldPackage", "OntologyPackage"):
        warnings.append("manifest.conformance-ignored: spec.conformance applies to WorldPackage and OntologyPackage only and is ignored")

    _validate_evaluation_lineage(kind, identity, grounding, local_asset_kinds, local_asset_docs, errors, warnings)

    return ValidationResult(not errors, errors, warnings, data)


def inspect_package(path: str | Path, graph: bool = False, resolved_views: bool = False) -> dict[str, Any]:
    root, data = load_manifest(path)
    result = validate_package(root)
    md = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
    spec = data.get("spec") if isinstance(data.get("spec"), dict) else {}
    summary: dict[str, Any] = {}
    if data.get("kind") == "WorldPackage" and isinstance(spec, dict):
        kinds, docs = local_assets(root, spec)
        ews_fields, _ = compiler_fields(root, kinds, docs)
        conformance = spec.get("conformance") if isinstance(spec.get("conformance"), dict) else {}
        summary["conformance"] = {
            "declared": conformance.get("profile", DEFAULT_WORLD_PROFILE),
            "satisfied": satisfied_world_profile(spec, {k for k in kinds.values()} | _ref_asset_kinds(spec), kinds, docs,
                                                 ews_fields,
                                                 f"{md.get('namespace')}/{md.get('name')}@{md.get('version')}"),
        }
    if data.get("kind") == "WorldPackage" and isinstance(dig(spec, "world", "semanticBinding"), str):
        bound_fields = dig(docs.get(spec["world"]["semanticBinding"]), "spec", "fields")
        bound = set(bound_fields) if isinstance(bound_fields, dict) else set()
        fields = {f for compiler in ews_fields.values() for f in compiler or []}
        summary["semanticCoverage"] = {"boundFields": len(bound & fields), "fields": len(fields)}
    if data.get("kind") == "OntologyPackage" and isinstance(spec, dict):
        conformance = spec.get("conformance") if isinstance(spec.get("conformance"), dict) else {}
        summary["conformance"] = {"declared": conformance.get("profile"),
                                  "satisfied": ontology_module.satisfied_ontology_profile(root, spec)}
    kinds_used, docs_used = local_assets(root, spec if isinstance(spec, dict) else {})
    summary["experimental"] = experimental.usage(kinds_used, docs_used, ASSET_KIND_STABILITY)
    if graph or resolved_views:
        kinds, docs = local_assets(root, spec if isinstance(spec, dict) else {})
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
        "asset_count": len(local_assets(root, spec)[0]) + len([a for a in _list(spec.get("assets")) if isinstance(a, dict) and "ref" in a]),
        "domains": spec.get("domains", []),
        "extensions": [
            {"name": d["as"], "ref": d.get("ref"), "mustUnderstand": bool(d.get("mustUnderstand", False))}
            for d in _list(spec.get("dependencies")) if isinstance(d, dict) and isinstance(d.get("as"), str)
        ],
        **summary,
    }


def is_owp_document(doc: Any) -> bool:
    """A YAML document that declares an OWP apiVersion (spec section 5)."""
    return isinstance(doc, dict) and isinstance(doc.get("apiVersion"), str) and doc["apiVersion"].startswith("openworld/")


def package_documents(root: Path, skip: set[str] = frozenset()) -> Iterator[tuple[str, Any]]:
    """Every YAML file that asset discovery reads (spec section 5), with its parsed content or the parse error.

    Discovery skips owp.yaml, the paths in skip, path components that start with '.', files that are not
    package files (see package_files), and subdirectories that hold their own owp.yaml (a nested package).
    """
    nested = [p.parent.relative_to(root).parts for p in root.rglob(MANIFEST) if p.parent != root]
    for path in package_files(root):
        parts = path.relative_to(root).parts
        rel = "/".join(parts)
        if path.suffix.lower() not in {".yaml", ".yml"} or rel == MANIFEST or rel in skip:
            continue
        if any(part.startswith(".") for part in parts) or any(parts[:len(n)] == n for n in nested):
            continue
        try:
            path.resolve().relative_to(root.resolve())
        except ValueError:
            continue  # a link that leads outside the package
        try:
            yield rel, load_yaml(path.read_text(encoding="utf-8"))
        except Exception as exc:
            yield rel, exc


def local_assets(root: Path, spec: dict[str, Any]) -> tuple[dict[str, str], dict[str, dict[str, Any]]]:
    """Kinds and parsed YAML documents of local assets (discovered, plus listed PackageExample files), by path."""
    kinds: dict[str, str] = PathMap()
    docs: dict[str, dict[str, Any]] = PathMap()
    assets = spec.get("assets") if isinstance(spec, dict) else None
    examples = {item["path"] for item in assets if isinstance(item, dict) and item.get("kind") == "PackageExample"
                and isinstance(item.get("path"), str)} if isinstance(assets, list) else set()
    for rel in examples:
        kinds[rel] = "PackageExample"
        norm = normalize_rel_path(rel)
        try:
            doc = load_yaml((root / norm).read_text(encoding="utf-8")) if norm else None
        except Exception:
            continue
        if isinstance(doc, dict):
            docs[rel] = doc
    for rel, doc in package_documents(root, skip=examples):
        if is_owp_document(doc) and isinstance(doc.get("kind"), str) and doc["kind"] not in DOCUMENT_KINDS:
            kinds[rel] = doc["kind"]
            docs[rel] = doc
    return kinds, docs


def _ref_asset_kinds(spec: dict[str, Any]) -> set[str]:
    assets = spec.get("assets")
    return {a["kind"] for a in assets if isinstance(a, dict) and nonempty_str(a.get("kind")) and isinstance(a.get("ref"), dict)
            and "path" not in a} if isinstance(assets, list) else set()


def package_files(root: Path) -> list[Path]:
    """The files a package consists of: what discovery reads and ontle pack archives.

    Paths with a component that starts with "." (.env, .git, .owpignore, ...), build and tooling directories,
    operating-system metadata, archives, and paths that .owpignore excludes are not package files, the same
    rule discovery follows (spec section 5). owp.yaml always is.
    """
    rules = load_ignore(root)
    ignored_parts = {"__pycache__", "venv", "node_modules", "dist", "build", "Thumbs.db"}
    files: list[Path] = []
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(root)
        if any(part in ignored_parts or part.startswith(".") for part in rel.parts):
            continue
        if p.name.endswith(".owp.zip"):
            continue
        if rel.as_posix() != MANIFEST and is_ignored(rules, rel.as_posix()):
            continue
        files.append(p)
    return sorted(files, key=lambda p: p.relative_to(root).as_posix())


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


LOCK_FORMAT = "owp-lock/v1alpha2"


def build_lock(root: Path, files: list[Path], extra: dict[str, bytes] | None = None,
               vendored: dict[str, str] | None = None) -> dict[str, Any]:
    from .distribution import lock_externals  # local import: distribution depends on core
    entries = []
    for p in files:
        data = p.read_bytes()
        entries.append({
            "path": p.relative_to(root).as_posix(),
            "sha256": sha256_bytes(data),
            "size": len(data),
        })
    for rel, data in sorted((extra or {}).items()):
        entries.append({"path": rel, "sha256": sha256_bytes(data), "size": len(data)})
    entries.sort(key=lambda e: e["path"])
    manifest_bytes = (root / MANIFEST).read_bytes()
    return {
        "format": LOCK_FORMAT,
        "manifest": MANIFEST,
        "manifest_sha256": sha256_bytes(manifest_bytes),
        "files": entries,
        "externals": lock_externals(load_yaml(manifest_bytes) or {}, vendored),
    }


def deterministic_pack(path: str | Path, output: str | Path | None = None, vendor: bool = False) -> Path:
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
    if load_ignore(root):
        _check_packed_files(root, files)
    extra: dict[str, bytes] = {}
    vendored: dict[str, str] = {}
    if vendor:
        from .distribution import vendor_https_refs
        for pointer, (rel, data) in vendor_https_refs(root, manifest).items():
            extra[rel] = data
            vendored[pointer] = rel
    lock = build_lock(root, files, extra, vendored)
    lock_bytes = (json.dumps(lock, indent=2, sort_keys=True) + "\n").encode("utf-8")

    fixed_date = (2020, 1, 1, 0, 0, 0)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for p in files:
            rel = p.relative_to(root).as_posix()
            zi = zipfile.ZipInfo(rel, date_time=fixed_date)
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = (0o644 & 0xFFFF) << 16
            zf.writestr(zi, p.read_bytes())
        for rel, data in sorted(extra.items()):
            zi = zipfile.ZipInfo(rel, date_time=fixed_date)
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = (0o644 & 0xFFFF) << 16
            zf.writestr(zi, data)
        zi = zipfile.ZipInfo("owp.lock.json", date_time=fixed_date)
        zi.compress_type = zipfile.ZIP_DEFLATED
        zi.external_attr = (0o644 & 0xFFFF) << 16
        zf.writestr(zi, lock_bytes)
    return output


def _check_packed_files(root: Path, files: list[Path]) -> None:
    """The package as archived, without the files .owpignore excludes, must still be valid (a manifest or asset may refer to one)."""
    with tempfile.TemporaryDirectory() as td:
        for p in files:
            dest = Path(td) / p.relative_to(root)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(p.read_bytes())
        result = validate_package(td)
    if not result.valid:
        raise OWPError(f"package is invalid without the files {IGNORE_FILE} excludes: " + "; ".join(result.errors))


def _ensure_term_index(root: Path, manifest: dict[str, Any]) -> None:
    """DD-2: an OntologyPackage whose schema is not owp-yaml needs a term index; generate it when it is missing and rdflib is available."""
    if manifest.get("kind") != "OntologyPackage":
        return
    onto = dig(manifest, "spec", "ontology")
    if not isinstance(onto, dict) or onto.get("termIndex"):
        return
    schema = [e for e in _list(onto.get("entrypoints")) if isinstance(e, dict) and e.get("role") == "schema"]
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
        if lock.get("format") != LOCK_FORMAT:
            return False, [f"unsupported lock format {lock.get('format')!r}"]
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
        else:
            from .distribution import lock_externals
            recorded = [{k: v for k, v in e.items() if k != "vendoredPath"} for e in lock.get("externals") or []]
            try:
                manifest = load_yaml(zf.read(MANIFEST)) or {}
            except Exception as exc:
                return False, errors + [f"cannot parse {MANIFEST}: {exc}"]
            if recorded != lock_externals(manifest):
                errors.append("lock externals do not match the manifest's external references")
            for entry in lock.get("externals") or []:
                if entry.get("vendoredPath") and entry["vendoredPath"] not in locked:
                    errors.append(f"vendored file {entry['vendoredPath']} is not locked")
                elif entry.get("vendoredPath") and entry.get("digest") and f"sha256:{sha256_bytes(zf.read(entry['vendoredPath']))}" != entry["digest"]:
                    errors.append(f"vendored file {entry['vendoredPath']} does not match its digest")
    return not errors, errors
