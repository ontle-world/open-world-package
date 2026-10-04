"""Package reports (informative): numbers a catalog or registry shows for a package, derived from the package itself.

The report is computed, never stored in the package: the same archive gives the same report, and authors do not write
statistics by hand. Its shape is schemas/package-report.schema.json. No rule here changes a verdict; the verdict comes
from validate_package.
"""
from __future__ import annotations

import re
import tempfile
import zipfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from . import __version__
from . import ontology as ontology_module
from .core import (DEFAULT_WORLD_PROFILE, OWPError, _list, _ref_asset_kinds, compiler_fields, load_manifest, local_assets,
                   satisfied_world_profile, sha256_bytes, validate_package, verify_archive)
from .distribution import external_refs
from .structure import COMMIT_RE

CARD_SECTIONS = ["Scope", "Sources", "Use it for", "Limitations", "Versions"]
DEFAULT_CARDS = {"WorldPackage": "WORLD.md", "WorldModelPackage": "WORLDMODEL.md", "OntologyPackage": "ONTOLOGY.md"}
CARD_SPEC_KEY = {"WorldPackage": "world", "WorldModelPackage": "worldModel", "OntologyPackage": "ontology"}
DESCRIPTION_LIMIT = 160  # one line on a package card


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _rule(message: str) -> str:
    return message.split(":", 1)[0]


def is_pinned(ref: dict[str, Any]) -> bool:
    """An ExternalRef is pinned by a digest, or by a commit-hash revision for git and Hugging Face (spec section 5.1)."""
    revision = ref.get("revision")
    return isinstance(ref.get("digest"), str) or (ref.get("provider") in {"git", "huggingface"} and isinstance(revision, str)
                                                   and bool(COMMIT_RE.match(revision)))


@contextmanager
def opened_package(path: str | Path) -> Iterator[tuple[Path, dict[str, Any] | None]]:
    """A package directory, or an .owp.zip extracted to a temporary directory; with an archive, also its integrity facts."""
    p = Path(path).expanduser()
    if not (p.is_file() and zipfile.is_zipfile(p)):
        yield p, None
        return
    ok, errors = verify_archive(p)
    if not ok:
        raise OWPError(f"{p} does not verify: " + "; ".join(errors))
    data = p.read_bytes()
    with zipfile.ZipFile(p) as zf, tempfile.TemporaryDirectory() as td:
        names = zf.namelist()
        for name in names:
            dest = (Path(td) / name).resolve()
            dest.relative_to(Path(td).resolve())  # verify_archive accepted the names; never write outside td
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(zf.read(name))
        integrity = {"digest": f"sha256:{sha256_bytes(data)}", "size": len(data), "files": len(names),
                     "signatureBundle": p.with_name(p.name + ".sigstore.json").is_file()}
        yield Path(td), integrity


def card_sections(text: str) -> list[str]:
    """Second-level headings of a card, as written."""
    return [m.group(1).strip() for m in re.finditer(r"^##[ \t]+(.+?)[ \t#]*$", text, re.MULTILINE)]


def package_report(path: str | Path) -> dict[str, Any]:
    """PackageReport for a package directory or .owp.zip archive (schemas/package-report.schema.json)."""
    with opened_package(path) as (root_path, integrity):
        report = _report(root_path)
        if integrity is not None:
            report["integrity"] = integrity
        return report


