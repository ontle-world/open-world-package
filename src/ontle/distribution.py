"""Distribution tooling: external content, OCI transport, package indexes, signatures, and catalogs.

Normative parts live in the spec (sections 7, 11, 15): the lock file's `externals`,
the OCI artifact profile, the package index format, and detached evidence. The
commands here are reference tooling; OCI and signing call the `oras` and `cosign`
command-line tools.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

import yaml

from .core import MANIFEST, OWPError, load_manifest, sha256_bytes, write_manifest

FILELIST_MEDIA_TYPE = "application/vnd.openworld.filelist+json"
OCI_ARTIFACT_TYPE = "application/vnd.openworld.package.v1alpha1"
OCI_LAYER_MEDIA_TYPE = "application/vnd.openworld.package.layer.v1alpha1+zip"
OCI_CONFIG_MEDIA_TYPE = "application/vnd.openworld.manifest.v1alpha1+json"
OCI_EVIDENCE_ARTIFACT_TYPE = "application/vnd.openworld.evidence.v1alpha1"
OCI_EVIDENCE_MEDIA_TYPE = "application/vnd.openworld.evidence.v1alpha1+yaml"
INDEX_KIND = "PackageIndex"


# --- external references ----------------------------------------------------

def external_refs(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    """Bound ExternalRefs the manifest declares, with where they are (JSON Pointer into owp.yaml)."""
    spec = manifest.get("spec") or {}
    out: list[dict[str, Any]] = []
    for i, item in enumerate(spec.get("assets") or []):
        if isinstance(item, dict) and isinstance(item.get("ref"), dict) and item["ref"].get("status", "bound") == "bound":
            out.append({"pointer": f"/spec/assets/{i}/ref", "ref": item["ref"]})
    for i, imp in enumerate(((spec.get("ontology") or {}).get("externalImports") or []) if isinstance(spec.get("ontology"), dict) else []):
        if isinstance(imp, dict) and isinstance(imp.get("ref"), dict) and imp["ref"].get("status", "bound") == "bound":
            out.append({"pointer": f"/spec/ontology/externalImports/{i}/ref", "ref": imp["ref"]})
    return out


def lock_externals(manifest: dict[str, Any], vendored: dict[str, str] | None = None) -> list[dict[str, Any]]:
    """The `externals` section of owp.lock.json (spec section 7)."""
    entries = []
    for item in external_refs(manifest):
        ref = item["ref"]
        entry = {"pointer": item["pointer"], "provider": ref.get("provider"), "uri": ref.get("uri")}
        for key in ("revision", "digest", "mediaType"):
            if ref.get(key) is not None:
                entry[key] = ref[key]
        if vendored and item["pointer"] in vendored:
            entry["vendoredPath"] = vendored[item["pointer"]]
        entries.append(entry)
    return entries


def _download(uri: str) -> bytes:
    parsed = urllib.parse.urlparse(uri)
    if parsed.scheme not in {"https", "http", "file"}:
        raise OWPError(f"cannot download {uri}: only https (and http/file for testing) are supported by the reference CLI")
    with urllib.request.urlopen(uri, timeout=60) as response:  # noqa: S310 (scheme checked above)
        return response.read()


def _check_digest(data: bytes, digest: str | None, what: str) -> None:
    if digest is not None and f"sha256:{sha256_bytes(data)}" != digest:
        raise OWPError(f"digest mismatch for {what}: expected {digest}, got sha256:{sha256_bytes(data)}")


def fetch_ref(ref: dict[str, Any], target: Path) -> list[Path]:
    """Download one bound ExternalRef into target and verify it (spec section 5.1). Returns the files written."""
    provider = ref.get("provider")
    uri = ref.get("uri")
    target.mkdir(parents=True, exist_ok=True)
    if provider in {"https"} or (isinstance(uri, str) and uri.startswith(("http://", "file://"))):
        data = _download(uri)
        _check_digest(data, ref.get("digest"), uri)
        if ref.get("mediaType") == FILELIST_MEDIA_TYPE:
            listing = json.loads(data)
            base = uri.rsplit("/", 1)[0] + "/"
            written = []
            for entry in listing.get("files") or []:
                rel = entry["path"]
                if rel.startswith("/") or ".." in Path(rel).parts:
                    raise OWPError(f"file list entry {rel!r} escapes the list's directory")
                blob = _download(urllib.parse.urljoin(base, rel))
                _check_digest(blob, f"sha256:{entry['sha256']}", rel)
                out = target / rel
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(blob)
                written.append(out)
            return written
        out = target / (Path(urllib.parse.urlparse(uri).path).name or "content")
        out.write_bytes(data)
        return [out]
    if provider in {"git", "huggingface"}:
        url = uri if provider == "git" or "://" in uri else f"https://huggingface.co/{uri.removeprefix('hf://')}"
        url = url.replace("hf://", "https://huggingface.co/", 1)
        subprocess.run(["git", "clone", "--quiet", url, str(target)], check=True)
        if ref.get("revision"):
            subprocess.run(["git", "-C", str(target), "checkout", "--quiet", ref["revision"]], check=True)
        return [target]
    if provider == "oci":
        oras = _tool("oras")
        reference = uri + (f"@{ref['digest']}" if ref.get("digest") and "@" not in uri else "")
        subprocess.run([oras, "pull", reference, "--output", str(target)], check=True, capture_output=True)
        return [target]
    raise OWPError(f"the reference CLI cannot fetch provider {provider!r}")


def fetch_package(package: str | Path, into: str | Path) -> list[Path]:
    root, manifest = load_manifest(package)
    written: list[Path] = []
    for i, item in enumerate(external_refs(manifest)):
        written += fetch_ref(item["ref"], Path(into) / item["pointer"].strip("/").replace("/", "_"))
    return written


def pin_https_refs(package: str | Path) -> list[str]:
    """`ontle lock`: add digests to unpinned https refs in owp.yaml by downloading them."""
    root, manifest = load_manifest(package)
    changed = []
    for item in external_refs(manifest):
        ref = item["ref"]
        if ref.get("provider") == "https" and not ref.get("digest"):
            ref["digest"] = f"sha256:{sha256_bytes(_download(ref['uri']))}"
            changed.append(item["pointer"])
    if changed:
        write_manifest(root / MANIFEST, manifest)
    return changed


def vendor_https_refs(root: Path, manifest: dict[str, Any]) -> dict[str, tuple[str, bytes]]:
    """Content of pinned https refs for `ontle pack --vendor`: pointer -> (vendor path, bytes)."""
    out = {}
    for item in external_refs(manifest):
        ref = item["ref"]
        if ref.get("provider") != "https" or ref.get("mediaType") == FILELIST_MEDIA_TYPE:
            continue
        if not ref.get("digest"):
            raise OWPError(f"{item['pointer']}: only pinned refs can be vendored; run `ontle lock` first")
        data = _download(ref["uri"])
        _check_digest(data, ref["digest"], ref["uri"])
        out[item["pointer"]] = (f"vendor/{ref['digest'].split(':', 1)[1]}", data)
    return out


# --- OCI ----------------------------------------------------------------------

def _tool(name: str) -> str:
    path = os.environ.get(f"ONTLE_{name.upper()}") or shutil.which(name)
    if not path:
        raise OWPError(f"{name} is required for this command; install it or set ONTLE_{name.upper()}")
    return path


def _oci_target(reference: str) -> list[str]:
    """oras arguments for a reference: a registry reference, or oci-layout:<dir>:<tag> for a local OCI layout."""
    if reference.startswith("oci-layout:"):
        path, _, tag = reference.removeprefix("oci-layout:").rpartition(":")
        return ["--oci-layout", f"{path}:{tag}"]
    return [reference]


def oci_push(archive: str | Path, reference: str) -> str:
    """Push a verified .owp.zip as an OCI artifact (spec section 7.1). Returns the manifest digest."""
    from .core import verify_archive
    archive = Path(archive).resolve()
    ok, errors = verify_archive(archive)
    if not ok:
        raise OWPError("archive does not verify: " + "; ".join(errors))
    with zipfile.ZipFile(archive) as zf:
        manifest = yaml.safe_load(zf.read(MANIFEST))
    with tempfile.TemporaryDirectory() as td:
        config = Path(td) / "config.json"
        config.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
        layer = Path(td) / archive.name
        shutil.copy(archive, layer)
        result = subprocess.run([_tool("oras"), "push", *_oci_target(reference),
                                 "--artifact-type", OCI_ARTIFACT_TYPE,
                                 "--config", f"{config.name}:{OCI_CONFIG_MEDIA_TYPE}",
                                 f"{layer.name}:{OCI_LAYER_MEDIA_TYPE}", "--format", "json"],
                                cwd=td, check=True, capture_output=True, text=True)
    return json.loads(result.stdout)["digest"]


def oci_pull(reference: str, into: Path) -> tuple[Path, str]:
    """Pull an OWP OCI artifact; returns the archive path and the OCI manifest digest."""
    oras = _tool("oras")
    fetched = subprocess.run([oras, "manifest", "fetch", *_oci_target(reference), "--descriptor"], check=True, capture_output=True, text=True)
    descriptor = json.loads(fetched.stdout)
    if descriptor.get("artifactType") not in {None, OCI_ARTIFACT_TYPE}:
        raise OWPError(f"{reference} is not an OWP package artifact ({descriptor.get('artifactType')})")
    into.mkdir(parents=True, exist_ok=True)
    subprocess.run([oras, "pull", *_oci_target(reference), "--output", str(into)], check=True, capture_output=True)
    archives = sorted(into.glob("*.owp.zip"))
    if len(archives) != 1:
        raise OWPError(f"{reference} must contain exactly one .owp.zip layer")
    return archives[0], descriptor["digest"]


def oci_attach_evidence(subject_reference: str, evidence: str | Path) -> str:
    """Attach a detached CompatibilityEvidence document to a pushed package as an OCI referrer."""
    evidence = Path(evidence).resolve()
    result = subprocess.run([_tool("oras"), "attach", *_oci_target(subject_reference),
                             "--artifact-type", OCI_EVIDENCE_ARTIFACT_TYPE,
                             f"{evidence.name}:{OCI_EVIDENCE_MEDIA_TYPE}", "--format", "json"],
                            cwd=evidence.parent, check=True, capture_output=True, text=True)
    return json.loads(result.stdout)["digest"]


# --- static package index ---------------------------------------------------------

def build_index(archives: list[Path], base: Path | None = None, base_url: str | None = None) -> dict[str, Any]:
    """A static package index (spec section 11.1) listing archives by identity and digest."""
    from .core import verify_archive
    packages = []
    for archive in sorted(archives):
        ok, errors = verify_archive(archive)
        if not ok:
            raise OWPError(f"{archive} does not verify: " + "; ".join(errors))
        with zipfile.ZipFile(archive) as zf:
            manifest = yaml.safe_load(zf.read(MANIFEST))
        md = manifest.get("metadata") or {}
        location = archive.name if base is None else archive.resolve().relative_to(base.resolve()).as_posix()
        if base_url:
            location = base_url.rstrip("/") + "/" + location
        entry = {"identity": f"{md['namespace']}/{md['name']}@{md['version']}", "kind": manifest.get("kind"),
                 "archive": location, "digest": f"sha256:{sha256_bytes(archive.read_bytes())}"}
        if md.get("title"):
            entry["title"] = md["title"]
        packages.append(entry)
    identities = [p["identity"] for p in packages]
    if len(set(identities)) != len(identities):
        raise OWPError("an index lists each package identity once")
    return {"apiVersion": "openworld/v1alpha1", "kind": INDEX_KIND, "packages": packages}


def index_lookup(index_location: str, identity: str, cache: Path) -> tuple[Path, str] | None:
    """Find an identity in a package index, download its archive, and verify the digest."""
    if "://" in index_location:
        index = json.loads(_download(index_location))
        base = index_location.rsplit("/", 1)[0] + "/"
    else:
        index = json.loads(Path(index_location).read_text(encoding="utf-8"))
        base = Path(index_location).resolve().parent.as_uri() + "/"
    if index.get("kind") != INDEX_KIND:
        raise OWPError(f"{index_location} is not a {INDEX_KIND}")
    for entry in index.get("packages") or []:
        if entry.get("identity") == identity:
            data = _download(urllib.parse.urljoin(base, entry["archive"]))
            _check_digest(data, entry.get("digest"), entry["archive"])
            cache.mkdir(parents=True, exist_ok=True)
            out = cache / f"{hashlib.sha256(identity.encode()).hexdigest()[:16]}.owp.zip"
            out.write_bytes(data)
            return out, entry["digest"]
    return None


# --- signatures (cosign) --------------------------------------------------------

def sign_archive(archive: str | Path, key: str | None = None) -> Path:
    """Sign an archive with cosign; writes <archive>.sigstore.json. Without a key, cosign signs keyless (OIDC)."""
    archive = Path(archive).resolve()
    bundle = archive.with_name(archive.name + ".sigstore.json")
    command = [_tool("cosign"), "sign-blob", "--yes", "--bundle", str(bundle)]
    if key:
        command += ["--key", key, "--use-signing-config=false", "--tlog-upload=false"]  # key-based: no transparency log
    subprocess.run(command + [str(archive)], check=True, capture_output=True)
    return bundle


def verify_signature(archive: str | Path, key: str | None = None, identity: str | None = None, issuer: str | None = None) -> None:
    archive = Path(archive).resolve()
    bundle = archive.with_name(archive.name + ".sigstore.json")
    if not bundle.exists():
        raise OWPError(f"no signature bundle {bundle.name}")
    command = [_tool("cosign"), "verify-blob", "--bundle", str(bundle)]
    if key:
        command += ["--key", key, "--insecure-ignore-tlog=true"]
    elif identity and issuer:
        command += ["--certificate-identity", identity, "--certificate-oidc-issuer", issuer]
    else:
        raise OWPError("verify --signature needs --key, or --identity and --issuer for keyless signatures")
    result = subprocess.run(command + [str(archive)], capture_output=True, text=True)
    if result.returncode != 0:
        raise OWPError("signature does not verify: " + (result.stderr.strip() or result.stdout.strip()))


# --- detached evidence ----------------------------------------------------------

def check_detached_evidence(evidence: dict[str, Any], archive: str | Path) -> list[str]:
    """Spec section 9.1: evidence published outside the package binds to the archive by identity and digest."""
    from .core import _validate_evaluation_lineage, verify_archive
    from .structure import COMPATIBILITY_EVIDENCE, structure_errors
    errors = structure_errors(evidence, COMPATIBILITY_EVIDENCE, "evidence", None)
    if evidence.get("kind") != "CompatibilityEvidence":
        return errors + ["evidence.detached-subject: document is not a CompatibilityEvidence"]
    archive = Path(archive)
    ok, problems = verify_archive(archive)
    if not ok:
        return errors + [f"evidence.detached-subject: archive does not verify: {'; '.join(problems)}"]
    with zipfile.ZipFile(archive) as zf:
        manifest = yaml.safe_load(zf.read(MANIFEST))
    md = manifest.get("metadata") or {}
    identity = f"{md.get('namespace')}/{md.get('name')}@{md.get('version')}"
    spec = evidence.get("spec") or {}
    if spec.get("subject") != identity:
        errors.append(f"evidence.detached-subject: spec.subject must be the archive's identity {identity}")
    digest = f"sha256:{sha256_bytes(archive.read_bytes())}"
    if spec.get("subjectDigest") != digest:
        errors.append(f"evidence.detached-subject: spec.subjectDigest must be the archive digest {digest}")
    lineage_errors: list[str] = []
    _validate_evaluation_lineage(manifest.get("spec") or {}, manifest.get("kind"), identity,
                                 {"evidence": "CompatibilityEvidence"}, {"evidence": evidence}, lineage_errors, [])
    return errors + [e for e in lineage_errors if not e.startswith("evidence.version-mismatch")]


# --- catalogs (informative exports) ------------------------------------------------

def catalog(package: str | Path, fmt: str) -> str:
    root, manifest = load_manifest(package)
    md = manifest.get("metadata") or {}
    spec = manifest.get("spec") or {}
    identity = f"{md.get('namespace')}/{md.get('name')}@{md.get('version')}"
    refs = external_refs(manifest)
    for item in spec.get("assets") or []:  # content refs of local KnowledgeAsset and Dataset descriptions
        if isinstance(item, dict) and item.get("kind") in {"KnowledgeAsset", "Dataset"} and isinstance(item.get("path"), str):
            doc = yaml.safe_load((root / item["path"]).read_text(encoding="utf-8")) or {}
            ref = ((doc.get("spec") or {}).get("content") or {}).get("ref")
            if isinstance(ref, dict) and ref.get("status", "bound") == "bound":
                refs.append({"pointer": item["path"], "ref": ref})
    if fmt == "dcat":
        distributions = [{"@type": "dcat:Distribution", "dcat:downloadURL": r["ref"].get("uri"),
                          **({"spdx:checksum": {"@type": "spdx:Checksum", "spdx:algorithm": "spdx:checksumAlgorithm_sha256",
                                                "spdx:checksumValue": r["ref"]["digest"].split(":", 1)[1]}} if r["ref"].get("digest") else {}),
                          **({"dcat:mediaType": r["ref"]["mediaType"]} if r["ref"].get("mediaType") else {})} for r in refs]
        doc = {"@context": {"dcat": "http://www.w3.org/ns/dcat#", "dct": "http://purl.org/dc/terms/", "spdx": "http://spdx.org/rdf/terms#"},
               "@type": "dcat:Dataset", "dct:identifier": identity, "dct:title": md.get("title") or md.get("name"),
               "dct:license": md.get("license"), "dcat:keyword": spec.get("domains") or [], "dcat:distribution": distributions}
        return json.dumps(doc, indent=2, ensure_ascii=False) + "\n"
    if fmt == "croissant":
        files = [{"@type": "cr:FileObject", "@id": r["pointer"], "name": r["pointer"], "contentUrl": r["ref"].get("uri"),
                  **({"sha256": r["ref"]["digest"].split(":", 1)[1]} if r["ref"].get("digest") else {}),
                  **({"encodingFormat": r["ref"]["mediaType"]} if r["ref"].get("mediaType") else {})} for r in refs]
        doc = {"@context": {"@vocab": "https://schema.org/", "cr": "http://mlcommons.org/croissant/", "sc": "https://schema.org/"},
               "@type": "sc:Dataset", "conformsTo": "http://mlcommons.org/croissant/1.0", "name": md.get("name"),
               "description": md.get("title") or md.get("name"), "license": md.get("license"), "url": identity,
               "distribution": files}
        return json.dumps(doc, indent=2, ensure_ascii=False) + "\n"
    if fmt == "hf-card":
        front = {"license": (md.get("license") or "other").lower(), "tags": ["open-world-package", *(spec.get("domains") or [])]}
        grounding = ((spec.get("worldModel") or {}).get("semanticGrounding") or {})
        body = [f"# {md.get('title') or md.get('name')}", "", f"Open World Package `{identity}` ({manifest.get('kind')}).", ""]
        if grounding:
            body += ["## World grounding", "", f"- World: `{grounding.get('worldRef')}`"]
            body += [f"- View: `{v}`" for v in grounding.get("compatibleWorldViews") or []]
            body += [f"- State Compiler: `{c}`" for c in grounding.get("compatibleStateCompilers") or []]
            body += [""]
        return "---\n" + yaml.safe_dump(front, sort_keys=False) + "---\n\n" + "\n".join(body)
    raise OWPError(f"unknown catalog format {fmt!r}")
