# Promoting experimental profiles

Experimental kinds and fields (spec Appendix C) can change or be removed. A profile becomes part of the standard vocabulary (`stability: standard` in `vocab/asset-kinds.yaml`, rules moved into the spec body) only when it passes every gate below.

## Gates

| Gate | Criteria |
|---|---|
| Semantic | Does not conflict with the meaning of World, World View, State Compiler, EWS, or World Model. Does not duplicate an existing kind or field. |
| Portability | Contains no product, vendor, or methodology names. Does not depend on a specific runtime, framework, or workflow engine. |
| Example | Used in example packages from at least three different domains. |
| Machine contract | Has a JSON Schema, a canonical example, and validation rules with rule ids. |
| Interoperability | Both implementations reach the same verdicts on its conformance cases; it round-trips through export and import; unknown fields and extensions follow spec sections 8 and 13. |
| Publication | Its license and publication are agreed by the maintainers. |

When a profile is promoted, its warnings become errors where the spec says MUST, its rule ids move from Appendix C to the main sections, and its conformance cases expect errors instead of warnings.

## Promoted

- Spec section 15: EvaluationProfile `assessmentKind`, `subject`, `objective`, `criteria`, `verifierRef`, `evidenceRefs`, `validityScope`, `resultSchemaRef`; ScenarioProfile fields; CapabilityContract `context`, `requiredInputs`, `capacity`, `maturity`, `validityScope`, `evidenceRefs`; WorldViewProfile `constraints`, `evidenceRefs`.
- Spec sections 16-19 (this alpha): TaskSetProfile, WorkPatternProfile and its graph, ActorProfile, RoleProfile, DelegationProfile, ArtifactContract, ConsumerRepresentationProfile, KnowledgeAsset, KnowledgeExtractionProfile, and the fields that reference them: WorldViewProfile `conditioning.actorRef`, `roleRefs`, `taskRef`; EvaluationProfile `evaluatorRef`; CapabilityContract `outcomeRefs`. Their checks became errors under the ids `work.*`, `actor.*`, `artifact.*`, `knowledge.*`, `view.conditioning-ref`, and `evaluation.evaluator-ref`. The vocabularies the taxonomy leaves open (work patterns, artifact types and representations, artifact operations, knowledge roles) stay open: a value outside them is the warning `value.unknown`.

## Status

| Profile | Semantic | Portability | Example domains | Machine contract | Interoperability |
|---|---|---|---|---|---|
| ArtifactTemplate (C) | reviewed | yes | none yet | schema, cases | 2 implementations, round trips |
| WorldViewProfile `specializes`, `composes`, `projection.exclude` (C.1) | open: operations beyond union, filter, and override are undecided | yes | manufacturing, sales, research | schema, cases | 2 implementations, round trips |

Round trips: every example and valid conformance case keeps its verdict, error ids, and warning ids after `ontle pack` and unpacking (`tests/test_roundtrip.py`) and after every YAML file is re-serialized in a different layout (Python `tests/test_roundtrip.py`, TypeScript `scripts/check-roundtrip.mjs`).
