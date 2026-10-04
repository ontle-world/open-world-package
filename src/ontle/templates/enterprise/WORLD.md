# Enterprise World

An intentionally incomplete enterprise representation designed for reusable task views and explicit source and action bindings. Put the one-line summary in `metadata.description` in `owp.yaml`; catalogs show it on the package card.

## Scope

Included:

- Add included entities, processes, and relations (`spec.world.boundary.included`).

Excluded:

- Add intentional exclusions (`spec.world.boundary.excluded`).

## Sources

Inbound sources can include ERP, MES, QMS, CRM, documents, APIs, events, and human observations (`interfaces/sources.yaml`, `interfaces/observations.yaml`).

Outbound bindings can include controlled API writes, approvals, workflows, notifications, and business commits (`interfaces/actions.yaml`, `interfaces/commit.yaml`).

Keep:

```text
Source Record != Observation != State
API Success != Business Commit != Realized World Change
```

## Use it for

- Three to five questions a user or agent can answer with this World, or decisions it supports.

## Limitations

This package does not require copying all enterprise data into a single graph or database. State the assumptions and known blind spots, and the fields that have no binding yet.

## Versions

- 0.1.0: first version.

## State

`views/default.yaml` is the default World View and `state/default-compiler.yaml` its State Compiler. The compiler starts with three fields per item, one of each kind: an observed status, an aggregate (events in the last 24 hours), and a classification of that aggregate by a named criterion. `examples/observations.yaml` holds sample observations and `examples/expected-ews.yaml` the Effective World State they compile to.

Try it, then replace the `item` fields with your own:

```bash
ontle validate .
ontle ews compile . --observations examples/observations.yaml --as-of 2026-01-02T00:00:00Z > ews.yaml
ontle ews check ews.yaml --world .
```

Writing fields and bindings: docs/STATE_COMPILATION.md in the OWP repository.
