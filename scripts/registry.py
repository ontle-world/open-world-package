#!/usr/bin/env python3
"""Community packages in the catalog: registry/packages.yaml lists them, and this script checks the list.

    python scripts/registry.py check [--file registry/packages.yaml] [--cache DIR]

Each entry names a package archive published elsewhere (a GitHub release asset, for example) by its identity, URL,
and digest. The check downloads every archive and requires that it matches its digest, verifies (owp.lock.json), has
the identity the entry names, is in a namespace that is not reserved, is listed once, declares a license, and
validates with its dependencies resolved from the examples and the other listed packages. Report hints (card
sections, a description) are printed but do not fail the check. registry/README.md describes how to submit one.

This is step ① of the registry plan: a reviewed list in this repository, no server. The catalog (site_catalog.py)
shows the listed packages next to the examples.
"""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from ontle.core import OWPError, verify_archive  # noqa: E402
from ontle.distribution import _download  # noqa: E402
from ontle.report import package_report  # noqa: E402
from ontle.resolve import validate_resolved  # noqa: E402
from ontle.yamlio import load_yaml  # noqa: E402

REGISTRY = ROOT / "registry" / "packages.yaml"
RESERVED_NAMESPACES = {"openworld", "openworld-examples", "conformance", "ontle", "owp", "scale"}
IDENTITY_RE = re.compile(r"^([a-z0-9][a-z0-9-]*)/([a-z0-9][a-z0-9-]*)@\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$")
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
FIELDS = {"identity", "archive", "digest", "source", "submittedBy", "description"}
REQUIRED = {"identity", "archive", "digest", "source", "submittedBy"}


def load_entries(path: Path = REGISTRY) -> tuple[list[dict[str, Any]], list[str]]:
    """The entries of the list, and what is wrong with its shape."""
    doc = load_yaml(path.read_text(encoding="utf-8")) or {}
    listed = doc.get("packages") if isinstance(doc, dict) else None
    if not isinstance(listed, list):
        return [], [f"{path.name}: needs `packages:`, a list (empty is fine)"]
    entries, problems = [], []
    for i, e in enumerate(listed):
        at = f"packages[{i}]"
        if not isinstance(e, dict):
            problems.append(f"{at}: must be a mapping")
            continue
        at = f"{at} ({e.get('identity', '?')})"
        problems += [f"{at}: missing {k}" for k in sorted(REQUIRED - set(e))]
        problems += [f"{at}: unknown field {k}" for k in sorted(set(e) - FIELDS)]
        if isinstance(e.get("identity"), str) and not IDENTITY_RE.match(e["identity"]):
            problems.append(f"{at}: identity must be <namespace>/<name>@<version> in lowercase")
        for key in ("archive", "source"):
            if key in e and not (isinstance(e[key], str) and e[key].startswith("https://")):
                problems.append(f"{at}: {key} must be an https URL")
        if "digest" in e and not (isinstance(e["digest"], str) and DIGEST_RE.match(e["digest"])):
            problems.append(f"{at}: digest must be sha256:<64 lowercase hex>")
        entries.append(e)
    return entries, problems


def fetch(entry: dict[str, Any], cache: Path) -> Path:
    """The entry's archive, downloaded into `cache` and checked against its digest."""
    digest = str(entry["digest"])
    target = cache / f"{digest.split(':', 1)[1]}.owp.zip"
    if not target.exists():
        data = _download(str(entry["archive"]))
        actual = "sha256:" + hashlib.sha256(data).hexdigest()
        if actual != digest:
            raise OWPError(f"the archive's digest is {actual}, not {digest}")
        target.write_bytes(data)
    return target


def example_identities() -> set[str]:
    out = set()
    for manifest in ROOT.glob("examples/*/*/owp.yaml"):
        md = (load_yaml(manifest.read_text(encoding="utf-8")) or {}).get("metadata") or {}
        out.add(f"{md.get('namespace')}/{md.get('name')}@{md.get('version')}")
    return out


def check(entries: list[dict[str, Any]], cache: Path, allow_any_url: bool = False) -> tuple[dict[str, Path], list[str], list[str]]:
    """(identity -> archive for the entries that pass, problems, notes). `allow_any_url` lets tests use http:// URLs."""
    problems: list[str] = []
    notes: list[str] = []
    archives: dict[str, Path] = {}
    seen = example_identities()
    for e in entries:
        identity = str(e.get("identity"))
        at = identity
        if identity in seen:
            problems.append(f"{at}: listed twice, or the identity of an example")
            continue
        seen.add(identity)
        if identity.split("/", 1)[0] in RESERVED_NAMESPACES:
            problems.append(f"{at}: the namespace {identity.split('/', 1)[0]!r} is reserved")
            continue
        if not allow_any_url and not str(e.get("archive", "")).startswith("https://"):
            continue  # reported by load_entries
        try:
            archive = fetch(e, cache)
        except (OWPError, OSError, ValueError) as exc:
            problems.append(f"{at}: cannot fetch the archive: {exc}")
            continue
        ok, errors = verify_archive(archive)
        if not ok:
            problems.append(f"{at}: the archive does not verify: {'; '.join(errors[:3])}")
            continue
        with zipfile.ZipFile(archive) as zf:
            md = (load_yaml(zf.read("owp.yaml")) or {}).get("metadata") or {}
        actual = f"{md.get('namespace')}/{md.get('name')}@{md.get('version')}"
        if actual != identity:
            problems.append(f"{at}: the archive is {actual}")
            continue
        if not isinstance(md.get("license"), str):
            problems.append(f"{at}: metadata.license is missing")
            continue
        archives[identity] = archive
    # validate each with its dependencies resolved from the examples and the other listed archives
    sources = [str(ROOT / "examples"), *[str(a) for a in archives.values()]]
    for identity, archive in list(archives.items()):
        with tempfile.TemporaryDirectory() as td, zipfile.ZipFile(archive) as zf:
            zf.extractall(td)
            result, _ = validate_resolved(td, sources)
        if not result.valid:
            problems.append(f"{identity}: invalid: {'; '.join(result.errors[:3])}")
            del archives[identity]
            continue
        notes += [f"{identity}: {h}" for h in package_report(archive)["hints"]]
    return archives, problems, notes


def main() -> int:
    ap = argparse.ArgumentParser(description="Check the community package list (registry/packages.yaml).")
    ap.add_argument("command", choices=["check"])
    ap.add_argument("--file", default=str(REGISTRY))
    ap.add_argument("--cache", help="directory for downloaded archives (default: a temporary one)")
    args = ap.parse_args()
    entries, problems = load_entries(Path(args.file))
    with tempfile.TemporaryDirectory() as td:
        cache = Path(args.cache) if args.cache else Path(td)
        cache.mkdir(parents=True, exist_ok=True)
        archives, more, notes = check(entries, cache) if not problems else ({}, [], [])
    problems += more
    for n in notes:
        print(f"NOTE: {n}")
    for p in problems:
        print(f"ERROR: {p}", file=sys.stderr)
    print(f"registry: {len(entries)} listed, {len(archives)} pass, {len(problems)} problem{'' if len(problems) == 1 else 's'}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
