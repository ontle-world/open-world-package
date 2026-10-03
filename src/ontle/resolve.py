"""Dependency resolution for OWP packages.

Resolves exact `<namespace>/<name>@<version>` references against package sources:

- a local directory containing a package (owp.yaml at its root) or packages in subdirectories
- a `.owp.zip` archive (hashes are verified before use)
- a git source `git+<url>@<rev>[#subdir=<path>]` (use immutable tags or commit SHAs)

No hosted registry is required. A registry or OCI transport can be added as another source type.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import hashlib
import os
import re
import shutil
import subprocess
import tempfile
import zipfile
from typing import Any

from .core import MANIFEST, SEMVER_PATTERN, OWPError, ValidationResult, load_manifest, local_assets, validate_package, verify_archive
from .yamlio import load_yaml

PACKAGE_REF_RE = re.compile(rf"^(?P<namespace>[^/@\s]+)/(?P<name>[^/@\s]+)@(?P<version>{SEMVER_PATTERN})\Z")
GIT_SOURCE_RE = re.compile(r"^git\+(?P<url>.+?)@(?P<rev>[^@#]+)(?:#subdir=(?P<subdir>.+))?\Z")


@dataclass
class ResolvedPackage:
    identity: str
    kind: str | None
    root: Path
    source: str
    manifest: dict[str, Any]
    revision: str | None = None
    _assets: tuple[dict[str, str], dict[str, dict[str, Any]]] | None = field(default=None, repr=False, compare=False)

    def local_assets(self) -> tuple[dict[str, str], dict[str, dict[str, Any]]]:
        """Kinds and documents of the package's local assets, read once per resolution."""
        if self._assets is None:
            self._assets = local_assets(self.root, self.manifest.get("spec") or {})
        return self._assets


@dataclass
class Resolution:
    root: ResolvedPackage
    packages: dict[str, ResolvedPackage] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "root": self.root.identity,
            "packages": {
                ident: {"kind": p.kind, "source": p.source, "path": str(p.root), **({"revision": p.revision} if p.revision else {})}
                for ident, p in sorted(self.packages.items())
            },
            "errors": self.errors,
        }


def parse_package_ref(ref: str) -> tuple[str, str, str]:
    m = PACKAGE_REF_RE.match(ref) if isinstance(ref, str) else None
    if not m:
        raise OWPError(f"package reference must be <namespace>/<name>@<exact-semver>: {ref!r}")
    return m["namespace"], m["name"], m["version"]


def identity_of(manifest: dict[str, Any]) -> str:
    md = manifest.get("metadata") or {}
    return f"{md.get('namespace')}/{md.get('name')}@{md.get('version')}"


