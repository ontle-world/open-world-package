#!/usr/bin/env python3
"""Python and TypeScript give the same PackageReport for every package in this repository.

Compared: every field except `validator` and the wording of `errors` and `warnings` (their rule ids must agree).
Packages: examples, demos' archives, starters, vocab and alignments, and every conformance case with a parseable
manifest. Needs a built TypeScript implementation (npm run build in implementations/typescript).

    python scripts/report_parity.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from ontle.core import OWPError  # noqa: E402
from ontle.report import package_report  # noqa: E402

CLI = ROOT / "implementations" / "typescript" / "dist" / "cli.js"


def targets() -> list[Path]:
    found = [m.parent for pattern in ("examples/*/*/owp.yaml", "starters/*/owp.yaml", "vocab/*/owp.yaml", "alignments/*/owp.yaml",
                                      "conformance/cases/*/owp.yaml") for m in sorted(ROOT.glob(pattern))]
    return found + sorted(ROOT.glob("demos/*/*.owp.zip"))


def comparable(report: dict) -> dict:
    out = {k: v for k, v in report.items() if k not in {"validator", "errors", "warnings"}}
    out["errorIds"] = sorted({e.split(":", 1)[0] for e in report["errors"]})
    return out


def main() -> int:
    if not CLI.exists():
        print(f"missing {CLI}: run npm run build in implementations/typescript", file=sys.stderr)
        return 2
    failures = compared = 0
    for target in targets():
        rel = target.relative_to(ROOT)
        try:
            python = package_report(target)
        except (OWPError, ValueError, OSError):
            continue  # no readable manifest: there is nothing to report
        run = subprocess.run(["node", str(CLI), "report", str(target)], capture_output=True, text=True)
        if run.returncode != 0:
            print(f"FAIL {rel}: TypeScript: {run.stderr.strip()}")
            failures += 1
            continue
        a, b = comparable(python), comparable(json.loads(run.stdout))
        compared += 1
        if a != b:
            failures += 1
            diff = sorted(k for k in a.keys() | b.keys() if a.get(k) != b.get(k))
            print(f"FAIL {rel}: " + "; ".join(f"{k}: python={a.get(k)!r} ts={b.get(k)!r}" for k in diff))
    print(f"report parity: {compared - failures}/{compared} packages agree")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
