# OWP — Experimental profiles (informative)

Part of the Open World Package specification; section numbers are shared across its documents (see the document map in `OWP_SPEC.md`). Everything here may change or be removed; checks produce warnings only.

## Appendix C. Experimental asset kinds (informative)

The kinds below are marked `stability: experimental` in `vocab/asset-kinds.yaml`. They may change or be removed. A validator reports `asset.kind-experimental` for each use and checks them against `schemas/experimental/` with warnings only (`experimental.field`, `experimental.value`, `experimental.reference`). Extension rules (section 13) still apply and remain errors. Value sets are in `vocab/value-sets.yaml`; a value outside its set is a warning, and an extension value `<extension>:<value>` is accepted when the extension is declared.

| Kind | Purpose | Main fields |
|---|---|---|
| `TaskSetProfile` | domain-specific bundle of work | `task.workPatterns`, `requires.worldViews`, `requires.knowledge`, `mayUse`, `produces.artifacts`, `evaluationRefs` |
| `WorkPatternProfile` | domain-independent shape of work (C.2) | `pattern.kind` (value set `workPatterns`), `pattern.family` (value set `workNodeFamilies`), `objective`, `inputContracts`, `outputContracts`, `graph`, `worldViewRef`, `governanceRefs`, `evaluationRefs` |
| `ArtifactContract` | contract for an output a person or system keeps | `artifact.type`, `artifact.representation`, `structure`, `schemaRef`, `serialization.formats`, `storage`, `delivery`, `allowedOperations` (value set `artifactOperations`), `sourceRefs`, `evidenceRefs`, `governance`, `supersedes` |
| `ArtifactTemplate` | template for an artifact contract | `artifactContractRef`, `format`, `content` (`path` or ExternalRef) |
| `ConsumerRepresentationProfile` | how a View is delivered to one kind of actor | `actor.kind` (value set `actorKinds`), `actor.ref` (ActorProfile), `worldViewRef`, `representation`, and one block named after the actor kind: `human`, `agent`, `model`, or `system` |
| `ActorProfile` | someone or something that acts in a World (C.3) | `actorType` (value set `actorTypes`), `roleRefs`, `capabilityRefs`, `agentRef`, `memberOf` |
| `RoleProfile` | what a role may do, decide, and answer for (C.3) | `permissions`, `authorities`, `responsibilities`, `accountabilities` |
| `DelegationProfile` | a bounded, time-limited transfer of permission or authority (C.3) | `delegator`, `delegatee`, `scope`, `permittedActions`, `authorityCeiling`, `validFrom`, `expiresAt`, `revocation`, `escalation`, `evidenceRefs` |
| `TaskSetProfile` (additions, C.4) | composition | `requires.actors`, `workPatternRefs`, `mayUse.scenarios`, `mayUse.skills`, `mayUse.tools` |
| `KnowledgeExtractionProfile` | turns query results over a knowledge graph into observations (C.1) | `source`, `parameters`, `query.language` (value set `queryLanguages`), `query.text`, `observations` |
| `KnowledgeAsset` | reusable knowledge | `roles`, `representation`, `format`, `conformsTo`, `snapshot`, `content` (`path` or ExternalRef), `license`, `access`, `sensitivity` |

Experimental checks:

- References written as package-relative paths (for example `TaskSetProfile.spec.requires.worldViews`, `ConsumerRepresentationProfile.spec.worldViewRef`) name a local asset of the expected kind. References containing `#` point into another package and are not checked.
- A ConsumerRepresentationProfile carries at most the actor block that matches `actor.kind`. The `model` block's `adapterRef` names a local RepresentationAdapterProfile; the model input path remains the one in section 6.
- `KnowledgeAsset.spec.conformsTo.ontology` is a package reference that is also listed in `spec.dependencies`. The ontology is the graph's T-box and the graph is an A-box; a KnowledgeAsset with `representation: graph` SHOULD declare it (`experimental.graph-ontology`). Validation does not parse the graph (section 3.1); tooling MAY check that the graph uses only classes and properties of that ontology (and the OntologyPackages it depends on), within their declared domains and ranges. The reference CLI does this with `ontle kg check`, which reports `kg.unknown-class`, `kg.unknown-property`, `kg.domain`, `kg.range`, and, for nodes without `rdf:type`, `kg.untyped`.

