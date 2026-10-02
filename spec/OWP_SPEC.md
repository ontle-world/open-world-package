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

References and package-relative paths are compared as exact strings, without normalization. Local asset paths, `defaultView`, `defaultStateCompiler`, `worldViewRef`, and `<asset path>` MUST be relative POSIX paths in normal form, without a leading `./`, written exactly as the file's path in the package. Validating a single package does not resolve the referenced World; section 11 defines the cross-package checks.

OWP does not standardize model weight bytes. Architecture names (VLM, VLA, video world model, solver) are expressed as `roles` and modalities, not as separate package kinds.

### OntologyPackage

Human card: `ONTOLOGY.md`. An OntologyPackage MUST declare `spec.ontology` as a mapping. Section 3.1 (`OWP_SEMANTICS.md`) defines its fields.

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

A local asset is a YAML file of the package that says what it is: its `apiVersion` is an OWP version and its `kind` is the asset kind. It is not listed in `owp.yaml`.

```yaml
# scenarios/pick-place.yaml
apiVersion: openworld/v1alpha1
kind: ScenarioProfile
metadata:
  name: pick-place
spec: {}
```

Discovery reads every `.yaml`/`.yml` file of the package except `owp.yaml` and the listed `PackageExample` files. It skips path components that start with `.` or are named `dist`, `build`, `venv`, `node_modules`, or `__pycache__`, files that resolve outside the package root, and subdirectories that contain their own `owp.yaml` (a nested package). For each file read:

- Every file MUST parse (`asset.yaml`, section 5.2).
- A file whose top-level `apiVersion` is not a string starting with `openworld/` is an ordinary package file, not an asset. Configuration of other tools (for example a Kubernetes manifest) can sit in a package.
- A file with an OWP `apiVersion` is an OWP document. Its `apiVersion` MUST equal the manifest's (`asset.api-version`), and it MUST declare `kind` (`asset.kind`).
- `ObservationSet` and `EffectiveWorldState` documents are package files, not assets.
- Any other `kind` MUST be a vocabulary kind or an extension kind `<extension>:<Kind>` (section 13); otherwise `asset.kind`. The file is then a local asset of that kind at its package-relative path.

`spec.assets` lists what discovery cannot find: external artifacts (`ref`) and `PackageExample` files (`path`), whose content may be any document. An entry has `kind`, exactly one of `path` and `ref`, and optionally an `extensions` block. A `path` entry of any other kind is an error (`asset.path-or-ref`).

```yaml
spec:
  assets:
    - kind: PackageExample
      path: examples/observations.yaml
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
  status: bound                           # bound (default; also when null) | unbound
```

- A bound reference declares `provider` and `uri`. An `unbound` reference records that no artifact has been chosen yet; its other fields are optional. Examples MUST NOT invent artifacts; they use `status: unbound` instead.
- `provider` is one of the listed values or an extension provider `<extension>:<provider>` (section 13).
- `digest` is `sha256:` followed by 64 lowercase hex digits. `size` is a non-negative integer.
- A bound reference SHOULD be pinned; otherwise the warning `ref.unpinned` applies. Pinning depends on the provider:

| Provider | Pinned by |
|---|---|
| `git`, `huggingface` | `revision` is a commit hash (40 or 64 lowercase hex digits), or `digest` |
| `oci` | `digest` of the OCI manifest |
| `https`, `s3`, `gcs`, `doi` | `digest` of the file bytes |
| extension providers | defined by the extension |

- Several files are pinned together through a file list: an artifact with `mediaType: application/vnd.openworld.filelist+json` whose content uses the `files` format of `owp.lock.json` (section 7), with `digest` taken over the list. A consumer verifies the list's digest and then each listed file.
- This alpha validates ExternalRefs in the manifest and in standard bindings (section 5.3). Other ExternalRefs inside asset documents are validated once their asset kind has a JSON Schema.

### 5.2 YAML documents

Every OWP YAML document (`owp.yaml`, local YAML assets, ObservationSet and EWS documents) is read with the YAML 1.2 core schema into the JSON data model. YAML 1.1 loaders MUST be configured to follow these rules:

