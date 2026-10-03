# OWP — Evaluation, state, and scenarios

Part of the Open World Package specification; section numbers are shared across its documents (see the document map in `OWP_SPEC.md`). Read this when a package compiles Effective World State, records evaluation evidence, or defines evaluations, scenarios, and capabilities.

## 9. Evaluation lineage and evidence binding

A score is reusable only together with the exact evaluation that produced it. OWP records that binding; it does not run, triage, generate, or evolve evaluations. Failure triage, eval generation, golden-case accumulation, replay/regression/shadow runs, and promotion or rollback of evaluation criteria belong to runtimes and registries layered on top; their outputs re-enter OWP as new versions and new evidence.

No separate evaluation package kind exists. Evaluation assets are ordinary typed assets, usually in a WorldModelPackage.

`EvaluationProfile` and `VerifierProfile` assets SHOULD declare `metadata.version` (SemVer). A changed evaluation declares its lineage:

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

Timestamps are UTC strings `YYYY-MM-DDTHH:MM:SSZ` that denote a valid calendar instant (no leap seconds; any year from `0000` to `9999`, in the proleptic Gregorian calendar) and are compared as text. YAML authors SHOULD quote them. An implementation MUST read an unquoted timestamp as its source text and MUST NOT convert it to another representation. ObservationSet and EWS documents, including values inside `values`, are read under the YAML rules of section 5.2, so unquoted timestamps stay strings.

ObservationSet and EWS documents contain only the fields of `schemas/observation-set.schema.json` and `schemas/effective-world-state.schema.json`. An ObservationSet MAY carry `spec.provenance` (`extraction`, `parameters`, `snapshot`) recording where its observations came from; compilation ignores it. They may carry `extensions` blocks in `spec`, in each observation, and in the EWS `spec.context`; these documents have no manifest, so extension names are not checked against declarations. Compilation and EWS equality ignore extension blocks.

Observation values are JSON values that every JSON implementation reads exactly: `.inf`, `.nan`, and integers outside ±(2^53−1) (an integer-valued number such as `1e300` included) are invalid input (`ews.input`). Values are compared in the JSON data model: types must match (a boolean never equals a number), numbers compare numerically (`1` equals `1.0`), arrays compare element by element in order, and mappings compare by key set and values.

### 12.1 Output contract (applies to every runtime)

A State Compiler's EWS fields are `spec.outputSchema.fields`, or the field names listed by `spec.outputSchemaRef`:

- `outputSchemaRef` is a package-relative path in the form of a local asset path (section 5): relative POSIX, without a leading `./`, naming a file inside the package. It is an ordinary package file, not an asset. `outputSchemaRef: null` counts as absent.
- The file is a UTF-8 JSON document (RFC 8259; `NaN` and `Infinity` are not JSON) holding a JSON Schema whose top-level `properties` is a non-empty object. Its keys are the EWS fields. The subschemas are informative in this alpha; validators do not apply them to EWS values.
- A reference that is malformed, missing, unreadable, not JSON, or lacks such `properties` is the error `compiler.output-schema-ref`, and it contributes no fields.
- A compiler that declares both MUST list the same set of fields in each (`compiler.output-schema-mismatch`); `outputSchema.fields`, in its order, is then used.

An EWS document conforms to its State Compiler when:

- `worldRef` is the World's identity, `stateCompiler` is `<worldRef>#<compiler path>`, and `worldView` is `<worldRef>#<the compiler's worldViewRef>`.
- When the compiler has EWS fields, each of those fields appears in exactly one of `state`, `unresolved`, `missing`, and no other field appears.
- Each `unresolved` field retains at least two distinct alternatives.
- Absent or null `unresolved`, `missing`, `provenance`, or `derivation` sections are empty. Checking an EWS does not require the World package to be valid; it requires the named State Compiler to be a local asset.
- `provenance` has entries only for fields in `state` or `unresolved`; when the compiler declares `traceRequired: true`, every such field has non-empty provenance.
- Per-subject fields (section 12.3) have a mapping from subject to value in `state` and `unresolved`, and to observation ids in `provenance` (`ews.per-subject-shape`). Such a field MAY appear in both `state` and `unresolved`, but no subject appears in both (`ews.per-subject-overlap`); each subject in `unresolved` retains at least two distinct alternatives; with `traceRequired: true`, each subject has non-empty provenance. A per-subject field in `missing` appears nowhere else.
- Latent fields (section 12.4) that have a value have a `derivation` entry, and no other field has one (`ews.derivation`).

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

Preconditions: the compiler is a local `StateCompilerProfile` asset of the World; a compiler without `spec.bindings` is opaque and compiling it MUST be refused; the input document has `kind: ObservationSet`; each observation has a string `id` and `type`, a valid `observedAt`, and a `values` mapping. The World package itself need not be valid.

1. Candidates are observations with `type == from`, `observedAt <= asOf`, and a `values` key equal to `value`, ordered by (`observedAt`, `id`), with `id` compared by Unicode code point.
2. No binding, or no candidates: the field is `missing`.
3. `select: all`: `state[field]` is the list of candidate values in candidate order; provenance is every candidate id.
4. `select: latest`: take the candidates with the greatest `observedAt`. If their values are all equal, `state[field]` is that value; otherwise `unresolved[field]` lists the distinct values in candidate order (first occurrence kept). Provenance is the ids of those newest candidates.

Invalid input (duplicate ids, a missing `id`/`type`/`values`, a non-UTC timestamp, an undefined field) MUST be rejected rather than compiled.

Two EWS documents are equal when `worldRef`, `worldView`, `stateCompiler`, `asOf`, `state`, `unresolved`, and `derivation` are equal, `missing` is equal as a set, and each `provenance` entry (for a per-subject field, each subject's entry) is equal as a set.

Reference CLI: `ontle ews compile <world> --compiler <path> --observations <file> --as-of <timestamp>`.

### 12.3 Per-subject fields

An observation MAY name its `subject`: the thing it is about (a machine, a lot, a work item). A field the compiler lists in `spec.outputSchema.perSubject` holds one value per subject instead of one value for the whole View. `perSubject` names EWS fields of the compiler (`compiler.per-subject-field`); it MAY accompany `outputSchemaRef`, in which case `outputSchema.fields` may be omitted.

```yaml
outputSchema:
  fields: [equipment.state, plant.alert_level]
  perSubject: [equipment.state]
```

Compilation of a per-subject field: every candidate MUST have a string `subject`, or the input is rejected. Candidates are grouped by `subject`, and rules 3 and 4 of section 12.2 apply to each group. `state[field]`, `unresolved[field]`, and `provenance[field]` are mappings keyed by subject; subjects without candidates do not appear, and a field with no candidates at all is `missing`. In the EWS above, two observations of `press-7` (08:00 `running`, 09:00 `down`) and two of `robot-2` at 09:30 (`running`, `idle`) give `state: {equipment.state: {press-7: down}}` and `unresolved: {equipment.state: {robot-2: [running, idle]}}`.

Subjects are the observation's `subject` strings, compared exactly. A SemanticBinding MAY map them to IRIs (section 14), which links per-subject state to the individuals of a knowledge graph.

### 12.4 Latent fields

State that is not observed directly is latent. OWP distinguishes three ways a latent value is produced and keeps them apart from observed state: an **estimate** (a model, estimator, or person's estimate of a value), an **aggregate** (a value computed from measurements over a time window), and a **classification** (a label assigned by a declared criterion). A compiler lists its latent fields in `spec.outputSchema.latent` (`compiler.latent-field`); each of them has a binding of one of the three forms below, and every other bound field has the observation binding of section 12.2 (`compiler.binding`).

```yaml
outputSchema:
  fields: [equipment.state, equipment.alarms_24h, equipment.risk, equipment.health]
  perSubject: [equipment.state, equipment.alarms_24h, equipment.risk, equipment.health]
  latent: [equipment.alarms_24h, equipment.risk, equipment.health]
