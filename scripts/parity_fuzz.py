#!/usr/bin/env python3
"""Mutation test of implementation parity: the Python reference and the TypeScript implementation must agree on mutants.

Each mutant is a conformance fixture with one YAML value changed: a wrong type, an odd string, a removed or renamed
key, a raw YAML token such as a tag. Both implementations validate it (or resolve it, compile or check its EWS), and
they must give the same verdict, the same error and warning ids, and an equal EWS. Neither may crash. Seeds are fixed,
so a failure reproduces; --keep leaves the mutants on disk.

    npm --prefix implementations/typescript run build
    python scripts/parity_fuzz.py                       # seeds 1-3, 3 mutants per fixture
    python scripts/parity_fuzz.py --seeds 7 --per-case 20 --keep /tmp/mutants
"""
from __future__ import annotations

import argparse
import collections
import copy
import json
import random
import re
import shutil
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from ontle.core import OWPError, validate_package  # noqa: E402
from ontle.ews import check_ews, compile_ews, json_equal, load_document  # noqa: E402
from ontle.resolve import validate_resolved  # noqa: E402
from ontle.yamlio import dump_yaml, load_yaml  # noqa: E402

SUITE = ROOT / "conformance"
TS_EVAL = ROOT / "implementations" / "typescript" / "scripts" / "parity-eval.mjs"
ID = re.compile(r"(?:^|; )([a-z][a-z0-9-]*(?:\.[a-z0-9-]+)+):")

RAW = ["1e3", "1.0", "!foo bar", "!!binary aGVsbG8=", "2024-01-01", "yes", "0o17", "0x1F", ".inf", ".nan", "-0",
       "9007199254740993", "!!str 12", "!!float 3", "!!int 7", "1_000", "+5", "0.", "!!set {a, b}", "!!timestamp 2024-01-01",
       "!!null ''", "!!bool true", "'1'", "!!omap [a: 1]", "1:20", "0b11", "Off", "~"]
VALUES = [None, [], {}, 0, -1, 1.5, True, False, "", "x" * 3000, "ünï©ødé 한글", "toString", "__proto__", "constructor",
          "hasOwnProperty", " lead", "trail ", "a:b", "../x", "/abs", 2 ** 60, "valueOf", "a#b", "a@1.0.0", "x\ny",
          [None], [1, 2], {"toString": 1}, ["toString"], 10 ** 30, 0.5, "1.0.0", "2026-01-01T00:00:00Z",
          "2026-01-01T00:00:00+00:00", "P1D", "constructor#x", "length", "0.1.1٣", "a﻿b", "0000-01-01T00:00:10Z"]
KEYS = ["toString", "__proto__", "constructor", "zzUnknown", "x-ext", "valueOf", "hasOwnProperty", "length", ""]


def _paths(node, pre=()):
    yield pre, node
    if isinstance(node, dict):
        for k, v in node.items():
            yield from _paths(v, pre + (k,))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _paths(v, pre + (i,))


def _set(doc, path, value):
    if not path:
        return value
    cur = doc
    for k in path[:-1]:
        cur = cur[k]
    cur[path[-1]] = value
    return doc


def _mutate(doc, rng: random.Random):
    """(mutated document, raw YAML tokens to splice in, description)."""
    doc = copy.deepcopy(doc)
    path, node = rng.choice(list(_paths(doc)))
    op, raws = rng.random(), {}
    if op < 0.35:
        v = copy.deepcopy(rng.choice(VALUES))
        return _set(doc, path, v), raws, f"set {path} = {str(v)[:40]!r}"
    if op < 0.5:
        token = rng.choice(RAW)
        raws["RAWPLACEHOLDER0"] = token
        return _set(doc, path, "RAWPLACEHOLDER0"), raws, f"raw {path} = {token}"
    if op < 0.65 and path:
        parent = doc
        for k in path[:-1]:
            parent = parent[k]
        if isinstance(parent, dict):
            del parent[path[-1]]
            return doc, raws, f"del {path}"
        parent.append(copy.deepcopy(parent[path[-1]]))
        return doc, raws, f"dup {path}"
    if op < 0.78 and isinstance(node, dict):
        k, v = rng.choice(KEYS), copy.deepcopy(rng.choice(VALUES[:12]))
        node[k] = v
        return doc, raws, f"add {path}.{k} = {str(v)[:30]!r}"
    if op < 0.85 and isinstance(node, dict) and node:
        k, nk = rng.choice(list(node)), rng.choice(KEYS[:7])
        node[nk] = node.pop(k)
        return doc, raws, f"rename {path}.{k} -> {nk}"
    if op < 0.92:
        if isinstance(node, list) and node:
            return _set(doc, path, node[0]), raws, f"unlist {path}"
        return _set(doc, path, [node]), raws, f"wrap {path}"
    if isinstance(node, str):
        v = rng.choice([node + "x", node.upper(), node[:-1], node + " ", node.replace(".", "-"), node + "#frag", "./" + node])
        return _set(doc, path, v), raws, f"str {path} = {v[:40]!r}"
    v = copy.deepcopy(rng.choice(VALUES))
    return _set(doc, path, v), raws, f"set {path} = {str(v)[:40]!r}"


