# Open World Package Specification — Public Alpha

This document defines the public-alpha authoring and package contract used by the ONTLE reference implementation.

## 1. Goals

OWP packages portable contracts for:

- Ontology/Semantic packages
- World packages
- World Model packages

The standard does not require a particular runtime, model checkpoint format, database, graph store, simulator, or hosted registry.

## 2. Manifest

Every package root contains exactly one machine manifest:

```text
owp.yaml
```

Required identity:

```yaml
apiVersion: openworld/v1alpha1
kind: WorldPackage
metadata:
  namespace: example
  name: manufacturing-quality
  version: 0.1.0
```

Logical package identity:

```text
<namespace>/<name>@<version>
```

Version uses SemVer. `namespace` and `name` MUST NOT contain `/`, `@`, `#`, or whitespace.

`spec.dependencies`, when present, lists exact package references (section 11); a version range makes the package invalid even without resolution. A dependency entry may also declare an extension (section 13).

A manifest contains only the fields defined by `schemas/owp-manifest.schema.json` and `extensions` blocks (section 13); any other key is an error (section 8).

## 3. Package kinds

```text
OntologyPackage
WorldPackage
WorldModelPackage
```

### WorldPackage

Human card: `WORLD.md`.

A World package describes an explicit, intentionally incomplete representation. It may reference World View and State Compiler profiles, semantic profiles, interfaces, models, scenarios, datasets, tests, and operational assets. Business and Physical AI use the same package contract; domain differences are expressed through typed assets.

A World is useful without a World Model. Reference and taxonomy Worlds (organizations, material taxonomies, regulatory concepts) need not compile state. A WorldPackage therefore declares a conformance profile (section 6.1) that states how far along the World -> View -> EWS chain it goes. Starter templates generate a default View and State Compiler and declare `stateful`.

### WorldModelPackage

Human card: `WORLDMODEL.md`.

A World Model package declares:

- semantic grounding (`worldRef` or compatible World contract)
- roles/capabilities
- one or more compatible World View contracts (`compatibleWorldViews`, required)
- one or more compatible State Compiler contracts (`compatibleStateCompilers`, required)
- representation adapter contract
- runtime input contract `EffectiveWorldState`
- input/output semantics
- validity envelope
- implementation/artifact references
- evaluation references and, optionally, compatibility evidence (section 9)

`semanticGrounding.worldRef` is an exact package reference `<namespace>/<name>@<semver>`. Entries in `compatibleWorldViews` and `compatibleStateCompilers` have the form `<worldRef>#<asset path>`, where `<worldRef>` equals `semanticGrounding.worldRef` and `<asset path>` is the package-relative path of the asset inside that World package:

```yaml
semanticGrounding:
  worldRef: example/mobile-manipulation-world@0.1.0
  compatibleWorldViews:
  - example/mobile-manipulation-world@0.1.0#views/pick-place-task.yaml
  compatibleStateCompilers:
  - example/mobile-manipulation-world@0.1.0#state/pick-place-compiler.yaml
```

References and package-relative paths are compared as exact strings, without normalization. Local asset paths, `defaultView`, `defaultStateCompiler`, `worldViewRef`, and `<asset path>` MUST be relative POSIX paths without a leading `./`, written exactly as they appear in `spec.assets`. Validating a single package does not resolve the referenced World; section 11 defines the cross-package checks.

OWP does not standardize model weight bytes. Architecture names (VLM, VLA, video world model, solver) are expressed as `roles` and modalities, not as separate package kinds.

### OntologyPackage

Human card: `ONTOLOGY.md`. An OntologyPackage MUST declare `spec.ontology` as a mapping. Section 3.1 defines its fields.

### 3.1 Ontology contract

```yaml
spec:
  ontology:
    description: ONTOLOGY.md
    iri: https://w3id.org/acme/quality#              # namespace IRI of the ontology
    prefixes:
      q: https://w3id.org/acme/quality#
    entrypoints:
    - {path: semantics/core.yaml, format: owp-yaml, role: schema}
    - {path: semantics/shapes.ttl, format: turtle, role: shapes}
    - {path: mappings/isa95.sssom.tsv, format: sssom-tsv, role: mappings}
    termIndex: semantics/terms.yaml                  # required when no schema entrypoint is owp-yaml
    externalImports:                                 # ontologies outside OWP, pinned (section 5.1)
    - iri: http://qudt.org/schema/qudt/
      ref: {provider: https, uri: https://qudt.org/2.1/schema/qudt, digest: "sha256:..."}
  conformance:
    profile: mapped
```

- Ontology packages this ontology builds on are listed in `spec.dependencies`; there is no separate import list.
- `iri` and every `prefixes` value are absolute IRIs; prefix names match `[A-Za-z][A-Za-z0-9_-]*`.
- Each entrypoint has a package-relative `path` naming an existing file inside the package, a `format` (`owp-yaml`, `turtle`, `jsonld`, `owl-xml`, `ntriples`, `linkml`, `sssom-tsv`), and a `role` (`schema`, `shapes`, `mappings`, `labels`).
- An `owp-yaml` entrypoint is a `SemanticProfile` document (`schemas/semantic-profile.schema.json`): `types` (each with `id`, optional `label`, `subClassOf`, `enum`, and `properties` with `id` and `range`) and `relations` (`id`, `domain`, `range`). Identifiers are CURIEs whose prefixes are declared in `prefixes`, or absolute IRIs.
- `termIndex` names an `OntologyTermIndex` document inside the package (`schemas/ontology-term-index.schema.json`) listing term IRIs with a type (`class`, `property`, `individual`, `datatype`, `concept`). The reference CLI writes it with `ontle ontology index`, and `ontle pack` writes it when it is required and missing and the optional RDF tooling is installed.
- Validation reads only the manifest, OWP YAML documents, and file existence. RDF, LinkML, and SSSOM content is not parsed for validity, so every implementation reaches the same verdict. Tooling may check that content and report it separately.

