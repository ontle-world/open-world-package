#!/usr/bin/env python3
"""Write or check RELEASE_MANIFEST.json: the path, SHA-256, and size of every file in the release (the files git tracks).

    python scripts/release_manifest.py            # rewrite it from the working tree
    python scripts/release_manifest.py --check    # exit 1 unless it matches the tree and the package version
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "RELEASE_MANIFEST.json"
sys.path.insert(0, str(ROOT / "src"))

from ontle import __version__  # noqa: E402

RELEASE = "public-alpha-3"


def compute() -> dict:
    paths = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-z"], check=True, capture_output=True).stdout.decode().split("\0")
    files = []
    for rel in sorted(p for p in paths if p and p != OUT.name):
        data = (ROOT / rel).read_bytes()
        files.append({"path": rel, "sha256": hashlib.sha256(data).hexdigest(), "size": len(data)})
    return {"manifest": "ontle-public-release-manifest/v1", "release": RELEASE, "version": __version__, "cli": "ontle",
            "distribution": "ontle", "file_count_excluding_manifest": len(files), "files": files}


def render(data: dict) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def main() -> int:
    text = render(compute())
    if "--check" in sys.argv:
        if not OUT.exists() or OUT.read_text(encoding="utf-8") != text:
            print("RELEASE_MANIFEST.json does not match the tree: run python scripts/release_manifest.py", file=sys.stderr)
            return 1
        return 0
    OUT.write_text(text, encoding="utf-8")
    print(f"wrote {OUT.name}: {len(json.loads(text)['files'])} files, version {__version__}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
