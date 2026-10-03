import functools
import hashlib
import http.server
import json
import os
import shutil
import subprocess
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path

import yaml

from ontle.core import OWPError, deterministic_pack, validate_package, verify_archive
from ontle.distribution import (build_index, catalog, check_detached_evidence, fetch_package, oci_push,
                                pin_https_refs, sign_archive, verify_signature)
from ontle.resolve import validate_resolved
from ontle.scaffold import init_project

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "examples"
ORAS = os.environ.get("ONTLE_ORAS") or shutil.which("oras")
COSIGN = os.environ.get("ONTLE_COSIGN") or shutil.which("cosign")


def sha(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


class Server:
    """A local HTTP server for one directory."""

    def __init__(self, directory: Path):
        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(directory))
        handler.log_message = lambda *a, **k: None
        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


def world_with_ref(td: Path, ref: dict) -> Path:
    p = init_project("demo", "test", "minimal", td / "demo")
    manifest = yaml.safe_load((p / "owp.yaml").read_text(encoding="utf-8"))
    manifest["spec"]["assets"].append({"kind": "Dataset", "ref": ref})
    (p / "owp.yaml").write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
    return p


class ExternalContentTests(unittest.TestCase):
    def setUp(self):
        self.td = Path(tempfile.mkdtemp())
        self.served = self.td / "served"
        (self.served / "set").mkdir(parents=True)
        self.blob = b"episode data\n"
        (self.served / "data.bin").write_bytes(self.blob)
        (self.served / "set" / "a.txt").write_bytes(b"a\n")
        (self.served / "set" / "b.txt").write_bytes(b"b\n")
        listing = {"files": [{"path": "a.txt", "sha256": hashlib.sha256(b"a\n").hexdigest(), "size": 2},
                             {"path": "b.txt", "sha256": hashlib.sha256(b"b\n").hexdigest(), "size": 2}]}
        (self.served / "set" / "files.json").write_text(json.dumps(listing))
        self.server = Server(self.served)

    def tearDown(self):
        self.server.close()
        shutil.rmtree(self.td)

    def test_lock_pins_and_fetch_verifies(self):
        p = world_with_ref(self.td, {"provider": "https", "uri": f"{self.server.url}/data.bin"})
        self.assertIn("ref.unpinned", " ".join(validate_package(p).warnings))
        pointer = f"/spec/assets/{len(yaml.safe_load((p / 'owp.yaml').read_text())['spec']['assets']) - 1}/ref"
        self.assertEqual(pin_https_refs(p), [pointer])
        self.assertNotIn("ref.unpinned", " ".join(validate_package(p).warnings))
        files = fetch_package(p, self.td / "fetched")
        self.assertEqual(files[0].read_bytes(), self.blob)
        (self.served / "data.bin").write_bytes(b"changed\n")
        with self.assertRaises(OWPError):
            fetch_package(p, self.td / "again")

    def test_fetch_file_list(self):
        listing = (self.served / "set" / "files.json").read_bytes()
        p = world_with_ref(self.td, {"provider": "https", "uri": f"{self.server.url}/set/files.json",
                                     "mediaType": "application/vnd.openworld.filelist+json", "digest": sha(listing)})
        files = fetch_package(p, self.td / "fetched")
        self.assertEqual(sorted(f.name for f in files), ["a.txt", "b.txt"])

    def test_lock_externals_and_vendoring(self):
        p = world_with_ref(self.td, {"provider": "https", "uri": f"{self.server.url}/data.bin", "digest": sha(self.blob)})
        archive = deterministic_pack(p, self.td / "plain.owp.zip")
        with zipfile.ZipFile(archive) as zf:
            lock = json.loads(zf.read("owp.lock.json"))
        self.assertEqual(lock["format"], "owp-lock/v1alpha2")
        pointer = f"/spec/assets/{len(yaml.safe_load((p / 'owp.yaml').read_text())['spec']['assets']) - 1}/ref"
        self.assertEqual(lock["externals"], [{"pointer": pointer, "provider": "https",
                                              "uri": f"{self.server.url}/data.bin", "digest": sha(self.blob)}])
        vendored = deterministic_pack(p, self.td / "vendored.owp.zip", vendor=True)
        self.assertTrue(verify_archive(vendored)[0])
        with zipfile.ZipFile(vendored) as zf:
            lock = json.loads(zf.read("owp.lock.json"))
            path = lock["externals"][0]["vendoredPath"]
            self.assertEqual(zf.read(path), self.blob)

    def test_tampered_externals_fail_verification(self):
        p = world_with_ref(self.td, {"provider": "https", "uri": f"{self.server.url}/data.bin", "digest": sha(self.blob)})
        archive = deterministic_pack(p, self.td / "a.owp.zip")
        tampered = self.td / "t.owp.zip"
        with zipfile.ZipFile(archive) as src, zipfile.ZipFile(tampered, "w") as dst:
            for name in src.namelist():
                data = src.read(name)
                if name == "owp.lock.json":
                    lock = json.loads(data)
                    lock["externals"][0]["digest"] = sha(b"other")
                    data = json.dumps(lock).encode()
                dst.writestr(name, data)
        ok, errors = verify_archive(tampered)
        self.assertFalse(ok)
        self.assertIn("lock externals do not match", " ".join(errors))


class IndexAndEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.td = Path(tempfile.mkdtemp())
        self.pub = self.td / "pub"
        self.pub.mkdir()
        self.world = deterministic_pack(EXAMPLES / "physical-ai" / "mobile-manipulation-world", self.pub / "world.owp.zip")
        self.model = deterministic_pack(EXAMPLES / "physical-ai" / "multimodal-action-world-model", self.pub / "model.owp.zip")
        (self.pub / "index.json").write_text(json.dumps(build_index([self.world, self.model], base=self.pub)))
        self.server = Server(self.pub)

    def tearDown(self):
        self.server.close()
        shutil.rmtree(self.td)

    def test_resolve_through_local_and_served_index(self):
        model = EXAMPLES / "physical-ai" / "multimodal-action-world-model"
        for source in (f"index:{self.pub / 'index.json'}", f"index:{self.server.url}/index.json"):
            with self.subTest(source=source):
                result, resolution = validate_resolved(model, [source])
                self.assertTrue(result.valid, result.errors)
                world = resolution.packages["openworld-examples/mobile-manipulation-world@0.1.0"]
                self.assertEqual(world.revision, sha(self.world.read_bytes()))

    def test_index_rejects_wrong_digest(self):
        index = json.loads((self.pub / "index.json").read_text())
        for entry in index["packages"]:
            if entry["identity"] == "openworld-examples/mobile-manipulation-world@0.1.0":
                entry["digest"] = sha(b"other")
        (self.pub / "index.json").write_text(json.dumps(index))
        result, _ = validate_resolved(EXAMPLES / "physical-ai" / "multimodal-action-world-model", [f"index:{self.pub / 'index.json'}"])
        self.assertFalse(result.valid)

    def test_detached_evidence(self):
        evidence = yaml.safe_load((EXAMPLES / "physical-ai" / "multimodal-action-world-model" / "eval" / "evidence-reference-sim.yaml").read_text())
        self.assertIn("evidence.detached-subject", " ".join(check_detached_evidence(evidence, self.model)))
        evidence["spec"]["subjectDigest"] = sha(self.model.read_bytes())
        self.assertEqual(check_detached_evidence(evidence, self.model), [])
        evidence["spec"]["scope"]["worldView"] = "openworld-examples/mobile-manipulation-world@0.1.0#views/other.yaml"
        self.assertIn("evidence.scope.world-view", " ".join(check_detached_evidence(evidence, self.model)))


