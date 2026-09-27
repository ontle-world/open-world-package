# OWP TypeScript implementation

An independent implementation of the Open World Package (OWP) validator, dependency resolver, and Effective World State (EWS) compiler/checker, in TypeScript.

It was written as a clean-room implementation: only `spec/`, `schemas/`, `vocab/`, `docs/`, `examples/`, and `conformance/` were available to the author; the Python reference implementation in `src/ontle/` was not. Its purpose is to show that the specification alone is enough to reach the same verdicts, rule ids, and EWS documents as the reference implementation.

Status: public alpha, not published to npm (`"private": true`).

## Use

Requires Node.js 20 or later.

```bash
npm ci
npm run build
npm run conformance     # runs ../../conformance (all four sections)
npm run examples        # validates ../../examples, resolves models, compiles example EWS

node dist/cli.js [--json] [--resolve] [--source <dir|.owp.zip|git+url@rev>]... <package-dir>
node dist/cli.js ews compile <world> --compiler <path> --observations <file> --as-of <timestamp>
node dist/cli.js ews check <ews.yaml> --world <world>
```

`npm run conformance -- --suite <dir>` (or `OWP_CONFORMANCE_DIR`) runs another copy of the suite.

`npm run probes` generates extra probe packages under `probes/` (not committed). Their expected verdicts are this implementation's reading of the spec, not reference results; they are useful for finding disagreements with other implementations.

## Layout

| File | Spec |
|---|---|
| `src/rules/manifest.ts`, `src/rules/assets.ts`, `src/rules/dependencies.ts` | 2, 3, 5, 8 |
| `src/rules/world.ts` | 6.1 conformance profiles |
| `src/rules/worldmodel.ts` | 3, 6 |
| `src/rules/evaluation.ts` | 9 |
| `src/resolve.ts`, `src/zip.ts` | 7, 11 |
| `src/ews.ts` | 12 |
| `src/conformance.ts` | conformance runner |

Errors carry the rule ids of spec Appendix A.

## Verification history

| Round | Spec revision | Result on first run |
|---|---|---|
| 1 | profiles, grounding, evaluation lineage | 23/23 |
| 2 | + resolution, EWS | 64/64 |
| 3 | + rule ids, archive format, timestamp/value rules | 99/99 |
| after round 3 | + 13 cases for previously unexercised rule ids | 112/112 |
| test audit | + git bundle source fixtures, PackageExample parse rule | 113/115 before the two spec decisions below, 115/115 after |

Each round's spec ambiguities were fed back into `spec/OWP_SPEC.md`.

After round 3 the code is maintained in this repository together with the spec. Two follow-up spec decisions were applied here by the maintainers rather than clean-room: `PackageExample` YAML must parse (its kind is not compared), and an unreadable package source is an error rather than a warning.
