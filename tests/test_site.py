"""The package catalog on the project site (scripts/site_catalog.py, registry step P0)."""
import functools
import http.server
import importlib.util
import json
import shutil
import subprocess
import sys
import threading
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


BUNDLE = ROOT / "implementations" / "typescript" / "dist-browser" / "owp-validator.js"


@unittest.skipUnless(HAS_MARKDOWN and BUNDLE.is_file() and shutil.which("node"), "needs markdown, node, and the browser bundle (npm run bundle)")
class PlaygroundTests(unittest.TestCase):
    def test_browser_bundle_resolves_dependencies_through_the_catalog_index(self):
        """What the Playground page does: a World Model whose World and ontology come from the served catalog."""
        sys.path.insert(0, str(ROOT / "scripts"))
        try:
            from site_catalog import build_catalog
            from site_playground import build_playground
        finally:
            sys.path.pop(0)
        packages = [ROOT / "examples" / "ontology" / "quality-ontology", ROOT / "examples" / "business" / "manufacturing-quality-world"]
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            build_catalog(out, lambda title, body: body, packages)
            self.assertTrue(build_playground(out, lambda title, body: body))
            handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(out))
            handler.log_message = lambda *a, **k: None
            httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
            threading.Thread(target=httpd.serve_forever, daemon=True).start()
            try:
                model = ROOT / "examples" / "business" / "quality-transition-world-model"
                script = f"""
import {{ readFileSync, readdirSync, statSync }} from "node:fs";
import {{ join }} from "node:path";
const {{ check }} = await import({json.dumps((out / "playground" / "owp-validator.js").as_uri())});
const files = {{}};
const walk = (d, rel) => {{ for (const n of readdirSync(join(d, rel))) {{ const r = rel ? rel + "/" + n : n;
  if (statSync(join(d, r)).isDirectory()) walk(d, r); else files[r] = new Uint8Array(readFileSync(join(d, r))); }} }};
walk({json.dumps(str(model))}, "");
const r = await check({{ files }}, {{ indexUrl: "http://127.0.0.1:{httpd.server_address[1]}/catalog/index.json" }});
console.log(JSON.stringify({{ valid: r.valid, resolved: r.resolved, unresolved: r.unresolved, errors: r.errors, kind: r.report.kind }}));
"""
                run = subprocess.run(["node", "--input-type=module", "-e", script], capture_output=True, text=True, timeout=120)
            finally:
                httpd.shutdown()
            self.assertEqual(run.returncode, 0, run.stderr)
            result = json.loads(run.stdout)
            self.assertEqual(result["errors"], [])
            self.assertTrue(result["valid"])
            self.assertEqual(sorted(result["resolved"]), ["openworld-examples/manufacturing-quality-world@0.1.0", "openworld-examples/quality-ontology@0.1.0"])
            self.assertEqual(result["kind"], "PackageReport")


if __name__ == "__main__":
    unittest.main()