def generate(out: Path, seed: int, per_case: int) -> list[dict]:
    expected = load_yaml((SUITE / "expected.yaml").read_text(encoding="utf-8"))
    rng = random.Random(seed)
    targets = [("cases", c, SUITE / "cases" / c, {}) for c in expected["cases"]]
    targets += [("resolution", c, SUITE / "resolution" / c, {}) for c in expected["resolutionCases"]]
    targets += [("ews", c, SUITE / "ews" / c, {"compiler": e["compiler"], "asOf": str(e["asOf"])}) for c, e in expected["ewsCases"].items()]
    targets += [("ews-check", c, SUITE / "ews-check" / c, {}) for c in expected["ewsCheckCases"]]
    manifest = []
    for section, case, src, meta in targets:
        files = []
        for f in sorted(src.rglob("*")):
            if f.is_file() and f.suffix in (".yaml", ".yml") and "expected-ews" not in f.name:
                try:
                    d = load_yaml(f.read_text(encoding="utf-8"))
                except Exception:
                    continue
                if isinstance(d, (dict, list)):
                    files.append((f.relative_to(src), d))
        for n in range(per_case if files else 0):
            rel, d = rng.choice(files)
            doc, raws, desc = _mutate(d, rng)
            try:
                text = dump_yaml(doc)
            except Exception:
                continue
            for placeholder, token in raws.items():
                text = text.replace(placeholder, token)
            mid = f"s{seed}__{section}__{case}__{n}"
            shutil.copytree(src, out / mid, symlinks=True)
            (out / mid / rel).write_text(text, encoding="utf-8")
            manifest.append({"id": mid, "section": section, "case": case, "file": str(rel), "desc": desc, **meta})
    return manifest


def _ids(messages: list[str]) -> list[str]:
    return sorted({m.split(":", 1)[0] for m in messages})


def python_eval(out: Path, manifest: list[dict]) -> dict:
    results = {}
    for m in manifest:
        base, section = out / m["id"], m["section"]
        try:
            if section == "cases":
                r = validate_package(base)
                res = {"valid": r.valid, "errors": _ids(r.errors), "warnings": _ids(r.warnings)}
            elif section == "resolution":
                r, _ = validate_resolved(base / "root", [str(base / "packages")])
                res = {"valid": r.valid, "errors": _ids(r.errors), "warnings": _ids(r.warnings)}
            elif section == "ews":
                try:
                    ews = compile_ews(base / "world", m["compiler"], load_document(base / "observations.yaml"), m["asOf"])
                    res = {"valid": True, "errors": [], "warnings": [], "ews": json.loads(json.dumps(ews, default=str))}
                except OWPError as exc:
                    res = {"valid": False, "errors": sorted(set(ID.findall(str(exc)))), "warnings": []}
            else:
                try:
                    doc = load_document(base / "ews.yaml")
                    errors = check_ews(base / "world", doc if isinstance(doc, dict) else {})
                    res = {"valid": not errors, "errors": _ids(errors), "warnings": []}
                except OWPError as exc:
                    res = {"valid": False, "errors": sorted(set(ID.findall(str(exc)))), "warnings": []}
        except Exception:
            res = {"crash": traceback.format_exc()[-500:]}
        results[m["id"]] = res
    return results


def _signature(m: dict, py: dict, ts: dict) -> str | None:
    py, ts = dict(py), dict(ts)
    py_ews, ts_ews = py.pop("ews", None), ts.pop("ews", None)
    ts["warnings"] = [w for w in ts.get("warnings", []) if ":" not in w]  # implementation-specific ids contain ':'
    if "crash" in py:
        return "python crash: " + py["crash"].strip().splitlines()[-1][:100]
    if "crash" in ts:
        return "typescript crash: " + ts["crash"].strip().splitlines()[0][:100]
    if py != ts:
        diff = lambda k: f"{k} python-only {sorted(set(py[k]) - set(ts[k]))} typescript-only {sorted(set(ts[k]) - set(py[k]))}"
        return f"{m['section']}: valid {py['valid']}/{ts['valid']}; {diff('errors')}; {diff('warnings')}"
    if py_ews is not None and not json_equal(py_ews, ts_ews):
        return f"{m['section']}: different EWS"
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seeds", type=int, default=3, help="run seeds 1..N")
    ap.add_argument("--per-case", type=int, default=3)
    ap.add_argument("--dist", default=str(ROOT / "implementations" / "typescript" / "dist"))
    ap.add_argument("--keep", help="directory to leave the mutants in")
    args = ap.parse_args()
    work = Path(args.keep) if args.keep else Path(tempfile.mkdtemp(prefix="owp-parity-"))
    groups: dict[str, list[str]] = collections.defaultdict(list)
    total = 0
    try:
        for seed in range(1, args.seeds + 1):
            out = work / f"seed-{seed}"
            shutil.rmtree(out, ignore_errors=True)
            out.mkdir(parents=True)
            manifest = generate(out, seed, args.per_case)
            (out / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            py = python_eval(out, manifest)
            proc = subprocess.run(["node", str(TS_EVAL), str(out), str(Path(args.dist).resolve())], capture_output=True, text=True)
            if proc.returncode != 0:
                print(proc.stderr, file=sys.stderr)
                return 2
            ts = json.loads(proc.stdout)
            for m in manifest:
                sig = _signature(m, py[m["id"]], ts[m["id"]])
                if sig:
                    groups[sig].append(f"{m['id']} ({m['file']}: {m['desc']})")
            total += len(manifest)
    finally:
        if not args.keep:
            shutil.rmtree(work, ignore_errors=True)
    bad = sum(len(v) for v in groups.values())
    print(f"parity: {total - bad}/{total} mutants agree")
    for sig, items in sorted(groups.items(), key=lambda x: -len(x[1])):
        print(f"  {len(items)} × {sig}")
        for item in items[:2]:
            print(f"      {item}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
