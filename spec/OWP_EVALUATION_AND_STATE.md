# OWP — Evaluation, state, and scenarios

Part of the Open World Package specification; section numbers are shared across its documents (see the document map in `OWP_SPEC.md`). Read this when a package compiles Effective World State, records evaluation evidence, or defines evaluations, scenarios, and capabilities.

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

### 9.1 Evidence published outside the package

Evaluations often finish after a package is released. Such evidence MAY be published as a standalone CompatibilityEvidence document (for example as an OCI referrer, section 7.1). It then MUST declare `spec.subjectDigest`, the SHA-256 digest of the subject archive (`sha256:<hex>`), and `spec.subject` MUST be that archive's identity. The scope rules of section 9 apply against the subject's grounding. The reference CLI checks this with `ontle evidence check <evidence.yaml> --package <archive>`.

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

Timestamps are UTC strings `YYYY-MM-DDTHH:MM:SSZ` that denote a valid calendar instant (no leap seconds) and are compared as text. YAML authors SHOULD quote them. An implementation MUST read an unquoted timestamp as its source text and MUST NOT convert it to another representation. ObservationSet and EWS documents, including values inside `values`, are read under the YAML rules of section 5.2, so unquoted timestamps stay strings.

ObservationSet and EWS documents contain only the fields of `schemas/observation-set.schema.json` and `schemas/effective-world-state.schema.json`. An ObservationSet MAY carry `spec.provenance` (`extraction`, `parameters`, `snapshot`) recording where its observations came from; compilation ignores it. They may carry `extensions` blocks in `spec`, in each observation, and in the EWS `spec.context`; these documents have no manifest, so extension names are not checked against declarations. Compilation and EWS equality ignore extension blocks.

Values are compared in the JSON data model: types must match (a boolean never equals a number), numbers compare numerically (`1` equals `1.0`), arrays compare element by element in order, and mappings compare by key set and values.

### 12.1 Output contract (applies to every runtime)

A State Compiler's EWS fields are `spec.outputSchema.fields`, or the field names listed by `spec.outputSchemaRef`:

- `outputSchemaRef` is a package-relative path in the form of a local asset path (section 5): relative POSIX, without a leading `./`, inside the package. The file need not be listed in `spec.assets`.
- The file is a JSON document holding a JSON Schema whose top-level `properties` is a non-empty object. Its keys are the EWS fields. The subschemas are informative in this alpha; validators do not apply them to EWS values.
- A reference that is malformed, missing, unreadable, not JSON, or lacks such `properties` is the error `compiler.output-schema-ref`, and it contributes no fields.
- A compiler that declares both MUST list the same set of fields in each (`compiler.output-schema-mismatch`); `outputSchema.fields` is then used.

An EWS document conforms to its State Compiler when:

- `worldRef` is the World's identity, `stateCompiler` is `<worldRef>#<compiler path>`, and `worldView` is `<worldRef>#<the compiler's worldViewRef>`.
- When the compiler has EWS fields, each of those fields appears in exactly one of `state`, `unresolved`, `missing`, and no other field appears.
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

Binding keys MUST be EWS fields of the compiler (section 12.1); `from` and `value` are strings; `select` is `latest` (default) or `all`.

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

## 15. Evaluation, scenario, capability, and view fields

These fields of standard kinds are part of the standard. Their schemas are under `schemas/`; undefined keys are errors (section 8).

### 15.1 EvaluationProfile

| Field | Meaning |
|---|---|
| `assessmentKind` | `verification` (conditions, facts, or specifications are met), `validation` (fit for purpose), `evaluation` (quality or performance against criteria), `review` (an examination activity), or `approval` (an authorized decision to use or execute); or an extension value |
| `subject` | `kind` (`model`, `agent`, `workflow`, `artifact`, `decision`, `process`, `capability`, `environment`, or an extension value) and `ref` (a local asset path, or a reference containing `#` or `@`) |
| `objective`, `criteria` | what is assessed; each criterion has `metric`, `rubric`, and `threshold` |
| `verifierRef` | a local VerifierPackage path or a pinned `<name>@<version>` |
| `evidenceRefs`, `validityScope` | supporting evidence; where the profile applies |
| `resultSchemaRef` | a file in the package describing results |

Rules: `evaluation.assessment-kind`, `evaluation.subject`, `evaluation.verifier-ref`, `evaluation.result-schema`.

### 15.2 ScenarioProfile

A scenario is not a prediction: it is a baseline, assumptions, an intervention, and an engine that yields an expected transition or outcome.

| Field | Meaning |
|---|---|
| `baselineStateRef` | a file in the package (for example an EWS or ObservationSet document) or a URI |
| `assumptions`, `constraints` | lists of conditions |
| `intervention`, `uncertainty`, `expectedOutcome` | open mappings |
| `engine` | `kind` (`rule`, `score_ranking`, `optimization`, `simulation`, `ml_prediction`, `world_model`, `llm_reasoning`, or an extension value) and `ref` |
| `timeHorizon` | an ISO 8601 duration such as `P14D` |
| `confidence` | a number from 0 to 1 |
| `evidenceRefs` | supporting evidence |

Rules: `scenario.engine-kind`, `scenario.baseline-ref`, `scenario.confidence`.

### 15.3 CapabilityContract

A capability is the ability to achieve a class of outcomes under a defined context. Fields: `description`, `effect`, `context`, `requiredInputs`, `capacity`, `maturity`, `validityScope`, `evidenceRefs`. Scoring or assessment methods are not part of the contract; publishers add them as extensions.

### 15.4 WorldViewProfile

Besides `worldRef`, `purpose`, `projection`, and `conditioning`, a View MAY list `constraints` and `evidenceRefs`.
