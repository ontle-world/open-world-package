# Changelog

## Unreleased

- Add semantic binding (spec section 14): a `SemanticBinding` asset maps World names, EWS fields (`{class, path}`), observation types, and actions to CURIEs; a World names it with `spec.world.semanticBinding`. Prefixes come from dependency OntologyPackages; under resolution every CURIE must expand to a term they define, and conflicting prefixes are errors. Unscoped terms are a warning.
- `ontle inspect` reports `semanticCoverage`; `ontle ews compile --jsonld` prints the EWS with a JSON-LD `@context` from the binding.
- The `manufacturing-quality-world` example depends on `quality-ontology` and binds all seven EWS fields.
- Define the ontology contract (spec section 3.1): `spec.ontology` with `iri`, `prefixes`, typed `entrypoints` (`format`, `role`), `termIndex`, and pinned `externalImports`; ontology conformance profiles `vocabulary`, `schema`, `constrained`, `mapped`. Validation reads only the manifest, OWP YAML documents, and file existence; RDF content is not parsed for validity.
- Add `SemanticProfile` and `OntologyTermIndex` schemas; `OntologyTermIndex` joins the vocabulary.
- Add `ontle ontology index` (term index from schema entrypoints; RDF needs the optional `rdf` extra), `ontle export --format turtle|jsonld`, and term-index generation in `ontle pack` when it is required and missing.
- Breaking: `spec.ontology` is no longer free-form (for example the old `formats` key is rejected); the ontology template uses the new contract. `spec.conformance` is now allowed on OntologyPackages.
- Add the `examples/ontology/quality-ontology` example (owp-yaml schema, SHACL shapes, SSSOM mappings; profile `mapped`).
- Add experimental asset kinds (spec Appendix C): `TaskSetProfile`, `WorkPatternProfile`, `ArtifactContract`, `ArtifactTemplate`, `ConsumerRepresentationProfile` (one block per actor kind: `human`, `agent`, `model`, `system`), and `KnowledgeAsset`. They are checked against `schemas/experimental/` with warnings only (`experimental.field`, `experimental.value`, `experimental.reference`); extension rules stay errors.
- Add experimental value sets in `vocab/value-sets.yaml`, including 22 work patterns.
- Add experimental World View specialization: `spec.specializes` and `spec.projection.exclude`; `ontle inspect --resolved-views` shows resolved Views.
- Add `ontle inspect --graph` (reference graph with informative relation names) and `ontle add task|pattern|artifact|template|consumer|knowledge` and `ontle add view --specializes`.
- Conformance cases may list `warnings` that an implementation must report.
- Add the `sales-prioritization-world` example (actor-specialized Views, tasks, artifacts, consumers, sample observations and EWS); extend `manufacturing-quality-world` with an RCA task, knowledge, report contract, and consumer.
- Add publisher extensions (spec section 13): an extension is a `spec.dependencies` entry with `as` (and optional `mustUnderstand`); extension kinds are `<extension>:<Kind>`; extension data goes in `extensions` blocks; a package that defines an extension declares `spec.extensionDefinition`. Undeclared extension names are errors.
- Defined fields are enforced: the manifest, CompatibilityEvidence, ObservationSet, and EWS documents reject keys that are neither defined fields nor `extensions` blocks (`schema.unknown-field`). The manifest JSON Schema now lists every field already in use (`dependencies`, `worldModel.description`, `world.boundary`, `domains`, and others); all four JSON Schemas are closed.
- Breaking for packages that used a namespaced kind such as `acme:SafetyCase` without declaring it: add a dependency with `as: acme`. The conformance case `asset-namespaced-kind` is replaced by `extension-kind-declared` and `extension-kind-undeclared`.
- Restructure `vocab/asset-kinds.yaml`: camelCase groups aligned with the asset-graph families (Attestation moves to `governancePublication`) and a `stability` per kind; experimental kinds produce the warning `asset.kind-experimental`. The reference implementation reads this file instead of a copied list.
- Add `spec/rule-ids.yaml`, a machine-readable registry of every error and warning id; warnings now have ids (spec Appendix A). Tests check that the spec, the conformance suite, and both implementations use exactly the registered ids.
- Add `ontle add extension <ref> [--as <name>] [--must-understand]`; `ontle inspect` lists declared extensions.
- Add spec Appendix B (notation).
- Define ExternalRef (spec section 5.1): `provider`, `uri`, `revision`, `digest`, `mediaType`, `size`, `status` (`bound`/`unbound`); provider-specific pinning with the warning `ref.unpinned`; several files pinned through a file list in the `owp.lock.json` `files` format; `repository` is accepted as the deprecated name of `uri` (warning `ref.legacy-shape`). The manifest's `spec.assets[].ref` is validated; examples and templates use `ref: {status: unbound}` instead of `ref: null`.
- Example: the multimodal World Model's evidence note moves from `spec.note` to `metadata.description`.
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
- Conformance suite: 135 validation, 27 resolution (including packed `.owp.zip` and `git bundle` fixtures), 20 EWS compile, 16 EWS check cases; every invalid case lists its expected rule ids.
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
