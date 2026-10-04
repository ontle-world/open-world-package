"""spec/rule-ids.yaml is the single list of rule ids.

The spec appendix, the conformance suite, the Python reference, and the
TypeScript implementation must use exactly the registered ids. Implementation-
specific warnings use ids containing ':' and are not registered.
"""
import re
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = yaml.safe_load((ROOT / "spec" / "rule-ids.yaml").read_text(encoding="utf-8"))["rules"]
ID_RE = r"[a-z][a-z0-9-]*(?:\.[a-z0-9-]+)+"


def appendix_ids() -> dict[str, str]:
    text = (ROOT / "spec" / "OWP_SPEC.md").read_text(encoding="utf-8")
    appendix = text[text.index("## Appendix A"):text.index("## Appendix B")]
    split = appendix.index("| Warning id")
    out = {}
    for part, severity in ((appendix[:split], "error"), (appendix[split:], "warning")):
        for line in part.splitlines():
            if line.startswith("| `"):
                for rule in re.findall(rf"`({ID_RE})`", line.split("|")[1]):
                    out[rule] = severity
    return out


def python_ids() -> set[str]:
    """Ids written as "<id>: message" or passed as a quoted argument, with a registered prefix."""
    prefixes = {rule.split(".")[0] for rule in REGISTRY}
    ids: set[str] = set()
    for path in (ROOT / "src" / "ontle").glob("*.py"):
        source = path.read_text(encoding="utf-8")
        ids |= set(re.findall(rf"[\"']({ID_RE}): ", source))
        ids |= {s for s in re.findall(rf"[\"']({ID_RE})[\"']", source)
                if s.split(".")[0] in prefixes and not re.search(r"\.(ya?ml|json|md|py)$", s)}
    return ids


def typescript_ids() -> set[str]:
    prefixes = {rule.split(".")[0] for rule in REGISTRY} | {"conformance"}
    ids: set[str] = set()
    for path in (ROOT / "implementations" / "typescript" / "src").rglob("*.ts"):
        source = re.sub(r"/\*.*?\*/|//[^\n]*", "", path.read_text(encoding="utf-8"), flags=re.S)
        for literal in re.findall(r"[\"'`]([a-z][a-zA-Z0-9-]*(?:\.[a-zA-Z0-9-]+)+)[\"'`]", source):
            if literal.split(".")[0] in prefixes and (literal in REGISTRY or not re.search(r"\.(ya?ml|json|md)$", literal)):
                ids.add(literal)
    return ids


class RuleIdRegistryTests(unittest.TestCase):
    def test_spec_appendix_matches_registry(self):
        self.assertEqual(appendix_ids(), {rule: entry["severity"] for rule, entry in REGISTRY.items()})

    def test_conformance_suite_uses_registered_error_ids(self):
        expected = yaml.safe_load((ROOT / "conformance" / "expected.yaml").read_text(encoding="utf-8"))
        used = {rule for section in ("cases", "resolutionCases", "ewsCases", "ewsCheckCases", "extractionCases", "evidenceCases")
                for case in expected[section].values() for rule in case.get("errors", [])}
        self.assertEqual(used - {r for r, e in REGISTRY.items() if e["severity"] == "error"}, set())

    def test_python_reference_emits_exactly_registered_ids(self):
        self.assertEqual(python_ids(), set(REGISTRY))

    def test_typescript_implementation_uses_exactly_registered_ids(self):
        self.assertEqual(typescript_ids(), set(REGISTRY))



class ReferenceIdsTests(unittest.TestCase):
    def test_python_reports_exactly_the_reference_ids(self):
        """conformance/reference-ids.json is current (the TypeScript runner checks the same file)."""
        import importlib.util
        spec = importlib.util.spec_from_file_location("reference_ids", ROOT / "scripts" / "reference_ids.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual(module.render(module.compute()), (ROOT / "conformance" / "reference-ids.json").read_text(encoding="utf-8"),
                         "run python scripts/reference_ids.py and review the diff")



# Error ids that no conformance case reaches yet. A new error id needs a case; remove an id here when it gets one.
UNCOVERED_ERRORS: set[str] = set()


class CoverageTests(unittest.TestCase):
    def test_every_error_id_has_a_conformance_case(self):
        text = "".join(p.read_text(encoding="utf-8") for p in sorted((ROOT / "conformance").rglob("*.yaml")) if "expected" in p.name)
        text += (ROOT / "conformance" / "reference-ids.json").read_text(encoding="utf-8")
        covered = {r for r in REGISTRY if re.search(rf"(?<![\w.-]){re.escape(r)}(?![\w.-])", text)}  # evidence.scope is not evidence.scope.world-ref
        errors = {r for r, v in REGISTRY.items() if v["severity"] == "error"}
        self.assertEqual(sorted(errors - covered - UNCOVERED_ERRORS), [], "error ids without a conformance case")
        self.assertEqual(sorted(UNCOVERED_ERRORS & covered), [], "covered now: remove from UNCOVERED_ERRORS")

    def test_open_value_sets_match_the_vocabulary(self):
        from ontle.experimental import OPEN_VALUE_SETS
        sets = yaml.safe_load((ROOT / "vocab" / "value-sets.yaml").read_text(encoding="utf-8"))["valueSets"]
        self.assertEqual(sorted(OPEN_VALUE_SETS), sorted(n for n, v in sets.items() if v.get("open") is True))

    def test_sssom_metadata_is_yaml(self):
        for tsv in sorted((ROOT / "alignments").glob("*/mappings.sssom.tsv")):
            header = "".join(line[2:] for line in tsv.read_text(encoding="utf-8").splitlines(True) if line.startswith("#"))
            meta = yaml.safe_load(header)
            for key in ("curie_map", "mapping_set_id", "mapping_set_version", "license"):
                self.assertIn(key, meta, f"{tsv}: {key}")

class ValueSetTests(unittest.TestCase):
    def test_value_entries_have_only_known_keys(self):
        """A comma in a flow mapping splits a label: {label: Image, audio, or video} has keys 'audio' and 'or video'."""
        sets = yaml.safe_load((ROOT / "vocab" / "value-sets.yaml").read_text(encoding="utf-8"))["valueSets"]
        bad = [(n, v, sorted(e)) for n, s in sets.items() for v, e in s["values"].items() if e and set(e) - {"label", "description", "family"}]
        self.assertEqual(bad, [])

    def test_skos_value_sets_are_current(self):
        import subprocess
        import sys
        r = subprocess.run([sys.executable, str(ROOT / "scripts" / "build_value_sets.py"), "--check"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)

if __name__ == "__main__":
    unittest.main()
