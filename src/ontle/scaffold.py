from __future__ import annotations

import os
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
    "ModelArtifact": "model-artifact.schema.json",
    "Dataset": "dataset.schema.json",
    "AgentProfile": "agent-profile.schema.json",
    "EnvironmentProfile": "environment-profile.schema.json",
    "SourceSystemSchemaProfile": "source-system-schema-profile.schema.json",
    "ObservationAcquisitionProfile": "observation-acquisition-profile.schema.json",
    "ActionBindingProfile": "action-binding-profile.schema.json",
    "CommitContract": "commit-contract.schema.json",
    "EffectVerificationProfile": "effect-verification-profile.schema.json",
    "VerifierProfile": "verifier-profile.schema.json",
}
HINTS = {
    "WorldViewProfile": "Fill purpose (task, objective), projection.include, and conditioning (spec section 6).",
    "StateCompilerProfile": "List the EWS fields in outputSchema.fields; add bindings to make the compiler declarative (docs/STATE_COMPILATION.md, spec section 12).",
    "ModelArtifact": "Set implementationStatus; name bundled code with entrypoint (<path>[#<function>]) or external weights with artifactRef (spec section 8).",
    "EvaluationProfile": "Set assessmentKind, subject, and criteria; bump metadata.version when they change (spec sections 9, 15.1).",
    "ScenarioProfile": "Describe baseline, assumptions, intervention, and engine (spec section 15.2).",
    "CapabilityContract": "Describe the outcomes this capability achieves and under which context (spec section 15.3).",
    "TaskSetProfile": "Name the Views, actors, knowledge, work patterns, and artifacts this task uses (spec section 16).",
    "WorkPatternProfile": "Pick pattern.kind from vocab/value-sets.yaml workPatterns; add a graph if the steps matter (spec section 16.1).",
    "ArtifactContract": "Set artifact.type, representation, formats, and allowedOperations (spec section 18).",
    "ConsumerRepresentationProfile": "Set actor.kind and keep only the matching human/agent/model/system block (spec section 18).",
    "KnowledgeAsset": "Set roles, representation, and content (a path or an ExternalRef) (spec section 19).",
    "ActorProfile": "actorType: human, ai_agent, team, organization, external_institution, or automated_system; assignments optional (spec section 17).",
    "RoleProfile": "permissions: what the role may do; authorities: what it may decide (spec section 17).",
    "DelegationProfile": "Delegate only actions and decisions the delegator's roles grant, for a bounded period (spec section 17).",
}


def schema_url(kind: str) -> str | None:
    """Schema of a kind for editors (yaml-language-server), or None when the kind has no schema."""
    if kind in SCHEMAS:
        return SCHEMA_BASE + SCHEMAS[kind]
    from .experimental import FAMILIES, TABLES
    if kind in TABLES:
        import re as _re
        folder = "" if kind in FAMILIES else "experimental/"
        return SCHEMA_BASE + folder + _re.sub(r"(?<!^)(?=[A-Z])", "-", kind).lower() + ".schema.json"
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
STARTER_OBSERVATIONS = "examples/observations.yaml"
STARTER_AS_OF = "2026-01-02T00:00:00Z"
CARDS = ["WORLD.md", "WORLDMODEL.md", "ONTOLOGY.md"]


def _grounding_target(world: str, view: str | None = None) -> tuple[str, str, str]:
    """(identity, View path, State Compiler path) of a World given as a directory or a reference.

    Without `view`, the World's defaults. With it, the State Compiler whose worldViewRef names that View.
    """
    path = Path(world).expanduser()
    if (path / "owp.yaml").is_file():
        manifest = load_yaml((path / "owp.yaml").read_text(encoding="utf-8")) or {}
        md, spec = manifest.get("metadata") or {}, manifest.get("spec") or {}
        w = spec.get("world") or {}
        identity = f"{md.get('namespace')}/{md.get('name')}@{md.get('version')}"
        if manifest.get("kind") != "WorldPackage":
            raise OWPError(f"{world} must be a WorldPackage")
        if view is not None:
            compilers = []
            for f in sorted(path.rglob("*.y*ml")):
                try:
                    doc = load_yaml(f.read_text(encoding="utf-8"))
                except Exception:
                    continue
                if isinstance(doc, dict) and doc.get("kind") == "StateCompilerProfile" and (doc.get("spec") or {}).get("worldViewRef") == view:
                    compilers.append(f.relative_to(path).as_posix())
            if len(compilers) != 1:
                raise OWPError(f"{world}: {'no' if not compilers else 'more than one'} State Compiler has worldViewRef {view!r}")
            return identity, view, compilers[0]
        if not (w.get("defaultView") and w.get("defaultStateCompiler")):
            raise OWPError(f"{world} declares no spec.world.defaultView and defaultStateCompiler; pass --view")
        return identity, w["defaultView"], w["defaultStateCompiler"]
    if view is not None:
        raise OWPError("--view needs --world to be a World package directory")
    if PACKAGE_REF_RE.match(world):
        return world, "views/default.yaml", "state/default-compiler.yaml"  # the World starter's paths
    raise OWPError(f"--world must be a World package directory or a <namespace>/<name>@<version> reference, not {world!r}")


