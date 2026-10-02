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
- Conformance suite: 165 validation, 27 resolution, 20 EWS compile, 16 EWS check, 12 extraction cases.
- Two implementations pass the suite: the Python reference and a clean-room TypeScript implementation.

## 1. Release 0.2.0a3

1. Move the `Unreleased` CHANGELOG section to `0.2.0-alpha.3`; bump `pyproject.toml` and `src/ontle/__init__.py`.
2. Regenerate `RELEASE_MANIFEST.json`; tag after CI passes.

## 2. Close known alpha limitations in the spec and suite

Order matters: each item can change verdicts, so both implementations and the suite move together.

1. **YAML profile for all OWP documents.** Specify the YAML 1.2 core schema for `owp.yaml` and assets, not only for ObservationSet and EWS documents. Today the Python reference reads manifests as YAML 1.1 (`yes` → true, `0755` → 493, `1:20` → 80), while YAML 1.2 loaders do not. Switch the reference loader and add cases.
2. **`outputSchemaRef` resolution.** Define it as a package-relative JSON Schema that lists EWS fields, apply the §12.1 field rules to it, and retire the `schema-ref-only-compiler` alpha-limitation case.
3. ~~**Warnings in the suite.**~~ Done: cases may list `warnings`; warning ids are in spec Appendix A.
4. **Recorded revisions.** Add the expected `git:<commit>` / `sha256:<digest>` revisions to resolution cases so recorded revisions are compared across implementations.
5. ~~**Machine-readable rule ids.**~~ Done: `spec/rule-ids.yaml`, checked by `tests/test_rule_ids.py`.

## 3. Bind the examples to real external artifacts

The examples currently declare which standard each part uses but leave the artifact unbound (`ref: null`, `status: unbound`):

| Example | Binding | Status |
|---|---|---|
| mobile-manipulation-world | ROS 2 message and action types | bound by type name |
| mobile-manipulation-world | OpenUSD scene | unbound |
| mobile-manipulation-world | LeRobot episodes (Hugging Face) | unbound |
| manufacturing-quality-world | ISA-95 object models | bound by name |
| manufacturing-quality-world | OPC UA companion specification | unbound |

1. Define the `standardBindings` shape in the spec (standard, ref, immutable revision or digest, license, status) and validate that bound references are pinned.
2. Choose public artifacts with compatible licenses: a LeRobot dataset revision, an OpenUSD scene, and an OPC UA companion specification identifier.
3. Bind them in the examples. Do not invent repositories or revisions; leave a binding unbound until a real artifact is chosen.

## 4. End-to-end demos

One Physical AI and one Business AI demo, each validated by both implementations:

```text
World -> View -> State Compiler -> EWS (from real sample data) -> Representation Adapter -> model stub -> CompatibilityEvidence
```

The Physical AI demo uses the bound LeRobot episodes and scene; the Business AI demo uses sample MES/QMS records mapped through the ISA-95 bindings.

## 5. Distribution without a hosted registry (done in the reference CLI; see spec sections 7, 7.1, 9.1, 11.1)

1. OCI source type: push and pull `.owp.zip` with ORAS to existing registries (GHCR, Docker Hub); record the OCI digest as the revision.
2. Static package index: a git repository of JSON index files served as static pages, listing identities, versions, and digests.

## 6. Independence and governance

1. Move `implementations/typescript/` to its own repository and publish to npm once it has maintainers of its own; keep running it against this suite in CI.
2. Invite a third-party implementation; a clean-room implementation by the same authors is weaker evidence than one by an independent party.
3. Define the promotion criteria for `openworld/v1beta1`: at least two independently maintained implementations, no open High-severity spec ambiguities, and a spec change process (proposal, suite update, both implementations updated).

## 7. Hosted ONTLE Registry (separate platform)

Namespace ownership, search, evidence aggregation, and certification scopes need a hosted service. It is a separate deployment that consumes this repository's spec and packages; it is not built here.

## Out of scope for this repository

- Evaluation execution, failure triage, evaluation generation, and promotion workflows (runtime and registry concerns; their outputs re-enter OWP as new versions and evidence).
- Runtime execution, connectors, and transactional commit handling.
- Model weight or checkpoint formats.
