#!/usr/bin/env python3
"""Do the tests catch bugs? Put one small bug at a time into the Python reference and run the tests; each bug the tests
miss ("survived") points at a gap in them. The source is restored after every run.

    python scripts/mutation_check.py            # all mutants
    python scripts/mutation_check.py ews        # mutants whose name contains "ews"
    MUTATION_TESTS=tests.test_scale python scripts/mutation_check.py ews   # how much one test module catches alone

Each mutant is (name, file, exact text, replacement). A mutant whose text is no longer in the file is reported, so the
list is kept current with the code.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "ontle"
# the whole suite (conformance verdicts, exact reference ids, scale, tools), or the modules in $MUTATION_TESTS
TESTS = os.environ.get("MUTATION_TESTS", "").split() or ["discover", "-s", "tests"]

MUTANTS = [
    # EWS compilation (spec 12)
    ("ews: a candidate after asOf counts", "ews.py", 'o["observedAt"] <= as_of and', 'True and'),
    ("ews: the window includes its start", "ews.py", 'o["observedAt"] > since)', 'o["observedAt"] >= since)'),
    ("ews: estimates are candidates", "ews.py", '("estimatedBy" in o) == estimates and', 'True and'),
    ("ews: where is ignored", "ews.py", 'and _passes(o, where)),', '),'),
    ("ews: where needs one condition, not all", "ews.py", "return w is None or all(key in o", "return w is None or any(key in o"),
    ("ews: a missing where key passes", "ews.py", 'key in o["values"] and all(', '(key not in o["values"]) or all('),
    ("ews: count is off by one", "ews.py", 'return "state", len(values), ids', 'return "state", len(values) + 1, ids'),
    ("ews: mean divides by one more", "ews.py", 'total / len(values), ids', 'total / (len(values) + 1), ids'),
    ("ews: max is min", "ews.py", '(min(values) if function == "min" else max(values))', '(min(values))'),
    ("ews: latest picks the oldest", "ews.py", 'newest = cands[-1]["observedAt"]', 'newest = cands[0]["observedAt"]'),
    ("ews: a tie is never unresolved", "ews.py", 'if len(distinct) == 1 else ("unresolved", distinct, ids)', 'if True else None'),
    ("ews: provenance drops the last id", "ews.py", 'ids = sorted(o["id"] for o in tied)', 'ids = sorted(o["id"] for o in tied)[:-1] or sorted(o["id"] for o in tied)'),
    ("ews: classify ignores rule order", "ews.py", 'for rule in criterion.get("rules") or []:', 'for rule in reversed(criterion.get("rules") or []):'),
    ("ews: classify has no otherwise", "ews.py", 'return criterion.get("otherwise")', 'return None'),
    # semantic binding checks (spec 14)
    ("binding: parent classes do not count", "binding.py", "todo += sorted(parents.get(c, ()))", "todo += []"),
    ("binding: path-domain never fires", "binding.py", "if owners and not owners & _ancestors(current, model[\"parents\"]):", "if False:"),
    ("binding: value-range never fires", "binding.py", 'outside = sorted(str(k) for k in values["map"] if str(k) not in enum)', "outside = []"),
    # report
    ("report: pinned counts every reference", "report.py", '"pinned": sum(is_pinned(r) for r in refs)}', '"pinned": len(refs)}'),
    ("report: withBinding counts every field", "report.py", "bound |= {f for f in listed or [] if f in bindings}", "bound |= set(listed or [])"),
    ("report: no template hint", "report.py", "elif TEMPLATE_DESCRIPTION.match(description):", "elif False:"),
    ("report: card sections are not checked", "report.py", "missing = [s for s in CARD_SECTIONS if s.lower() not in lowered]", "missing = []"),
    # World View composition (Appendix C)
    ("views: composed include drops parents", "experimental.py", 'include += [x for x in _names(pp.get("include")) if x not in include]', "pass"),
    ("views: composed conflict never found", "experimental.py", "if not json_equal(v, first_v)), None)", "if False), None)"),
    ("views: specializes target not checked", "experimental.py", 'if local_kinds.get(base) != "WorldViewProfile":', "if False:"),
    # validation core
    ("core: viewable does not need a default view", "core.py", 'errors.append("profile.viewable: requires spec.world.defaultView")', "pass"),
    ("core: evidence version never compared", "core.py", "if versions is not None and version not in", "if False and version not in"),
    ("resolve: lock ignores a null status", "distribution.py", 'return isinstance(ref, dict) and ref.get("status") in (None, "bound")', 'return isinstance(ref, dict) and ref.get("status", "bound") == "bound"'),
    ("resolve: archive hash not checked", "core.py", 'if sha256_bytes(data) != entry["sha256"]:', "if False:"),
    ("ontology: subclass parents dropped", "ontology.py", 'model["parents"].setdefault(cls, set()).update(p for p in (iri(x) for x in parents) if p)', 'model["parents"].setdefault(cls, set())'),
    ("extraction: no multi-latest warning", "extraction.py", 'warnings.append(f"compiler.multi-latest', 'print(f"compiler.multi-latest'),
]


def run_tests() -> bool:
    return subprocess.run([sys.executable, "-m", "unittest", *TESTS], cwd=ROOT, capture_output=True).returncode == 0


def main() -> int:
    only = sys.argv[1] if len(sys.argv) > 1 else ""
    assert run_tests(), "the tests fail without any mutant"
    killed, survived, stale = [], [], []
    for name, file, old, new in MUTANTS:
        if only not in name:
            continue
        path = SRC / file
        original = path.read_text(encoding="utf-8")
        if original.count(old) != 1:
            stale.append(name)
            continue
        try:
            path.write_text(original.replace(old, new), encoding="utf-8")
            (survived if run_tests() else killed).append(name)
        finally:
            path.write_text(original, encoding="utf-8")
        print(("killed   " if name in killed else "SURVIVED ") + name, flush=True)
    for name in stale:
        print(f"STALE    {name}: its text is not in the source once")
    print(f"mutants: {len(killed)} killed, {len(survived)} survived, {len(stale)} stale")
    return 1 if survived or stale else 0


if __name__ == "__main__":
    raise SystemExit(main())