**World View specialization.** A WorldViewProfile MAY declare the experimental fields `spec.specializes` (the local path of another WorldViewProfile) and `spec.projection.exclude`. The resolved View is the base View's resolved spec with: `projection.include` = base include ∪ include − exclude; `purpose` and `conditioning` overridden key by key; other fields replaced. `specializes` naming anything other than a local WorldViewProfile, or a cycle, is `experimental.reference`. State Compilers keep binding to the specialized View's own path. The reference CLI shows resolved Views with `ontle inspect --resolved-views`.

**Reference graph.** `ontle inspect --graph` lists the package, its assets, and the references between them with informative relation names (`contains`, `depends_on`, `uses_extension`, `grounded_in`, `valid_for_view`, `valid_for_compiler`, `uses_adapter`, `compiles_view`, `specializes`, `uses_pattern`, `requires_view`, `requires_knowledge`, `produces_artifact`, `evaluated_by`, `template_for`, `represents_view`, `consumes_contract`, `conforms_to`, `evidences`, `for_actor`, `for_role`, `for_task`, `occupies_role`, `has_capability`, `implemented_by`, `member_of`, `delegated_by`, `delegated_to`, `produces_contract`, `evaluates`, `evaluated_by_actor`, `baseline`, `uses_engine`, `performed_by`, `may_use_scenario`). These names are not part of the package contract.

### C.1 Knowledge extraction

A KnowledgeExtractionProfile connects a knowledge graph to the World chain without changing EWS (section 12): a runtime runs its query over the source KnowledgeAsset, and the result rows become an ObservationSet that State Compilers read as usual.

```yaml
kind: KnowledgeExtractionProfile
metadata: {name: claim-context, version: 0.1.0}
spec:
  source: knowledge/plant-kg.yaml            # local KnowledgeAsset
  parameters:
    claimId: {type: string}                  # the task's subject, supplied at run time
  query:
    language: sparql                         # sparql | opencypher | gql | <extension>:<language>
    text: SELECT ?lot ?equipment WHERE { ... }
  observations:
  - type: KG.lot_equipment
    id: [lot, equipment]                     # result columns that identify the observation
    values: {equipment: equipment}          # values key -> result column
    observedAt: {column: recordedAt, default: snapshot}
    multi: true                              # several values per subject are expected
```

Running the query is outside this specification. Given the result rows (each a mapping from column to JSON value), the parameter values, and the source's `snapshot.asOf`, a conforming implementation builds the ObservationSet as follows:

1. Every declared parameter has a value of its declared `type` (`string`, the default, `number`, or `boolean`), and no undeclared parameter is given.
2. For each entry of `observations`, in order, and each row: if any `id` column is absent or null, the row yields nothing for that entry. `values` copies each mapped column that is present and not null; if none is, the row yields nothing. `observedAt` is the `observedAt.column` value when present and not null, otherwise `default`, where `snapshot` (the default) means the source's `snapshot.asOf`; it MUST be a valid UTC timestamp (section 12).
3. The observation `id` is `<type>:` followed by the `id` column values joined with `|`. A string is used as is, a boolean as `true` or `false`, and a number in its shortest decimal form, without a fraction when the value is integral (`10.0` gives `10`). An array or mapping id value is invalid input.
4. The observations of one entry are ordered by `id` (Unicode code points); entries keep their order. Rows that repeat an observation (same `id`, `values`, and `observedAt`, as joins often do) yield it once; the same `id` with different content, or from two entries, is an error.
5. `spec.provenance` records `extraction` (`<name>@<version>`, or the name when unversioned), `parameters` when any were given, and `snapshot` when known.

Invalid input is `extraction.input` and nothing is produced. A State Compiler binding with `select: latest` that reads a type an extraction marks `multi: true` is the warning `compiler.multi-latest`; such types are read with `select: all`.

### C.2 Work pattern graph

A WorkPatternProfile describes a shape of work independent of any workflow engine. `graph` is optional:

```yaml
graph:
  nodes:
  - {id: gather, family: observe_knowledge}
  - {id: hypothesize, family: analyze_reason}
  - {id: test, family: evaluate_recover}
  - {id: report, family: create_modify}
  transitions:
  - {from: gather, to: hypothesize}
  - {from: hypothesize, to: test}
  - {from: test, to: hypothesize, guard: hypothesis_rejected}
  - {from: test, to: report, guard: hypothesis_supported}
  guards: [{id: hypothesis_rejected}, {id: hypothesis_supported}]
  events: [{id: new_evidence, triggers: [gather]}]
  loops: [{nodes: [hypothesize, test], maxIterations: 5, until: hypothesis_supported}]
```

Node ids, guard ids, and event ids are unique strings. Transitions, events, and loops refer only to declared nodes and guards; `maxIterations` is a positive integer. Node families come from the value set `workNodeFamilies` (`observe_knowledge`, `analyze_reason`, `create_modify`, `decide_plan`, `execute_operate`, `evaluate_recover`); each work pattern in `workPatterns` names its family. A work pattern is semantic structure; a runtime graph (for example in a workflow engine) is an implementation of it and is bound through an extension (section 13).

### C.3 Actors, roles, and delegation

These kinds keep apart concepts that are often conflated:

- An **actor** (ActorProfile) is a person, AI agent, team, organization, external institution, or automated system that acts in a World. A **role** (RoleProfile) is a position an actor occupies. A persona (a user-experience archetype) is not modeled.
- A **capability** (CapabilityContract) is what an actor is able to achieve; a **permission** is what it is allowed to do on a system (`permissions[].actions` within a `scope`); an **authority** is what it may decide (`authorities[].decisions` within a `scope`, with an optional `ceiling`).
- A **responsibility** is work an actor must perform; an **accountability** is an outcome it answers for.
- An ActorProfile with `actorType: ai_agent` MAY point at an `AgentProfile` (`agentRef`) that describes how the agent is implemented; the ActorProfile describes its place in the World.
- An ActorProfile is the actor's persistent profile: identity, type, standing roles, baseline capabilities. Time-bound bindings (a delegation, a task assignment, current availability or location) are context: DelegationProfile covers delegation, and the rest is runtime state, observed like any other World state.
- Actor, tool, and resource are different things. Equipment and software are resources or tools by default; they take an actor role (`actorType: automated_system`) only when they observe, decide, or act on their own. A capability is not the availability of the resource it needs.
- Work has three levels: a WorkPatternProfile is a domain-independent shape of work, a TaskSetProfile is a domain task definition, and a task instance is an actual work item in the World (for example quality issue 37). Task instances are World state, not assets: they arrive as observations and appear in EWS. A task instance may exist without an assigned actor.

A DelegationProfile transfers part of a delegator's permissions or authority to a delegatee for a `scope` and a period (`validFrom` before `expiresAt`, UTC timestamps). Its `permittedActions` and `authorityCeiling.decisions` stay within what the delegator's roles grant; otherwise the warning `experimental.delegation-exceeds-authority` applies. `revocation.by` and `escalation.to` name ActorProfiles. Organization-specific approval chains, HR evaluations, and legal liability are policy bindings outside this profile.

### C.4 Experimental fields of standard kinds

These fields of standard kinds are experimental; their checks produce warnings only. The other fields of these kinds are standard (sections 6, 9, 15).

| Kind | Experimental fields | Checks (warnings) |
|---|---|---|
| `WorldViewProfile` | `specializes`, `projection.exclude` (View specialization, Appendix C); `conditioning.actorRef`, `conditioning.roleRefs`, `conditioning.taskRef` | the refs name a local ActorProfile, RoleProfile, TaskSetProfile |
| `EvaluationProfile` | `evaluatorRef` | names a local ActorProfile |
| `CapabilityContract` | `outcomeRefs` | none |

A TaskSetProfile composes these profiles: `requires.actors` (ActorProfile or RoleProfile), `workPatternRefs` (WorkPatternProfile), and `mayUse.scenarios`, `mayUse.skills`, `mayUse.tools` (ScenarioProfile, SkillProfile, ToolProfile), next to its Views, knowledge, models, capabilities, workflows, artifacts, and evaluations.
