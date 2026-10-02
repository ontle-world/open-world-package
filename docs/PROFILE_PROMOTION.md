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

Promoted to the standard (spec section 15): EvaluationProfile `assessmentKind`, `subject`, `objective`, `criteria`, `verifierRef`, `evidenceRefs`, `validityScope`, `resultSchemaRef`; ScenarioProfile fields; CapabilityContract `context`, `requiredInputs`, `capacity`, `maturity`, `validityScope`, `evidenceRefs`; WorldViewProfile `constraints`, `evidenceRefs`. They were used in at least three domains and do not reference experimental kinds. Fields that reference experimental kinds (`purpose.actorRef`, `roleRef`, `taskRef`, `evaluatorRef`, `outcomeRefs`) stay experimental until those kinds are promoted.

## Status

| Profile | Semantic | Portability | Example domains | Machine contract | Interoperability |
|---|---|---|---|---|---|
| ActorProfile, RoleProfile, DelegationProfile (C.3) | reviewed | yes | manufacturing, sales, research | schema, cases | 2 implementations, round trips |
| WorldViewProfile actor/role/task refs (C.4) | reviewed | yes | manufacturing, sales, research | schema, cases | 2 implementations, round trips |
| WorkPatternProfile graph (C.2) | reviewed | yes | manufacturing, sales, research | schema, cases | 2 implementations, round trips |
| ArtifactContract (C) | reviewed | yes | manufacturing, sales, research | schema, cases | 2 implementations, round trips |
| EvaluationProfile `evaluatorRef` (C.4) | reviewed | yes | manufacturing, research, robotics | schema, cases | 2 implementations, round trips |
| CapabilityContract `outcomeRefs` (C.4) | reviewed | yes | manufacturing, sales, research | schema, cases | 2 implementations, round trips |
| TaskSetProfile (C, C.4) | reviewed | yes | manufacturing, sales, research | schema, cases | 2 implementations, round trips |
| KnowledgeAsset (C) | reviewed | yes | manufacturing, sales, research | schema, cases | 2 implementations, round trips |
| KnowledgeExtractionProfile (C.1) | reviewed | yes | manufacturing, sales, research | schema, cases, extraction suite | 2 implementations, round trips |
| ConsumerRepresentationProfile (C) | reviewed | yes | manufacturing, sales, research | schema, cases | 2 implementations, round trips |

Round trips: every example and valid conformance case keeps its verdict, error ids, and warning ids after `ontle pack` and unpacking (`tests/test_roundtrip.py`) and after every YAML file is re-serialized in a different layout (Python `tests/test_roundtrip.py`, TypeScript `scripts/check-roundtrip.mjs`).

Still open for every profile: independent review of the semantic gate and the maintainers' publication decision.
