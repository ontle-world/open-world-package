import math
import unittest
from pathlib import Path

import yaml

from ontle.yamlio import CoreLoader, FastCoreLoader

ROOT = Path(__file__).resolve().parent.parent


def load(text, loader):
    try:
        return "ok", yaml.load(text, Loader=loader)
    except yaml.YAMLError as exc:
        return "error", type(exc).__name__


def same(a, b):
    if isinstance(a, float) and isinstance(b, float) and math.isnan(a) and math.isnan(b):
        return True
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(same(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(same(x, y) for x, y in zip(a, b))
    return type(a) is type(b) and a == b


class FastLoaderMatchesPurePython(unittest.TestCase):
    @unittest.skipUnless(yaml.__with_libyaml__, "PyYAML is built without libyaml")
    def test_repository_yaml(self):
        files = [p for d in ("conformance", "examples", "demos", "starters", "src/ontle/templates")
                 for p in sorted((ROOT / d).rglob("*.y*ml")) if "node_modules" not in p.parts]
        self.assertGreater(len(files), 500)
        for path in files:
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=str(path.relative_to(ROOT))):
                slow, fast = load(text, CoreLoader), load(text, FastCoreLoader)
                self.assertEqual(slow[0], fast[0])
                self.assertTrue(same(slow[1], fast[1]))

    def test_core_schema_scalars(self):
        text = "a: yes\nb: 0o17\nc: 0x1f\nd: .inf\ne: 1:20\nf: 2026-09-01\ng: ~\n'<<': x\n"
        want = {"a": "yes", "b": 15, "c": 31, "d": math.inf, "e": "1:20", "f": "2026-09-01", "g": None, "<<": "x"}
        for loader in (CoreLoader, FastCoreLoader):
            self.assertEqual(yaml.load(text, Loader=loader), want)
            for bad in ("a: 1\na: 2\n", "1: x\n"):
                with self.assertRaises(yaml.constructor.ConstructorError):
                    yaml.load(bad, Loader=loader)


if __name__ == "__main__":
    unittest.main()
