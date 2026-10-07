# Contributing

Thank you for contributing to ONTLE / OWP public-alpha tooling.

## Development setup

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e .   # installs the runtime dependency PyYAML
python -m unittest discover -s tests -v
./scripts/golden_smoke.sh
```

Starter templates live only in `src/ontle/templates/` and ship as package data; edit them there.

## Design rules

1. Keep the default authoring surface small.
2. Do not expose registry-internal complexity as mandatory authoring files.
3. `owp.yaml` is the single machine-readable package manifest.
4. `WORLD.md`, `WORLDMODEL.md`, and `ONTOLOGY.md` are human-readable cards by package kind.
5. Package identity and semantic identity are related but not identical.
6. Runtime state, especially Effective World State, is not automatically a registry asset.
7. A package or fixture never overrides semantic meaning; it tests or instantiates a contract.
8. Add deterministic validation where possible. Keep model-specific execution optional.

## Changing both implementations

The Python reference (`src/ontle/`) and the TypeScript implementation (`implementations/typescript/src/`) give the same verdicts. A change to a rule, a field, or a closed list goes into both, in the same pull request, with conformance cases. The modules correspond:

| Concern | Python | TypeScript |
|---|---|---|
| Validation entry point, manifest and identity, profiles, evaluation lineage | `core.py` | `validate.ts`, `rules/manifest.ts`, `rules/world.ts`, `rules/worldmodel.ts`, `rules/evaluation.ts` |
| Asset discovery, `.owpignore` | `core.py` (`package_documents`, `local_assets`), `ignore.py` | `discovery.ts`, `rules/assets.ts`, `ignore.ts` |
| Defined fields, ExternalRef, standard bindings | `structure.py` | `structure.ts`, `rules/externalref.ts` |
| Extensions, work, actors, experimental kinds and fields, standard-kind fields (spec 15) | `experimental.py` | `rules/experimental.ts`, `rules/extensions.ts`, `rules/standard-fields.ts` |
| Ontology contract, term index, schema model | `ontology.py` | `rules/ontology.ts` |
| Semantic binding and its cross-package rules | `binding.py` | `rules/binding.ts` |
| EWS compile and check, binding forms | `ews.py` | `ews.ts`, `rules/world.ts` |
| Resolution, archives, lock | `resolve.py`, `core.py` (`verify_archive`) | `resolve.ts`, `zip.ts` |
| Detached evidence | `distribution.py` | `evidence.ts` |
| Knowledge extraction | `extraction.py` | `extraction.ts` |
| PackageReport | `report.py` | `report.ts` |
| YAML profile, text rules | `yamlio.py`, `values.py` | `util.ts` |

Python only: the CLI and authoring (`cli.py`, `scaffold.py`, `observations.py`), distribution transport (`distribution.py`: OCI, signing, fetch, indexes, catalogs), RDF output and checks (`rdfexport.py`, `kgcheck.py`), and MCP (`mcp.py`, `interop.py`). TypeScript only: the browser build (`src/browser/`) and the conformance runner.

Shared data lives once, outside both: rule ids in `spec/rule-ids.yaml`, the vocabularies in `vocab/`, the document fields in `schemas/`, and the expected results in `conformance/`. Checks keep the copies in step; each runs in CI:

| What could drift | Check |
|---|---|
| Verdicts, error and warning ids | the conformance suite and `conformance/reference-ids.json` (`python scripts/reference_ids.py --check`, `npm test`) |
| Behavior outside the cases | `scripts/parity_fuzz.py`: mutants of every fixture through both |
| Rule ids used in code | `tests/test_rule_ids.py` against `spec/rule-ids.yaml` |
| Field tables | `tests/test_structure.py` (Python) and `scripts/check-structure.mjs` (TypeScript) against `schemas/` |
| Vocabularies | `scripts/check-vocab.mjs` against `vocab/`; Python reads `vocab/` directly |
| Closed lists and tables (profiles, providers, operators, formats, report constants) | `tests/test_implementation_constants.py` |
| PackageReport | `scripts/report_parity.py` |
| Browser build | `npm run browser`: every validation case through the bundle |
| Behavior at scale | `tests/test_scale.py` on `scripts/make_scale_fixture.py`'s synthetic plant: EWS against independently computed values, TypeScript against Python, a time budget |

Whether the tests catch bugs at all: `python scripts/mutation_check.py` puts 57 small bugs (38 in Python and the registry check, 19 in TypeScript), one at a time, into the two implementations (a window that includes its start, a `where` that needs one condition instead of all, `gt` read as `gte`, a tie that is never unresolved, a check that never fires, ...) and runs the tests on each: the Python suite for a Python mutant; `npm test`, the scale comparison, and report parity for a TypeScript one. Every one must make a test fail. It takes about 45 minutes, so it is not in CI; run it after changing tests or the rules they cover (`python scripts/mutation_check.py ews` runs the mutants whose name matches), and add a mutant for each new rule.

## Pull requests

Please include:
- the problem being solved,
- compatibility impact,
- tests or fixtures,
- documentation changes when the public contract changes.

For manifest/schema changes, include at least one positive and one negative case.
