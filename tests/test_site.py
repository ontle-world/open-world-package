"""The package catalog on the project site (scripts/site_catalog.py, registry step P0)."""
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HAS_MARKDOWN = importlib.util.find_spec("markdown") is not None


@unittest.skipUnless(HAS_MARKDOWN, "markdown not installed (the site build needs it)")
class CatalogTests(unittest.TestCase):
    def test_catalog_pages_index_and_resolution(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        try:
            from site_catalog import build_catalog
        finally:
            sys.path.pop(0)
        from ontle.resolve import validate_resolved
        packages = [ROOT / "examples" / "ontology" / "quality-ontology", ROOT / "examples" / "business" / "manufacturing-quality-world"]
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            built = build_catalog(out, lambda title, body: f"<title>{title}</title>{body}", packages)
            self.assertEqual([b["identity"] for b in built],
                             ["openworld-examples/quality-ontology@0.1.0", "openworld-examples/manufacturing-quality-world@0.1.0"])
            index = json.loads((out / "catalog" / "index.json").read_text(encoding="utf-8"))
            self.assertEqual(len(index["packages"]), 2)
            self.assertIn("terms", index)
            world = out / "catalog" / "openworld-examples" / "manufacturing-quality-world" / "0.1.0"
            page = (world / "index.html").read_text(encoding="utf-8")
            self.assertIn("action-ready", page)
            self.assertIn('href="../../../openworld-examples/quality-ontology/0.1.0/"', page)  # its dependency, in the catalog
            self.assertIn("https://github.com/ontle-world/open-world-package/tree/main/examples/business/manufacturing-quality-world", page)
            self.assertEqual(json.loads((world / "report.json").read_text(encoding="utf-8"))["kind"], "PackageReport")
            self.assertIn("openworld-examples/manufacturing-quality-world@0.1.0", (out / "catalog" / "index.html").read_text(encoding="utf-8"))
            result, _ = validate_resolved(str(packages[1]), [f"index:{out / 'catalog' / 'index.json'}"])
            self.assertTrue(result.valid, result.errors)


if __name__ == "__main__":
    unittest.main()