class CatalogTests(unittest.TestCase):
    def test_catalog_formats(self):
        world = EXAMPLES / "business" / "manufacturing-quality-world"
        dcat = json.loads(catalog(world, "dcat"))
        self.assertEqual(dcat["dct:identifier"], "openworld-examples/manufacturing-quality-world@0.1.0")
        croissant = json.loads(catalog(world, "croissant"))
        self.assertEqual(croissant["@type"], "sc:Dataset")
        card = catalog(EXAMPLES / "physical-ai" / "multimodal-action-world-model", "hf-card")
        self.assertTrue(card.startswith("---\n"))
        self.assertIn("openworld-examples/mobile-manipulation-world@0.1.0", card)


@unittest.skipUnless(ORAS, "oras not installed (set ONTLE_ORAS)")
class OciTests(unittest.TestCase):
    def test_push_and_resolve_from_oci_layout(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            world = deterministic_pack(EXAMPLES / "physical-ai" / "mobile-manipulation-world", td / "world.owp.zip")
            layout = td / "layout"
            digest = oci_push(world, f"oci-layout:{layout}:mobile-0.1.0")
            self.assertTrue(digest.startswith("sha256:"))
            descriptor = json.loads(subprocess.run([ORAS, "manifest", "fetch", "--oci-layout", f"{layout}:mobile-0.1.0"],
                                                   check=True, capture_output=True, text=True).stdout)
            self.assertEqual(descriptor["artifactType"], "application/vnd.openworld.package.v1alpha1")
            self.assertEqual([l["mediaType"] for l in descriptor["layers"]], ["application/vnd.openworld.package.layer.v1alpha1+zip"])
            result, resolution = validate_resolved(EXAMPLES / "physical-ai" / "multimodal-action-world-model",
                                                   [f"oci-layout:{layout}:mobile-0.1.0"])
            self.assertTrue(result.valid, result.errors)
            self.assertEqual(resolution.packages["openworld-examples/mobile-manipulation-world@0.1.0"].revision, f"oci:{digest}")


@unittest.skipUnless(COSIGN, "cosign not installed (set ONTLE_COSIGN)")
class SignatureTests(unittest.TestCase):
    def test_sign_and_verify_with_key(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            env = {**os.environ, "COSIGN_PASSWORD": "test"}
            subprocess.run([COSIGN, "generate-key-pair"], cwd=td, env=env, check=True, capture_output=True)
            os.environ["COSIGN_PASSWORD"] = "test"
            archive = deterministic_pack(EXAMPLES / "physical-ai" / "mobile-manipulation-world", td / "world.owp.zip")
            bundle = sign_archive(archive, str(td / "cosign.key"))
            self.assertTrue(bundle.exists())
            verify_signature(archive, key=str(td / "cosign.pub"))
            archive.write_bytes(archive.read_bytes() + b"x")
            with self.assertRaises(OWPError):
                verify_signature(archive, key=str(td / "cosign.pub"))



class EvidenceConformanceTests(unittest.TestCase):
    def test_evidence_conformance_cases(self):
        """evidenceCases: CompatibilityEvidence published outside the package (spec 9.1)."""
        import yaml
        suite = Path(__file__).resolve().parent.parent / "conformance"
        expected = yaml.safe_load((suite / "expected.yaml").read_text(encoding="utf-8"))["evidenceCases"]
        self.assertEqual({p.name for p in (suite / "evidence").iterdir() if p.is_dir()}, set(expected))
        for case_id, exp in expected.items():
            with self.subTest(case=case_id):
                case = suite / "evidence" / case_id
                errors = check_detached_evidence(yaml.safe_load((case / "evidence.yaml").read_text(encoding="utf-8")), case / "package.owp.zip")
                self.assertEqual(not errors, exp["valid"], errors)
                self.assertLessEqual(set(exp.get("errors", [])), {e.split(":", 1)[0] for e in errors}, errors)

if __name__ == "__main__":
    unittest.main()
