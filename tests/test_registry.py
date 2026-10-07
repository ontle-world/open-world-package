"""Community packages (registry/packages.yaml, scripts/registry.py): what a listed package must satisfy, checked on
archives served over HTTP, and how the catalog shows one."""
import functools
import hashlib
import http.server
import importlib.util
import sys
import tempfile
import threading
import unittest
from pathlib import Path

from ontle.core import deterministic_pack
from ontle.scaffold import init_project

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import registry  # noqa: E402

HAS_MARKDOWN = importlib.util.find_spec("markdown") is not None


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


class RegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.dir = Path(cls._tmp.name)
        served = cls.dir / "served"
        served.mkdir()
        world = init_project("line-world", "acme", destination=cls.dir / "line-world")
        cls.world = deterministic_pack(world, served / "acme-line-world-0.1.0.owp.zip")
        # a World Model grounded in a World that is in no source: valid alone, invalid with its dependencies resolved
        model = init_project("orphan-model", "acme", "worldmodel", cls.dir / "orphan-model", world="nobody/missing-world@1.0.0")
        cls.orphan = deterministic_pack(model, served / "acme-orphan-model-0.1.0.owp.zip")
        cls.example = deterministic_pack(ROOT / "examples" / "ontology" / "sales-ontology", served / "sales.owp.zip")
        reserved = init_project("thing", "ontle", destination=cls.dir / "thing")
        cls.reserved = deterministic_pack(reserved, served / "ontle-thing-0.1.0.owp.zip")
        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(served))
        handler.log_message = lambda *a, **k: None
        cls.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}/"

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls._tmp.cleanup()

    def entry(self, archive: Path, identity: str, **extra) -> dict:
        return {"identity": identity, "archive": self.base + archive.name, "digest": digest(archive),
                "source": "https://github.com/acme/line-world", "submittedBy": "acme-maintainer", **extra}

    def check(self, *entries):
        with tempfile.TemporaryDirectory() as cache:
            archives, problems, notes = registry.check(list(entries), Path(cache), allow_any_url=True)
            return sorted(archives), problems, notes

    def test_a_good_package_passes_with_its_hints(self):
        passed, problems, notes = self.check(self.entry(self.world, "acme/line-world@0.1.0"))
        self.assertEqual((passed, problems), (["acme/line-world@0.1.0"], []))
        self.assertTrue(any("template text" in n for n in notes))  # hints are notes, not failures

    def test_what_a_listed_package_must_satisfy(self):
        wrong_digest = self.entry(self.world, "acme/line-world@0.1.0", digest="sha256:" + "0" * 64)
        cases = {
            "digest is": wrong_digest,
            "is reserved": self.entry(self.reserved, "ontle/thing@0.1.0"),
            "the identity of an example": self.entry(self.example, "openworld-examples/sales-ontology@0.1.0"),
            "the archive is acme/line-world@0.1.0": self.entry(self.world, "acme/other-world@0.1.0"),
            "invalid: resolve.unresolved": self.entry(self.orphan, "acme/orphan-model@0.1.0"),
        }
        for expected, entry in cases.items():
            with self.subTest(expected):
                passed, problems, _ = self.check(entry)
                self.assertEqual(passed, [])
                self.assertEqual(len(problems), 1, problems)
                self.assertIn(expected, problems[0])
        good = self.entry(self.world, "acme/line-world@0.1.0")
        passed, problems, _ = self.check(good, dict(good))
        self.assertEqual(passed, ["acme/line-world@0.1.0"])
        self.assertIn("listed twice", problems[0])

    def test_list_shape(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "packages.yaml"
            path.write_text("packages:\n- identity: Acme/World@1\n  archive: http://example.org/a.zip\n  digest: abc\n  colour: red\n",
                            encoding="utf-8")
            _, problems = registry.load_entries(path)
            text = "\n".join(problems)
            for expected in ("missing source", "missing submittedBy", "unknown field colour", "identity must be",
                             "archive must be an https URL", "digest must be"):
                self.assertIn(expected, text)
            path.write_text("packages: {}\n", encoding="utf-8")
            self.assertTrue(registry.load_entries(path)[1])

    def test_the_repository_list_is_well_formed(self):
        entries, problems = registry.load_entries()
        self.assertEqual(problems, [])
        self.assertIsInstance(entries, list)

    @unittest.skipUnless(HAS_MARKDOWN, "markdown not installed (the site build needs it)")
    def test_the_catalog_shows_a_listed_package(self):
        from site_catalog import build_catalog
        entry = self.entry(self.world, "acme/line-world@0.1.0")
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            build_catalog(out, lambda title, body: body, [ROOT / "examples" / "ontology" / "sales-ontology"], [(entry, self.world)])
            page = (out / "catalog" / "acme" / "line-world" / "0.1.0" / "index.html").read_text(encoding="utf-8")
            self.assertIn('class="badge ok">community', page)
            self.assertIn("https://github.com/acme/line-world", page)
            self.assertIn("acme-maintainer", page)
            published = out / "catalog" / "archives" / "acme-line-world-0.1.0.owp.zip"
            self.assertEqual(digest(published), entry["digest"])  # published as listed, not repacked
            self.assertIn("community", (out / "catalog" / "index.html").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
