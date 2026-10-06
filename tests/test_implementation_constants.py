"""The two implementations keep the same closed lists and tables.

The conformance suite, parity fuzz, and report parity compare what the implementations do; this compares what each
one declares (profiles, providers, operators, ontology formats, rule families, report constants), so a value added
to one is not missing from the other. It needs node and the built TypeScript implementation
(implementations/typescript: npm run build).
"""
import json
import shutil
import subprocess
import unittest
from pathlib import Path

from ontle import core, ews, experimental, ignore, ontology, report, resolve, structure

ROOT = Path(__file__).resolve().parent.parent
TS = ROOT / "implementations" / "typescript"


def python_constants() -> dict:
    return {
        "apiVersion": ews.API_VERSION,
        "packageKinds": sorted(core.KINDS),
        "legacyManifests": sorted(core.LEGACY_MANIFESTS),
        "documentKinds": sorted(core.DOCUMENT_KINDS),
        "ignoredPathParts": sorted(core.IGNORED_PATH_PARTS),
        "ignoreFile": ignore.IGNORE_FILE,
        "lockFormat": core.LOCK_FORMAT,
        "worldProfiles": list(core.WORLD_PROFILES),
        "ontologyProfiles": list(ontology.ONTOLOGY_PROFILES),
        "ontologyFormats": sorted(ontology.FORMATS),
        "ontologyRoles": sorted(ontology.ROLES),
        "termTypes": sorted(ontology.TERM_TYPES),
        "providers": sorted(structure.PROVIDERS),
        "reservedExtensionNames": sorted(structure.RESERVED_EXTENSION_NAMES),
        "selectors": sorted(ews.SELECTORS),
        "aggregateFunctions": sorted(ews.AGGREGATE_FUNCTIONS),
        "conditions": sorted(ews.CONDITIONS),
        "actorBlocks": list(experimental.ACTOR_BLOCKS),
        "families": dict(experimental.FAMILIES),
        "openValueSets": sorted(experimental.OPEN_VALUE_SETS),
        "dependencyDirections": {k: sorted(v) for k, v in resolve.DEPENDENCY_DIRECTIONS.items()},
        "cardSections": list(report.CARD_SECTIONS),
        "defaultCards": dict(report.DEFAULT_CARDS),
        "cardSpecKey": dict(report.CARD_SPEC_KEY),
        "descriptionLimit": report.DESCRIPTION_LIMIT,
        "templateCardText": list(report.TEMPLATE_CARD_TEXT),
    }


@unittest.skipUnless(shutil.which("node") and (TS / "dist" / "report.js").is_file(), "needs node and the built TypeScript implementation")
class ImplementationConstantsTests(unittest.TestCase):
    def test_typescript_declares_the_same_lists_and_tables(self):
        run = subprocess.run(["node", str(TS / "scripts" / "dump-constants.mjs")], capture_output=True, text=True, timeout=60)
        self.assertEqual(run.returncode, 0, run.stderr)
        ts = json.loads(run.stdout)
        py = python_constants()
        self.assertEqual(sorted(ts), sorted(py))
        for key in py:
            with self.subTest(constant=key):
                self.assertEqual(ts[key], py[key])


if __name__ == "__main__":
    unittest.main()