def _report(path: Path) -> dict[str, Any]:
    root, manifest = load_manifest(path)
    result = validate_package(root)
    kind = manifest.get("kind")
    md = _dict(manifest.get("metadata"))
    spec = _dict(manifest.get("spec"))
    identity = f"{md.get('namespace', '?')}/{md.get('name', '?')}@{md.get('version', '?')}"
    kinds, docs = local_assets(root, spec)

    by_kind: dict[str, int] = {}
    for k in kinds.values():
        by_kind[k] = by_kind.get(k, 0) + 1
    for a in _list(spec.get("assets")):
        if isinstance(a, dict) and isinstance(a.get("ref"), dict) and isinstance(a.get("kind"), str):
            by_kind[a["kind"]] = by_kind.get(a["kind"], 0) + 1

    report: dict[str, Any] = {
        "kind": "PackageReport",
        "identity": identity,
        "packageKind": kind,
        "validator": {"implementation": "ontle-python", "version": __version__},
        "valid": result.valid,
        "errors": result.errors,
        "warnings": result.warnings,
        "warningIds": sorted({_rule(w) for w in result.warnings}),
        "metadata": {k: md[k] for k in ("title", "description", "license") if isinstance(md.get(k), str)},
        "domains": [d for d in _list(spec.get("domains")) if isinstance(d, str)],
        "assets": {"total": sum(by_kind.values()), "byKind": dict(sorted(by_kind.items()))},
    }

    conformance = _dict(spec.get("conformance"))
    if kind == "WorldPackage":
        ews_fields, _ = compiler_fields(root, kinds, docs)
        report["profile"] = {"declared": conformance.get("profile", DEFAULT_WORLD_PROFILE),
                             "satisfied": satisfied_world_profile(spec, set(kinds.values()) | _ref_asset_kinds(spec), kinds, docs,
                                                                  ews_fields, identity)}
        fields = {f for listed in ews_fields.values() for f in listed or []}
        bound = set()
        for rel, listed in ews_fields.items():
            bindings = _dict(_dict(_dict(docs.get(rel)).get("spec")).get("bindings"))
            bound |= {f for f in listed or [] if f in bindings}
        report["state"] = {"stateCompilers": len(ews_fields), "fields": len(fields), "boundFields": len(bound)}
        binding_rel = _dict(spec.get("world")).get("semanticBinding")
        if isinstance(binding_rel, str):
            semantic = set(_dict(_dict(_dict(docs.get(binding_rel)).get("spec")).get("fields")))
            report["semanticCoverage"] = {"boundFields": len(semantic & fields), "fields": len(fields)}
    elif kind == "OntologyPackage":
        report["profile"] = {"declared": conformance.get("profile"),
                             "satisfied": ontology_module.satisfied_ontology_profile(root, spec)}
        report["ontology"] = {"terms": len(ontology_module.terms(root, manifest)[1])}

    refs = [r["ref"] for r in external_refs(manifest)]
    standards: set[str] = set()
    licensed = bound_bindings = 0
    for rel, k in sorted(kinds.items()):
        aspec = _dict(_dict(docs.get(rel)).get("spec"))
        if k in {"KnowledgeAsset", "Dataset"}:
            content_ref = _dict(aspec.get("content")).get("ref")
            if isinstance(content_ref, dict) and content_ref.get("status", "bound") == "bound":
                refs.append(content_ref)
        for binding in _dict(aspec.get("standardBindings")).values():
            if not isinstance(binding, dict):
                continue
            if isinstance(binding.get("standard"), str):
                standards.add(binding["standard"])
            ref = binding.get("ref")
            if isinstance(ref, dict) and ref.get("status", "bound") == "bound":
                refs.append(ref)
                bound_bindings += 1
                licensed += isinstance(binding.get("license"), str)
    report["externalRefs"] = {"total": len(refs), "pinned": sum(is_pinned(r) for r in refs)}
    report["standardBindings"] = {"standards": sorted(standards), "boundRefs": bound_bindings, "licensedRefs": licensed}

    evidence = [_dict(_dict(docs.get(rel)).get("spec")) for rel, k in sorted(kinds.items()) if k == "CompatibilityEvidence"]
    report["evidence"] = {
        "included": len(evidence),
        "subjects": sorted({e["subject"] for e in evidence if isinstance(e.get("subject"), str)}),
        "statuses": sorted({_dict(e.get("result")).get("status") for e in evidence if isinstance(_dict(e.get("result")).get("status"), str)}),
    }

    hints: list[str] = []
    description = md.get("description")
    if not isinstance(description, str) or not description.strip():
        hints.append("metadata.description is missing: catalogs show it as the package's one-line summary")
    elif len(description) > DESCRIPTION_LIMIT:
        hints.append(f"metadata.description has {len(description)} characters; catalogs show about {DESCRIPTION_LIMIT}")
    if not isinstance(md.get("license"), str):
        hints.append("metadata.license is missing")
    card_rel = _dict(spec.get(CARD_SPEC_KEY.get(kind, ""))).get("description")
    card_rel = card_rel if isinstance(card_rel, str) and card_rel.endswith(".md") else DEFAULT_CARDS.get(kind)
    if card_rel and ontology_module.inside_package(root, card_rel) and (root / card_rel).is_file():
        present = card_sections((root / card_rel).read_text(encoding="utf-8"))
        lowered = {s.lower() for s in present}
        missing = [s for s in CARD_SECTIONS if s.lower() not in lowered]
        report["card"] = {"path": card_rel, "sections": present, "missingRecommended": missing}
        if missing:
            hints.append(f"{card_rel} has no section {', '.join(missing)} (recommended card sections: {', '.join(CARD_SECTIONS)})")
    elif card_rel:
        hints.append(f"no card {card_rel}")
    unpinned = report["externalRefs"]["total"] - report["externalRefs"]["pinned"]
    if unpinned:
        hints.append(f"{unpinned} external {'reference is' if unpinned == 1 else 'references are'} not pinned (ontle lock pins https references)")
    report["hints"] = hints
    return report


def pack_size_hint(size: int, limit: int) -> str | None:
    """A note for `ontle pack` when an archive is large; the limit is a registry policy, not a spec rule."""
    if size <= limit:
        return None
    return (f"archive is {size / 1_000_000:.1f} MB (over {limit / 1_000_000:.0f} MB): registries may refuse large archives; "
            "keep large data outside the package as an ExternalRef (spec section 5.1)")

