# OWP Conformance Suite

Language-neutral fixtures for checking that an OWP implementation interprets packages the same way as the reference implementation.

A single implementation reading its own packages does not demonstrate interoperability. An independent parser, validator, resolver, or runtime should run this suite and report its results.

All expected outcomes are in `expected.yaml`. Rule ids are listed in `spec/rule-ids.yaml`. For an invalid case, `errors` lists the rule ids (spec Appendix A) a conforming implementation MUST report; it MAY report more. `rule` is informative; error wording and ordering are implementation-defined.

## Sections

| Section | Fixtures | A conforming implementation must |
|---|---|---|
| `cases` | `cases/<id>/` (one package) | match `valid`, and `satisfiedProfile` for WorldPackage cases (spec 6.1, 8, 9, 13) |
| `resolutionCases` | `resolution/<id>/root/` + `resolution/<id>/packages/` | validate `root` with `packages` as the only source and match `valid` (spec 11, 13) |
| `ewsCases` | `ews/<id>/world/`, `observations.yaml`, `expected-ews.yaml` | compile at `asOf` with `compiler` and produce an EWS equal to `expected-ews.yaml` under spec 12.2 equality, or refuse the input when `error: true` |
| `ewsCheckCases` | `ews-check/<id>/world/`, `ews.yaml` | check the EWS against the compiler output contract and match `valid` (spec 12.1) |

The `ewsCases` are the cross-runtime check: two runtimes that honour declarative bindings must produce the same EWS for the same World, View, State Compiler, observations, and `asOf`.

## Implementations

| Implementation | Language | Run |
|---|---|---|
| `src/ontle/` (reference) | Python | `python -m unittest tests.test_conformance tests.test_resolve tests.test_ews -v` |
| `implementations/typescript/` (clean-room) | TypeScript | `cd implementations/typescript && npm ci && npm test` |

## Running against the reference implementation

```bash
python -m unittest tests.test_conformance tests.test_resolve tests.test_ews -v
```
