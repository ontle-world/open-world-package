# OWP TypeScript implementation

An independent implementation of the Open World Package (OWP) validator, dependency resolver, and Effective World State (EWS) compiler/checker, in TypeScript.

It was written as a clean-room implementation: only `spec/`, `schemas/`, `vocab/`, `docs/`, `examples/`, and `conformance/` were available to the author; the Python reference implementation in `src/ontle/` was not. Its purpose is to show that the specification alone is enough to reach the same verdicts, rule ids, and EWS documents as the reference implementation.

Status: public alpha, not published to npm (`"private": true`).

## Use

Requires Node.js 20 or later.

```bash
npm ci
npm run build
npm test                # build + vocab check + conformance + examples
npm run vocab           # checks src/vocab.ts against ../../vocab/asset-kinds.yaml
npm run conformance     # runs ../../conformance (all four sections)
npm run examples        # validates ../../examples, resolves models, compiles example EWS

node dist/cli.js [--json] [--resolve] [--source <dir|.owp.zip|git+url@rev>]... <package-dir>
node dist/cli.js ews compile <world> --compiler <path> --observations <file> --as-of <timestamp>
node dist/cli.js ews check <ews.yaml> --world <world>
```

The conformance runner checks that the reported ids include every id a case lists under `errors` and, for validation and resolution cases, under `warnings`.

`npm run conformance -- --suite <dir>` (or `OWP_CONFORMANCE_DIR`) runs another copy of the suite.

`npm run probes` generates extra probe packages under `probes/` (not committed). Their expected verdicts are this implementation's reading of the spec, not reference results; they are useful for finding disagreements with other implementations.

## Layout

| File | Spec |
|---|---|
| `src/rules/manifest.ts`, `src/rules/assets.ts`, `src/rules/dependencies.ts` | 2, 3, 5, 8 |
| `src/rules/externalref.ts` | 5.1 ExternalRef (`spec.assets[].ref`) |
| `src/rules/ontology.ts` | 3.1 OntologyPackage contract and ontology conformance profiles |
| `src/rules/experimental.ts` | Appendix C experimental kinds (warnings) and World View `specializes` |
| `src/structure.ts` | 8 defined fields: field tables mirroring `schemas/*.schema.json` |
| `src/rules/extensions.ts` | 13 extension declarations, definitions, `extensions` blocks |
| `src/vocab.ts` | 8 asset-kind vocabulary and Appendix C value sets (copies of `vocab/asset-kinds.yaml` and `vocab/value-sets.yaml`, checked by `scripts/check-vocab.mjs`) |
| `src/rules/world.ts` | 6.1 conformance profiles |
| `src/rules/worldmodel.ts` | 3, 6 |
| `src/rules/evaluation.ts` | 9 |
| `src/resolve.ts`, `src/zip.ts` | 7, 11, 13.1 |
| `src/ews.ts` | 12 |
| `src/conformance.ts` | conformance runner |

Errors and warnings carry the rule ids of spec Appendix A (`spec/rule-ids.yaml`). Rule ids are written as plain string literals so `tests/test_rule_ids.py` can check that this implementation uses exactly the registered ids. Warnings that only this implementation reports use ids containing `:`:

| Warning id | Condition |
|---|---|
| `owp-ts:asset-api-version` | a typed local YAML asset declares an `apiVersion` other than `openworld/v1alpha1` |
| `owp-ts:eval-name` | EvaluationProfile or VerifierPackage without `metadata.name` |
| `owp-ts:eval-supersedes-name` | `supersedes` names a different asset than `metadata.name` |
| `owp-ts:eval-supersedes-order` | `metadata.version` is not greater than the superseded version |

## Verification history

| Round | Spec revision | Result on first run |
|---|---|---|
| 1 | profiles, grounding, evaluation lineage | 23/23 |
| 2 | + resolution, EWS | 64/64 |
| 3 | + rule ids, archive format, timestamp/value rules | 99/99 |
| after round 3 | + 13 cases for previously unexercised rule ids | 112/112 |
| test audit | + git bundle source fixtures, PackageExample parse rule | 113/115 before the two spec decisions below, 115/115 after |
| extensions | + defined fields, extensions (section 13), vocabulary stability, warning ids | 122/140 before the update, 142/142 after (two cases added during the update) (maintainer update, not clean-room) |
| external refs | + ExternalRef (section 5.1), 14 `ref-*` cases | 156/156 after the update (maintainer update, not clean-room) |
| experimental kinds | + Appendix C experimental kinds, value sets, View `specializes`; expected `warnings` checked by the runner; 10 `experimental-*`/`view-specializes*` cases | 166/166 after the update (maintainer update, not clean-room) |
| ontology contract | + OntologyPackage contract (section 3.1): entrypoints, prefixes, SemanticProfile and OntologyTermIndex documents, external imports, ontology profiles; 20 `ontology-*` cases | 186/186 after the update (maintainer update, not clean-room) |

Each round's spec ambiguities were fed back into `spec/OWP_SPEC.md`.

After round 3 the code is maintained in this repository together with the spec. Follow-up spec changes were applied here by the maintainers rather than clean-room: `PackageExample` YAML must parse (its kind is not compared); an unreadable package source is an error rather than a warning; and the extensions round (closed documents with `extensions` blocks, `<extension>:<Kind>` asset kinds declared through `spec.dependencies[].as`, `spec.extensionDefinition`, vocabulary `stability`, and registered warning ids); ExternalRef validation of `spec.assets[].ref` (section 5.1); experimental kinds (Appendix C); and the ontology contract (section 3.1). The probes `p2-namespaced-asset-kind`, `p2-package-example-unparseable`, and `p-action-ready-via-refs` were updated to these rules.