bindings:
  equipment.state: {from: OT.equipment_state, value: state, select: latest}
  equipment.health: {estimate: {from: WM.health, value: index, select: latest}}
  equipment.alarms_24h: {aggregate: {from: OT.alarm, value: code, function: count, window: PT24H}}
  equipment.risk:
    classify:
      input: equipment.alarms_24h
      criterion:
        id: alarm-escalation
        version: 1.2.0
        basis: docs/alarm-escalation-sop.md
        rules:
        - {when: {gte: 5}, label: high}
        - {when: {gte: 2}, label: elevated}
        otherwise: normal
```

**Estimates.** An observation that is an estimate names its producer in `estimatedBy` (a package reference, an asset path, or another identifier) and MAY carry `uncertainty` (any JSON value). An observation binding of section 12.2 ignores observations with `estimatedBy`, so an estimate never becomes observed state; an `estimate` binding (`from`, `value`, `select`) considers only them and otherwise compiles as in section 12.2.

**Aggregates.** An `aggregate` binding has `from`, `value`, `function` (`count`, `distinct_count`, `sum`, `mean`, `min`, `max`), and optionally `window`, an ISO 8601 duration of days, hours, minutes, and seconds (`P7D`, `PT24H`, `P1DT12H`). Candidates are the observations of section 12.2 rule 1 without `estimatedBy`, further limited to `observedAt` after `asOf` minus `window` when a window is given. `count` is the number of candidates and `distinct_count` the number of distinct values; both are 0 when there are none. `sum`, `mean`, `min`, and `max` need every candidate value to be a number, or the input is rejected; `sum` is 0 without candidates, and `mean`, `min`, and `max` are then `missing`. Values are combined in candidate order. Provenance is every candidate id; an aggregate over no candidates has an empty provenance list, which satisfies `traceRequired`.

**Classifications.** A `classify` binding has `input`, another EWS field of the same compiler, and `criterion`: the declared basis of the judgement. `criterion.id` names it, `criterion.version` (SemVer) versions it, and `criterion.basis` MAY point at its source (a package file or a URI such as a standard or SOP). `criterion.rules` is a list of `{when, label}` tried in order; `when` holds one or more of `eq`, `in` (JSON value equality), `gt`, `gte`, `lt`, `lte` (numbers only; any other operand never matches), all of which must hold. The first matching rule gives the label; with no match, `otherwise` gives it, or the field is `missing` when `otherwise` is absent. A classification is per-subject exactly when its input is; it uses the input's value for each subject, applies the criterion to each alternative of an unresolved input (one distinct label resolves, several are `unresolved`), is `missing` where the input is, and takes the input's provenance. Inputs MUST NOT form a cycle (`compiler.binding`).

**Derivation record.** For each latent field with a value the EWS has an entry in `spec.derivation`:

| Form | Entry |
|---|---|
| estimate | `{kind: estimate, by: [<estimatedBy values of the provenance observations, distinct, sorted>]}`; per subject, `by` is a mapping from subject to that list |
| aggregate | `{kind: aggregate, from, value, function}` and `window` when declared |
| classification | `{kind: classify, input, criterion: {id}}` with `version` and `basis` when declared |

The record states how a latent value was produced, so a consumer can tell a measured `down` from an estimated health index or a `high` risk judged by `alarm-escalation@1.2.0`. An opaque compiler declares `latent` the same way and its EWS carries the same records.

### 12.5 Units

A State Compiler MAY declare the unit of a field's values in `spec.outputSchema.units`, a mapping from EWS field to a UCUM code (`Cel`, `mm/s`, `kW.h`, `{alarm}`). Units are declared per field and never per value: EWS values stay plain JSON, so EWS equality (section 12.2) and the numeric rules of 12.4 are unchanged. A unit is a property of the compiler that `stateCompiler` names, and EWS documents carry none.

```yaml
outputSchema:
  fields: [line.temp, equipment.alarms_24h]
  units: {line.temp: Cel, equipment.alarms_24h: "{alarm}"}