The terms an ontology defines are the expanded identifiers of its `owp-yaml` schema entrypoints (types, their properties, and relations) together with the terms in its `termIndex`.

**Ontology conformance profiles.** An OntologyPackage MAY declare `spec.conformance`; when present, its `profile` MUST be one of the profiles below. Profiles are cumulative; when `spec.conformance` is absent, no profile is required, and a validator SHOULD still report the highest satisfied profile.

| Profile | Adds |
|---|---|
| `vocabulary` | `iri` and at least one entrypoint |
| `schema` | an entrypoint with role `schema`; if none of them is `owp-yaml`, a `termIndex` |
| `constrained` | an entrypoint with role `shapes` (for example SHACL) |
| `mapped` | an entrypoint with role `mappings` (for example SSSOM) |

## 4. Common package layout

```text
owp.yaml
WORLD.md | WORLDMODEL.md | ONTOLOGY.md
views/            WorldPackage, profile viewable and above
state/            WorldPackage, profile stateful and above
examples/
semantics/        optional
interfaces/       optional
mappings/         optional
models/           optional
scenarios/        optional
datasets/         optional
eval/             optional
tests/            optional
assets/           optional
```

## 5. Assets

`spec.assets` can reference local package assets or external artifacts. An entry has `kind`, exactly one of `path` and `ref`, and optionally an `extensions` block. `kind` is a vocabulary kind or an extension kind `<extension>:<Kind>` (section 13).

Local example:

```yaml
spec:
  assets:
    - kind: ScenarioProfile
      path: scenarios/pick-place.yaml
```

External artifact example:

```yaml
spec:
  assets:
    - kind: ModelArtifact
      ref:
        provider: huggingface
        uri: hf://organization/model-name
        revision: 0123456789abcdef0123456789abcdef01234567
```

### 5.1 External references

An external reference (`ExternalRef`) points at an artifact outside the package. The manifest's `spec.assets[].ref` is an ExternalRef; asset documents SHOULD use the same shape wherever they point outside the package (for example `ModelArtifact.spec.artifactRef` or a `standardBindings` entry's `ref`). An asset has at most one ExternalRef for its content: an asset with a local description file puts it in that file, not also in the manifest entry.

```yaml
ref:
  provider: huggingface                   # huggingface | oci | git | https | s3 | gcs | doi | <extension>:<provider>
  uri: hf://datasets/organization/name
  revision: <commit hash>
  digest: "sha256:<64 lowercase hex>"
  mediaType: application/vnd.openworld.filelist+json
  size: 1234567890                        # informative
  status: bound                           # bound (default) | unbound
```

- A bound reference declares `provider` and `uri`. An `unbound` reference records that no artifact has been chosen yet; its other fields are optional. Examples MUST NOT invent artifacts; they use `status: unbound` instead.
- `provider` is one of the listed values or an extension provider `<extension>:<provider>` (section 13).
- `digest` is `sha256:` followed by 64 lowercase hex digits. `size` is a non-negative integer.
- `repository` is the deprecated name of `uri`; it is accepted with the warning `ref.legacy-shape` and MUST NOT appear together with `uri`.
- A bound reference SHOULD be pinned; otherwise the warning `ref.unpinned` applies. Pinning depends on the provider:

| Provider | Pinned by |
|---|---|
| `git`, `huggingface` | `revision` is a commit hash (40 or 64 lowercase hex digits), or `digest` |
| `oci` | `digest` of the OCI manifest |
| `https`, `s3`, `gcs`, `doi` | `digest` of the file bytes |
| extension providers | defined by the extension |

- Several files are pinned together through a file list: an artifact with `mediaType: application/vnd.openworld.filelist+json` whose content uses the `files` format of `owp.lock.json` (section 7), with `digest` taken over the list. A consumer verifies the list's digest and then each listed file.
- This alpha validates ExternalRefs in the manifest. ExternalRefs inside asset documents are validated once their asset kind has a JSON Schema.

## 6. World/View/EWS/Model rule

```text
World(schema)
-> World View            [packaged WorldViewProfile]
-> State Compiler        [packaged StateCompilerProfile]
-> Effective World State [runtime-derived]
-> Representation Adapter
-> World Model
```

A World Model must not imply that it models every entity/state known to a World package. `worldRef` alone is insufficient: a valid WorldModelPackage MUST name the World View(s) and State Compiler(s) for which its input semantics are valid.

The model runtime path is explicit:

```text
compatible World View
-> compatible State Compiler
-> EffectiveWorldState
-> RepresentationAdapterProfile
-> model-native input
```

`spec.worldModel.inputs.contract` MUST be `EffectiveWorldState`, and `spec.worldModel.representation.adapterRef` MUST point to the packaged Representation Adapter used for model-native conversion. An identity adapter is valid when the model consumes the EWS shape directly. The adapter named by `adapterRef` MUST declare `spec.source: EffectiveWorldState`; other packaged adapters are not checked.

### 6.1 WorldPackage conformance profiles

A WorldPackage MAY declare a conformance profile. Profiles are cumulative; when `spec.conformance` is absent the profile is `descriptive`.

```yaml
spec:
  conformance:
    profile: stateful
```

| Profile | Adds |
|---|---|
| `descriptive` | `spec.world` (always required for a WorldPackage) with `spec.world.definition`, or a `WorldDefinition` asset |
| `viewable` | at least one `WorldViewProfile`; `spec.world.defaultView` is the path of a local `WorldViewProfile` asset whose `spec.worldRef` is `self` or this package's identity |
| `stateful` | at least one `StateCompilerProfile`; `spec.world.defaultStateCompiler` is the path of a local `StateCompilerProfile` whose `spec.worldViewRef` equals `spec.world.defaultView`; every local `StateCompilerProfile` has a `spec.worldViewRef` naming a local `WorldViewProfile` path and `spec.outputContract: EffectiveWorldState` |
| `stateful` (bindings) | a State Compiler's `spec.bindings`, when present, is well formed (section 12.2); a malformed binding fails `stateful` for both the declared and the satisfied profile |
| `model-ready` | every local `StateCompilerProfile` declares a concrete EWS schema: a non-empty `spec.outputSchema.fields` list, or `spec.outputSchemaRef` |
| `action-ready` | `ActionBindingProfile`, `CommitContract`, and `EffectVerificationProfile` assets |