- A plain (unquoted) scalar is null for `~`, `null`, `Null`, `NULL`, or nothing; a boolean for `true`, `True`, `TRUE`, `false`, `False`, `FALSE`; an integer for `[-+]?[0-9]+` (decimal, also with leading zeros), `0o[0-7]+`, or `0x[0-9a-fA-F]+`; a number for `[-+]?(\.[0-9]+|[0-9]+(\.[0-9]*)?)([eE][-+]?[0-9]+)?`, `[-+]?.inf` (any of `inf`, `Inf`, `INF`), or `.nan` (`nan`, `NaN`, `NAN`). Every other plain scalar is a string.
- So `yes`, `no`, `on`, `off`, `1:20`, `1_000`, and `2026-01-01` are strings; `0755` is the integer 755.
- `<<` is an ordinary key; there are no merge keys.
- Mapping keys are strings, as in the JSON data model: a key that reads as null, a boolean, or a number (`1:`, `true:`), or a key that is a sequence or mapping, does not parse. Quote such keys (`"1":`).
- A mapping with two equal keys does not parse (`manifest.load`, `asset.yaml`).

Authors SHOULD quote strings that a YAML 1.1 reader would type differently, for example `"yes"` or `"2026-01-01"`.

### 5.3 Standard bindings

An asset ties its parts to external standards (message types, scene formats, dataset formats, information models) under `spec.standardBindings`, a mapping of binding name to binding. This applies to every local YAML asset other than a `PackageExample`.

```yaml
spec:
  standardBindings:
    actions:
      standard: ros2
      terms: {grasp: control_msgs/action/GripperCommand}
    scene:
      standard: openusd
      ref: {status: unbound}
    episodes:
      standard: lerobot
      license: Apache-2.0
      ref: {provider: huggingface, uri: "hf://datasets/<org>/<name>", revision: <commit hash>}
```

- `standard` (required) names the standard in lowercase, for example `ros2`, `openusd`, `lerobot`, `isa95`, `opcua`.
- `terms` maps names used in the asset to the standard's type or term names (strings).
- `ref` is an ExternalRef (section 5.1) to the artifact that realizes the binding, such as a scene, a dataset revision, or a specification document.
- A binding declares `ref`, `terms`, or both. Other keys are errors (`schema.unknown-field`), apart from an `extensions` block.
- A bound `ref` MUST be pinned as in section 5.1 (`standard.unpinned`; extension providers define their own pinning) and MUST come with `license`, an SPDX license expression for the artifact (`standard.license`). An `unbound` ref needs neither; examples leave a binding unbound until a real artifact is chosen.
- A `license` or `terms` that is null counts as absent.

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
| `model-ready` | every local `StateCompilerProfile` declares a concrete EWS schema: a non-empty `spec.outputSchema.fields` list, or a `spec.outputSchemaRef` that resolves to EWS fields (section 12.1) |
| `action-ready` | `ActionBindingProfile`, `CommitContract`, and `EffectVerificationProfile` assets |

Requirements of a profile are checked only when that profile or a higher one is declared. "At least one X asset" and the `action-ready` assets may be local (`path`) or external (`ref`); assets named by `defaultView`, `defaultStateCompiler`, or `worldViewRef`, and State Compilers checked for content, are local. A validator MUST reject a package that does not satisfy its declared profile, and SHOULD report the highest profile the package satisfies independent of the declaration.

Every WorldModelPackage requires compatible View and State Compiler references regardless of the World's profile; in practice the referenced World is `stateful` or higher.

## 7. Integrity

`ontle pack` creates a deterministic ZIP-compatible OWP archive (`.owp.zip`). The package root is the archive root. The archive contains the package files and one `owp.lock.json`:

```json
{
  "format": "owp-lock/v1alpha2",
  "manifest": "owp.yaml",
  "manifest_sha256": "<hex sha256 of owp.yaml>",
  "files": [{"path": "<posix path>", "sha256": "<hex sha256>", "size": 123}],
  "externals": [{"pointer": "/spec/assets/0/ref", "provider": "huggingface", "uri": "hf://org/name", "revision": "<commit>"}]
}
```

