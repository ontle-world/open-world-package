#!/usr/bin/env python3
"""Write or check vocab/owp/value-sets.ttl: the value sets of vocab/value-sets.yaml as SKOS concept schemes.

Each value set is a skos:ConceptScheme at https://w3id.org/owp/vs/<set>, and each value a skos:Concept at
https://w3id.org/owp/vs/<set>#<value> with the value as its skos:notation. A work pattern points to its node family
in the workNodeFamilies scheme with skos:broadMatch. The YAML file stays the source; this file is generated.

    python scripts/build_value_sets.py           # rewrite it
    python scripts/build_value_sets.py --check   # exit 1 when it is out of date
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "vocab" / "value-sets.yaml"
OUT = ROOT / "vocab" / "owp" / "value-sets.ttl"
BASE = "https://w3id.org/owp/vs/"


def _lit(text: str) -> str:
    return json.dumps(text, ensure_ascii=False) + "@en"


def render() -> str:
    sets = yaml.safe_load(SOURCE.read_text(encoding="utf-8"))["valueSets"]
    lines = [
        "@prefix skos: <http://www.w3.org/2004/02/skos/core#> .",
        "@prefix dct: <http://purl.org/dc/terms/> .",
        "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .",
        "",
        "# Generated from vocab/value-sets.yaml by scripts/build_value_sets.py; do not edit by hand. CC BY 4.0.",
        "",
    ]
    for name in sorted(sets):
        entry = sets[name]
        scheme = f"<{BASE}{name}>"
        openness = ("Open: a value outside it is the warning value.unknown." if entry.get("open") is True
                    else "Closed: a value outside it is an error.")
        lines.append(f"{scheme} a skos:ConceptScheme ;")
        lines.append(f"  skos:prefLabel {_lit(name)} ;")
        comment = "Used by " + str(entry.get("usedBy")) + ". " + openness  # Python 3.11: no nested quotes in f-strings
        lines.append(f"  rdfs:comment {_lit(comment)} ;")
        lines.append("  dct:source <https://github.com/ontle-world/open-world-package/blob/main/vocab/value-sets.yaml> .")
        for value in sorted(entry["values"]):
            info = entry["values"][value] or {}
            parts = [f"<{BASE}{name}#{value}> a skos:Concept", f"skos:inScheme {scheme}", f"skos:topConceptOf {scheme}",
                     f"skos:notation {json.dumps(value)}", f"skos:prefLabel {_lit(info.get('label') or value)}"]
            if info.get("description"):
                parts.append(f"skos:definition {_lit(info['description'])}")
            if info.get("family"):
                parts.append(f"skos:broadMatch <{BASE}workNodeFamilies#{info['family']}>")
            lines.append(" ;\n  ".join(parts) + " .")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    text = render()
    if "--check" in sys.argv:
        if not OUT.exists() or OUT.read_text(encoding="utf-8") != text:
            print("vocab/owp/value-sets.ttl is out of date: run python scripts/build_value_sets.py", file=sys.stderr)
            return 1
        return 0
    OUT.write_text(text, encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