Requirements of a profile are checked only when that profile or a higher one is declared. "At least one X asset" and the `action-ready` assets may be local (`path`) or external (`ref`); assets named by `defaultView`, `defaultStateCompiler`, or `worldViewRef`, and State Compilers checked for content, are local. `outputSchemaRef` is any non-empty string; this alpha does not resolve it. A validator MUST reject a package that does not satisfy its declared profile, and SHOULD report the highest profile the package satisfies independent of the declaration.

Every WorldModelPackage requires compatible View and State Compiler references regardless of the World's profile; in practice the referenced World is `stateful` or higher.

## 7. Integrity

`ontle pack` creates a deterministic ZIP-compatible OWP archive (`.owp.zip`). The package root is the archive root. The archive contains the package files and one `owp.lock.json`:

```json
{
  "format": "owp-lock/v1alpha1",
  "manifest": "owp.yaml",
  "manifest_sha256": "<hex sha256 of owp.yaml>",
  "files": [{"path": "<posix path>", "sha256": "<hex sha256>", "size": 123}]
}
```

`files` lists every archived file except `owp.lock.json` itself (including `owp.yaml`). `manifest_sha256` MUST match `owp.yaml`; `size` is informative. Hashes are lowercase hex without prefix. An archive is valid only when its entries other than `owp.lock.json` are exactly the locked paths and every hash matches. The digest of an archive is the SHA-256 of the archive bytes. Registry/OCI transport can be layered on top without changing authoring semantics.

## 8. Validation

The reference validator checks at minimum:

- manifest parseability
- package kind
- namespace/name/version
- required human card
- local asset references
- the declared WorldPackage conformance profile (section 6.1)
- WorldModel `worldRef` + compatible World View(s) + compatible State Compiler(s) in `<worldRef>#<path>` form + Representation Adapter
- evaluation lineage and evidence binding (section 9)
- declarative State Compiler bindings, when present, at `stateful` and above (section 12.2)
- absence of legacy manifest names

Precise meaning of the checks above:

- **Legacy manifests:** `package.yaml` or `world.yaml` at the package root makes the package invalid.
- **Local asset paths** are package-relative; a path that resolves outside the package root (for example `../x.yaml` or an absolute path) is invalid; the file must exist; the same path may be listed once.
- **Dependencies:** every `spec.dependencies` entry is `<namespace>/<name>@<semver>` or a mapping whose `ref` is; otherwise the package is invalid.
- **Evaluation asset names:** two local assets of the same kind (EvaluationProfile or VerifierPackage) MUST NOT share `metadata.name`. A non-SemVer `metadata.version` on them is an error; a missing one is a warning.
- **Typed local YAML assets:** every local `.yaml`/`.yml` asset MUST parse. If an asset other than `PackageExample` declares a top-level `kind`, that kind MUST equal the manifest entry's `kind`. `PackageExample` files may contain any document (for example an `ObservationSet`), so their `kind` is not compared.
- **Asset-kind vocabulary** (`vocab/asset-kinds.yaml`) is open: a kind without `:` that is not in the vocabulary is a warning; a vocabulary kind marked `stability: experimental` is a warning, because it may change or be removed; a kind containing `:` is an extension kind and follows section 13.
- **Defined fields:** the manifest, CompatibilityEvidence, SemanticProfile, OntologyTermIndex, and SemanticBinding assets, ObservationSet documents, and EWS documents contain only the fields defined by their JSON Schemas under `schemas/` and `extensions` blocks (section 13). Any other key, including a misspelt field or a field named `<extension>:<field>`, is an error. Objects the schemas mark as open containers (for example `spec.validity`) are not checked inside. Asset kinds without a JSON Schema are checked only for `extensions` blocks in their top-level `metadata` and `spec`. `PackageExample` files are not checked, because they may hold any document.
- **Severity:** MUST/required rules are errors and make the package invalid. Warnings never invalidate; Appendix A lists them.
- **Satisfied profile** is computed even when the declared profile is invalid or unknown.
- **Experimental kinds and fields** (Appendix C) produce warnings only; they never make a package invalid, except that extension rules (section 13) still apply.

The reference validator also rejects legacy manifest names, validates typed local YAML asset references, detects duplicate paths, and requires a Representation Adapter for every WorldModelPackage (an identity adapter is valid when no transform is needed). Additional domain-specific validators may be layered on top.

Implementations can check agreement with the reference validator using the language-neutral suite in `conformance/`, which also covers dependency resolution (section 11) and EWS documents (section 12).

## 9. Evaluation lineage and evidence binding

A score is reusable only together with the exact evaluation that produced it. OWP records that binding; it does not run, triage, generate, or evolve evaluations. Failure triage, eval generation, golden-case accumulation, replay/regression/shadow runs, and promotion or rollback of evaluation criteria belong to runtimes and registries layered on top; their outputs re-enter OWP as new versions and new evidence.

No separate evaluation package kind exists. Evaluation assets are ordinary typed assets, usually in a WorldModelPackage.

`EvaluationProfile` and `VerifierPackage` assets SHOULD declare `metadata.version` (SemVer). A changed evaluation declares its lineage:

```yaml
kind: EvaluationProfile
metadata:
  name: manipulation-basic
  version: 0.2.0
spec:
  supersedes: manipulation-basic@0.1.0
  changedBecause:
  - Controller-accepted grasps were counted as success without a verified pose change.
```

A `CompatibilityEvidence` asset binds a result to pinned versions and to a scope within the model's declared applicability:

```yaml
kind: CompatibilityEvidence
metadata:
  name: reference-sim-pick-place
spec:
  subject: example/multimodal-action-world-model@0.1.0
  evaluationProfile: manipulation-basic@0.2.0          # required, pinned
  verifier: pick-place-effect-verifier@0.1.0           # optional, pinned
  goldenSet: pick-place-regression@1.0.0               # optional, pinned
  scope:
    worldRef: example/mobile-manipulation-world@0.1.0                                  # required
    worldView: example/mobile-manipulation-world@0.1.0#views/pick-place-task.yaml       # required
    stateCompiler: example/mobile-manipulation-world@0.1.0#state/pick-place-compiler.yaml
    environment: example/mobile-manipulation-world@0.1.0#environment/reference-environment.yaml
    task: pick_place
  result:
    metrics: {task_success: 0.92}
```

Rules:

- `evaluationProfile`, `verifier`, `goldenSet`, and `dataset` use `<name>@<exact-semver>`. Ranges are not allowed.
- Inside a WorldModelPackage, `subject` MUST equal the package identity `<namespace>/<name>@<version>`.
- A reference `<name>@<version>` is packaged locally when an asset of the bound kind has `metadata.name` equal to `<name>`. That asset MUST then declare `metadata.version` equal to `<version>`; an unversioned local asset does not satisfy the binding. References to assets that are not packaged locally are accepted as external.
- `supersedes`, when present, is a pinned reference. `changedBecause` is recommended and not validated in this alpha.
- Inside a WorldModelPackage, `scope.worldRef` equals `semanticGrounding.worldRef`, `scope.worldView` is one of `compatibleWorldViews`, and `scope.stateCompiler`, when present, is one of `compatibleStateCompilers`.
- Changing an objective or constraint is a World/View change, not an evaluation change, and is versioned with the World package.

JSON Schema: `schemas/compatibility-evidence.schema.json`.

## 10. Relationship to adjacent standards (informative)

OWP is a glue contract, not a replacement for existing standards. Scene description (OpenUSD), scenarios (ASAM OpenSCENARIO), robot interfaces (ROS 2), episodic datasets (LeRobot), enterprise-control models (ISA-95), industrial information models (OPC UA), model/dataset cards (Hugging Face), model signatures (MLflow), and content-addressed distribution (OCI) stay authoritative in their domains. OWP records how their artifacts relate inside one World, View, and model applicability scope. See `docs/STANDARDS_INTEROP.md`.

## 11. Dependency resolution

`spec.dependencies` lists exact package references `<namespace>/<name>@<version>` (strings), or mappings `{ref, source}` where `source` is a package source used for that dependency before the global sources. Version ranges are not allowed.

A resolver finds each reference in an ordered list of package sources. This alpha defines three source types; a registry or OCI transport is another source type and does not change these rules:

| Source | Form | Revision recorded |
|---|---|---|
| directory | a path containing `owp.yaml`, or packages up to two directory levels below it, or `*.owp.zip` files in it | none |
| archive | a path ending in `.owp.zip`; its `owp.lock.json` hashes MUST verify before use | `sha256:<archive digest>` |
| git | `git+<url>@<rev>[#subdir=<path>]`; `<url>` may be a remote URL, a local repository path, or a `git bundle` file; a relative local path is resolved like a directory source; `<rev>` SHOULD be an immutable tag or commit; `<subdir>` is scanned like a directory source | `git:<commit>` |

Resolution rules:

- Dependencies are resolved transitively, in declaration order, depth first.
- One `<namespace>/<name>` resolves to exactly one version in a closure; a second version is a conflict error.
- Cycles are errors.
- A source that cannot be read or verified (an archive failing verification, a failed git fetch, a missing directory) is an error (`resolve.source`), even if another source could supply the package; resolvers MUST NOT silently fall back.
- Every resolved package MUST itself be valid under single-package validation (sections 6.1, 8, 9).
- The root package is part of the closure: depending on its own identity is a cycle, and on its own name at another version is a conflict.
- The cross-package rules below apply to every WorldModelPackage in the closure, not only the root.

Directory sources: candidates are `<dir>/owp.yaml`, then all `<dir>/*/owp.yaml` in sorted order, then all `<dir>/*/*/owp.yaml` in sorted order, then `<dir>/*.owp.zip` (directly in `<dir>` only) in sorted order. Directories whose name starts with `.` are skipped. When two candidates in one source share an identity, the first in this order wins. A relative `source` in a `{ref, source}` dependency is resolved against the declaring package's directory. `ONTLE_PATH` uses the platform path-list separator.

Cross-package rule for extensions: a dependency declared with `as` (section 13) MUST resolve to a package that declares `spec.extensionDefinition`.

Cross-package rules for a WorldModelPackage:

- `semanticGrounding.worldRef` MUST be listed in `spec.dependencies` and resolve to a WorldPackage.
- Each `compatibleWorldViews` path names a `WorldViewProfile` asset of that World; each `compatibleStateCompilers` path names a `StateCompilerProfile` asset of that World.
- Each compatible State Compiler's `spec.worldViewRef` is one of the model's compatible View paths.

The reference CLI: `ontle resolve`, `ontle validate --resolve`, with `--source` (repeatable) and the `ONTLE_PATH` environment variable.

## 12. Effective World State documents

An EWS is runtime-derived and is not a registry asset, but its document form is standardized so that EWS produced by different runtimes can be compared and checked.

```yaml
apiVersion: openworld/v1alpha1
kind: EffectiveWorldState
spec:
  worldRef: example/w@0.1.0
  worldView: example/w@0.1.0#views/task.yaml
  stateCompiler: example/w@0.1.0#state/task-compiler.yaml
  context:
    asOf: "2026-01-01T00:00:10Z"
  state: {a.latest: 2}
  unresolved: {b.pose: [[0.42, 0.1], [0.43, 0.1]]}
  missing: [c.unbound]
  provenance: {a.latest: [o2], b.pose: [o5, o6]}
```

