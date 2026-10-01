"""Round trips (docs/PROFILE_PROMOTION.md, Interoperability gate).

1. pack -> unpack -> validate gives the same verdict, error ids, and warning ids.
2. Re-serializing every YAML file (load, then dump with a different layout) does not change the verdict:
   meaning depends on the JSON data model, not on YAML formatting.
"""
import shutil
import tempfile
import unittest
import zipfile
from collections import Counter
from pathlib import Path

import yaml

from ontle.core import deterministic_pack, validate_package
from ontle.ews import _TextTimestampLoader

ROOT = Path(__file__).resolve().parent.parent
EXPECTED = yaml.safe_load((ROOT / "conformance" / "expected.yaml").read_text(encoding="utf-8"))["cases"]


def packages():
    for manifest in sorted((ROOT / "examples").glob("**/owp.yaml")):
        yield manifest.parent
    for case, exp in sorted(EXPECTED.items()):
        if exp["valid"]:
            yield ROOT / "conformance" / "cases" / case


def outcome(path: Path):
    result = validate_package(path)
    return result.valid, Counter(e.split(":", 1)[0] for e in result.errors), Counter(w.split(":", 1)[0] for w in result.warnings)


class _FlowDumper(yaml.SafeDumper):
    """Dumps in flow style with sorted keys, so the layout differs from the source files."""


class RoundTripTests(unittest.TestCase):
    def test_pack_unpack_keeps_verdict(self):
        for pkg in packages():
            with self.subTest(package=str(pkg.relative_to(ROOT))), tempfile.TemporaryDirectory() as td:
                archive = deterministic_pack(pkg, Path(td) / "p.owp.zip")
                out = Path(td) / "unpacked"
                with zipfile.ZipFile(archive) as zf:
                    zf.extractall(out)
                self.assertEqual(outcome(out), outcome(pkg))

    def test_reserialized_yaml_keeps_verdict(self):
        for pkg in packages():
            with self.subTest(package=str(pkg.relative_to(ROOT))), tempfile.TemporaryDirectory() as td:
                copy = Path(td) / "pkg"
                shutil.copytree(pkg, copy)
                for f in list(copy.rglob("*.yaml")) + list(copy.rglob("*.yml")):
                    # Timestamps stay text (spec section 12); everything else follows YAML 1.2 core types.
                    doc = yaml.load(f.read_text(encoding="utf-8"), Loader=_TextTimestampLoader)
                    f.write_text(yaml.dump(doc, Dumper=_FlowDumper, default_flow_style=True, sort_keys=True,
                                           allow_unicode=True, width=1000), encoding="utf-8")
                self.assertEqual(outcome(copy), outcome(pkg))


if __name__ == "__main__":
    unittest.main()