def init_project(name: str, namespace: str, template: str = "minimal", destination: str | Path | None = None,
                 world: str | None = None, view: str | None = None) -> Path:
    if world is not None and template not in WORLD_MODEL_TEMPLATES:
        raise OWPError("--world applies to the worldmodel and worldmodel-multimodal templates")
    if view is not None and world is None:
        raise OWPError("--view applies with --world")
    grounding = _grounding_target(world, view) if world is not None else None
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

    if (dest / STARTER_OBSERVATIONS).is_file():  # World starters ship the EWS their sample observations compile to
        from .ews import compile_ews  # local import: ews depends on core, as scaffold does
        observations = load_yaml((dest / STARTER_OBSERVATIONS).read_text(encoding="utf-8"))
        ews = compile_ews(dest, data["spec"]["world"]["defaultStateCompiler"], observations, STARTER_AS_OF)
        (dest / "examples" / "expected-ews.yaml").write_text(dump_yaml(ews), encoding="utf-8")

    state = dest / ".ontle" / "project.yaml"
    state.parent.mkdir(parents=True, exist_ok=True)
    project = {
        "generator": "ontle",
        "template": template,
        "manifest": "owp.yaml",
        "authoring": [p for p in CARDS if (dest / p).exists()],
    }
    world_dir = Path(world).expanduser().resolve() if world is not None else None
    if world_dir is not None and (world_dir / "owp.yaml").is_file():  # where `ontle validate` finds the World and its siblings
        project["sources"] = [os.path.relpath(world_dir.parent, dest)]
    state.write_text(dump_yaml(project), encoding="utf-8")
    return dest


def _skeleton_spec(kind: str, manifest: dict) -> dict:
    world = ((manifest or {}).get("spec") or {}).get("world") or {}
    if kind == "WorldViewProfile":
        return {"purpose": {"task": None, "actorScope": None, "objective": None},
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
    if kind == "ModelArtifact":
        return {"description": None, "implementationStatus": "unbound", "bundled": False, "artifactRef": {"status": "unbound"}}
    if kind == "CapabilityContract":
        return {"description": None, "outcomeRefs": [], "requiredInputs": []}
    if kind == "KnowledgeAsset":
        return {"roles": ["definition"], "representation": "documents", "content": {"ref": {"status": "unbound"}}}
    return {}


def new_asset(project: str | Path, kind: str, rel: str, specializes: str | None = None, composes: list[str] | None = None) -> Path:
    """Write a skeleton asset file. Discovery finds it by its apiVersion and kind; owp.yaml is not changed."""
    from .core import KNOWN_ASSET_KINDS, local_assets
    from .structure import EXTENSION_KIND_RE
    root = Path(project).expanduser().resolve()
    manifest_path = root / "owp.yaml"
    if not manifest_path.exists():
        raise OWPError(f"missing owp.yaml in {root}")
    if kind in {"ObservationSet", "EffectiveWorldState"}:
        raise OWPError(f"{kind} is a runtime document, not an asset: the World starter's examples/ shows one, and "
                       "docs/STATE_COMPILATION.md describes it. To ship one with the package, list it as a PackageExample in spec.assets")
    if kind not in KNOWN_ASSET_KINDS and not EXTENSION_KIND_RE.match(kind):
        raise OWPError(f"{kind!r} is not an asset kind of the vocabulary or an <extension>:<Kind>")
    if kind == "PackageExample":
        raise OWPError("PackageExample files are listed in spec.assets; write the example and add a {kind, path} entry")
    if not rel.endswith((".yaml", ".yml")) or rel.startswith(("/", "./")) or ".." in Path(rel).parts:
        raise OWPError(f"path must be a package-relative .yaml file, for example views/{Path(rel).stem or 'name'}.yaml: {rel}")
    target = root / rel
    if target.exists():
        raise OWPError(f"file already exists: {target}")
    manifest = load_yaml(manifest_path.read_text(encoding="utf-8"))
    metadata = {"name": target.stem}
    if kind in {"EvaluationProfile", "VerifierProfile"}:
        metadata["version"] = "0.1.0"
    skeleton = _skeleton_spec(kind, manifest)
    if specializes is not None:
        if kind != "WorldViewProfile":
            raise OWPError("--specializes applies to WorldViewProfile only")
        if local_assets(root, manifest.get("spec") or {})[0].get(specializes) != "WorldViewProfile":
            raise OWPError(f"--specializes must name a local WorldViewProfile asset: {specializes}")
        skeleton = {"specializes": specializes, "purpose": {"actorScope": None},
                    "projection": {"include": [], "exclude": []}, "conditioning": {}}
    if composes:
        if kind != "WorldViewProfile":
            raise OWPError("--composes applies to WorldViewProfile only")
        if specializes is not None:
            raise OWPError("a View composes or specializes, not both")
        kinds = local_assets(root, manifest.get("spec") or {})[0]
        for part in composes:
            if kinds.get(part) != "WorldViewProfile":
                raise OWPError(f"--composes must name local WorldViewProfile assets: {part}")
        skeleton = {"composes": list(composes), "purpose": {"task": None, "objective": None},
                    "projection": {"exclude": []}}

    def blank(value):  # editors validate against the schemas: placeholders are empty strings, not null
        if isinstance(value, dict):
            return {k: blank(v) for k, v in value.items()}
        if isinstance(value, list):
            return [blank(v) for v in value]
        return "" if value is None else value

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(_header(kind) + dump_yaml({
        "apiVersion": manifest.get("apiVersion", "openworld/v1alpha1"),  # with kind, this is how the file is found
        "kind": kind,
        "metadata": metadata,
        "spec": blank(skeleton),
    }), encoding="utf-8")
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