Timestamps are UTC strings `YYYY-MM-DDTHH:MM:SSZ` that denote a valid calendar instant (no leap seconds) and are compared as text. YAML authors SHOULD quote them. An implementation MUST read an unquoted timestamp as its source text and MUST NOT convert it to another representation. ObservationSet and EWS documents are loaded with YAML 1.2 core schema rules into the JSON data model (YAML 1.1 loaders that produce date objects must be configured not to), including values inside `values`.

ObservationSet and EWS documents contain only the fields of `schemas/observation-set.schema.json` and `schemas/effective-world-state.schema.json`. They may carry `extensions` blocks in `spec`, in each observation, and in the EWS `spec.context`; these documents have no manifest, so extension names are not checked against declarations. Compilation and EWS equality ignore extension blocks.

Values are compared in the JSON data model: types must match (a boolean never equals a number), numbers compare numerically (`1` equals `1.0`), arrays compare element by element in order, and mappings compare by key set and values.

### 12.1 Output contract (applies to every runtime)

An EWS document conforms to its State Compiler when:

- `worldRef` is the World's identity, `stateCompiler` is `<worldRef>#<compiler path>`, and `worldView` is `<worldRef>#<the compiler's worldViewRef>`.
- When the compiler declares `outputSchema.fields`, each of those fields appears in exactly one of `state`, `unresolved`, `missing`, and no other field appears. A compiler with only `outputSchemaRef` skips these field rules in this alpha.
- Each `unresolved` field retains at least two distinct alternatives.
- Absent `unresolved`, `missing`, or `provenance` sections are empty. Checking an EWS does not require the World package to be valid; it requires the named State Compiler to be a listed local asset.
- `provenance` has entries only for fields in `state` or `unresolved`; when the compiler declares `traceRequired: true`, every such field has non-empty provenance.

Reference CLI: `ontle ews check <ews.yaml> --world <world package>`.

### 12.2 Declarative bindings (optional)

A State Compiler MAY declare `spec.bindings`, mapping EWS fields to observations. A compiler without bindings is opaque: its implementation is runtime-specific and only the output contract applies.

```yaml
spec:
  outputSchema:
    fields: [claim.status, inspection.results, evidence.open_hypotheses]
  bindings:
    claim.status: {from: QMS.claim, value: status, select: latest}
    inspection.results: {from: QMS.inspection, value: result, select: all}
```

Binding keys MUST be fields of `outputSchema.fields`; `from` and `value` are strings; `select` is `latest` (default) or `all`.

Input is an `ObservationSet`:

```yaml
apiVersion: openworld/v1alpha1
kind: ObservationSet
spec:
  observations:
  - id: qms-claim-001          # unique within the set
    type: QMS.claim            # matched against binding.from
    observedAt: "2026-09-03T09:00:00Z"
    values: {status: open}     # binding.value selects a key
```

Given an ObservationSet and `asOf`, a conforming compiler computes each schema field as follows:

Preconditions: the compiler is a listed local `StateCompilerProfile` asset of the World; a compiler without `spec.bindings` is opaque and compiling it MUST be refused; the input document has `kind: ObservationSet`; each observation has a string `id` and `type`, a valid `observedAt`, and a `values` mapping. The World package itself need not be valid.

1. Candidates are observations with `type == from`, `observedAt <= asOf`, and a `values` key equal to `value`, ordered by (`observedAt`, `id`), with `id` compared by Unicode code point.
2. No binding, or no candidates: the field is `missing`.
3. `select: all`: `state[field]` is the list of candidate values in candidate order; provenance is every candidate id.
4. `select: latest`: take the candidates with the greatest `observedAt`. If their values are all equal, `state[field]` is that value; otherwise `unresolved[field]` lists the distinct values in candidate order (first occurrence kept). Provenance is the ids of those newest candidates.

Invalid input (duplicate ids, a missing `id`/`type`/`values`, a non-UTC timestamp, an undefined field) MUST be rejected rather than compiled.

Two EWS documents are equal when `worldRef`, `worldView`, `stateCompiler`, `asOf`, `state`, and `unresolved` are equal, `missing` is equal as a set, and each `provenance` entry is equal as a set.

Reference CLI: `ontle ews compile <world> --compiler <path> --observations <file> --as-of <timestamp>`.

## 13. Extensions

Publishers can add their own asset kinds, fields, and vocabulary values without changing this specification. Tools that do not know an extension can ignore it safely.

### 13.1 Declaring an extension

An extension is declared as a dependency with a local name:

```yaml
spec:
  dependencies:
  - ref: acme/quality-extension@1.2.0    # package that defines the extension
    as: acme-quality                     # name used in this package
    mustUnderstand: true                 # optional, default false
```

- `as`, when present, MUST be a string matching `[a-z][a-z0-9-]*` (at most 63 characters); `as: null` is invalid. `owp` and `openworld` are reserved. A name is declared at most once per package.
- `mustUnderstand: true` means a runtime that does not implement the extension MUST NOT run the package. It does not change validation. `mustUnderstand` requires `as`.
- The name is local to the declaring package. Two packages may use the same name for different extensions; the package reference identifies the extension.
- Under resolution (section 11), the dependency MUST resolve to a package that declares `spec.extensionDefinition`.

### 13.2 Defining an extension

A package that defines an extension declares:

```yaml
spec:
  extensionDefinition:
    description: Line balancing assets and plant metadata.
    kinds: [LineBalancingProfile]            # kinds it defines, without a prefix
    schemas: [schemas/line-balancing.schema.json]   # package-relative JSON Schema files
