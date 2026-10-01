# Manufacturing Quality World

Represents quality incidents and their evidence, production lineage, equipment context, decisions, corrective actions, and outcomes.

The package is intentionally not a full MES or QMS database schema. Native system records are bound through explicit interface/mapping assets.

## Conformance

Declared profile: `action-ready` — a World View, a State Compiler with a concrete EWS schema, and action/commit/effect-verification interfaces.

## Work (experimental)

`tasks/claim-rca.yaml` combines the Diagnose and Recommend work patterns, needs the quality-incident View and the RCA playbook (`knowledge/rca-playbook.yaml`), and produces the RCA report described by `artifacts/rca-report.yaml`. `consumers/quality-manager.yaml` describes how the quality manager receives the View. These asset kinds are experimental (spec Appendix C).

## Adjacent standards

ISA-95 (enterprise-control object models) and OPC UA (equipment information models) are referenced from `interfaces/sources.yaml`. OWP does not redefine them; it binds them to this World and View.
