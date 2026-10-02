from __future__ import annotations

from pathlib import Path
from importlib import resources
import shutil

from .core import MANIFEST_SCHEMA_LINE, OWPError, PACKAGE_REF_RE, write_manifest
from .structure import EXTENSION_NAME_RE, RESERVED_EXTENSION_NAMES
from .yamlio import dump_yaml, load_yaml

SCHEMA_BASE = "https://raw.githubusercontent.com/ontle-world/open-world-package/main/schemas/"
SCHEMAS = {
    "manifest": "owp-manifest.schema.json",
    "WorldViewProfile": "world-view-profile.schema.json",
    "EvaluationProfile": "evaluation-profile.schema.json",
    "ScenarioProfile": "scenario-profile.schema.json",
    "CapabilityContract": "capability-contract.schema.json",
    "CompatibilityEvidence": "compatibility-evidence.schema.json",
    "SemanticProfile": "semantic-profile.schema.json",
    "OntologyTermIndex": "ontology-term-index.schema.json",
    "SemanticBinding": "semantic-binding.schema.json",
}
HINTS = {
    "WorldViewProfile": "Fill purpose (task, objective), projection.include, and conditioning (spec section 6).",
    "StateCompilerProfile": "List the EWS fields in outputSchema.fields; add bindings to make the compiler declarative (spec section 12).",
    "EvaluationProfile": "Set assessmentKind, subject, and criteria; bump metadata.version when they change (spec sections 9, 15.1).",
    "ScenarioProfile": "Describe baseline, assumptions, intervention, and engine (spec section 15.2).",
    "CapabilityContract": "Describe the outcomes this capability achieves and under which context (spec section 15.3).",
    "TaskSetProfile": "Name the Views, actors, knowledge, work patterns, and artifacts this task uses (spec Appendix C).",
    "WorkPatternProfile": "Pick pattern.kind from vocab/value-sets.yaml workPatterns; add a graph if the steps matter (Appendix C.2).",
    "ArtifactContract": "Set artifact.type, representation, formats, and allowedOperations (Appendix C).",
    "ConsumerRepresentationProfile": "Set actor.kind and keep only the matching human/agent/model/system block (Appendix C).",
    "KnowledgeAsset": "Set roles, representation, and content (a path or an ExternalRef) (Appendix C).",
    "ActorProfile": "actorType: human, ai_agent, team, organization, external_institution, or automated_system (Appendix C.3).",
    "RoleProfile": "permissions: what the role may do; authorities: what it may decide (Appendix C.3).",
    "DelegationProfile": "Delegate only actions and decisions the delegator's roles grant, for a bounded period (Appendix C.3).",
}


def schema_url(kind: str) -> str | None:
    """Schema of a kind for editors (yaml-language-server), or None when the kind has no schema."""
    if kind in SCHEMAS:
        return SCHEMA_BASE + SCHEMAS[kind]
    from .experimental import TABLES
    if kind in TABLES:
        import re as _re
        return SCHEMA_BASE + "experimental/" + _re.sub(r"(?<!^)(?=[A-Z])", "-", kind).lower() + ".schema.json"
    return None


def _header(kind: str) -> str:
    lines = []
    url = schema_url(kind)
    if url:
        lines.append(f"# yaml-language-server: $schema={url}")
    if kind in HINTS:
        lines.append(f"# {HINTS[kind]}")
    return "".join(line + "\n" for line in lines)


TEMPLATES = {"minimal", "enterprise", "ontology", "worldmodel", "worldmodel-multimodal"}


def _template_dir(template: str):
    if template not in TEMPLATES:
        raise OWPError(f"unknown template {template!r}; choose one of {sorted(TEMPLATES)}")
    return resources.files("ontle").joinpath("templates", template)


WORLD_MODEL_TEMPLATES = {"worldmodel", "worldmodel-multimodal"}
CARDS = ["WORLD.md", "WORLDMODEL.md", "ONTOLOGY.md"]