```

`kinds` entries are PascalCase names; `schemas` entries are package-relative paths of existing files inside the package. This alpha recommends an OntologyPackage for extension definitions; no separate package kind exists.

### 13.3 Using an extension

| Extension point | Form | Where |
|---|---|---|
| Asset kind | `<extension>:<Kind>`, for example `acme-quality:LineBalancingProfile` | `spec.assets[].kind` and the asset file's `kind`; package kinds cannot be extended |
| Fields | `extensions: {<extension>: {...}}` | any object the manifest schema defines except the document root; the top-level `metadata` and `spec` of local asset documents other than `PackageExample`; objects defined by the CompatibilityEvidence schema; ObservationSet and EWS documents as in section 12 |
| Rule ids | `<extension>:<rule>` | errors and warnings reported by domain validators |

An `extensions` block maps extension names to mappings. In a package, every name used in an extension kind or an `extensions` block MUST be declared with `as` in the same package's `spec.dependencies`.

Extensions MUST NOT change the meaning of standard fields. A tool that ignores every extension still interprets the package correctly, apart from extensions declared with `mustUnderstand: true`. `extensions` is reserved: this specification does not use the name for any other field.

## 14. Semantic binding

A SemanticBinding connects the names a World uses to terms of the ontologies it depends on, so two packages can be compared by meaning rather than by spelling.

```yaml
kind: SemanticBinding
metadata:
  name: quality-terms
spec:
  terms:                                   # World name -> class
    claim: q:Claim
    lot: q:Lot
  fields:                                  # EWS field -> class and property path
    claim.status: {class: q:Claim, path: [q:claimStatus]}
    lot.genealogy: {class: q:Lot, path: [q:derivedFrom]}
  observationTypes:                        # observation type -> class
    QMS.claim: q:Claim
  actions:                                 # action name -> term
    propose-capa: q:ProposeCapa
