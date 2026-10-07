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

## From records to observations

A State Compiler reads an ObservationSet: one entry per thing a source system recorded, with its `type`, its `subject`, when it was observed, and its `values`. For a CSV export with one record type per file, `ontle observations csv` does the mapping:

```bash
ontle observations csv qms_claims.csv --type QMS.claim --subject claim_id --time recorded_at > claims.yaml
ontle observations csv mes_lots.csv --type MES.production_lot --subject lot_id --time recorded_at --list genealogy > lots.yaml
ontle ews compile . --observations claims.yaml --observations lots.yaml --as-of 2026-09-05T00:00:00Z
```

The other columns become `values`, as strings unless you name them with `--number` or `--list`. For anything else (joins, renamed columns, several record types in one file), write the mapping yourself; a short script is enough:

```python
# records_to_observations.py: one CSV per record type -> an ObservationSet (YAML is a superset of JSON)
import csv, json, sys

FILES = {  # file -> (observation type, subject column, time column)
    "qms_claims.csv": ("QMS.claim", "claim_id", "recorded_at"),
    "qms_inspections.csv": ("QMS.inspection", "lot_id", "recorded_at"),
}
observations = []
for file, (otype, subject, time) in FILES.items():
    with open(file, newline="", encoding="utf-8") as f:
        for i, row in enumerate(csv.DictReader(f), 1):
            observations.append({
                "id": f"{otype}-{i}", "type": otype, "subject": row.pop(subject), "observedAt": row.pop(time),
                "values": row,  # the remaining columns; a binding's `value` names one of them
            })
json.dump({"apiVersion": "openworld/v1alpha1", "kind": "ObservationSet", "spec": {"observations": observations}}, sys.stdout, indent=2)
```

```bash
python records_to_observations.py > observations.json
ontle ews compile . --observations observations.json --as-of 2026-09-05T00:00:00Z
```

Ids must be unique across the set, and `observedAt` is UTC (`YYYY-MM-DDTHH:MM:SSZ`). A binding's `from` matches `type`, and its `value` names a key of `values`. To count only some records (say, failed inspections), keep one type and filter in the aggregate with `where` (section 5). [demos/business-ai/map_records.py](../demos/business-ai/map_records.py) is a fuller version that reads the record types from the World's source system profile. For records in a knowledge graph, `ontle kg extract` does the mapping declaratively.

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

A per-subject aggregate has a value only for subjects with observations, so a machine without alarms has no `alarms_24h`. To get 0 for it, declare where the subjects come from: `outputSchema.subjects: {from: [MES.equipment_state]}`. Then every machine with a state observation gets 0 from `count`, `distinct_count`, and `sum`, and a classification of that 0 gives its `otherwise` label (`normal`). `mean`, `min`, and `max` stay empty: there is no value to average.

## 5. Latent fields: estimate, aggregate, classify

State that is not observed directly is latent; list such fields in `latent` and bind each in one of three forms:

| Form | Binding | Example |
|---|---|---|
| Estimate | `{estimate: {from, value, select}}`, reading only observations that carry `estimatedBy` (a model's or person's estimate) | a health index from a degradation model |
| Aggregate | `{aggregate: {from, value, function, window, where}}`; `function` is `count`, `distinct_count`, `sum`, `mean`, `min`, or `max`; `window` an ISO 8601 duration such as `PT24H` or `P7D`; `where` keeps only matching observations | alarms in the last 24 hours |
| Classification | `{classify: {input: <another field>, criterion: {id, version, basis, rules, otherwise}}}`; rules `{when: {eq, in, gt, gte, lt, lte}, label}` are tried in order | `high` risk by an escalation SOP |

`where` filters the candidates of an aggregate with the same conditions a classification rule uses, on any key of the observation's `values`. Every condition must hold, and an observation without the key does not count:

```yaml
inspection.failures_7d:
  aggregate: {from: QMS.inspection, value: result, function: count, window: P7D,
              where: {result: {in: [seal_leak_detected, dimension_out_of_spec]}}}
line.hot_readings_24h:
  aggregate: {from: OT.temperature, value: celsius, function: count, window: PT24H,
              where: {celsius: {gte: 80}, sensor: {eq: T1}}}
```

A classification always names its criterion, so a consumer can tell which rule judged a value; `basis` may point at the SOP or standard it comes from. The EWS records how each latent value was produced in `derivation`.

## 6. Declare units

Give a numeric field its unit as a UCUM code: `outputSchema.units: {line.temp: Cel, item.events_24h: "{event}"}`. A count takes a dimensionless unit (`1` or an annotation in braces). An observation may report its unit (`units: {temp: Cel}`). If that differs from the field's unit, compilation refuses the input instead of converting. Convert where observations are acquired, before compiling. To say what the unit means in an ontology, add `unit: unit:DEG_C` (QUDT) to the field's SemanticBinding entry.

## 7. Read the EWS

| Section | Holds |
|---|---|
| `state` | fields with one value |
| `unresolved` | fields whose newest observations disagree: the alternatives are kept rather than one picked |
| `missing` | fields with no observation up to `asOf` (an aggregate count is 0 instead) |
| `provenance` | the observation ids each value came from |
| `derivation` | for latent fields: estimate, aggregate, or classification, and with what |

Every field of the compiler appears in exactly one of `state`, `unresolved`, and `missing` (for a per-subject field, each subject in one of them).

## 8. Check and keep an expected EWS

```bash
ontle ews compile . --observations examples/observations.yaml --as-of 2026-01-02T00:00:00Z > ews.yaml
ontle ews check ews.yaml --world .
ontle ews check examples/expected-ews.yaml --world . --observations examples/observations.yaml
```

`ews check` alone checks an EWS against its State Compiler's output contract: its shape, not its values. With `--observations` it also compiles them at the EWS's `asOf` and reports every field whose value, `unresolved`, `missing`, provenance, or derivation differs. Run it in CI to keep an expected EWS current. `--compiler state/<file>.yaml` compiles a compiler other than the World's default. Keep sample observations and the EWS they compile to under `examples/` and list them as `PackageExample` assets, as the starter does: a reader sees what the compiler produces, and a runtime can check that it produces the same.

## Common errors

| Message starts with | Meaning |
|---|---|
| `ews.opaque-compiler` | the compiler has no `bindings`; it can only be checked, not compiled |
| `ews.input` | an observation is malformed: missing `subject` on a per-subject field, a duplicate `id`, a non-UTC time |
| `compiler.binding` | a binding does not fit its field: a latent field with an observed binding, an unknown function, a classification cycle |
| `compiler.per-subject-field`, `compiler.latent-field` | `perSubject` or `latent` names a field the compiler does not declare |
