# Compiling state

A World says what exists. A World View picks what one task needs. A State Compiler turns observations into the Effective World State (EWS) of that View at one moment: the state a model, agent, or person acts on. This guide writes a State Compiler step by step, starting from the one `ontle init` generates. The normative rules are in [spec section 12](../spec/OWP_EVALUATION_AND_STATE.md#12-effective-world-state-documents).

## 1. Start from the starter

```bash
ontle init my-world && cd my-world
ontle ews compile . --observations examples/observations.yaml --as-of 2026-01-02T00:00:00Z
```

`state/default-compiler.yaml` declares three fields, one of each kind, with one value per item:

```yaml
outputSchema:
  fields: [item.status, item.events_24h, item.attention]
  perSubject: [item.status, item.events_24h, item.attention]
  latent: [item.events_24h, item.attention]
bindings:
  item.status: {from: source.item_status, value: status, select: latest}
  item.events_24h: {aggregate: {from: source.item_event, value: code, function: count, window: PT24H}}
  item.attention:
    classify:
      input: item.events_24h
      criterion:
        id: attention-threshold
        version: 0.1.0
        rules:
        - {when: {gte: 2}, label: needs_attention}
        otherwise: normal
```

Rename `item` to your own entities and add fields as you go; the rest of this guide explains each part.

## 2. Name fields inside the View

A field name is `<name>.<attribute>`. Its first part must be something the View includes (`projection.include` in the View), and what the View includes should be inside the World's boundary (`spec.world.boundary.included`). Otherwise validation warns with `compiler.field-outside-view` or `view.outside-world`. For a field `zone.picks_4h`, add `zone` to both.

## 3. Bind observed fields

Observations come as an ObservationSet. Each has an `id`, a `type`, an `observedAt` (UTC, `YYYY-MM-DDTHH:MM:SSZ`, quoted), `values`, and usually a `subject`, the thing it is about:

```yaml
- {id: s3, type: source.item_status, subject: item-2, observedAt: "2026-01-01T15:00:00Z", values: {status: blocked}}
```

A binding `{from: <type>, value: <key>, select: latest}` takes the newest value of that key; `select: all` takes every value, oldest first. Observations after `asOf` are ignored.

## 4. One value per subject

Listing a field in `perSubject` gives it one value per `subject` instead of one for the whole View: `item.status: {item-1: active, item-2: blocked}`. Every observation a per-subject field uses must have a `subject`.

## 5. Latent fields: estimate, aggregate, classify

State that is not observed directly is latent; list such fields in `latent` and bind each in one of three forms:

| Form | Binding | Example |
|---|---|---|
| Estimate | `{estimate: {from, value, select}}`, reading only observations that carry `estimatedBy` (a model's or person's estimate) | a health index from a degradation model |
| Aggregate | `{aggregate: {from, value, function, window}}`; `function` is `count`, `distinct_count`, `sum`, `mean`, `min`, or `max`; `window` an ISO 8601 duration such as `PT24H` or `P7D` | alarms in the last 24 hours |
| Classification | `{classify: {input: <another field>, criterion: {id, version, basis, rules, otherwise}}}`; rules `{when: {eq, in, gt, gte, lt, lte}, label}` are tried in order | `high` risk by an escalation SOP |

A classification always names its criterion, so a consumer can tell which rule judged a value; `basis` may point at the SOP or standard it comes from. The EWS records how each latent value was produced in `derivation`.

## 6. Read the EWS

| Section | Holds |
|---|---|
| `state` | fields with one value |
| `unresolved` | fields whose newest observations disagree: the alternatives are kept rather than one picked |
| `missing` | fields with no observation up to `asOf` (an aggregate count is 0 instead) |
| `provenance` | the observation ids each value came from |
| `derivation` | for latent fields: estimate, aggregate, or classification, and with what |

Every field of the compiler appears in exactly one of `state`, `unresolved`, and `missing` (for a per-subject field, each subject in one of them).

## 7. Check and keep an expected EWS

```bash
ontle ews compile . --observations examples/observations.yaml --as-of 2026-01-02T00:00:00Z > ews.yaml
ontle ews check ews.yaml --world .
```

`--compiler state/<file>.yaml` compiles a compiler other than the World's default. Keep sample observations and the EWS they compile to under `examples/` and list them as `PackageExample` assets, as the starter does: a reader sees what the compiler produces, and a runtime can check that it produces the same.

## Common errors

| Message starts with | Meaning |
|---|---|
| `ews.opaque-compiler` | the compiler has no `bindings`; it can only be checked, not compiled |
| `ews.input` | an observation is malformed: missing `subject` on a per-subject field, a duplicate `id`, a non-UTC time |
| `compiler.binding` | a binding does not fit its field: a latent field with an observed binding, an unknown function, a classification cycle |
| `compiler.per-subject-field`, `compiler.latent-field` | `perSubject` or `latent` names a field the compiler does not declare |
