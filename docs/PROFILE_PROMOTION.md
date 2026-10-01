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

## Status

| Profile | Semantic | Portability | Example domains | Machine contract | Interoperability |
|---|---|---|---|---|---|
| ActorProfile, RoleProfile, DelegationProfile (C.3) | reviewed | yes | manufacturing, sales, research | schema, cases | 2 implementations |
| WorldViewProfile actor/role/task refs (C.4) | reviewed | yes | manufacturing, sales, research | schema, cases | 2 implementations |
| WorkPatternProfile graph (C.2) | reviewed | yes | manufacturing, research | schema, cases | 2 implementations |
| ArtifactContract (C) | reviewed | yes | manufacturing, sales, research | schema, cases | 2 implementations |
| EvaluationProfile fields (C.4) | reviewed | yes | manufacturing, research | schema, cases | 2 implementations |
| ScenarioProfile fields (C.4) | reviewed | yes | manufacturing, research | schema, cases | 2 implementations |
| CapabilityContract fields (C.4) | reviewed | yes | manufacturing, sales, research | schema, cases | 2 implementations |
| TaskSetProfile (C, C.4) | reviewed | yes | manufacturing, sales, research | schema, cases | 2 implementations |
| KnowledgeAsset (C) | reviewed | yes | manufacturing, sales | schema, cases | 2 implementations |
| KnowledgeExtractionProfile (C.1) | reviewed | yes | manufacturing | schema, cases | 2 implementations |
| ConsumerRepresentationProfile (C) | reviewed | yes | manufacturing, sales | schema, cases | 2 implementations |

Profiles used in fewer than three domains do not yet pass the Example gate.

"Reviewed" means the maintainers checked the semantic gate; independent review is still open for every profile. Round-trip export and import tests are not yet in the suite. Both implementations live in this repository, so interoperability evidence from an independently maintained implementation is also still open (see `ROADMAP.md` section 6).
