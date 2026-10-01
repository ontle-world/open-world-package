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
    ids: set[str] = set()
    for path in (ROOT / "src" / "ontle").glob("*.py"):
        ids |= set(re.findall(rf"[\"']({ID_RE}): ", path.read_text(encoding="utf-8")))
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
        used = {rule for section in ("cases", "resolutionCases", "ewsCases", "ewsCheckCases", "extractionCases")
                for case in expected[section].values() for rule in case.get("errors", [])}
        self.assertEqual(used - {r for r, e in REGISTRY.items() if e["severity"] == "error"}, set())

    def test_python_reference_emits_exactly_registered_ids(self):
        self.assertEqual(python_ids(), set(REGISTRY))

    def test_typescript_implementation_uses_exactly_registered_ids(self):
        self.assertEqual(typescript_ids(), set(REGISTRY))


if __name__ == "__main__":
    unittest.main()