def _grounding_target(world: str) -> tuple[str, str, str]:
    """(identity, default View path, default State Compiler path) of a World given as a directory or a reference."""
    path = Path(world).expanduser()
    if (path / "owp.yaml").is_file():
        manifest = load_yaml((path / "owp.yaml").read_text(encoding="utf-8")) or {}
        md, spec = manifest.get("metadata") or {}, manifest.get("spec") or {}
        w = spec.get("world") or {}
        if manifest.get("kind") != "WorldPackage" or not (w.get("defaultView") and w.get("defaultStateCompiler")):
            raise OWPError(f"{world} must be a WorldPackage that declares spec.world.defaultView and defaultStateCompiler")
        return f"{md.get('namespace')}/{md.get('name')}@{md.get('version')}", w["defaultView"], w["defaultStateCompiler"]
    if PACKAGE_REF_RE.match(world):
        return world, "views/default.yaml", "state/default-compiler.yaml"  # the World starter's paths
    raise OWPError(f"--world must be a World package directory or a <namespace>/<name>@<version> reference, not {world!r}")


def init_project(name: str, namespace: str, template: str = "minimal", destination: str | Path | None = None,
                 world: str | None = None) -> Path:
    if world is not None and template not in WORLD_MODEL_TEMPLATES:
        raise OWPError("--world applies to the worldmodel and worldmodel-multimodal templates")
    grounding = _grounding_target(world) if world is not None else None
    dest = Path(destination or name).expanduser().resolve()
    if dest.exists() and any(dest.iterdir()):
        raise OWPError(f"destination is not empty: {dest}")
    dest.mkdir(parents=True, exist_ok=True)

    src = _template_dir(template)
    for item in src.iterdir():
        target = dest / item.name
        if item.is_dir():
            shutil.copytree(item, target, dirs_exist_ok=True)
        else:
            shutil.copy2(item, target)

    manifest = dest / "owp.yaml"
    data = load_yaml(manifest.read_text(encoding="utf-8"))
    title = " ".join(part.capitalize() for part in name.replace("_", "-").split("-") if part)
    data["metadata"]["namespace"] = namespace
    data["metadata"]["name"] = name
    data["metadata"]["title"] = title
    if grounding is not None:
        identity, view, compiler = grounding
        spec = data["spec"]
        spec["worldModel"]["semanticGrounding"] = {
            "worldRef": identity,
            "compatibleWorldViews": [f"{identity}#{view}"],
            "compatibleStateCompilers": [f"{identity}#{compiler}"],
        }
        deps = [identity] + [d for d in spec.pop("dependencies", None) or [] if d != identity]
        data["spec"] = {"dependencies": deps, **spec}
    manifest.write_text(MANIFEST_SCHEMA_LINE + dump_yaml(data), encoding="utf-8")
    for card in CARDS:  # the card's first heading names the package
        path = dest / card
        if path.exists():
            lines = path.read_text(encoding="utf-8").split("\n", 1)
            if lines[0].startswith("# "):
                path.write_text(f"# {title}\n" + (lines[1] if len(lines) > 1 else ""), encoding="utf-8")

    state = dest / ".ontle" / "project.yaml"
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text(dump_yaml({
        "generator": "ontle",
        "template": template,
        "manifest": "owp.yaml",
        "authoring": [p for p in CARDS if (dest / p).exists()],
    }), encoding="utf-8")
    return dest


