# Example Conventions

Business AI and Physical AI examples use the same OWP package concepts. Domain differences belong in asset contents, not in competing package standards.

## World package reference skeleton

```text
WORLD.md
owp.yaml
views/                 viewable and above: one or more WorldViewProfile contracts
  <task-view>.yaml
state/                 stateful and above: one or more StateCompilerProfile contracts
  <task-compiler>.yaml
interfaces/            optional, explicit World Interface contracts
  sources.yaml         when native source schemas matter
  observations.yaml    inbound acquisition/observation semantics
  actions.yaml         outbound action binding
  commit.yaml          command/business commit semantics
  effect-verification.yaml
scenarios/
examples/
```

A World package at `viewable`/`stateful` or above declares a default View / default State Compiler in `owp.yaml`. Both reference Worlds declare `conformance.profile: action-ready`; reference or taxonomy Worlds would normally stay `descriptive`. A domain MAY omit interface files that are not meaningful. For example, Physical AI often exposes sensor observations directly without an ERP-like source schema profile.

## World Model package reference skeleton

```text
WORLDMODEL.md
owp.yaml
models/
  model-artifact.yaml
  adapter.yaml
eval/
  <profile>.yaml       EvaluationProfile with metadata.version
  verifier.yaml        optional VerifierProfile
  evidence-*.yaml      optional CompatibilityEvidence
```

`semanticGrounding` MUST identify `worldRef`, at least one `compatibleWorldViews` entry, and at least one `compatibleStateCompilers` entry. A package may be contract-only. In that case `ModelArtifact` explicitly says that no implementation is bundled instead of inventing a fake external repository.

The WorldModel manifest also declares `inputs.contract: EffectiveWorldState` and an explicit `representation.adapterRef`. This keeps semantic state compilation separate from model-native preprocessing even when the adapter is an identity mapping.

## Invariants

- Source record != Observation != committed State.
- API/controller success != business/action commit != realized World change.
- WorldModel semantic grounding != whole-World model input.
- EffectiveWorldState != model-native tensor/latent representation.
- A result without a pinned EvaluationProfile version is not reusable evidence.
