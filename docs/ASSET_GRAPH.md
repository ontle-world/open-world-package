# Public Asset Graph Model

The authoring surface is intentionally small, but a Registry may index a richer typed graph.

Representative asset kinds:

- WorldDefinition / SemanticProfile / WorldViewProfile
- SourceSystemSchemaProfile / MappingSpec / ActionBindingProfile
- ReferenceEnterpriseProfile / ScenarioProfile
- WorldModelContract / ModelArtifact / RepresentationAdapter
- Skill / Tool / Workflow / OperationalAsset
- Dataset / Fixture / Benchmark / Validator / EvaluationProfile / Attestation

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
WorldDefinition / World contract
-> WorldViewProfile         packaged
-> StateCompilerProfile     packaged
-> EffectiveWorldState      runtime-derived
-> RepresentationAdapter    packaged with WorldModel
-> WorldModel
```

A `worldRef` does not replace View/Compiler compatibility.
