"""Shared steps of the end-to-end demos (ROADMAP section 4).

World -> View -> State Compiler -> EWS -> Representation Adapter -> model stub -> CompatibilityEvidence

OWP standardizes the World, View, State Compiler, EWS, and evidence documents. The adapter and the model stub
are runtime code; each demo implements them in its run.py for illustration only.

Each run.py writes its outputs, or with --check compares them with the committed files and checks the
evidence against the committed subject archive (spec section 9.1).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from ontle.core import deterministic_pack
from ontle.distribution import check_detached_evidence
from ontle.ews import canonical, check_ews, compile_ews, ews_equal
from ontle.yamlio import dump_yaml, load_yaml

REPO = Path(__file__).resolve().parent.parent


def load(path: Path) -> Any:
    return load_yaml(path.read_text(encoding="utf-8"))


def compile_steps(world: Path, compiler: str, observations: dict[str, Any], steps: list[str]) -> list[dict[str, Any]]:
    """Compile one EWS per asOf; every EWS must satisfy the compiler's output contract (spec 12.1)."""
    out = []
    for as_of in steps:
        ews = compile_ews(world, compiler, observations, as_of)
        errors = check_ews(world, ews)
        if errors:
            raise SystemExit(f"EWS at {as_of} violates the output contract: {errors}")
        out.append(ews)
    return out


def observations_at(observations: dict[str, Any], kind: str, as_of: str) -> list[dict[str, Any]]:
    return [o for o in observations["spec"]["observations"] if o["type"] == kind and o["observedAt"] == as_of]


def sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def locked_files(archive: Path) -> Any:
    with zipfile.ZipFile(archive) as zf:
        return json.loads(zf.read("owp.lock.json"))["files"]


def finish(here: Path, subject_package: Path, archive_name: str, expected_ews: dict[str, Any],
           evidence: dict[str, Any], header: str) -> None:
    """Write (or with --check, compare) expected-ews.yaml, evidence.yaml, and the subject archive."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="compare with the committed files instead of writing")
    args = parser.parse_args()
    archive = here / archive_name
    if args.check:
        # The committed archive must still hold the World Model package as it is now. Compare the locked file
        # hashes, not the archive bytes, which depend on the zlib build.
        with tempfile.TemporaryDirectory() as tmp:
            fresh = locked_files(deterministic_pack(subject_package, Path(tmp) / archive_name))
        if fresh != locked_files(archive):
            raise SystemExit(f"{archive_name} is stale: the World Model package changed; rerun without --check")
    else:
        deterministic_pack(subject_package, archive)
    evidence["spec"]["subjectDigest"] = sha256_file(archive)
    problems = check_detached_evidence(evidence, archive)
    if problems:
        raise SystemExit(f"evidence does not bind to {archive_name}: {problems}")
    if args.check:
        if not ews_equal(load(here / "expected-ews.yaml"), expected_ews):
            raise SystemExit(f"expected-ews.yaml differs from the compiled EWS: {canonical(expected_ews)}")
        if load(here / "evidence.yaml") != evidence:
            raise SystemExit("evidence.yaml differs from the computed evidence")
        print(f"OK {here.name}: EWS and evidence match; evidence binds to {archive_name}")
        return
    (here / "expected-ews.yaml").write_text(dump_yaml(expected_ews, width=1000, default_flow_style=None), encoding="utf-8")
    (here / "evidence.yaml").write_text(header + dump_yaml(evidence, width=1000), encoding="utf-8")
    print(f"wrote {here.name}/expected-ews.yaml, evidence.yaml, {archive_name}")