```

- `units` keys are EWS fields of the compiler, and values are UCUM codes: non-empty printable ASCII without spaces (`compiler.unit`). Codes are compared as text; `mm/s` and `mm.s-1` are different codes.
- A `count` or `distinct_count` field, if it declares a unit, declares a dimensionless one: `1` or an annotation only, such as `{alarm}` (`compiler.unit`).
- A classification field declares no unit, since a label has none. A `criterion` MAY declare `unit`, which MUST equal its input field's unit (`compiler.unit`), so that a threshold is not read in the wrong unit.
- An observation MAY report units per `values` key: `units: {c: Cel}`. When a candidate reports a unit for the key a binding reads and the field declares a different one, the input is rejected (`ews.input`). A candidate without a reported unit is taken to be in the declared unit.
- A `sum`, `mean`, `min`, or `max` aggregate rejects candidates that report different units, whether or not the field declares one (`ews.input`).
- Implementations MUST NOT convert units. Conversion belongs before compilation, where observations are acquired.

A SemanticBinding MAY name the unit as an ontology term, such as a QUDT unit (section 14). The UCUM code in the compiler is what compilation checks.

## 15. Evaluation, scenario, capability, and view fields

These fields of standard kinds are part of the standard. Their schemas are under `schemas/`; undefined keys are errors (section 8).

### 15.1 EvaluationProfile

| Field | Meaning |
|---|---|
| `assessmentKind` | `verification` (conditions, facts, or specifications are met), `validation` (fit for purpose), `evaluation` (quality or performance against criteria), `review` (an examination activity), or `approval` (an authorized decision to use or execute); or an extension value |
| `subject` | `kind` (`model`, `agent`, `workflow`, `artifact`, `decision`, `process`, `capability`, `environment`, or an extension value) and `ref` (a local asset path, or a reference containing `#` or `@`) |
| `objective`, `criteria` | what is assessed; each criterion has `metric`, `rubric`, and `threshold` |
| `verifierRef` | a local VerifierProfile path or a pinned `<name>@<version>` |
| `evidenceRefs`, `validityScope` | supporting evidence; where the profile applies |
| `resultSchemaRef` | a file in the package describing results |
| `evaluatorRef` | the actor that performs the assessment: a local ActorProfile (section 17) |

Rules: `evaluation.assessment-kind`, `evaluation.subject`, `evaluation.verifier-ref`, `evaluation.result-schema`, `evaluation.evaluator-ref`.

### 15.2 ScenarioProfile

A scenario is not a prediction: it is a baseline, assumptions, an intervention, and an engine that yields an expected transition or outcome.

| Field | Meaning |
|---|---|
| `baselineStateRef` | a file in the package (for example an EWS or ObservationSet document) or a URI |
| `assumptions`, `constraints` | lists of conditions |
| `intervention`, `uncertainty`, `expectedOutcome` | open mappings; by convention `uncertainty` gives each outcome variable as `{low, mode, high}` (a missing `mode` reads as the midpoint), which three-point and Monte Carlo models use directly |
| `engine` | `kind` (`rule`, `score_ranking`, `optimization`, `simulation`, `ml_prediction`, `world_model`, `llm_reasoning`, or an extension value) and `ref` |
| `timeHorizon` | an ISO 8601 duration such as `P14D` |
| `confidence` | a number from 0 to 1 |
| `evidenceRefs` | supporting evidence |

Rules: `scenario.engine-kind`, `scenario.baseline-ref`, `scenario.confidence`.

### 15.3 CapabilityContract

A capability is the ability to achieve a class of outcomes under a defined context. Fields: `description`, `effect`, `outcomeRefs` (the outcomes it achieves), `context`, `requiredInputs`, `capacity`, `maturity`, `validityScope`, `evidenceRefs`. Scoring or assessment methods are not part of the contract; publishers add them as extensions.

### 15.4 WorldViewProfile

A View's fields follow `WorldView = Project(World, ViewSpec)` (section 6):

| Field | Holds |
|---|---|
| `purpose` | what the View is for, as text: `task`, `objective`, `actorScope` |
| `projection` | what is selected and how it is represented: `include`, `exclude` (experimental, Appendix C), `principle`, `scale`, `resolution`, `timeScope` |
| `conditioning` | optional conditions: `authorityScope`, and the references `actorRef` (ActorProfile), `roleRefs` (RoleProfile), `taskRef` (TaskSetProfile) of sections 16-17 (`view.conditioning-ref`) |
| `externalWorldRefs` | other Worlds the View reads (section 6) |

A View MAY also list `constraints` and `evidenceRefs`.
