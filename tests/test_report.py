import contextlib
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ontle import cli
from ontle.core import deterministic_pack
from ontle.ews import compile_ews
from ontle.mcp import PackageServer, serve
from ontle.report import CARD_SECTIONS, card_sections, pack_size_hint, package_report
from ontle.scaffold import init_project
from ontle.yamlio import load_yaml

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "examples"
WORLD = EXAMPLES / "business" / "manufacturing-quality-world"
SCHEMA = json.loads((ROOT / "schemas" / "package-report.schema.json").read_text(encoding="utf-8"))


def schema_problems(value, schema, at="$"):
    """The parts of the schema the report uses: type, const, enum, required, closed objects, items, patterns."""
    problems = []
    types = schema.get("type")
    types = [types] if isinstance(types, str) else types or []
    py = {"object": dict, "array": list, "string": str, "boolean": bool, "null": type(None)}
    if types and not any((t == "integer" and isinstance(value, int) and not isinstance(value, bool))
                         or (t in py and isinstance(value, py[t])) for t in types):
        return [f"{at}: {value!r} is not {types}"]
    if "const" in schema and value != schema["const"]:
        problems.append(f"{at}: {value!r} != {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        problems.append(f"{at}: {value!r} not in {schema['enum']}")
    if "minimum" in schema and value < schema["minimum"]:
        problems.append(f"{at}: {value} < {schema['minimum']}")
    if "pattern" in schema:
        import re
        if not re.search(schema["pattern"], value):
            problems.append(f"{at}: {value!r} does not match {schema['pattern']}")
    if isinstance(value, dict):
        props = schema.get("properties", {})
        problems += [f"{at}: missing {k}" for k in schema.get("required", []) if k not in value]
        for k, v in value.items():
            if k in props:
                problems += schema_problems(v, props[k], f"{at}.{k}")
            elif schema.get("additionalProperties") is False:
                problems.append(f"{at}: unexpected {k}")
            elif isinstance(schema.get("additionalProperties"), dict):
                problems += schema_problems(v, schema["additionalProperties"], f"{at}.{k}")
    if isinstance(value, list) and "items" in schema:
        for i, v in enumerate(value):
            problems += schema_problems(v, schema["items"], f"{at}[{i}]")
    return problems


def run_cli(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli.main(argv)
    return code, out.getvalue(), err.getvalue()


class PackageReportTests(unittest.TestCase):
    def test_every_example_report_matches_the_schema(self):
        for manifest in sorted(EXAMPLES.glob("*/*/owp.yaml")):
            with self.subTest(package=manifest.parent.name):
                report = package_report(manifest.parent)
                self.assertEqual(schema_problems(report, SCHEMA), [])
                self.assertTrue(report["valid"])

    def test_world_report_counts(self):
        report = package_report(WORLD)
        self.assertEqual(report["identity"], "openworld-examples/manufacturing-quality-world@0.1.0")
        self.assertEqual(report["profile"], {"declared": "action-ready", "satisfied": "action-ready"})
        self.assertEqual(report["state"], {"stateCompilers": 1, "fields": 9, "withBinding": 8})
        self.assertEqual(report["semanticCoverage"], {"boundToTerms": 9, "fields": 9})
        self.assertEqual(report["externalRefs"]["total"], report["externalRefs"]["pinned"])
        self.assertIn("opcua", report["standardBindings"]["standards"])
        self.assertEqual(report["assets"]["total"], sum(report["assets"]["byKind"].values()))
        self.assertNotIn("integrity", report)

    def test_archive_report_adds_integrity_and_is_reproducible(self):
        with tempfile.TemporaryDirectory() as td:
            first = deterministic_pack(WORLD, Path(td) / "a.owp.zip")
            second = deterministic_pack(WORLD, Path(td) / "b.owp.zip")
            report = package_report(first)
            self.assertEqual(report["integrity"]["digest"], "sha256:" + hashlib.sha256(first.read_bytes()).hexdigest())
            self.assertFalse(report["integrity"]["signatureBundle"])
            (first.parent / (first.name + ".sigstore.json")).write_text("{}", encoding="utf-8")
            self.assertTrue(package_report(first)["integrity"]["signatureBundle"])
            self.assertEqual(package_report(second), {**report, "integrity": {**report["integrity"], "signatureBundle": False}})
            without = {k: v for k, v in report.items() if k != "integrity"}
            self.assertEqual(without, package_report(WORLD))

    def test_card_sections_and_hints(self):
        self.assertEqual(card_sections("# T\n\n## Scope\ntext\n### Deeper\n##  Use it for ##\n"), ["Scope", "Use it for"])
        with tempfile.TemporaryDirectory() as td:
            root = init_project("hinted", "acme", destination=Path(td) / "p")
            report = package_report(root)
            self.assertEqual(report["card"]["missingRecommended"], [])
            self.assertEqual(report["hints"], ["metadata.description is still the template text", "WORLD.md still has template text to replace"])
            (root / "WORLD.md").write_text("# Hinted\n\n## Scope\n\nSee `views/default.yaml` and `views/gone.yaml`.\n", encoding="utf-8")
            manifest = (root / "owp.yaml").read_text(encoding="utf-8")
            (root / "owp.yaml").write_text(manifest.replace("  description: One line", "  description: " + "x" * 200 + " One line"), encoding="utf-8")
            report = package_report(root)
            self.assertEqual(report["card"]["missingRecommended"], CARD_SECTIONS[1:])
            self.assertTrue(any("has no section Sources" in h for h in report["hints"]))
            self.assertTrue(any("metadata.description has" in h for h in report["hints"]))
            self.assertIn("WORLD.md names files that are not in the package: views/gone.yaml", report["hints"])

    def test_cli_report_and_archive_inspect(self):
        code, out, _ = run_cli(["inspect", str(WORLD), "--report"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["kind"], "PackageReport")
        with tempfile.TemporaryDirectory() as td:
            archive = deterministic_pack(WORLD, Path(td) / "w.owp.zip")
            code, out, _ = run_cli(["inspect", str(archive)])
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(out)["root"], str(archive.resolve()))


class AuthoringHintTests(unittest.TestCase):
    def test_init_prints_next_steps_on_stderr(self):
        with tempfile.TemporaryDirectory() as td:
            code, out, err = run_cli(["init", "steps", "--destination", str(Path(td) / "steps")])
            self.assertEqual(code, 0)
            self.assertEqual(out.strip(), str((Path(td) / "steps").resolve()))
            self.assertIn("ontle validate", err)
            self.assertIn("--report", err)

    def test_pack_warns_about_large_archives(self):
        self.assertIsNone(pack_size_hint(10, 50))
        self.assertIn("ExternalRef", pack_size_hint(60_000_000, 50_000_000))
        with tempfile.TemporaryDirectory() as td, mock.patch.object(cli, "PACK_SIZE_HINT", 100):
            code, out, err = run_cli(["pack", str(WORLD), "--output", str(Path(td) / "w.owp.zip")])
            self.assertEqual(code, 0)
            self.assertIn("WARN: archive is", err)
            self.assertTrue(out.strip().endswith("w.owp.zip"))
        with tempfile.TemporaryDirectory() as td:  # a directory as --output: the default file name inside it
            code, out, _ = run_cli(["pack", str(WORLD), "--output", td])
            self.assertEqual(code, 0)
            self.assertEqual(Path(out.strip()).name, "openworld-examples-manufacturing-quality-world-0.1.0.owp.zip")


class McpServerTests(unittest.TestCase):
    def exchange(self, server, *messages):
        out = io.StringIO()
        serve(server, io.StringIO("".join(json.dumps(m) + "\n" for m in messages)), out)
        return {r["id"]: r for r in map(json.loads, out.getvalue().splitlines())}

    def call(self, server, name, arguments=None):
        reply = self.exchange(server, {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": arguments or {}}})[1]
        return reply["result"]

    def test_handshake_and_listing(self):
        server = PackageServer(WORLD, WORLD)
        replies = self.exchange(server,
                                {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-03-26"}},
                                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                                {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                                {"jsonrpc": "2.0", "id": 3, "method": "resources/list"},
                                {"jsonrpc": "2.0", "id": 4, "method": "nope"})
        self.assertEqual(sorted(replies), [1, 2, 3, 4])  # the notification gets no reply
        self.assertEqual(replies[1]["result"]["protocolVersion"], "2025-03-26")
        self.assertEqual([t["name"] for t in replies[2]["result"]["tools"]],
                         ["world_describe", "view_get", "term_lookup", "ews_compile", "package_report"])
        self.assertTrue(all(t["annotations"]["readOnlyHint"] for t in replies[2]["result"]["tools"]))
        names = [r["name"] for r in replies[3]["result"]["resources"]]
        self.assertIn("card", names)
        self.assertEqual(replies[4]["error"]["code"], -32601)

    def test_tools(self):
        server = PackageServer(WORLD, WORLD)
        described = self.call(server, "world_describe")["structuredContent"]
        self.assertEqual(described["views"], ["views/quality-incident-task.yaml"])
        self.assertIn("# Manufacturing Quality World", described["card"])
        view = self.call(server, "view_get")["structuredContent"]
        self.assertEqual(view["path"], "views/quality-incident-task.yaml")
        matches = self.call(server, "term_lookup", {"query": "q:Claim"})["structuredContent"]["matches"]
        self.assertTrue(any(m["name"] == "claim" for m in matches))
        observations = load_yaml((WORLD / "examples" / "observations.yaml").read_text(encoding="utf-8"))
        expected = compile_ews(WORLD, "state/quality-incident-compiler.yaml", observations, "2026-09-05T00:00:00Z")
        for args in ({"observationsPath": "examples/observations.yaml"}, {"observations": observations}):
            result = self.call(server, "ews_compile", {"asOf": "2026-09-05T00:00:00Z", **args})
            self.assertEqual(result["structuredContent"], expected)
        self.assertEqual(self.call(server, "package_report")["structuredContent"]["kind"], "PackageReport")
        failed = self.call(server, "ews_compile", {"asOf": "2026-09-05T00:00:00Z", "observationsPath": "../outside.yaml"})
        self.assertTrue(failed["isError"])
        unknown = self.call(server, "view_get", {"view": "views/quality-incident-task.yaml"})
        self.assertTrue(unknown["isError"])
        self.assertIn("does not take view", unknown["content"][0]["text"])
        as_path = self.call(server, "ews_compile", {"asOf": "2026-09-05T00:00:00Z", "observations": "examples/observations.yaml"})
        self.assertIn("observationsPath", as_path["content"][0]["text"])

    def test_resources(self):
        server = PackageServer(WORLD, WORLD, [str(WORLD / "examples" / "observations.yaml")])
        replies = self.exchange(server,
                                {"jsonrpc": "2.0", "id": 1, "method": "resources/templates/list"},
                                {"jsonrpc": "2.0", "id": 2, "method": "resources/read",
                                 "params": {"uri": "https://w3id.org/owp/pkg/openworld-examples/manufacturing-quality-world/0.1.0"}})
        template = replies[1]["result"]["resourceTemplates"][0]["uriTemplate"]
        self.assertIn("kind: WorldPackage", replies[2]["result"]["contents"][0]["text"])
        uri = template.replace("{asOf}", "2026-09-05T00:00:00Z")
        ews = self.exchange(server, {"jsonrpc": "2.0", "id": 1, "method": "resources/read", "params": {"uri": uri}})[1]
        self.assertIn("kind: EffectiveWorldState", ews["result"]["contents"][0]["text"])
        bare = PackageServer(WORLD, WORLD)
        refused = self.exchange(bare, {"jsonrpc": "2.0", "id": 1, "method": "resources/read", "params": {"uri": uri}})[1]
        self.assertIn("--observations", refused["error"]["message"])

    def test_ontology_package_terms(self):
        onto = EXAMPLES / "ontology" / "quality-ontology"
        matches = self.call(PackageServer(onto, onto), "term_lookup", {"query": "claim"})["structuredContent"]["matches"]
        self.assertTrue(matches)
        self.assertTrue(all(m["in"] == "ontology terms" for m in matches))


if __name__ == "__main__":
    unittest.main()
