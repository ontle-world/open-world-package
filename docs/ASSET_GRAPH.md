# Public Asset Graph Model

The authoring surface is intentionally small, but a Registry may index a richer typed graph.

Representative asset kinds (`vocab/asset-kinds.yaml` lists them all with their stability):

- World: the manifest's `spec.world`, SemanticBinding, WorldViewProfile, StateCompilerProfile
- Ontology (T-box): SemanticProfile, OntologyTermIndex
- Integration: SourceSystemSchemaProfile, ObservationAcquisitionProfile, ActionBindingProfile, CommitContract, EffectVerificationProfile
- Scenarios and environments: ScenarioProfile, EnvironmentProfile
- Models: the manifest's `spec.worldModel`, ModelArtifact, RepresentationAdapterProfile
- Evaluation: Dataset, EvaluationProfile, VerifierPackage, CompatibilityEvidence
- Reserved names without a definition yet: SkillProfile, ToolProfile, WorkflowProfile, OperationalAsset, fixtures, benchmark and acceptance cases, Attestation, and others

Important distinction:

```text
Asset      = independently identifiable reusable artifact
Package    = versioned distribution envelope
Collection = curated grouping
Binding    = explicit relation between assets
Runtime    = execution-time materialization, not automatically a Registry asset
```

The Registry can expose multiple catalog views over one asset identity/lineage graph.

## WorldPackage minimum semantic execution chain

```text
World (spec.world)
-> WorldViewProfile         packaged
-> StateCompilerProfile     packaged
-> EffectiveWorldState      runtime-derived
-> RepresentationAdapter    packaged with WorldModel
-> WorldModel
```

A `worldRef` does not replace View/Compiler compatibility.