```

A WorldPackage names its binding with `spec.world.semanticBinding`, the path of a local `SemanticBinding` asset. The binding declares no prefixes: they come from the OntologyPackages in `spec.dependencies` (section 3.1).

Single-package rules:

- `spec.world.semanticBinding`, when present, is a listed local SemanticBinding asset.
- Every value in `terms`, `observationTypes`, and `actions`, and every `class` and `path` entry in `fields`, is a CURIE `<prefix>:<local name>`.
- Every key of `fields` is a field of some local State Compiler's `outputSchema.fields`.
- A `terms` key that is neither in `spec.world.boundary.included` nor in the resolved `projection.include` of a local World View is a warning. When neither list exists, the check is skipped.
- SemanticBinding documents contain only the fields of `schemas/semantic-binding.schema.json` and `extensions` blocks.

Cross-package rules (section 11), for every package in the closure that has SemanticBinding assets:

- The prefixes of all dependency OntologyPackages are merged. Two ontologies that declare the same prefix with different IRIs are an error.
- Every CURIE expands with a merged prefix, and the expanded IRI is a term of one of those ontologies (section 3.1).

The reference CLI reports `semanticCoverage` (bound fields out of compiler fields) in `ontle inspect`, and `ontle ews compile --jsonld` prints an EWS document with a JSON-LD `@context` built from the binding. Neither changes the EWS document.

## Appendix A. Rule ids

Each error has a stable rule id. Implementations SHOULD prefix error messages with `<rule-id>: `. The conformance suite lists, for each invalid case, the rule ids a conforming implementation MUST report; it MAY report additional ids for consequential errors. Message wording is implementation-defined.

| Rule id | Section | Violation |
|---|---|---|
| `manifest.load` | 8 | `owp.yaml` missing, unparseable, or not a mapping |
| `manifest.api-version` | 2 | `apiVersion` is not `openworld/v1alpha1` |
| `manifest.kind` | 3 | unknown package `kind` |
| `manifest.metadata` | 2 | `metadata` is not a mapping |
| `manifest.identity` | 2 | missing `namespace`, `name`, or `version`, or `namespace`/`name` containing `/`, `@`, `#`, or whitespace |
| `manifest.version` | 2 | `metadata.version` is not SemVer |
| `manifest.spec` | 2 | `spec` is not a mapping |
| `package.card` | 3 | required human card missing |
| `package.legacy-manifest` | 8 | `package.yaml` or `world.yaml` at the root |
| `asset.list`, `asset.entry`, `asset.kind` | 5 | malformed `spec.assets` or entry, missing entry `kind`, or a kind containing `:` that is not `<extension>:<Kind>` |
| `asset.path-or-ref` | 5 | entry has both or neither of `path` and `ref` |
| `ref.shape` | 5.1 | malformed ExternalRef: not a mapping, bad `status`, `digest`, `size`, or field type, a bound reference without `provider` or `uri`, or both `uri` and `repository` |
| `ref.provider` | 5.1 | `provider` is neither a listed provider nor `<extension>:<provider>` |
| `asset.path-form` | 3 | local path is not a relative POSIX path, or starts with `./` |
| `manifest.dependency` | 2 | `spec.dependencies` entry is not an exact package reference |
| `eval.duplicate-name` | 8 | two local EvaluationProfile or VerifierPackage assets share `metadata.name` |
| `asset.duplicate-path` | 8 | same local path listed twice |
| `asset.path-escape` | 8 | local path resolves outside the package root |
| `asset.missing-file` | 8 | local path does not exist |
| `asset.yaml` | 8 | local YAML asset (including a `PackageExample`) does not parse |
| `asset.kind-mismatch` | 8 | file `kind` differs from manifest `kind` |
| `world.spec` | 6.1 | WorldPackage without `spec.world` |
| `profile.unknown` | 3.1, 6.1 | undefined `spec.conformance.profile` for the package kind |
| `profile.descriptive` | 6.1 | no definition and no WorldDefinition asset |
| `profile.viewable` | 6.1 | no View, no `defaultView`, or `defaultView` not a local View |
| `profile.viewable.world-ref` | 6.1 | default View `worldRef` is not `self` or the package identity |
| `profile.stateful` | 6.1 | no State Compiler, no `defaultStateCompiler`, or it is not a local compiler |
| `profile.stateful.default-compiler-view` | 6.1 | default compiler does not compile `defaultView` |
| `profile.stateful.compiler-view` | 6.1 | a compiler's `worldViewRef` is not a local View |
| `profile.stateful.output-contract` | 6.1 | a compiler's `outputContract` is not `EffectiveWorldState` |
| `profile.model-ready.output-schema` | 6.1 | a compiler lacks `outputSchema.fields` and `outputSchemaRef` |
| `profile.action-ready` | 6.1 | missing action, commit, or effect-verification asset |
| `compiler.binding` | 12.2 | malformed declarative binding, or binding outside `outputSchema` |
| `worldmodel.spec`, `worldmodel.roles` | 3 | missing `spec.worldModel` or roles |
| `worldmodel.world-ref` | 3 | missing `semanticGrounding.worldRef`, or not `<namespace>/<name>@<semver>` |
| `worldmodel.compatible-views` | 3 | missing `compatibleWorldViews` |
| `worldmodel.compatible-compilers` | 3 | missing `compatibleStateCompilers` |
| `worldmodel.grounding-ref` | 3 | grounding entry not `<worldRef>#<asset path>` |
| `worldmodel.adapter`, `worldmodel.adapter-ref`, `worldmodel.adapter-source` | 6 | Representation Adapter missing, not referenced locally, or not sourced from EWS |
| `worldmodel.input-contract` | 6 | `inputs.contract` is not `EffectiveWorldState` |
| `ontology.spec` | 3 | OntologyPackage without `spec.ontology` |
| `ontology.iri` | 3.1 | `iri` is not an absolute IRI |
| `ontology.prefix` | 3.1 | malformed `prefixes` |
| `ontology.entrypoint` | 3.1 | entrypoint not a mapping, missing file, or unknown `role` |
| `ontology.format` | 3.1 | unknown entrypoint `format` |
| `ontology.parse` | 3.1 | `owp-yaml` entrypoint is not a SemanticProfile document |
| `ontology.prefix-undeclared` | 3.1 | SemanticProfile identifier uses an undeclared prefix |
| `ontology.term-index` | 3.1 | `termIndex` missing, not an OntologyTermIndex, or a malformed term |
| `ontology.external-import` | 3.1 | `externalImports` entry without an absolute `iri` or a `ref` |
| `profile.ontology.vocabulary`, `profile.ontology.schema`, `profile.ontology.constrained`, `profile.ontology.mapped` | 3.1 | declared ontology profile not satisfied |
| `eval.version` | 9 | EvaluationProfile/VerifierPackage `metadata.version` not SemVer |
| `eval.supersedes` | 9 | `supersedes` not pinned |
| `evidence.subject` | 9 | `subject` missing or not the package identity |
| `evidence.required`, `evidence.result`, `evidence.scope` | 9 | missing `evaluationProfile`, `result`, or `scope.worldRef`/`scope.worldView` |
| `evidence.unpinned` | 9 | reference not `<name>@<exact-semver>` |
| `evidence.version-mismatch` | 9 | bound local asset missing that exact version |
| `evidence.scope.world-ref`, `evidence.scope.world-view`, `evidence.scope.state-compiler` | 9 | scope outside the model's grounding |
| `resolve.reference` | 11 | malformed dependency reference |
| `resolve.source` | 11 | source unusable (for example an archive fails verification) |
| `resolve.unresolved` | 11 | dependency not found in any source |
| `resolve.version-conflict` | 11 | two versions of one package in a closure |
| `resolve.cycle` | 11 | dependency cycle |
| `resolve.dependency-invalid` | 11 | a resolved dependency is itself invalid |
| `grounding.world-not-dependency` | 11 | `worldRef` not listed in `spec.dependencies` |
| `grounding.world-kind` | 11 | `worldRef` does not resolve to a WorldPackage |
| `grounding.world-view`, `grounding.state-compiler` | 11 | grounding path is not a View or State Compiler asset of the World |
| `grounding.compiler-view` | 11 | a compatible compiler compiles a View outside `compatibleWorldViews` |
| `ews.input` | 12.2 | invalid ObservationSet or `asOf`; compilation refused |
| `ews.opaque-compiler` | 12.2 | compiler has no `spec.bindings`; compilation refused |
| `ews.state-compiler` | 12 | named State Compiler is not a listed local asset, or has no `spec` |
| `ews.kind`, `ews.shape` | 12 | not an EffectiveWorldState document, or malformed sections |
| `ews.world-ref`, `ews.world-view` | 12.1 | references do not match the World, compiler, and compiled View |
| `ews.as-of` | 12.1 | `context.asOf` not a UTC timestamp |
| `ews.field-placement` | 12.1 | schema field not in exactly one of state/unresolved/missing |
| `ews.field-unknown` | 12.1 | field outside `outputSchema` |
| `ews.unresolved-alternatives` | 12.1 | unresolved field with fewer than two alternatives |
| `ews.provenance-orphan`, `ews.provenance-required` | 12.1 | provenance for a field without value, or missing under `traceRequired` |
| `binding.asset` | 14 | `spec.world.semanticBinding` is not a local SemanticBinding asset |
| `binding.curie` | 14 | binding value or section is not a CURIE or a mapping as required |
| `binding.field-unknown` | 14 | bound field is not in any local State Compiler `outputSchema.fields` |
| `grounding.prefix-unknown` | 14 | binding CURIE uses a prefix no dependency OntologyPackage declares |
| `grounding.prefix-conflict` | 14 | two dependency OntologyPackages declare one prefix with different IRIs |
| `grounding.ontology-term` | 14 | expanded binding IRI is not a term of a dependency OntologyPackage |
| `schema.unknown-field` | 8, 12 | a key that is neither a defined field nor an `extensions` block |
| `extension.name` | 13.1 | `as` malformed or reserved |
| `extension.duplicate` | 13.1 | extension name declared twice |
| `extension.declaration` | 13.1 | `mustUnderstand` without `as`, or not a boolean |
| `extension.undeclared` | 13.3 | extension kind or `extensions` block uses an undeclared name |
| `extension.block` | 13.3 | `extensions` value is not a mapping of names to mappings |
| `extension.definition` | 13.1, 13.2 | malformed `spec.extensionDefinition`, a missing schema file, or (under resolution) an `as` dependency without one |

