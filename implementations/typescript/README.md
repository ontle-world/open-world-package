# OWP TypeScript implementation

An independent implementation of the Open World Package (OWP) validator, dependency resolver, and Effective World State (EWS) compiler/checker, in TypeScript.

It was written as a clean-room implementation: only `spec/`, `schemas/`, `vocab/`, `docs/`, `examples/`, and `conformance/` were available to the author; the Python reference implementation in `src/ontle/` was not. Its purpose is to show that the specification alone is enough to reach the same verdicts, rule ids, and EWS documents as the reference implementation.

Status: public alpha, not published to npm (`"private": true`).

## Use

Requires Node.js 24 or later. CI runs on Node.js 24 and 26.

```bash
npm ci
npm run build
npm test                # build + vocab check + conformance + examples + round trip
npm run vocab           # checks src/vocab.ts against ../../vocab/asset-kinds.yaml and value-sets.yaml
npm run roundtrip       # re-serializes every example and valid case in flow style; verdicts and ids must not change
npm run conformance     # runs ../../conformance (all five sections)
npm run examples        # validates ../../examples, resolves models, compiles example EWS

node dist/cli.js [--json] [--resolve] [--source <dir|.owp.zip|git+url@rev>]... <package-dir>
node dist/cli.js ews compile <world> --compiler <path> --observations <file> --as-of <timestamp>
node dist/cli.js ews check <ews.yaml> --world <world>
node dist/cli.js evidence check <evidence.yaml> --package <archive.owp.zip>   # detached evidence, spec 9.1
```

The conformance runner checks that the reported ids include every id a case lists under `errors` and, for validation and resolution cases, under `warnings`.

`npm run conformance -- --suite <dir>` (or `OWP_CONFORMANCE_DIR`) runs another copy of the suite.

`npm run probes` generates extra probe packages under `probes/` (not committed). Their expected verdicts are this implementation's reading of the spec, not reference results; they are useful for finding disagreements with other implementations.

## Layout

Section numbers refer to the specification, which is split across files with unchanged numbering: `spec/OWP_SPEC.md` (sections 1–8, 10, 11, 13, Appendices A and B), `spec/OWP_SEMANTICS.md` (3.1, 14), `spec/OWP_EVALUATION_AND_STATE.md` (9, 12, 15), and `spec/OWP_EXPERIMENTAL.md` (Appendix C).

| File | Spec |
|---|---|
| `src/rules/manifest.ts`, `src/rules/assets.ts`, `src/rules/dependencies.ts` | 2, 3, 5, 8 |
| `src/rules/externalref.ts` | 5.1 ExternalRef (`spec.assets[].ref`) |
| `src/rules/ontology.ts` | 3.1 OntologyPackage contract and ontology conformance profiles |
| `src/rules/binding.ts` | 14 SemanticBinding (single-package; cross-package grounding called from `src/resolve.ts`) |
| `src/rules/standard-fields.ts` | 15 EvaluationProfile and ScenarioProfile fields (errors) |
| `src/rules/experimental.ts` | 16-19 work, actor, artifact, and knowledge kinds (errors, via `promote`), and the remaining experimental kind and View `specializes` (Appendix C, warnings) |
| `src/structure.ts` | 8 defined fields: field tables mirroring `schemas/*.schema.json` (manifest, CompatibilityEvidence, SemanticProfile, OntologyTermIndex, SemanticBinding, WorldViewProfile, EvaluationProfile, ScenarioProfile, CapabilityContract, ObservationSet, EWS) |
| `src/rules/extensions.ts` | 13 extension declarations, definitions, `extensions` blocks |
| `src/vocab.ts` | 8 asset-kind vocabulary and Appendix C value sets (copies of `vocab/asset-kinds.yaml` and `vocab/value-sets.yaml`, checked by `scripts/check-vocab.mjs`) |
| `src/rules/world.ts` | 6.1 conformance profiles |
| `src/rules/worldmodel.ts` | 3, 6 |
| `src/rules/evaluation.ts` | 9 |
| `src/resolve.ts`, `src/zip.ts` | 7 (lock format `owp-lock/v1alpha2` with `externals`), 11 (directory, archive, git, and local `index:` sources), 13.1, 14 |
| `src/evidence.ts` | 9.1 detached CompatibilityEvidence |
| `src/ews.ts` | 12 |
| `src/extraction.ts` | Appendix C.1 knowledge extraction transform (query results to ObservationSet) |
| `src/conformance.ts` | conformance runner |

