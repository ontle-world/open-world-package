# Manufacturing Quality World

Represents quality incidents and their evidence, production lineage, equipment context, decisions, corrective actions, and outcomes.

## Scope

Included: `quality_incident`, `lot`, `equipment`, `inspection`, `claim`, `evidence`, `constraint`, `decision`, `capa`, `outcome`.

Excluded: `complete_mes_implementation`, `complete_qms_implementation`.

The package is intentionally not a full MES or QMS database schema.

## Sources

- Source systems (`interfaces/sources.yaml`): MES (production orders, operation execution, production lots, equipment, defect events) and QMS (inspections, nonconformances, claims, CAPA, verification).
- Standards: ISA-95 and OPC UA, bound in `interfaces/sources.yaml` (see Adjacent standards).
- Ontology: `openworld-examples/quality-ontology@0.1.0`, a dependency.
- Knowledge graph: `knowledge/plant-kg.yaml`, a small illustrative plant graph.

Native system records are bound through explicit interface/mapping assets.

## Use it for

- What is the current status of an incident, its claim, and its CAPA, and which inspection results and equipment condition events go with it?
- Which lots, equipment, and parts are behind a customer claim (`extraction/claim-context.yaml`)?
- Should affected lots be put on quality hold (`scenarios/quality-hold.yaml`)?
- Trace a claim to production and equipment evidence and propose a reviewed RCA and CAPA (`tasks/claim-rca.yaml`).
- Check whether a committed action had its intended effect: QMS status, follow-up inspection, CAPA outcome (`interfaces/effect-verification.yaml`).

## Limitations

- Reference semantic package; source systems remain external.
- `evidence.open_hypotheses` is in the EWS schema but has no binding in the State Compiler.
- The RCA playbook (`knowledge/rca-playbook.yaml`) has no bound content.
- The plant knowledge graph holds no real plant data.
- Task, work, artifact, and consumer assets are experimental (spec Appendix C).

## Versions

- 0.1.0: first public example.

## Conformance

Declared profile: `action-ready` — a World View, a State Compiler with a concrete EWS schema, and action/commit/effect-verification interfaces.

## Semantics

`semantics/quality-terms.yaml` binds the World's names, all nine EWS fields, the observation types, and the actions to terms of `openworld-examples/quality-ontology` (a dependency). Check it with `ontle validate --resolve --source examples`.

## Knowledge graph (experimental)

`knowledge/plant-kg.yaml` is a small illustrative plant graph (`kg/plant.ttl`). It is the A-box for the T-box in `openworld-examples/quality-ontology`; `ontle kg check . --source ../..` confirms it uses only that ontology's classes and properties, within their domains and ranges. `extraction/claim-context.yaml` selects the lots, equipment, and parts behind one claim: `ontle kg extract . --profile extraction/claim-context.yaml --param claimId=C-102` produces `examples/kg-observations.yaml`, and compiling it together with `examples/observations.yaml` gives `examples/expected-ews-with-kg.yaml`.

## Work (experimental)

`tasks/claim-rca.yaml` combines the Diagnose and Recommend work patterns, needs the quality-incident View and the RCA playbook (`knowledge/rca-playbook.yaml`), and produces the RCA report described by `artifacts/rca-report.yaml`. `consumers/quality-manager.yaml` describes how the quality manager receives the View. These asset kinds are experimental (spec Appendix C).

## Adjacent standards

ISA-95 (enterprise-control object models) and OPC UA (equipment information models) are referenced from `interfaces/sources.yaml`. OWP does not redefine them; it binds them to this World and View. The OPC UA binding points at the OPC 40001-1 Machinery 1.04.1 NodeSet in the OPC Foundation UA-Nodeset repository, pinned by digest (the NodeSet files are under the OPC Foundation MIT License 1.00; the specification documents are not redistributable and are only linked).