Warnings also have ids. Implementations SHOULD prefix warning messages with them. An implementation MAY report additional warnings; their ids MUST contain `:` (for example `owp-ts:eval-order`) so they cannot collide with ids added to this table.

| Warning id | Section | Condition |
|---|---|---|
| `world.undescribed` | 8 | `spec.world` without definition or description |
| `worldmodel.model-artifact-missing` | 8 | WorldModelPackage without a `ModelArtifact` asset |
| `worldmodel.evaluation-profile-missing` | 8 | WorldModelPackage without an `EvaluationProfile` asset |
| `eval.version-missing` | 9 | EvaluationProfile or VerifierPackage without `metadata.version` |
| `asset.kind-unknown` | 8 | kind without `:` outside the vocabulary |
| `asset.kind-experimental` | 8 | vocabulary kind marked `experimental` |
| `manifest.conformance-ignored` | 3.1, 6.1 | `spec.conformance` on a WorldModelPackage |
| `binding.term-unscoped` | 14 | binding term outside the World boundary and every View projection |
| `ref.unpinned` | 5.1 | bound ExternalRef that is not pinned |
| `ref.legacy-shape` | 5.1 | ExternalRef uses `repository` instead of `uri` |
| `experimental.field` | C | experimental kind or field: undefined key, missing required field, or malformed value |
| `experimental.value` | C | value outside an experimental value set |
| `experimental.reference` | C | experimental reference that does not name a suitable local asset, or a `specializes` cycle |

The machine-readable list of every id is `spec/rule-ids.yaml`.


## Appendix B. Notation (informative)

| Item | Form | Examples |
|---|---|---|
| Field keys | camelCase | `worldViewRef`, `outputSchema`, `mustUnderstand` |
| Kinds | PascalCase | `WorldViewProfile`, `EffectiveWorldState` |
| ExternalRef `provider` values | lowercase | `huggingface`, `oci` |
| Vocabulary values | snake_case | roles `semantic_grounding`, capabilities `state_tracking` |
| Conformance profile names | kebab-case | `model-ready`, `action-ready` |
| References | `…Ref` (one), `…Refs` (several) | `adapterRef` |
| Extension names | lowercase, digits, `-` | `acme-quality` |
| Rule ids | dotted lowercase, kebab-case parts | `profile.stateful.output-contract` |

## Appendix C. Experimental asset kinds (informative)

The kinds below are marked `stability: experimental` in `vocab/asset-kinds.yaml`. They may change or be removed. A validator reports `asset.kind-experimental` for each use and checks them against `schemas/experimental/` with warnings only (`experimental.field`, `experimental.value`, `experimental.reference`). Extension rules (section 13) still apply and remain errors. Value sets are in `vocab/value-sets.yaml`; a value outside its set is a warning, and an extension value `<extension>:<value>` is accepted when the extension is declared.

| Kind | Purpose | Main fields |
|---|---|---|
| `TaskSetProfile` | domain-specific bundle of work | `task.workPatterns`, `requires.worldViews`, `requires.knowledge`, `mayUse`, `produces.artifacts`, `evaluationRefs` |
| `WorkPatternProfile` | domain-independent shape of work | `pattern.kind` (value set `workPatterns`), `inputs.semanticRoles`, `outputs.semanticRoles`, `optionalCapabilities` |
| `ArtifactContract` | contract for an output a person or system keeps | `artifact.type`, `artifact.representation`, `structure`, `serialization.formats`, `delivery`, `governance` |
| `ArtifactTemplate` | template for an artifact contract | `artifactContractRef`, `format`, `content` (`path` or ExternalRef) |
| `ConsumerRepresentationProfile` | how a View is delivered to one kind of actor | `actor.kind` (value set `actorKinds`), `worldViewRef`, `representation`, and one block named after the actor kind: `human`, `agent`, `model`, or `system` |
| `KnowledgeAsset` | reusable knowledge | `roles`, `representation`, `conformsTo`, `snapshot`, `content` (`path` or ExternalRef), `license`, `access`, `sensitivity` |

Experimental checks:

- References written as package-relative paths (for example `TaskSetProfile.spec.requires.worldViews`, `ConsumerRepresentationProfile.spec.worldViewRef`) name a listed local asset of the expected kind. References containing `#` point into another package and are not checked.
- A ConsumerRepresentationProfile carries at most the actor block that matches `actor.kind`. The `model` block's `adapterRef` names a local RepresentationAdapterProfile; the model input path remains the one in section 6.
- `KnowledgeAsset.spec.conformsTo.ontology` is a package reference that is also listed in `spec.dependencies`.

**World View specialization.** A WorldViewProfile MAY declare the experimental fields `spec.specializes` (the local path of another WorldViewProfile) and `spec.projection.exclude`. The resolved View is the base View's resolved spec with: `projection.include` = base include ∪ include − exclude; `purpose` and `conditioning` overridden key by key; other fields replaced. `specializes` naming anything other than a local WorldViewProfile, or a cycle, is `experimental.reference`. State Compilers keep binding to the specialized View's own path. The reference CLI shows resolved Views with `ontle inspect --resolved-views`.

**Reference graph.** `ontle inspect --graph` lists the package, its assets, and the references between them with informative relation names (`contains`, `depends_on`, `uses_extension`, `grounded_in`, `valid_for_view`, `valid_for_compiler`, `uses_adapter`, `compiles_view`, `specializes`, `uses_pattern`, `requires_view`, `requires_knowledge`, `produces_artifact`, `evaluated_by`, `template_for`, `represents_view`, `consumes_contract`, `conforms_to`, `evidences`). These names are not part of the package contract.
