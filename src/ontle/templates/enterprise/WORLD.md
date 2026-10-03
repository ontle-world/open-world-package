# Enterprise World

## Definition

An intentionally incomplete enterprise representation designed for reusable task views and explicit source/action bindings.

## Interface boundary

Inbound sources can include ERP, MES, QMS, CRM, documents, APIs, events, and human observations.

Outbound bindings can include controlled API writes, approvals, workflows, notifications, and business commits.

Keep:

```text
Source Record != Observation != State
API Success != Business Commit != Realized World Change
```

## Validity and limitations

This package does not require copying all enterprise data into a single graph or database.

## State

`views/default.yaml` is the default World View and `state/default-compiler.yaml` its State Compiler. The compiler starts with three fields per item, one of each kind: an observed status, an aggregate (events in the last 24 hours), and a classification of that aggregate by a named criterion. `examples/observations.yaml` holds sample observations and `examples/expected-ews.yaml` the Effective World State they compile to.

Try it, then replace the `item` fields with your own:

```bash
ontle validate .
ontle ews compile . --observations examples/observations.yaml --as-of 2026-01-02T00:00:00Z > ews.yaml
ontle ews check ews.yaml --world .
```

Writing fields and bindings: docs/STATE_COMPILATION.md in the OWP repository.
