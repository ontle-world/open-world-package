#!/usr/bin/env python3
"""Write or check conformance/reference-ids.json: every rule id the reference implementations report per case.

The suite (expected.yaml) lists the ids a conforming implementation MUST report and lets it report more. The two
reference implementations in this repository are held to more: both report exactly the ids in this file, so they
cannot drift apart unnoticed. The Python tests and the TypeScript conformance runner compare against it.

    python scripts/reference_ids.py          # rewrite the file from the Python implementation
    python scripts/reference_ids.py --check  # exit 1 when the Python implementation disagrees with the file
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from ontle.core import validate_package  # noqa: E402
from ontle.core import OWPError  # noqa: E402
from ontle.distribution import check_detached_evidence  # noqa: E402
from ontle.ews import check_ews, compile_ews, load_document  # noqa: E402
from ontle.resolve import validate_resolved  # noqa: E402

SUITE = ROOT / "conformance"
OUT = SUITE / "reference-ids.json"


def _ids(messages: list[str]) -> list[str]:
    return sorted({m.split(":", 1)[0] for m in messages})


def compute() -> dict:
    expected = yaml.safe_load((SUITE / "expected.yaml").read_text(encoding="utf-8"))
    out: dict = {"cases": {}, "resolutionCases": {}, "ewsCases": {}, "ewsCheckCases": {}, "evidenceCases": {}}
    for case_id in sorted(expected["cases"]):
        r = validate_package(SUITE / "cases" / case_id)
        out["cases"][case_id] = {"errors": _ids(r.errors), "warnings": _ids(r.warnings)}
    for case_id in sorted(expected["resolutionCases"]):
        case = SUITE / "resolution" / case_id
        r, _ = validate_resolved(case / "root", [str(case / "packages")])
        out["resolutionCases"][case_id] = {"errors": _ids(r.errors), "warnings": _ids(r.warnings)}
    for case_id, exp in sorted(expected["ewsCases"].items()):
        case = SUITE / "ews" / case_id
        try:
            compile_ews(case / "world", exp["compiler"], load_document(case / "observations.yaml"), str(exp["asOf"]))
            errors: list[str] = []
        except OWPError as exc:  # a refusal: every rule id in the message
            errors = re.findall(r"(?:^|; )([a-z][a-z0-9-]*(?:\.[a-z0-9-]+)+):", str(exc))
        out["ewsCases"][case_id] = {"errors": _ids(e + ":" for e in errors), "warnings": []}
    for case_id in sorted(expected["ewsCheckCases"]):
        case = SUITE / "ews-check" / case_id
        try:
            errors = check_ews(case / "world", load_document(case / "ews.yaml", rule="ews.kind"))
        except OWPError as exc:
            errors = [str(exc)]
        out["ewsCheckCases"][case_id] = {"errors": _ids(errors), "warnings": []}
    for case_id in sorted(expected.get("evidenceCases") or {}):
        case = SUITE / "evidence" / case_id
        errors = check_detached_evidence(yaml.safe_load((case / "evidence.yaml").read_text(encoding="utf-8")), case / "package.owp.zip")
        out["evidenceCases"][case_id] = {"errors": _ids(errors), "warnings": []}
    return out


def render(data: dict) -> str:
    return json.dumps(data, indent=1, sort_keys=True) + "\n"


def main() -> int:
    text = render(compute())
    if "--check" in sys.argv:
        if not OUT.exists() or OUT.read_text(encoding="utf-8") != text:
            print(f"{OUT.relative_to(ROOT)} is out of date: run python scripts/reference_ids.py", file=sys.stderr)
            return 1
        return 0
    OUT.write_text(text, encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