`files` lists every archived file except `owp.lock.json` itself (including `owp.yaml`). `externals` has one entry per bound ExternalRef (section 5.1) in `owp.yaml`, in manifest order, with `pointer` (a JSON Pointer into `owp.yaml`), `provider`, `uri`, and the `revision`, `digest`, and `mediaType` it declares. An entry MAY add `vendoredPath`, the archive path of the referenced content included in the archive (vendoring); that file is listed in `files` and its bytes match `digest`. A verifier MUST check that `externals` equals the manifest's bound references. The schema is `schemas/owp-lock.schema.json`. `manifest_sha256` MUST match `owp.yaml`; `size` is informative. Hashes are lowercase hex without prefix. An archive is valid only when its entries other than `owp.lock.json` are exactly the locked paths and every hash matches. The digest of an archive is the SHA-256 of the archive bytes.

### 7.1 OCI artifacts

An archive MAY be distributed through an OCI registry. The OCI manifest has `artifactType` `application/vnd.openworld.package.v1alpha1`, a config blob of media type `application/vnd.openworld.manifest.v1alpha1+json` holding `owp.yaml` as JSON, and exactly one layer of media type `application/vnd.openworld.package.layer.v1alpha1+zip` holding the `.owp.zip`. A consumer verifies the archive (section 7) after pulling it. Evidence published outside the package (section 9.1) MAY be attached as an OCI referrer with `artifactType` `application/vnd.openworld.evidence.v1alpha1` and a layer of media type `application/vnd.openworld.evidence.v1alpha1+yaml`. Signatures (for example Sigstore bundles) MAY be attached the same way or stored next to the archive as `<archive>.sigstore.json`.

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
- **Listed PackageExample paths** are package-relative; a path that resolves outside the package root (for example `../x.yaml` or an absolute path) is invalid; the file must exist; the same path may be listed once.
- **Dependencies:** every `spec.dependencies` entry is `<namespace>/<name>@<semver>` or a mapping whose `ref` is; otherwise the package is invalid.
- **Evaluation asset names:** two local assets of the same kind (EvaluationProfile or VerifierPackage) MUST NOT share `metadata.name`. A non-SemVer `metadata.version` on them is an error; a missing one is a warning.
- **YAML files:** every `.yaml`/`.yml` file that discovery reads, and every listed `PackageExample`, MUST parse. `PackageExample` files may contain any document (for example an `ObservationSet`), so their `kind` is not checked.
- **Asset-kind vocabulary** (`vocab/asset-kinds.yaml`): a discovered OWP document MUST name a vocabulary kind or an extension kind (`asset.kind`). The `kind` of an external `spec.assets` entry is open: one without `:` outside the vocabulary is a warning. A vocabulary kind marked `stability: experimental` is a warning, because it may change or be removed; a kind containing `:` is an extension kind and follows section 13.
- **Defined fields:** the manifest, CompatibilityEvidence, SemanticProfile, OntologyTermIndex, SemanticBinding, WorldViewProfile, EvaluationProfile, ScenarioProfile, and CapabilityContract assets, ObservationSet documents, and EWS documents contain only the fields defined by their JSON Schemas under `schemas/` and `extensions` blocks (section 13). Any other key, including a misspelt field or a field named `<extension>:<field>`, is an error. Objects the schemas mark as open containers (for example `spec.validity`) are not checked inside. Asset kinds without a JSON Schema are checked only for `extensions` blocks in their top-level `metadata` and `spec`. `PackageExample` files are not checked, because they may hold any document.
- **Severity:** MUST/required rules are errors and make the package invalid. Warnings never invalidate; Appendix A lists them.
- **Satisfied profile** is computed even when the declared profile is invalid or unknown.
- **Experimental kinds and fields** (Appendix C) produce warnings only; they never make a package invalid, except that extension rules (section 13) still apply.

The reference validator also rejects legacy manifest names, validates typed local YAML asset references, detects duplicate paths, and requires a Representation Adapter for every WorldModelPackage (an identity adapter is valid when no transform is needed). Additional domain-specific validators may be layered on top.

Implementations can check agreement with the reference validator using the language-neutral suite in `conformance/`, which also covers dependency resolution (section 11) and EWS documents (section 12).

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

A resolver records, for every package in the closure other than the root, the revision in the table: none for a directory source, `sha256:<archive digest>` for an archive (also one found in a directory source), `git:<commit>` with the full commit hash `<rev>` resolved to. The revision depends only on the bytes fetched, so two resolvers given the same sources record the same revisions.

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

Further source types. An implementation MAY support them; when it does, it follows these rules:

| Source | Form | Revision recorded |
|---|---|---|
| OCI | `oci:<registry reference>` (or `oci-layout:<dir>:<tag>` for a local OCI layout); the pulled archive is verified like an archive source | `oci:<manifest digest>` |
| index | `index:<path or URL of a PackageIndex>` (section 11.1); the listed archive is downloaded and its digest checked before it is verified | `sha256:<archive digest>` |

The reference CLI: `ontle resolve`, `ontle validate --resolve`, with `--source` (repeatable) and the `ONTLE_PATH` environment variable.

### 11.1 Package index

A package index is a static JSON document (`schemas/package-index.schema.json`) that can be served from any web server or repository:

```json
{"apiVersion": "openworld/v1alpha1", "kind": "PackageIndex",
 "packages": [{"identity": "acme/line-world@0.1.0", "kind": "WorldPackage",
               "archive": "acme-line-world-0.1.0.owp.zip", "digest": "sha256:<hex>"}]}
```

Each identity appears once. `archive` is a URL or a path relative to the index. A resolver MUST reject an archive whose bytes do not match `digest`. The reference CLI writes indexes with `ontle index build`.

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

## Appendix A. Rule ids

Each error has a stable rule id. Implementations SHOULD prefix error messages with `<rule-id>: `. The conformance suite lists, for each invalid case, the rule ids a conforming implementation MUST report; it MAY report additional ids for consequential errors. Message wording is implementation-defined.