def cache_dir() -> Path:
    base = os.environ.get("ONTLE_CACHE") or os.path.join(os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache")), "ontle")
    return Path(base)


def _dependency_refs(manifest: dict[str, Any]) -> list[tuple[str, str | None]]:
    """(ref, per-dependency source) pairs from spec.dependencies (strings or {ref, source} mappings)."""
    out: list[tuple[str, str | None]] = []
    spec = manifest.get("spec") if isinstance(manifest.get("spec"), dict) else {}  # a malformed spec is manifest.spec
    for dep in spec.get("dependencies", []) or []:
        if isinstance(dep, str):
            out.append((dep, None))
        elif isinstance(dep, dict) and isinstance(dep.get("ref"), str):
            out.append((dep["ref"], dep.get("source")))
        else:
            raise OWPError(f"spec.dependencies entries must be a reference string or a mapping with ref: {dep!r}")
    return out


class PackageSource:
    """One place packages can come from. Indexes lazily by identity."""

    def __init__(self, spec: str):
        self.spec = spec
        self._index: dict[str, ResolvedPackage] | None = None

    def find(self, identity: str) -> ResolvedPackage | None:
        if self._index is None:
            self._index = {}
            for pkg in self._scan():
                # First occurrence wins inside one source; duplicates are reported by the resolver via source order.
                self._index.setdefault(pkg.identity, pkg)
        return self._index.get(identity)

    def versions_of(self, name: str) -> list[str]:
        """Identities in this source with the same <namespace>/<name> (after a find)."""
        return sorted(i for i in (self._index or {}) if i.rsplit("@", 1)[0] == name)

    def _scan(self) -> list[ResolvedPackage]:
        raise NotImplementedError


class DirectorySource(PackageSource):
    def __init__(self, spec: str, path: Path, revision: str | None = None, label: str | None = None):
        super().__init__(spec)
        self.path = path
        self.revision = revision
        self.label = label or spec

    def _scan(self) -> list[ResolvedPackage]:
        if not self.path.is_dir():
            raise OWPError(f"package source is not a directory: {self.path}")
        candidates = [self.path / MANIFEST] if (self.path / MANIFEST).exists() else []
        # Hidden directories (such as .git or tool caches) are not scanned.
        visible = lambda p: not any(part.startswith(".") for part in p.relative_to(self.path).parts)
        candidates += sorted(p for p in self.path.glob(f"*/{MANIFEST}") if visible(p))
        candidates += sorted(p for p in self.path.glob(f"*/*/{MANIFEST}") if visible(p))
        out = []
        for manifest_path in candidates:
            try:
                root, manifest = load_manifest(manifest_path.parent)
            except OWPError:
                continue
            out.append(ResolvedPackage(identity_of(manifest), manifest.get("kind"), root, self.label, manifest, self.revision))
        for archive in sorted(self.path.glob("*.owp.zip")):
            out.extend(ArchiveSource(str(archive), archive)._scan())
        return out


class ArchiveSource(PackageSource):
    def __init__(self, spec: str, path: Path):
        super().__init__(spec)
        self.path = path

    def _scan(self) -> list[ResolvedPackage]:
        ok, errors = verify_archive(self.path)
        if not ok:
            raise OWPError(f"archive failed verification {self.path}: {'; '.join(errors)}")
        digest = hashlib.sha256(self.path.read_bytes()).hexdigest()
        target = cache_dir() / "archives" / digest
        if not (target / MANIFEST).exists():
            target.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(self.path) as zf:
                for name in zf.namelist():
                    dest = (target / name).resolve()
                    dest.relative_to(target.resolve())
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(zf.read(name))
        root, manifest = load_manifest(target)
        return [ResolvedPackage(identity_of(manifest), manifest.get("kind"), root, str(self.path), manifest, f"sha256:{digest}")]


class GitSource(PackageSource):
    def __init__(self, spec: str, url: str, rev: str, subdir: str | None):
        super().__init__(spec)
        self.url, self.rev, self.subdir = url, rev, subdir

    def _remote_commit(self) -> str | None:
        """The commit `rev` names on the remote now (tags and branches move), matched by exact ref name; None offline."""
        if re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", self.rev):
            return self.rev
        try:
            out = _git("ls-remote", self.url)
        except OWPError:
            return None
        refs = dict(reversed(line.split("\t", 1)) for line in out.splitlines() if "\t" in line)
        for name in (f"refs/tags/{self.rev}^{{}}", f"refs/tags/{self.rev}", f"refs/heads/{self.rev}", self.rev):
            if name in refs:  # a peeled annotated tag first: the commit, not the tag object
                return refs[name]
        return None

    def _checkout(self) -> tuple[Path, str]:
        """A checkout keyed by the commit it holds; `refs/` remembers the commit each rev last resolved to, for offline use."""
        root = cache_dir() / "git"
        ref_file = root / "refs" / hashlib.sha256(f"{self.url}@{self.rev}".encode()).hexdigest()[:32]
        commit = self._remote_commit()
        if commit is None and ref_file.is_file():
            commit = ref_file.read_text(encoding="utf-8").strip()  # offline: the commit this rev resolved to last time
        keyed = lambda c: root / hashlib.sha256(f"{self.url}@{c}".encode()).hexdigest()[:32]
        if commit is None or not (keyed(commit) / ".git").exists():
            root.mkdir(parents=True, exist_ok=True)
            tmp = Path(tempfile.mkdtemp(dir=root))
            try:
                _git("init", "-q", str(tmp))
                _git("-C", str(tmp), "fetch", "-q", "--depth", "1", self.url, self.rev)
                _git("-C", str(tmp), "checkout", "-q", "FETCH_HEAD")
                commit = _git("-C", str(tmp), "rev-parse", "HEAD").strip()  # what was fetched, not what was expected
                if (keyed(commit) / ".git").exists():
                    shutil.rmtree(tmp, ignore_errors=True)
                else:
                    tmp.rename(keyed(commit))
            except Exception:
                shutil.rmtree(tmp, ignore_errors=True)
                raise
        target = keyed(commit)
        actual = _git("-C", str(target), "rev-parse", "HEAD").strip()
        ref_file.parent.mkdir(parents=True, exist_ok=True)
        ref_file.write_text(actual + "\n", encoding="utf-8")
        return target, actual

    def _scan(self) -> list[ResolvedPackage]:
        checkout, commit = self._checkout()
        path = checkout / self.subdir if self.subdir else checkout
        return DirectorySource(self.spec, path, revision=f"git:{commit}", label=self.spec)._scan()


def _git(*args: str) -> str:
    proc = subprocess.run(["git", *args], capture_output=True, text=True)
    if proc.returncode != 0:
        raise OWPError(f"git {' '.join(args[:3])} failed: {proc.stderr.strip()}")
    return proc.stdout


class OciSource(PackageSource):
    """oci:<registry reference> or oci-layout:<dir>:<tag>: the package is pulled and verified like an archive."""

    def _scan(self) -> list[ResolvedPackage]:
        from .distribution import oci_pull
        reference = self.spec.removeprefix("oci:")
        archive, digest = oci_pull(reference, Path(tempfile.mkdtemp(prefix="ontle-oci-")))
        found = ArchiveSource(self.spec, archive)._scan()
        for pkg in found:
            pkg.revision = f"oci:{digest}"
        return found


class IndexSource(PackageSource):
    """index:<path or URL of a PackageIndex>: archives are downloaded on demand and their digests checked."""

    def find(self, identity: str) -> ResolvedPackage | None:
        from .distribution import index_lookup
        hit = index_lookup(self.spec.removeprefix("index:"), identity, Path(tempfile.mkdtemp(prefix="ontle-index-")))
        if hit is None:
            return None
        return ArchiveSource(self.spec, hit[0])._scan()[0]


def make_source(spec: str, base: Path | None = None) -> PackageSource:
    if spec.startswith(("oci:", "oci-layout:")):
        return OciSource(spec)
    if spec.startswith("index:"):
        return IndexSource(spec)
    m = GIT_SOURCE_RE.match(spec)
    if m:
        url = m["url"]
        # A local repository or bundle path without a URL scheme is resolved like a directory source.
        if "://" not in url and not url.startswith("git@"):
            local = Path(url).expanduser()
            url = str(((base / local) if (not local.is_absolute() and base is not None) else local).resolve())
        return GitSource(spec, url, m["rev"], m["subdir"])
    path = Path(spec).expanduser()
    if not path.is_absolute() and base is not None:
        path = base / path
    path = path.resolve()
    if path.name.endswith(".owp.zip"):
        return ArchiveSource(spec, path)
    return DirectorySource(spec, path)


def default_sources(extra: list[str] | None = None) -> list[str]:
    sources = list(extra or [])
    env = os.environ.get("ONTLE_PATH")
    if env:
        sources += [s for s in env.split(os.pathsep) if s]
    return sources


def resolve_package(path: str | Path, sources: list[str] | None = None) -> Resolution:
    """Resolve the dependency closure of the package at `path`. Errors are collected, not raised."""
    root_dir, manifest = load_manifest(path)
    root_pkg = ResolvedPackage(identity_of(manifest), manifest.get("kind"), root_dir, "local", manifest)
    resolution = Resolution(root_pkg, {root_pkg.identity: root_pkg})
    global_sources = [make_source(s) for s in default_sources(sources)]
    by_name: dict[str, str] = {root_pkg.identity.rsplit("@", 1)[0]: root_pkg.identity}

    def visit(pkg: ResolvedPackage, stack: list[str]) -> None:
        try:
            deps = _dependency_refs(pkg.manifest)
        except OWPError as exc:
            resolution.errors.append(f"resolve.reference: {pkg.identity}: {exc}")
            return
        for ref, dep_source in deps:
            try:
                parse_package_ref(ref)
            except OWPError as exc:
                resolution.errors.append(f"resolve.reference: {pkg.identity}: {exc}")
                continue
            if ref in stack:
                resolution.errors.append(f"resolve.cycle: dependency cycle: {' -> '.join(stack + [ref])}")
                continue
            unversioned = ref.rsplit("@", 1)[0]
            if unversioned in by_name and by_name[unversioned] != ref:
                resolution.errors.append(f"resolve.version-conflict: version conflict for {unversioned}: {by_name[unversioned]} and {ref}")
                continue
            if ref in resolution.packages:
                continue
            candidates = ([make_source(dep_source, base=pkg.root)] if dep_source else []) + global_sources
            found = None
            for src in candidates:
                try:
                    found = src.find(ref)
                except OWPError as exc:
                    resolution.errors.append(f"resolve.source: {pkg.identity}: source {src.spec}: {exc}")
                    continue
                if found:
                    break
            if not found:
                nearby = sorted({i for src in candidates for i in src.versions_of(ref.rsplit("@", 1)[0])})
                hint = f" (found {', '.join(nearby)}: the version differs)" if nearby else ""
                resolution.errors.append(f"resolve.unresolved: {pkg.identity}: cannot resolve {ref}{hint}")
                continue
            resolution.packages[ref] = found
            by_name[unversioned] = ref
            visit(found, stack + [ref])

    visit(root_pkg, [root_pkg.identity])
    return resolution


def _local_asset_kind(pkg: ResolvedPackage, rel: str) -> str | None:
    return pkg.local_assets()[0].get(rel)


def _load_asset(pkg: ResolvedPackage, rel: str) -> dict[str, Any]:
    try:
        doc = load_yaml((pkg.root / rel).read_text(encoding="utf-8"))
    except Exception:
        return {}
    return doc if isinstance(doc, dict) else {}


def _binding_grounding_errors(pkg: ResolvedPackage, resolution: Resolution) -> list[str]:
    """SemanticBinding CURIEs resolve against the OntologyPackages this package depends on (spec section 14)."""
    from .binding import grounding_issues
    from .ontology import terms as ontology_terms
    kinds, docs = pkg.local_assets()
    binding_docs = {rel: docs.get(rel) or {} for rel, kind in kinds.items() if kind == "SemanticBinding"}
    if not binding_docs:
        return []
    ontologies = []
    for ref, _ in _dependency_refs(pkg.manifest):
        dep = resolution.packages.get(ref)
        if dep is not None and dep.kind == "OntologyPackage":
            prefixes, defined = ontology_terms(dep.root, dep.manifest)
            ontologies.append((ref, prefixes, defined))
    return grounding_issues(pkg.identity, binding_docs, ontologies)


def _ontology_dependency_errors(pkg: ResolvedPackage, resolution: Resolution) -> list[str]:
    """Spec 3.1: a term an OntologyPackage uses from the namespace of an OntologyPackage it depends on is defined there."""
    if pkg.kind != "OntologyPackage":
        return []
    from .ontology import _load, _profile_curies, expand, terms as ontology_terms
    deps = []
    for ref, _ in _dependency_refs(pkg.manifest):
        dep = resolution.packages.get(ref)
        iri = (((dep.manifest.get("spec") or {}).get("ontology") or {}).get("iri") if dep is not None and dep.kind == "OntologyPackage" else None)
        if isinstance(iri, str) and iri:
            deps.append((ref, iri, ontology_terms(dep.root, dep.manifest)[1]))  # type: ignore[union-attr]
    ontology = (pkg.manifest.get("spec") or {}).get("ontology") or {}
    prefixes = ontology.get("prefixes") if isinstance(ontology.get("prefixes"), dict) else {}
    errors: list[str] = []
    for entry in ontology.get("entrypoints") or [] if deps else []:
        if not (isinstance(entry, dict) and entry.get("format") == "owp-yaml" and entry.get("role") == "schema" and isinstance(entry.get("path"), str)):
            continue
        doc = _load(pkg.root / entry["path"])
        for where, value, term_type in _profile_curies(doc) if isinstance(doc, dict) else []:
            full = expand(value, prefixes) if isinstance(value, str) and not term_type else None
            for ref, iri, defined in deps:
                if full and full.startswith(iri) and full not in defined:
                    errors.append(f"ontology.dependency-term: {pkg.identity}: {entry['path']}: {where} {value!r} ({full}) is not a term of {ref}")
    return errors


def cross_package_errors(resolution: Resolution) -> list[str]:
    """Rules that need more than one package: extension definitions and World Model grounding against the referenced World."""
    errors: list[str] = []
    for pkg in resolution.packages.values():
        errors += _binding_grounding_errors(pkg, resolution)
        errors += _ontology_dependency_errors(pkg, resolution)
        deps = (pkg.manifest.get("spec") or {}).get("dependencies") or []
        for dep in deps if isinstance(deps, list) else []:
            if not (isinstance(dep, dict) and isinstance(dep.get("as"), str) and isinstance(dep.get("ref"), str)):
                continue
            target = resolution.packages.get(dep["ref"])
            if target is not None and not isinstance((target.manifest.get("spec") or {}).get("extensionDefinition"), dict):
                errors.append(f"extension.definition: {pkg.identity}: extension {dep['as']!r} resolves to {dep['ref']}, which declares no spec.extensionDefinition")
        if pkg.kind != "WorldModelPackage":
            continue
        grounding = ((pkg.manifest.get("spec") or {}).get("worldModel") or {}).get("semanticGrounding") or {}
        world_ref = grounding.get("worldRef")
        if not isinstance(world_ref, str):
            continue
        if world_ref not in {ref for ref, _ in _dependency_refs(pkg.manifest)}:
            errors.append(f"grounding.world-not-dependency: {pkg.identity}: semanticGrounding.worldRef {world_ref} must also be listed in spec.dependencies")
            continue
        world = resolution.packages.get(world_ref)
        if world is None:
            continue  # already reported as unresolved
        if world.kind != "WorldPackage":
            errors.append(f"grounding.world-kind: {pkg.identity}: worldRef {world_ref} resolves to {world.kind}, not WorldPackage")
            continue
        view_paths = set()
        for ref in grounding.get("compatibleWorldViews") or []:
            rel = ref.partition("#")[2]
            view_paths.add(rel)
            if _local_asset_kind(world, rel) != "WorldViewProfile":
                views = sorted(p for p, k in world.local_assets()[0].items() if k == "WorldViewProfile")
                errors.append(f"grounding.world-view: {pkg.identity}: compatibleWorldViews entry {ref} is not a WorldViewProfile asset of {world_ref}"
                              f" (its Views: {', '.join(views) or 'none'})")
        for ref in grounding.get("compatibleStateCompilers") or []:
            rel = ref.partition("#")[2]
            if _local_asset_kind(world, rel) != "StateCompilerProfile":
                errors.append(f"grounding.state-compiler: {pkg.identity}: compatibleStateCompilers entry {ref} is not a StateCompilerProfile asset of {world_ref}")
                continue
            compiled_view = (_load_asset(world, rel).get("spec") or {}).get("worldViewRef")
            if compiled_view not in view_paths:
                errors.append(f"grounding.compiler-view: {pkg.identity}: State Compiler {ref} compiles {compiled_view!r}, which is not among compatibleWorldViews")
    return errors


# Package kinds each kind may depend on: the hierarchy Ontology <- World <- World Model (spec section 11).
DEPENDENCY_DIRECTIONS = {
    "OntologyPackage": ("OntologyPackage",),
    "WorldPackage": ("OntologyPackage", "WorldPackage"),
    "WorldModelPackage": ("OntologyPackage", "WorldPackage", "WorldModelPackage"),
}


def external_world_issues(resolution: Resolution) -> tuple[list[str], list[str]]:
    """Section 6: a View's external Worlds resolve to WorldPackages; names it takes from them are in their boundary."""
    from .core import view_external_names
    errors: list[str] = []
    warnings: list[str] = []
    for pkg in resolution.packages.values():
        if pkg.kind != "WorldPackage":
            continue
        kinds, docs = pkg.local_assets()
        for rel in sorted(r for r, k in kinds.items() if k == "WorldViewProfile"):
            vspec = (docs.get(rel) or {}).get("spec") or {}
            refs = vspec.get("externalWorldRefs") if isinstance(vspec.get("externalWorldRefs"), list) else []
            for ref in refs:
                target = resolution.packages.get(ref) if isinstance(ref, str) else None
                if target is not None and target.kind != "WorldPackage":
                    errors.append(f"view.external-world: {pkg.identity}: {rel}: external World {ref} resolves to a {target.kind}, not a WorldPackage")
            for ref, name in view_external_names(vspec):
                target = resolution.packages.get(ref)
                world = ((target.manifest.get("spec") or {}).get("world") or {}) if target is not None and target.kind == "WorldPackage" else {}
                included = (world.get("boundary") or {}).get("included") if isinstance(world.get("boundary"), dict) else None
                if isinstance(included, list) and included and name not in included:
                    warnings.append(f"view.outside-world: {pkg.identity}: {rel}: projection.include '{ref}#{name}' is not in that World's spec.world.boundary.included")
    return errors, warnings


def dependency_direction_warnings(resolution: Resolution) -> list[str]:
    """Dependencies that point up the hierarchy. Extension dependencies (declared with `as`) are exempt."""
    warnings: list[str] = []
    for pkg in resolution.packages.values():
        allowed = DEPENDENCY_DIRECTIONS.get(pkg.kind or "")
        for dep in (pkg.manifest.get("spec") or {}).get("dependencies") or []:
            if allowed is None or (isinstance(dep, dict) and "as" in dep):
                continue
            ref = dep if isinstance(dep, str) else dep.get("ref") if isinstance(dep, dict) else None
            target = resolution.packages.get(ref) if isinstance(ref, str) else None
            if target is not None and target.kind not in allowed:
                warnings.append(f"resolve.dependency-direction: {pkg.identity} ({pkg.kind}) depends on {ref} ({target.kind}); "
                                f"allowed for {pkg.kind}: {', '.join(allowed)}")
    return warnings


def validate_resolved(path: str | Path, sources: list[str] | None = None) -> tuple[ValidationResult, Resolution]:
    """Validate a package, its resolved dependency closure, and the cross-package grounding rules."""
    result = validate_package(path)
    errors, warnings = list(result.errors), list(result.warnings)
    manifest = result.manifest or {}
    if not (isinstance(manifest.get("metadata"), dict) and isinstance(manifest.get("spec"), dict)):
        return result, None  # type: ignore[return-value]  # manifest.metadata / manifest.spec: nothing to resolve
    try:
        resolution = resolve_package(path, sources)
    except OWPError as exc:
        return ValidationResult(False, errors + [f"resolve.reference: {exc}"], warnings, result.manifest), None  # type: ignore[return-value]
    errors += resolution.errors
    for ident, pkg in sorted(resolution.packages.items()):
        if pkg is not resolution.root:
            errors += [f"resolve.dependency-invalid: {ident}: {e}" for e in validate_package(pkg.root).errors]
    errors += cross_package_errors(resolution)
    warnings += dependency_direction_warnings(resolution)
    ext_errors, ext_warnings = external_world_issues(resolution)
    errors += ext_errors
    warnings += ext_warnings
    return ValidationResult(not errors, errors, warnings, result.manifest), resolution


def binding_and_prefixes(world_path: str | Path, sources: list[str] | None = None) -> tuple[Path, dict[str, Any], dict[str, Any] | None, dict[str, str]]:
    """(World root, manifest, SemanticBinding or None, prefixes of its dependency ontologies), for RDF-based output."""
    from .ontology import terms as ontology_terms
    root, manifest = load_manifest(world_path)
    binding_rel = ((manifest.get("spec") or {}).get("world") or {}).get("semanticBinding")
    binding, prefixes = None, {}
    if isinstance(binding_rel, str):
        resolution = resolve_package(world_path, sources)
        if resolution.errors:
            raise OWPError("; ".join(resolution.errors) + " (the SemanticBinding's ontologies are needed for --rdf and --ngsi-ld: pass --source)")
        world = resolution.root
        for ref, _ in _dependency_refs(world.manifest):
            dep = resolution.packages.get(ref)
            if dep is not None and dep.kind == "OntologyPackage":
                prefixes.update(ontology_terms(dep.root, dep.manifest)[0])
        binding = _load_asset(world, binding_rel)
    return root, manifest, binding, prefixes


def ews_rdf(world_path: str | Path, ews: dict[str, Any], observations: dict[str, Any], sources: list[str] | None = None) -> str:
    """The EWS as Turtle 1.2 in the OWP vocabulary. Bound fields and subjects become triple terms when the World's
    SemanticBinding and its dependency ontologies resolve; otherwise values are given as rdf:value."""
    from .rdfexport import ews_turtle
    root, manifest, binding, prefixes = binding_and_prefixes(world_path, sources)
    return ews_turtle(root, manifest, ews, observations, binding, prefixes)


def ews_ngsi(world_path: str | Path, ews: dict[str, Any], observations: dict[str, Any], sources: list[str] | None = None) -> list[dict[str, Any]]:
    """The EWS as NGSI-LD entities (docs/interop/NGSI-LD.md)."""
    from .interop import ews_ngsi_ld
    root, manifest, binding, prefixes = binding_and_prefixes(world_path, sources)
    return ews_ngsi_ld(root, manifest, ews, observations, binding, prefixes)


def ews_jsonld(world_path: str | Path, ews: dict[str, Any], sources: list[str] | None = None) -> dict[str, Any]:
    """The EWS document as JSON with an @context mapping bound fields to ontology IRIs. The EWS content is unchanged."""
    from .binding import jsonld_context
    from .ontology import terms as ontology_terms
    resolution = resolve_package(world_path, sources)
    if resolution.errors:
        raise OWPError("; ".join(resolution.errors))
    world = resolution.root
    binding_rel = ((world.manifest.get("spec") or {}).get("world") or {}).get("semanticBinding")
    if not isinstance(binding_rel, str):
        raise OWPError("the World declares no spec.world.semanticBinding")
    prefixes: dict[str, str] = {}
    for ref, _ in _dependency_refs(world.manifest):
        dep = resolution.packages.get(ref)
        if dep is not None and dep.kind == "OntologyPackage":
            prefixes.update(ontology_terms(dep.root, dep.manifest)[0])
    binding = _load_asset(world, binding_rel)
    out = {"@context": jsonld_context(binding, prefixes), **ews}
    graph = _subject_nodes(world, binding, ews, prefixes)
    if graph:
        out["@graph"] = graph
    return out


def _concepts(field: str, value: Any, bspec: dict[str, Any], prefixes: dict[str, str]) -> Any:
    """A coded value (or each element of a list) as {"@id": concept IRI} when the field's binding declares `values`."""
    from .binding import concept_iris
    fb = (bspec.get("fields") or {}).get(field) if isinstance(bspec.get("fields"), dict) else None
    values = fb.get("values") if isinstance(fb, dict) and isinstance(fb.get("values"), dict) else None
    if values is None:
        return value
    out = [{"@id": iri} for iri in concept_iris(field, values, value, prefixes)]
    return out if isinstance(value, list) else out[0]


def _subject_nodes(world: ResolvedPackage, binding: dict[str, Any], ews: dict[str, Any],
                   prefixes: dict[str, str] | None = None) -> list[dict[str, Any]]:
    """Section 12.3/14: per-subject state as individuals, when the SemanticBinding maps the field's subjects to IRIs.
    A field whose binding declares `values` gives concept IRIs instead of codes."""
    from .binding import subject_iri
    from .ews import binding_form, output_lists
    bspec = binding.get("spec") or {}
    subjects = bspec.get("subjects") if isinstance(bspec.get("subjects"), dict) else {}
    types = bspec.get("observationTypes") if isinstance(bspec.get("observationTypes"), dict) else {}
    compiler_ref = ((ews.get("spec") or {}).get("stateCompiler") or "").partition("#")[2]
    if not subjects or not compiler_ref:
        return []
    compiler = (_load_asset(world, compiler_ref).get("spec") or {})
    bindings = compiler.get("bindings") if isinstance(compiler.get("bindings"), dict) else {}
    per_subject, _ = output_lists(compiler)

    def source_type(field: str, seen: tuple[str, ...] = ()) -> str | None:
        b = bindings.get(field)
        form = binding_form(b)
        if form == "observe":
            return b.get("from")
        if form in ("estimate", "aggregate"):
            return b[form].get("from")
        if form == "classify" and field not in seen:
            return source_type(b["classify"].get("input"), seen + (field,))
        return None

    nodes: dict[str, dict[str, Any]] = {}
    state = (ews.get("spec") or {}).get("state") or {}
    for field in per_subject:
        otype = source_type(field)
        rule = subjects.get(otype) if otype else None
        if not isinstance(rule, dict) or not isinstance(state.get(field), dict):
            continue
        for subject, value in state[field].items():
            node = nodes.setdefault(subject_iri(rule, subject), {"@id": subject_iri(rule, subject)})
            if isinstance(types.get(otype), str):
                node["@type"] = types[otype]
            node[field] = _concepts(field, value, bspec, prefixes or {})
    return [nodes[k] for k in sorted(nodes)]
