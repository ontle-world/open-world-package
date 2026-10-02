# Manufacturing Quality World

Represents quality incidents and their evidence, production lineage, equipment context, decisions, corrective actions, and outcomes.

The package is intentionally not a full MES or QMS database schema. Native system records are bound through explicit interface/mapping assets.

## Conformance

Declared profile: `action-ready` — a World View, a State Compiler with a concrete EWS schema, and action/commit/effect-verification interfaces.

## Semantics

`semantics/quality-terms.yaml` binds the World's names, all seven EWS fields, the observation types, and the actions to terms of `openworld-examples/quality-ontology` (a dependency). Check it with `ontle validate --resolve --source examples`.

## Knowledge graph (experimental)

`knowledge/plant-kg.yaml` is a small illustrative plant graph (`kg/plant.ttl`). `extraction/claim-context.yaml` selects the lots, equipment, and parts behind one claim: `ontle kg extract . --profile extraction/claim-context.yaml --param claimId=C-102` produces `examples/kg-observations.yaml`, and compiling it together with `examples/observations.yaml` gives `examples/expected-ews-with-kg.yaml`.

## Work (experimental)

`tasks/claim-rca.yaml` combines the Diagnose and Recommend work patterns, needs the quality-incident View and the RCA playbook (`knowledge/rca-playbook.yaml`), and produces the RCA report described by `artifacts/rca-report.yaml`. `consumers/quality-manager.yaml` describes how the quality manager receives the View. These asset kinds are experimental (spec Appendix C).

## Adjacent standards

ISA-95 (enterprise-control object models) and OPC UA (equipment information models) are referenced from `interfaces/sources.yaml`. OWP does not redefine them; it binds them to this World and View. The OPC UA binding points at the OPC 40001-1 Machinery 1.04.1 NodeSet in the OPC Foundation UA-Nodeset repository, pinned by digest (the NodeSet files are under the OPC Foundation MIT License 1.00; the specification documents are not redistributable and are only linked).
