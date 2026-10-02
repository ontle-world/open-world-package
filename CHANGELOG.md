# Changelog

## Unreleased

- The spec is split: `spec/OWP_SPEC.md` keeps the core (sections 1–8, 10, 11, 13, Appendices A, B); `OWP_SEMANTICS.md` (3.1, 14), `OWP_EVALUATION_AND_STATE.md` (9, 12, 15), and `OWP_EXPERIMENTAL.md` (Appendix C) hold the profiles. Section numbers are unchanged. `docs/REFERENCES.md` lists the six reference forms and where each is used.
- Asset files may omit `apiVersion` (inherited from `owp.yaml`); a different value is `asset.api-version`. Generated assets omit it.
- `ontle validate` prints errors that are likely consequences of a misspelt field under that field's error.
- Promote experimental fields used in three domains that do not depend on experimental kinds (spec section 15): EvaluationProfile `assessmentKind`, `subject`, `objective`, `criteria`, `verifierRef`, `evidenceRefs`, `validityScope`, `resultSchemaRef`; all ScenarioProfile fields; CapabilityContract `context`, `requiredInputs`, `capacity`, `maturity`, `validityScope`, `evidenceRefs`; WorldViewProfile `constraints`, `evidenceRefs`. Their checks are errors (`evaluation.*`, `scenario.*`); the value sets `assessmentKinds`, `evaluationSubjects`, `scenarioEngines` are standard.
- `asset.kind-experimental` is reported once per kind with a count.
- Generated files carry a `yaml-language-server` schema line and a one-line hint; placeholders are empty strings, so editors validate and complete them. `owp.yaml` keeps its leading comments when the CLI rewrites it.
- `ontle sync` lists asset files that `spec.assets` is missing; `ontle inspect` reports the experimental kinds and fields a package uses.
- Every experimental profile is used in at least three example domains (manufacturing, sales, research, robotics); see `docs/PROFILE_PROMOTION.md`.
- Round-trip checks: `tests/test_roundtrip.py` (pack/unpack and YAML re-serialization) and the TypeScript `scripts/check-roundtrip.mjs`.
- `schema.unknown-field` messages suggest the closest defined field. `docs/QUICKSTART.md` covers ontology binding, actors and tasks, extensions, and publishing.
- Add `docs/GLOSSARY.md` (actor, role, capability, permission, authority, responsibility, accountability, artifact type/representation/format/storage, verification/validation/evaluation/review/approval, scenario) and `docs/PROFILE_PROMOTION.md` (gates and status for experimental profiles).
- `ontle add actor|role|delegation|capability`; `ontle inspect --graph` shows actor, role, delegation, view, task, evaluation, and scenario relations.
- Examples: `research/assay-optimization-world` (third domain); `manufacturing-quality-world` and `sales-prioritization-world` gain actors, roles, delegations, capabilities, a work pattern graph, an evaluation, and a scenario.
- WorldViewProfile, EvaluationProfile, ScenarioProfile, and CapabilityContract have JSON Schemas; undefined keys are errors. Experimental fields (spec Appendix C.4): World View `purpose.actorRef`/`roleRef`/`taskRef`, `constraints`, `evidenceRefs`; Evaluation `assessmentKind` (verification, validation, evaluation, review, approval), `subject`, `objective`, `criteria`, `verifierRef`, `evaluatorRef`, `evidenceRefs`, `validityScope`, `resultSchemaRef`; Scenario `baselineStateRef`, `assumptions`, `intervention`, `engine` (value set `scenarioEngines`), `timeHorizon`, `constraints`, `uncertainty`, `confidence`, `expectedOutcome`; Capability `outcomeRefs`, `context`, `requiredInputs`, `capacity`, `maturity`, `validityScope`.
- TaskSetProfile composes actors (`requires.actors`), work patterns (`workPatternRefs`), and `mayUse.scenarios`/`skills`/`tools`.
- Experimental actors, roles, and delegation (spec Appendix C.3): `ActorProfile` (`actorType` from the value set `actorTypes`), `RoleProfile` (permissions, authorities with ceilings, responsibilities, accountabilities), and `DelegationProfile` (scope, period, revocation, escalation; the warning `experimental.delegation-exceeds-authority`). ConsumerRepresentationProfile gains `actor.ref`.
- Experimental work pattern graphs (spec Appendix C.2): nodes, transitions, guards, events, and loops; node families in the value set `workNodeFamilies`; each of the 22 work patterns names its family. WorkPatternProfile gains `objective`, `inputContracts`, `outputContracts`, `worldViewRef`, `governanceRefs`.
- ArtifactContract gains `schemaRef`, `storage`, `allowedOperations` (value set `artifactOperations`), `sourceRefs`, `evidenceRefs`, and `supersedes`.
- `scripts/generate_experimental_schemas.py` regenerates `schemas/experimental/`; `scripts/sync_rule_ids.py` regenerates `spec/rule-ids.yaml`.
- Lock format `owp-lock/v1alpha2` (spec section 7): `externals` records every bound ExternalRef; vendored content is listed with `vendoredPath`; verifiers check `externals` against the manifest.
- OCI artifact profile (spec section 7.1): artifact, config, layer, and evidence media types. `ontle push` (and `oci:`/`oci-layout:` resolver sources) use `oras`.
- Static package index (spec section 11.1, `schemas/package-index.schema.json`): `ontle index build` and the `index:` resolver source, with digest checks.
- Evidence published outside the package (spec section 9.1): `spec.subjectDigest`; `ontle evidence check` and `ontle evidence attach` (OCI referrer).
- `ontle fetch` (download and verify external content, including file lists), `ontle lock` (pin https references), `ontle pack --vendor`, `ontle sign` and `ontle verify --signature` (cosign; keyless by default, `--key` for key pairs), and `ontle catalog --format dcat|croissant|hf-card`.
- Add `schemas/owp-lock.schema.json`.
- Add knowledge extraction (spec Appendix C.1, experimental): a `KnowledgeExtractionProfile` maps query result rows over a KnowledgeAsset to an ObservationSet with a deterministic transform (ids from columns, snapshot-time default, repeated join rows collapse). EWS is unchanged. ObservationSet gains an optional `spec.provenance` (`extraction`, `parameters`, `snapshot`). Reading a `multi` type with `select: latest` is the warning `compiler.multi-latest`.
- Add `ontle kg extract` (runs SPARQL over a local RDF KnowledgeAsset with the `rdf` extra, or transforms a `--results` file) and repeatable `--observations` for `ontle ews compile`.
- Conformance: new `extractionCases` section (12 cases) and 2 validation cases.
- Example: `manufacturing-quality-world` adds a small plant knowledge graph and a `claim-context` extraction; the State Compiler and binding cover 9 fields.
- Add semantic binding (spec section 14): a `SemanticBinding` asset maps World names, EWS fields (`{class, path}`), observation types, and actions to CURIEs; a World names it with `spec.world.semanticBinding`. Prefixes come from dependency OntologyPackages; under resolution every CURIE must expand to a term they define, and conflicting prefixes are errors. Unscoped terms are a warning.
- `ontle inspect` reports `semanticCoverage`; `ontle ews compile --jsonld` prints the EWS with a JSON-LD `@context` from the binding.
- The `manufacturing-quality-world` example depends on `quality-ontology` and binds all seven EWS fields.
- Define the ontology contract (spec section 3.1): `spec.ontology` with `iri`, `prefixes`, typed `entrypoints` (`format`, `role`), `termIndex`, and pinned `externalImports`; ontology conformance profiles `vocabulary`, `schema`, `constrained`, `mapped`. Validation reads only the manifest, OWP YAML documents, and file existence; RDF content is not parsed for validity.
- Add `SemanticProfile` and `OntologyTermIndex` schemas; `OntologyTermIndex` joins the vocabulary.
- Add `ontle ontology index` (term index from schema entrypoints; RDF needs the optional `rdf` extra), `ontle export --format turtle|jsonld`, and term-index generation in `ontle pack` when it is required and missing.
- `spec.ontology` follows the new contract (the old `formats` key is rejected); the ontology template uses it. `spec.conformance` is allowed on OntologyPackages.
- Add the `examples/ontology/quality-ontology` example (owp-yaml schema, SHACL shapes, SSSOM mappings; profile `mapped`).
- Add experimental asset kinds (spec Appendix C): `TaskSetProfile`, `WorkPatternProfile`, `ArtifactContract`, `ArtifactTemplate`, `ConsumerRepresentationProfile` (one block per actor kind: `human`, `agent`, `model`, `system`), and `KnowledgeAsset`. They are checked against `schemas/experimental/` with warnings only (`experimental.field`, `experimental.value`, `experimental.reference`); extension rules stay errors.
- Add experimental value sets in `vocab/value-sets.yaml`, including 22 work patterns.
- Add experimental World View specialization: `spec.specializes` and `spec.projection.exclude`; `ontle inspect --resolved-views` shows resolved Views.
- Add `ontle inspect --graph` (reference graph with informative relation names) and `ontle add task|pattern|artifact|template|consumer|knowledge` and `ontle add view --specializes`.
- Conformance cases may list `warnings` that an implementation must report.
- Add the `sales-prioritization-world` example (actor-specialized Views, tasks, artifacts, consumers, sample observations and EWS); extend `manufacturing-quality-world` with an RCA task, knowledge, report contract, and consumer.
- Add publisher extensions (spec section 13): an extension is a `spec.dependencies` entry with `as` (and optional `mustUnderstand`); extension kinds are `<extension>:<Kind>`; extension data goes in `extensions` blocks; a package that defines an extension declares `spec.extensionDefinition`. Undeclared extension names are errors.
- Defined fields are enforced: the manifest, CompatibilityEvidence, ObservationSet, and EWS documents reject keys that are neither defined fields nor `extensions` blocks (`schema.unknown-field`). The manifest JSON Schema now lists every field already in use (`dependencies`, `worldModel.description`, `world.boundary`, `domains`, and others); all four JSON Schemas are closed.
- The conformance case `asset-namespaced-kind` is replaced by `extension-kind-declared` and `extension-kind-undeclared`.
- Restructure `vocab/asset-kinds.yaml`: camelCase groups aligned with the asset-graph families (Attestation moves to `governancePublication`) and a `stability` per kind; experimental kinds produce the warning `asset.kind-experimental`. The reference implementation reads this file instead of a copied list.
- Add `spec/rule-ids.yaml`, a machine-readable registry of every error and warning id; warnings now have ids (spec Appendix A). Tests check that the spec, the conformance suite, and both implementations use exactly the registered ids.
- Add `ontle add extension <ref> [--as <name>] [--must-understand]`; `ontle inspect` lists declared extensions.
- Add spec Appendix B (notation).
- Define ExternalRef (spec section 5.1): `provider`, `uri`, `revision`, `digest`, `mediaType`, `size`, `status` (`bound`/`unbound`); provider-specific pinning with the warning `ref.unpinned`; several files pinned through a file list in the `owp.lock.json` `files` format. The manifest's `spec.assets[].ref` is validated; examples and templates use `ref: {status: unbound}` instead of `ref: null`.
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
- Conformance suite: 165 validation, 27 resolution (including packed `.owp.zip` and `git bundle` fixtures), 20 EWS compile, 16 EWS check, 12 extraction cases; every invalid case lists its expected rule ids.
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
