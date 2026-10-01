from __future__ import annotations

from pathlib import Path
from importlib import resources
import shutil
import yaml

from .core import OWPError, PACKAGE_REF_RE
from .structure import EXTENSION_NAME_RE, RESERVED_EXTENSION_NAMES

TEMPLATES = {"minimal", "enterprise", "ontology", "worldmodel", "worldmodel-multimodal"}


def _template_dir(template: str):
    if template not in TEMPLATES:
        raise OWPError(f"unknown template {template!r}; choose one of {sorted(TEMPLATES)}")
    return resources.files("ontle").joinpath("templates", template)


def init_project(name: str, namespace: str, template: str = "minimal", destination: str | Path | None = None) -> Path:
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
    data = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    data["metadata"]["namespace"] = namespace
    data["metadata"]["name"] = name
    manifest.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")

    state = dest / ".ontle" / "project.yaml"
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text(yaml.safe_dump({
        "generator": "ontle",
        "template": template,
        "manifest": "owp.yaml",
        "authoring": [p for p in ["WORLD.md", "WORLDMODEL.md", "ONTOLOGY.md"] if (dest / p).exists()],
    }, sort_keys=False), encoding="utf-8")
    return dest


def _skeleton_spec(kind: str, manifest: dict) -> dict:
    world = ((manifest or {}).get("spec") or {}).get("world") or {}
    if kind == "WorldViewProfile":
        return {"worldRef": "self", "purpose": {"task": None, "actorScope": None, "objective": None},
                "projection": {"include": [], "principle": "minimal_sufficient_representation"}}
    if kind == "StateCompilerProfile":
        return {"worldViewRef": world.get("defaultView"), "outputContract": "EffectiveWorldState",
                "outputSchema": {"fields": []}}
    return {}


def add_asset(project: str | Path, asset_kind: str, name: str) -> Path:
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
    }
    if asset_kind not in mapping:
        raise OWPError(f"asset kind must be one of {sorted(mapping)}")
    folder, kind = mapping[asset_kind]
    target = root / folder / f"{name}.yaml"
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise OWPError(f"asset already exists: {target}")
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    metadata = {"name": name}
    if kind in {"EvaluationProfile", "VerifierPackage"}:
        metadata["version"] = "0.1.0"
    target.write_text(yaml.safe_dump({
        "apiVersion": "openworld/v1alpha1",
        "kind": kind,
        "metadata": metadata,
        "spec": _skeleton_spec(kind, manifest),
    }, sort_keys=False), encoding="utf-8")

    spec = manifest.setdefault("spec", {})
    assets = spec.setdefault("assets", [])
    rel = target.relative_to(root).as_posix()
    if not any(isinstance(a, dict) and a.get("path") == rel for a in assets):
        assets.append({"kind": kind, "path": rel})
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True), encoding="utf-8")
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
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
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
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return name
