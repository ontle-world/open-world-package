# Roadmap

This file lists, in order, how this repository is expected to change. Each step should land as its own change with the conformance suite passing in both implementations (`src/ontle/` and `implementations/typescript/`).

OWP stays a portable contract: World, View, State Compiler, EWS, World Model applicability, evaluation lineage, and evidence. Evaluation execution and evolution, runtime execution, and model weight formats stay out of this repository (see "Out of scope").

## Current state (Unreleased)

- WorldPackage conformance profiles (`descriptive` → `action-ready`); every World Model names its compatible Views and State Compilers.
- Evaluation lineage and pinned `CompatibilityEvidence`.
- Registry-free dependency resolution (directory, `.owp.zip`, git).
- Standard EWS documents, output-contract checks, and optional declarative bindings.
- Stable rule ids (spec Appendix A).
- Publisher extensions (spec section 13), closed document schemas, and a rule-id registry (`spec/rule-ids.yaml`).
- Conformance suite: 206 validation, 29 resolution, 28 EWS compile, 22 EWS check, 13 extraction cases.
- Two implementations pass the suite: the Python reference and a clean-room TypeScript implementation.

## 1. Release 0.2.0a3

1. Move the `Unreleased` CHANGELOG section to `0.2.0-alpha.3`; bump `pyproject.toml` and `src/ontle/__init__.py`.
2. Regenerate `RELEASE_MANIFEST.json`; tag after CI passes.

## 2. Close known alpha limitations in the spec and suite

Order matters: each item can change verdicts, so both implementations and the suite move together.

1. ~~**YAML profile for all OWP documents.**~~ Done: spec section 5.2; both implementations read every OWP YAML document with the YAML 1.2 core schema and reject duplicate keys.
2. ~~**`outputSchemaRef` resolution.**~~ Done: spec section 12.1; the EWS fields are the top-level `properties` of a package-relative JSON Schema, and the field rules apply to them.
3. ~~**Warnings in the suite.**~~ Done: cases may list `warnings`; warning ids are in spec Appendix A.
4. ~~**Recorded revisions.**~~ Done: valid resolution cases list `resolved` (identity and recorded revision); both implementations match them.
5. ~~**Machine-readable rule ids.**~~ Done: `spec/rule-ids.yaml`, checked by `tests/test_rule_ids.py`.

## 3. Bind the examples to real external artifacts

| Example | Binding | Status |
|---|---|---|
| mobile-manipulation-world | ROS 2 message and action types | `terms` (type names) |
| mobile-manipulation-world | OpenUSD scene | bound: `nvidia/PhysicalAI-SimReady-Warehouse-01` @ `c7fe115c`, CC-BY-4.0 |
| mobile-manipulation-world | LeRobot episodes (Hugging Face) | bound: `k-chan-l/lekiwi_pick_and_place2` @ `de33a7ae`, Apache-2.0 |
| manufacturing-quality-world | ISA-95 object models | `terms` (object model names) |
| manufacturing-quality-world | OPC UA companion specification | bound: OPC 40001-1 Machinery 1.04.1 NodeSet, digest-pinned, MIT |

1. ~~Define the `standardBindings` shape in the spec and validate that bound references are pinned.~~ Done: spec section 5.3 (`standard`, `ref`, `license`, `terms`); a bound reference must be pinned and licensed. The examples use this shape.
2. ~~Choose public artifacts with compatible licenses.~~ Done: chosen for pinnability, license, fit to the World, size, and anonymous download.
3. ~~Bind them in the examples.~~ Done. Open: the LeRobot dataset is a personal repository (pinning keeps it reproducible, not available), and the OPC UA bindings pin Machinery with its DI and IA models but not the core OPC UA model.

## 4. End-to-end demos

One Physical AI and one Business AI demo, each validated by both implementations:

```text
World -> View -> State Compiler -> EWS (from real sample data) -> Representation Adapter -> model stub -> CompatibilityEvidence
```

The Physical AI demo uses the bound LeRobot episodes and scene; the Business AI demo uses sample MES/QMS records mapped through the ISA-95 bindings.

Done: `demos/physical-ai/` (one real LeKiwi episode, a hold-position stub, detached evidence) and `demos/business-ai/` (sample MES/QMS records through the ISA-95 binding, a rule stub, detached evidence). Both implementations check the EWS and the evidence binding.

## 5. Distribution without a hosted registry (done in the reference CLI; see spec sections 7, 7.1, 9.1, 11.1)

1. OCI source type: push and pull `.owp.zip` with ORAS to existing registries (GHCR, Docker Hub); record the OCI digest as the revision.
2. Static package index: a git repository of JSON index files served as static pages, listing identities, versions, and digests.

## 6. Hosted ONTLE Registry (separate platform)

Namespace ownership, search, evidence aggregation, and certification scopes need a hosted service. It is a separate deployment that consumes this repository's spec and packages; it is not built here.

## Out of scope for this repository

- Evaluation execution, failure triage, evaluation generation, and promotion workflows (runtime and registry concerns; their outputs re-enter OWP as new versions and evidence).
- Runtime execution, connectors, and transactional commit handling.
- Runtime contexts built from EWS (an actor's current context, the operational or decision context) and the product surfaces that present them, such as a WorldView board.
- Model weight or checkpoint formats.
