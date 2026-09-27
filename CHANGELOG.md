# Changelog

## Unreleased

- Replace the unconditional WorldPackage View/State Compiler requirement with cumulative conformance profiles (`descriptive`, `viewable`, `stateful`, `model-ready`, `action-ready`); absent means `descriptive`. Starter templates declare `stateful`.
- `model-ready` requires a concrete EWS schema (`outputSchema.fields` or `outputSchemaRef`) on every State Compiler.
- WorldModel grounding references must have the form `<worldRef>#<asset path>`.
- Add evaluation lineage and evidence binding: versioned `EvaluationProfile`/`VerifierPackage`, `supersedes`, and pinned `CompatibilityEvidence` scoped to compatible Views/State Compilers. No new package kind.
- Add `conformance/` language-neutral suite and `schemas/compatibility-evidence.schema.json`; make the manifest schema profile-conditional.
- Add `ontle add verifier`; `ontle add compiler` generates a skeleton bound to the default View; `ontle inspect` reports declared vs satisfied profile.
- Examples: declare `action-ready`, add EWS output schemas, OpenUSD/ROS 2/LeRobot and ISA-95/OPC UA `standardBindings`, and an evaluation lineage example.
- Add `docs/STANDARDS_INTEROP.md`.
- Add `implementations/typescript/`, an independent clean-room TypeScript implementation (validator, resolver, EWS compiler/checker) that passes the full conformance suite; CI runs it.
- Add dependency resolution without a hosted registry: directory, `.owp.zip` (hash-verified), and `git+<url>@<rev>` sources; `ontle resolve` and `ontle validate --resolve` with cross-package World Model grounding checks.
- Standardize the Effective World State document and its output contract; add optional declarative State Compiler bindings (`latest`, `all`) with deterministic semantics; `ontle ews compile|check`.
- Extend `conformance/` with resolution, EWS compile, and EWS check cases.
- Add stable rule ids (spec Appendix A) to every validation, resolution, and EWS error; the conformance suite lists the rule ids each invalid case must report.
- Second review round: define the exact `owp.lock.json` format and archive layout (archives with unlocked files are rejected); timestamps are read and compared as text and must be valid calendar instants (the reference loader no longer converts unquoted YAML timestamps); JSON-data-model value equality in EWS compilation; code-point id ordering; opaque compilers are refused; dependency entries, `worldRef`, identity characters, `./` paths, and duplicate evaluation asset names are validated; hidden directories are skipped by directory sources.
- Conformance suite: 62 validation, 21 resolution (including packed `.owp.zip` and `git bundle` fixtures), 18 EWS compile, 14 EWS check cases; every invalid case lists its expected rule ids.
- `PackageExample` YAML must parse (its kind is not compared); an unreadable or unverifiable package source is an error, not a fallback; git sources accept local repository and `git bundle` paths.
- Add `ROADMAP.md`.
- Require Python 3.11+ (3.10 reaches end of life in October 2026); CI tests 3.11–3.14, and release builds use 3.14.
- Tighten the spec after an independent clean-room implementation review: a default View's `worldRef` is `self` or the package identity; evidence `subject` is the package identity; local version binding is by `metadata.name` and requires a matching `metadata.version`; exact-string reference comparison; explicit legacy manifest names, typed-YAML asset rules, open asset-kind vocabulary, and error/warning severity.
- Examples: declarative bindings, sample ObservationSets, and expected EWS for both reference Worlds.

## 0.2.0-alpha.2 — World View / EWS Contract Alignment

- Require every `WorldPackage` to package at least one `WorldViewProfile` and one `StateCompilerProfile`.
- Add generated default View/State Compiler assets to minimal, enterprise, and standalone GitHub World starters.
- Require every `WorldModelPackage` to declare `worldRef`, `compatibleWorldViews`, and `compatibleStateCompilers`.
- Require `EffectiveWorldState` as the logical WorldModel input contract and an explicit `RepresentationAdapterProfile` binding.
- Add `ontle add view` and `ontle add compiler` progressive scaffolding.
- Align Business AI and Physical AI examples to the same World -> View -> State Compiler -> EWS -> Adapter -> WorldModel chain.
- Strengthen validation and JSON Schema coverage for the above invariants.

## 0.2.0-alpha.1 — Public Alpha Candidate

- Establish `owp.yaml` as the single public package manifest.
- Establish `ontle` as the reference CLI.
- Add minimal and enterprise World starters, an ontology starter, and generic/multimodal World Model starters.
- Add Business AI and Physical AI reference examples.
- Add deterministic `.owp.zip` reference packing with SHA-256 lock verification.
- Add progressive asset scaffolding.
- Add GitHub CI/release workflows and standalone World repository starter.
- Add public asset-graph, runtime-boundary, and multimodal World Model documentation.