def _skeleton_spec(kind: str, manifest: dict) -> dict:
    world = ((manifest or {}).get("spec") or {}).get("world") or {}
    if kind == "WorldViewProfile":
        return {"worldRef": "self", "purpose": {"task": None, "actorScope": None, "objective": None},
                "projection": {"include": [], "principle": "minimal_sufficient_representation"}}
    if kind == "StateCompilerProfile":
        return {"worldViewRef": world.get("defaultView"), "outputContract": "EffectiveWorldState",
                "outputSchema": {"fields": []}}
    # Experimental kinds (spec Appendix C)
    if kind == "TaskSetProfile":
        views = [world["defaultView"]] if world.get("defaultView") else []
        return {"task": {"objectiveRefs": [], "workPatterns": []},
                "requires": {"worldViews": views, "knowledge": []},
                "mayUse": {"worldModels": [], "capabilities": [], "workflows": []},
                "produces": {"artifacts": []}, "evaluationRefs": []}
    if kind == "WorkPatternProfile":
        return {"pattern": {"kind": "analyze"}, "inputs": {"semanticRoles": []}, "outputs": {"semanticRoles": []},
                "optionalCapabilities": [], "evaluationRefs": []}
    if kind == "ArtifactContract":
        return {"artifact": {"type": "report", "representation": "document"},
                "structure": {"required": [], "optional": []}, "serialization": {"formats": ["markdown"]},
                "delivery": {"destinations": []}, "governance": {"approvalRequired": False, "policyRefs": []},
                "evaluationRefs": []}
    if kind == "ArtifactTemplate":
        return {"artifactContractRef": None, "format": "markdown", "content": {"ref": {"status": "unbound"}}}
    if kind == "ConsumerRepresentationProfile":
        return {"actor": {"kind": "human"}, "worldViewRef": world.get("defaultView"),
                "representation": {"mode": "board"}, "human": {"artifactContractRefs": [], "presentation": "board"}}
    if kind == "ActorProfile":
        return {"actorType": "human", "roleRefs": [], "capabilityRefs": []}
    if kind == "RoleProfile":
        return {"permissions": [], "authorities": [], "responsibilities": [], "accountabilities": []}
    if kind == "DelegationProfile":
        return {"delegator": None, "delegatee": None, "scope": None, "permittedActions": [],
                "authorityCeiling": {"decisions": []}, "validFrom": None, "expiresAt": None}
    if kind == "CapabilityContract":
        return {"description": None, "outcomeRefs": [], "requiredInputs": []}
    if kind == "KnowledgeAsset":
        return {"roles": ["definition"], "representation": "documents", "content": {"ref": {"status": "unbound"}}}
    return {}


def add_asset(project: str | Path, asset_kind: str, name: str, specializes: str | None = None) -> Path:
    root = Path(project).expanduser().resolve()
    manifest_path = root / "owp.yaml"
    if not manifest_path.exists():
        raise OWPError(f"missing owp.yaml in {root}")

    mapping = {
        "view": ("views", "WorldViewProfile"),
        "compiler": ("state", "StateCompilerProfile"),
        "source": ("interfaces", "SourceSystemSchemaProfile"),
        "observation": ("interfaces", "ObservationAcquisitionProfile"),
        "action": ("interfaces", "ActionBindingProfile"),
        "commit": ("interfaces", "CommitContract"),
        "effect": ("interfaces", "EffectVerificationProfile"),
        "model": ("models", "WorldModelContract"),
        "adapter": ("models", "RepresentationAdapterProfile"),
        "scenario": ("scenarios", "ScenarioProfile"),
        "dataset": ("datasets", "Dataset"),
        "eval": ("eval", "EvaluationProfile"),
        "verifier": ("eval", "VerifierPackage"),
        "test": ("tests", "AcceptanceCase"),
        "asset": ("assets", "OperationalAsset"),
        # experimental kinds (spec Appendix C)
        "task": ("tasks", "TaskSetProfile"),
        "pattern": ("patterns", "WorkPatternProfile"),
        "artifact": ("artifacts", "ArtifactContract"),
        "template": ("artifacts/templates", "ArtifactTemplate"),
        "consumer": ("consumers", "ConsumerRepresentationProfile"),
        "knowledge": ("knowledge", "KnowledgeAsset"),
        "actor": ("actors", "ActorProfile"),
        "role": ("roles", "RoleProfile"),
        "delegation": ("delegations", "DelegationProfile"),
        "capability": ("capabilities", "CapabilityContract"),
    }
    if asset_kind not in mapping:
        raise OWPError(f"asset kind must be one of {sorted(mapping)}")
    folder, kind = mapping[asset_kind]
    target = root / folder / f"{name}.yaml"
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise OWPError(f"asset already exists: {target}")
    manifest = load_yaml(manifest_path.read_text(encoding="utf-8"))
    metadata = {"name": name}
    if kind in {"EvaluationProfile", "VerifierPackage"}:
        metadata["version"] = "0.1.0"
    skeleton = _skeleton_spec(kind, manifest)
    if specializes is not None:
        if kind != "WorldViewProfile":
            raise OWPError("--specializes applies to 'view' only")
        listed = {a.get("path"): a.get("kind") for a in (manifest.get("spec") or {}).get("assets", []) or [] if isinstance(a, dict)}
        if listed.get(specializes) != "WorldViewProfile":
            raise OWPError(f"--specializes must name a local WorldViewProfile asset: {specializes}")
        skeleton = {"worldRef": "self", "specializes": specializes, "purpose": {"actorScope": None},
                    "projection": {"include": [], "exclude": []}, "conditioning": {}}
    def blank(value):  # editors validate against the schemas: placeholders are empty strings, not null
        if isinstance(value, dict):
            return {k: blank(v) for k, v in value.items()}
        if isinstance(value, list):
            return [blank(v) for v in value]
        return "" if value is None else value

    skeleton = blank(skeleton)
    target.write_text(_header(kind) + dump_yaml({  # apiVersion is inherited from owp.yaml (spec section 5)
        "kind": kind,
        "metadata": metadata,
        "spec": skeleton,
    }), encoding="utf-8")

    spec = manifest.setdefault("spec", {})
    assets = spec.setdefault("assets", [])
    rel = target.relative_to(root).as_posix()
    if not any(isinstance(a, dict) and a.get("path") == rel for a in assets):
        assets.append({"kind": kind, "path": rel})
    write_manifest(manifest_path, manifest)
    return target