| Rule id | Section | Violation |
|---|---|---|
| `manifest.load` | 5.2, 8 | `owp.yaml` missing, unparseable (including duplicate keys), or not a mapping |
| `manifest.api-version` | 2 | `apiVersion` is not `openworld/v1alpha1` |
| `manifest.kind` | 3 | unknown package `kind` |
| `manifest.metadata` | 2 | `metadata` is not a mapping |
| `manifest.identity` | 2 | missing `namespace`, `name`, or `version`, or `namespace`/`name` containing `/`, `@`, `#`, or whitespace |
| `manifest.version` | 2 | `metadata.version` is not SemVer |
| `manifest.spec` | 2 | `spec` is not a mapping |
| `package.card` | 3 | required human card missing |
| `package.legacy-manifest` | 8 | `package.yaml` or `world.yaml` at the root |
| `asset.list`, `asset.entry`, `asset.kind` | 5 | malformed `spec.assets` or entry, missing entry `kind`, a kind containing `:` that is not `<extension>:<Kind>`, or a discovered OWP document without a kind or with a kind that is neither a vocabulary nor an extension kind |
| `asset.path-or-ref` | 5 | entry has both or neither of `path` and `ref`, or a `path` entry is not a `PackageExample` |
| `ref.shape` | 5.1 | malformed ExternalRef: not a mapping, bad `status`, `digest`, `size`, or field type, or a bound reference without `provider` or `uri` |
| `ref.provider` | 5.1 | `provider` is neither a listed provider nor `<extension>:<provider>` |
| `asset.path-form` | 3 | local path is not a relative POSIX path, or starts with `./` |
| `manifest.dependency` | 2 | `spec.dependencies` entry is not an exact package reference |
| `eval.duplicate-name` | 8 | two local EvaluationProfile or VerifierPackage assets share `metadata.name` |
| `asset.duplicate-path` | 8 | same `PackageExample` path listed twice |
| `asset.path-escape` | 8 | listed `PackageExample` path resolves outside the package root |
| `asset.missing-file` | 8 | listed `PackageExample` path does not exist |
| `standard.binding` | 5.3 | malformed `spec.standardBindings`: not a mapping, an entry without `standard`, `terms` not a mapping of strings, an empty `license`, or neither `ref` nor `terms` |
| `standard.unpinned` | 5.3 | a bound `ref` in a standard binding is not pinned |
| `standard.license` | 5.3 | a standard binding binds an artifact without `license` |
| `asset.yaml` | 5.2, 8 | local YAML asset (including a `PackageExample`) does not parse, including duplicate keys |
| `asset.api-version` | 5 | a discovered OWP document's `apiVersion` differs from the manifest's |
| `world.spec` | 6.1 | WorldPackage without `spec.world` |
| `profile.unknown` | 3.1, 6.1 | undefined `spec.conformance.profile` for the package kind |
| `profile.descriptive` | 6.1 | no definition and no WorldDefinition asset |
| `profile.viewable` | 6.1 | no View, no `defaultView`, or `defaultView` not a local View |
| `profile.viewable.world-ref` | 6.1 | default View `worldRef` is not `self` or the package identity |
| `profile.stateful` | 6.1 | no State Compiler, no `defaultStateCompiler`, or it is not a local compiler |
| `profile.stateful.default-compiler-view` | 6.1 | default compiler does not compile `defaultView` |
| `profile.stateful.compiler-view` | 6.1 | a compiler's `worldViewRef` is not a local View |
| `profile.stateful.output-contract` | 6.1 | a compiler's `outputContract` is not `EffectiveWorldState` |
| `profile.model-ready.output-schema` | 6.1 | a compiler has no EWS fields: neither `outputSchema.fields` nor a resolvable `outputSchemaRef` |
| `profile.action-ready` | 6.1 | missing action, commit, or effect-verification asset |
| `compiler.binding` | 12.2 | malformed declarative binding, or binding a field that is not an EWS field of the compiler |
| `compiler.output-schema-ref` | 12.1 | `outputSchemaRef` is not a package-relative path to a JSON Schema with a non-empty top-level `properties` object |
| `compiler.output-schema-mismatch` | 12.1 | `outputSchema.fields` and the `properties` of `outputSchemaRef` list different fields |
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
| `evidence.detached-subject` | 9.1 | detached evidence whose `subject` or `subjectDigest` does not match the archive |
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
| `evaluation.assessment-kind` | 15.1 | `assessmentKind` outside its value set |
| `evaluation.subject` | 15.1 | `subject.kind` outside its value set, or `subject.ref` names nothing |
| `evaluation.verifier-ref` | 15.1 | `verifierRef` is neither a local VerifierPackage nor a pinned reference |
| `evaluation.result-schema` | 15.1 | `resultSchemaRef` is not a file in the package |
| `scenario.engine-kind` | 15.2 | `engine.kind` outside its value set |
| `scenario.baseline-ref` | 15.2 | `baselineStateRef` is neither a file in the package nor a URI |
| `scenario.confidence` | 15.2 | `confidence` is not a number from 0 to 1 |
| `extraction.input` | C.1 | invalid extraction input; nothing is produced |
| `ews.input` | 12.2 | invalid ObservationSet or `asOf`; compilation refused |
| `ews.opaque-compiler` | 12.2 | compiler has no `spec.bindings`; compilation refused |
| `ews.state-compiler` | 12 | named State Compiler is not a local asset, or has no `spec` |
| `ews.kind`, `ews.shape` | 12 | not an EffectiveWorldState document, or malformed sections |
| `ews.world-ref`, `ews.world-view` | 12.1 | references do not match the World, compiler, and compiled View |
| `ews.as-of` | 12.1 | `context.asOf` not a UTC timestamp |
| `ews.field-placement` | 12.1 | schema field not in exactly one of state/unresolved/missing |
| `ews.field-unknown` | 12.1 | field that is not an EWS field of the compiler |
| `ews.unresolved-alternatives` | 12.1 | unresolved field with fewer than two alternatives |
| `ews.provenance-orphan`, `ews.provenance-required` | 12.1 | provenance for a field without value, or missing under `traceRequired` |
| `binding.asset` | 14 | `spec.world.semanticBinding` is not a local SemanticBinding asset |
| `binding.curie` | 14 | binding value or section is not a CURIE or a mapping as required |
| `binding.field-unknown` | 14 | bound field is not an EWS field of any local State Compiler |
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
| `asset.kind-unknown` | 8 | external `spec.assets` entry kind without `:` outside the vocabulary |
| `asset.kind-experimental` | 8 | vocabulary kind marked `experimental` |
| `manifest.conformance-ignored` | 3.1, 6.1 | `spec.conformance` on a WorldModelPackage |
| `compiler.multi-latest` | C.1 | State Compiler binding reads a multi-valued extracted type with `select: latest` |
| `experimental.delegation-exceeds-authority` | C.3 | a delegation grants actions or decisions the delegator's roles do not hold |
| `binding.term-unscoped` | 14 | binding term outside the World boundary and every View projection |
| `ref.unpinned` | 5.1 | bound ExternalRef that is not pinned |
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