Errors and warnings carry the rule ids of spec Appendix A (`spec/rule-ids.yaml`). Rule ids are written as plain string literals so `tests/test_rule_ids.py` can check that this implementation uses exactly the registered ids. Warnings that only this implementation reports use ids containing `:`:

| Warning id | Condition |
|---|---|
| `owp-ts:eval-name` | EvaluationProfile or VerifierProfile without `metadata.name` |
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
| semantic binding | + SemanticBinding (section 14): single-package rules and grounding against dependency ontologies; 7 validation and 4 resolution `binding-*` cases | 198/198 after the update (maintainer update, not clean-room) |
| knowledge extraction | + KnowledgeExtractionProfile and the extraction transform (Appendix C.1), ObservationSet `spec.provenance`, `compiler.multi-latest`; new `extractionCases` section (10) and 2 validation cases | 210/210 after the update (maintainer update, not clean-room) |
| distribution | + lock `owp-lock/v1alpha2` externals and vendoring checks, detached evidence (9.1), local `index:` sources (11.1); no new conformance cases (checked against reference-built archives and indexes) | 212/212 (includes two later extraction cases) (maintainer update, not clean-room) |
| work, artifacts, actors | + work pattern graphs (C.2), ArtifactContract additions, ActorProfile, RoleProfile, DelegationProfile (C.3), `experimental.delegation-exceeds-authority`; 13 validation cases | 223/223 after the update (maintainer update, not clean-room) |
| standard-kind fields | + defined fields for WorldViewProfile, EvaluationProfile, ScenarioProfile, CapabilityContract; their experimental fields (C.4); TaskSetProfile composition; 13 validation cases | 236/236 after the update (maintainer update, not clean-room) |
| round trip | + `scripts/check-roundtrip.mjs` (docs/PROFILE_PROMOTION.md, Interoperability): every example and every valid case keeps its verdict, error ids, and warning ids after YAML re-serialization | 72/72 packages |
| promotion | + section 15 (EvaluationProfile, ScenarioProfile fields promoted from Appendix C.4 warnings to errors); `asset.kind-experimental` reported once per kind with a count; 4 new invalid cases, 3 cases now invalid | 240/240 after the update; round trip 69/69 (maintainer update, not clean-room) |
| asset headers | + section 5: asset files may omit `apiVersion` and `kind`; a declared `apiVersion` that differs from the manifest's is the error `asset.api-version` (was the warning `owp-ts:asset-api-version`); 2 validation cases | see the run below |

Each round's spec ambiguities were fed back into the specification (now `spec/OWP_SPEC.md` and the companion files listed under Layout).

After round 3 the code is maintained in this repository together with the spec. Follow-up spec changes were applied here by the maintainers rather than clean-room: `PackageExample` YAML must parse (its kind is not compared); an unreadable package source is an error rather than a warning; and the extensions round (closed documents with `extensions` blocks, `<extension>:<Kind>` asset kinds declared through `spec.dependencies[].as`, `spec.extensionDefinition`, vocabulary `stability`, and registered warning ids); ExternalRef validation of `spec.assets[].ref` (section 5.1); experimental kinds (Appendix C); the ontology contract (section 3.1); semantic binding (section 14); knowledge extraction (Appendix C.1); work pattern graphs, actors, roles, and delegation, and experimental fields of standard kinds (Appendix C.2–C.4); and distribution (sections 7, 9.1, 11.1). OCI sources and http(s) package indexes are not implemented. The probes `p2-namespaced-asset-kind`, `p2-package-example-unparseable`, and `p-action-ready-via-refs` were updated to these rules.