def add_extension(project: str | Path, ref: str, name: str | None = None, must_understand: bool = False) -> str:
    """Declare an extension (spec section 13) as a spec.dependencies entry with 'as'."""
    root = Path(project).expanduser().resolve()
    manifest_path = root / "owp.yaml"
    if not manifest_path.exists():
        raise OWPError(f"missing owp.yaml in {root}")
    if not PACKAGE_REF_RE.match(ref):
        raise OWPError(f"extension reference must be <namespace>/<name>@<exact-semver>: {ref}")
    if name is None:
        package_name = ref.split("/", 1)[1].split("@", 1)[0]
        name = package_name[: -len("-extension")] if package_name.endswith("-extension") else package_name
    if not EXTENSION_NAME_RE.match(name) or name in RESERVED_EXTENSION_NAMES:
        raise OWPError(f"extension name {name!r} must match [a-z][a-z0-9-]* and must not be owp or openworld")
    manifest = load_yaml(manifest_path.read_text(encoding="utf-8"))
    deps = manifest.setdefault("spec", {}).setdefault("dependencies", [])
    for dep in deps:
        existing_ref = dep.get("ref") if isinstance(dep, dict) else dep
        if isinstance(dep, dict) and dep.get("as") == name:
            raise OWPError(f"extension name {name!r} is already declared for {existing_ref}")
        if existing_ref == ref:
            raise OWPError(f"{ref} is already a dependency; add 'as: {name}' to that entry instead")
    entry = {"ref": ref, "as": name}
    if must_understand:
        entry["mustUnderstand"] = True
    deps.append(entry)
    write_manifest(manifest_path, manifest)
    return name


def sync_assets(project: str | Path) -> tuple[list[str], list[str]]:
    """List every OWP asset file of the package in spec.assets. Returns (added paths, listed paths that do not exist)."""
    from .core import KNOWN_ASSET_KINDS, package_files
    from .structure import EXTENSION_KIND_RE
    root = Path(project).expanduser().resolve()
    manifest_path = root / "owp.yaml"
    if not manifest_path.exists():
        raise OWPError(f"missing owp.yaml in {root}")
    manifest = load_yaml(manifest_path.read_text(encoding="utf-8"))
    assets = manifest.setdefault("spec", {}).setdefault("assets", [])
    listed = {a.get("path") for a in assets if isinstance(a, dict)}
    added: list[str] = []
    for path in package_files(root):
        rel = path.relative_to(root).as_posix()
        if rel == "owp.yaml" or rel in listed or path.suffix not in {".yaml", ".yml"} or any(p.startswith(".") for p in Path(rel).parts):
            continue
        try:
            doc = load_yaml(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        kind = doc.get("kind") if isinstance(doc, dict) else None
        if isinstance(doc, dict) and doc.get("apiVersion", manifest.get("apiVersion")) == manifest.get("apiVersion") and isinstance(kind, str) \
                and (kind in KNOWN_ASSET_KINDS or EXTENSION_KIND_RE.match(kind)) and kind != "PackageExample":
            assets.append({"kind": kind, "path": rel})
            added.append(rel)
    missing = sorted(p for p in listed if isinstance(p, str) and not (root / p).exists())
    if added:
        write_manifest(manifest_path, manifest)
    return added, missing
