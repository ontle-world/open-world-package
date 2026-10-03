# OWP — Work, actors, artifacts, and knowledge

Part of the Open World Package specification; section numbers are shared across its documents (see the document map in `OWP_SPEC.md`). Read this when a World represents who does what work, what they produce, and what knowledge they use. A World need not contain any of it (section 3); an enterprise World usually does.

The kinds here are standard (`vocab/asset-kinds.yaml`). Their schemas are under `schemas/`; undefined keys are `schema.unknown-field` (section 8).

## Common rules

- **Local references.** A reference written as a package-relative path (for example `TaskSetProfile.spec.requires.worldViews`) MUST name a local asset of the kind the field expects. References containing `#` point into another package and are checked only under resolution, where they apply. A bad local reference is `<family>.reference`, where the family is `work` (section 16), `actor` (17), `artifact` (18), or `knowledge` (19).
- **Required fields and forms.** A missing required field or a malformed value is `<family>.field`.
- **Value sets.** Value sets are in `vocab/value-sets.yaml`. A value MAY be an extension value `<extension>:<value>` when the extension is declared (section 13; otherwise `extension.undeclared`). The value sets `actorTypes`, `actorKinds`, `workNodeFamilies`, `queryLanguages`, and `knowledgeRepresentations` are closed: another value is `<family>.field`. The value sets `workPatterns`, `artifactTypes`, `artifactRepresentations`, `artifactOperations`, and `knowledgeRoles` are open: they grow with use, and another value is the warning `value.unknown`.

## 16. Work

Work has three levels: a WorkPatternProfile is a domain-independent shape of work, a TaskSetProfile is a domain task definition, and a task instance is an actual work item in the World (for example quality issue 37). Task instances are World state, not assets: they arrive as observations and appear in EWS (section 12). A task instance may exist without an assigned actor.

| Kind | Purpose | Fields |
|---|---|---|
| `TaskSetProfile` | domain-specific bundle of work | `task.objectiveRefs`, `task.workPatterns` (value set `workPatterns`), `requires.worldRefs`, `requires.worldViews` (WorldViewProfile), `requires.knowledge` (KnowledgeAsset), `requires.actors` (ActorProfile or RoleProfile), `workPatternRefs` (WorkPatternProfile), `mayUse.worldModels`, `mayUse.capabilities`, `mayUse.workflows`, `mayUse.scenarios` (ScenarioProfile), `mayUse.skills`, `mayUse.tools`, `produces.artifacts` (ArtifactContract), `evaluationRefs` |
| `WorkPatternProfile` | domain-independent shape of work | `pattern.kind` (required; value set `workPatterns`), `pattern.family` (value set `workNodeFamilies`), `objective`, `inputContracts`, `outputContracts` (ArtifactContract), `graph`, `worldViewRef` (WorldViewProfile), `governanceRefs`, `evaluationRefs` |

One View may serve several tasks, and one task may require several Views: `requires.worldViews` records the use, and a View's `conditioning.taskRef` records the task it is conditioned on (section 6).

### 16.1 Work pattern graph

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

Node ids, guard ids, and event ids are unique strings (`work.field`). Transitions, events, and loops refer only to declared nodes and guards (`work.reference`); `maxIterations` is a positive integer (`work.field`). Node families come from the value set `workNodeFamilies` (`observe_knowledge`, `analyze_reason`, `create_modify`, `decide_plan`, `execute_operate`, `evaluate_recover`); each work pattern in `workPatterns` names its family. A work pattern is semantic structure; a runtime graph (for example in a workflow engine) is an implementation of it and is bound through an extension (section 13).

## 17. Actors, roles, and delegation

These kinds keep apart concepts that are often conflated:

- An **actor** (ActorProfile) is a person, AI agent, team, organization, external institution, or automated system that acts in a World. A **role** (RoleProfile) is a position an actor occupies. A persona (a user-experience archetype) is not modeled.
- A **capability** (CapabilityContract) is what an actor is able to achieve; a **permission** is what it is allowed to do on a system (`permissions[].actions` within a `scope`); an **authority** is what it may decide (`authorities[].decisions` within a `scope`, with an optional `ceiling`).
- A **responsibility** is work an actor must perform; an **accountability** is an outcome it answers for.
- Actor, tool, and resource are different things. Equipment and software are resources or tools by default; they take an actor role (`actorType: automated_system`) only when they observe, decide, or act on their own. A capability is not the availability of the resource it needs.

| Kind | Purpose | Fields |
|---|---|---|
| `ActorProfile` | someone or something that acts in a World | `actorType` (required; value set `actorTypes`), `roleRefs` (RoleProfile), `capabilityRefs` (CapabilityContract), `agentRef` (AgentProfile), `memberOf` (ActorProfile), `assignments` (section 17.1) |
| `RoleProfile` | what a role may do, decide, and answer for | `permissions` (`actions`, `scope`), `authorities` (`decisions`, `scope`, `ceiling`), `responsibilities`, `accountabilities` |
| `DelegationProfile` | a bounded, time-limited transfer of permission or authority | `delegator`, `delegatee` (ActorProfile), `scope`, `permittedActions`, `authorityCeiling` (`decisions`, `limits`), `validFrom`, `expiresAt`, `revocation.by`, `escalation` (`to`, `when`), `evidenceRefs` |

An ActorProfile with `actorType: ai_agent` MAY point at an `AgentProfile` (`agentRef`) that describes how the agent is implemented; the ActorProfile describes its place in the World. `roleRefs` are the actor's standing roles.

A DelegationProfile transfers part of a delegator's permissions or authority to a delegatee for a `scope` and a period. `validFrom` and `expiresAt` are UTC timestamps (section 12) with `validFrom` first (`actor.field`). Its `permittedActions` and `authorityCeiling.decisions` MUST stay within what the delegator's roles grant (`actor.delegation-exceeds-authority`). `revocation.by` and `escalation.to` name ActorProfiles. Organization-specific approval chains, HR evaluations, and legal liability are policy bindings outside this profile.

### 17.1 Assignments

Who holds which role or task at a given time can be declared in the package or left to runtime; the author chooses:

- **Declared.** An ActorProfile MAY list `assignments`, each naming exactly one of `roleRef` (a local RoleProfile) or `taskRef` (a local TaskSetProfile), with an optional `scope` and an optional period `validFrom` / `expiresAt` (UTC, `validFrom` first). Without a period an assignment is standing. Use this when the assignment is part of what the World represents: a fixed rotation, a published duty roster, the owner of a process.
- **Observed.** Otherwise assignments are runtime state: they arrive as observations (for example of type `HR.assignment` with the actor as subject) and appear in EWS like any other state.

The two can coexist. Declared assignments describe the arrangement the package publishes; observed ones describe what holds at `asOf`. OWP does not reconcile them; a runtime that uses both says which wins.

```yaml
kind: ActorProfile
metadata: {name: quality-engineer}
spec:
  actorType: human
  roleRefs: [roles/quality-engineer.yaml]
  assignments:
  - {roleRef: roles/incident-owner.yaml, scope: line-3, validFrom: "2026-10-01T00:00:00Z", expiresAt: "2026-11-01T00:00:00Z"}
  - {taskRef: tasks/quality-incident.yaml}
```

`assignments` entries name exactly one of `roleRef` and `taskRef` (`actor.field`) and local assets of those kinds (`actor.reference`).

## 18. Artifacts and consumer representations

| Kind | Purpose | Fields |
|---|---|---|
| `ArtifactContract` | contract for an output a person or system keeps | `artifact.type` (required; value set `artifactTypes`), `artifact.representation` (value set `artifactRepresentations`), `structure`, `schemaRef` (a file in the package), `serialization.formats`, `storage`, `delivery`, `allowedOperations` (value set `artifactOperations`), `sourceRefs`, `evidenceRefs`, `governance`, `supersedes` (a pinned `<name>@<version>`) |
| `ConsumerRepresentationProfile` | how a View is delivered to one kind of actor | `actor.kind` (required; value set `actorKinds`), `actor.ref` (ActorProfile), `worldViewRef` (WorldViewProfile), `representation`, and one block named after the actor kind: `human`, `agent`, `model`, or `system` |

A ConsumerRepresentationProfile carries at most the actor block that matches `actor.kind` (`artifact.field`). A person receives an artifact (`human.artifactContractRefs`); an agent receives a structured context with tool and memory scope (`agent`); a model receives EWS through its Representation Adapter (`model.adapterRef`, a local RepresentationAdapterProfile; the model input path remains the one in section 6); a system receives it through interfaces (`system.interfaceRefs`).

## 19. Knowledge

| Kind | Purpose | Fields |
|---|---|---|
| `KnowledgeAsset` | reusable knowledge | `roles` (value set `knowledgeRoles`), `representation` (value set `knowledgeRepresentations`), `format`, `conformsTo`, `snapshot`, `content` (exactly one of `path`, a file in the package, or `ref`, an ExternalRef), `license`, `access`, `sensitivity`, `evaluationRefs` |
| `KnowledgeExtractionProfile` | turns query results over a knowledge graph into observations (section 19.2) | `source` (KnowledgeAsset), `parameters`, `query.language` (required; value set `queryLanguages`), `query.text`, `observations` |

### 19.1 Graphs and their ontology

`KnowledgeAsset.spec.conformsTo.ontology` is a package reference that MUST also be listed in `spec.dependencies` (`knowledge.reference`). The ontology is the graph's T-box and the graph is an A-box (section 3.1); a KnowledgeAsset with `representation: graph` SHOULD declare it (warning `knowledge.graph-ontology`). Validation does not parse the graph. Tooling MAY check that the graph uses only classes and properties of that ontology (and the OntologyPackages it depends on), within their declared domains and ranges. Within one OntologyPackage, separate domain (or range) statements must all hold, as in RDFS, and any member of a union is enough; when several packages in the closure each state a domain for a property, one package's statements holding is enough, so a package can reuse a property for its own types. The reference CLI does this with `ontle kg check`, which reports `kg.unknown-class`, `kg.unknown-property`, `kg.domain`, `kg.range`, `kg.parse` for a graph it cannot read, and, for nodes without `rdf:type`, `kg.untyped`. Terms of a standard vocabulary (SKOS, PROV, schema.org, ...) are checked when an OntologyPackage that publishes it, with that vocabulary as its `iri`, is in the closure; otherwise they are left alone.

### 19.2 Knowledge extraction

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
    subject: lot                             # optional: the column naming what each observation is about
```

`observations` is a non-empty list whose entries have a `type`, a non-empty `id` column list, and a `values` mapping (`knowledge.field`). Running the query is outside this specification. Given the result rows (each a mapping from column to JSON value), the parameter values, and the source's `snapshot.asOf`, a conforming implementation builds the ObservationSet as follows:

1. Every declared parameter has a value of its declared `type` (`string`, the default, `number`, or `boolean`), and no undeclared parameter is given.
2. For each entry of `observations`, in order, and each row: if any `id` column is absent or null, the row yields nothing for that entry. `values` copies each mapped column that is present and not null; if none is, the row yields nothing. `observedAt` is the `observedAt.column` value when present and not null, otherwise `default`, where `snapshot` (the default) means the source's `snapshot.asOf`; it MUST be a valid UTC timestamp (section 12).
3. The observation `id` is `<type>:` followed by the `id` column values joined with `|`. A string is used as is, a boolean as `true` or `false`, and a number in its shortest decimal form, without a fraction when the value is integral (`10.0` gives `10`). An array or mapping id value is invalid input.
4. The observations of one entry are ordered by `id` (Unicode code points); entries keep their order. Rows that repeat an observation (same `id`, `values`, and `observedAt`, as joins often do) yield it once; the same `id` with different content, or from two entries, is an error.
5. When the entry names a `subject` column whose value in the row is present and not null, the observation's `subject` is that value, written as for `id` (rule 3). Per-subject State Compiler fields (section 12.3) need it.
6. `spec.provenance` records `extraction` (`<name>@<version>`, or the name when unversioned), `parameters` when any were given, and `snapshot` when known.

Invalid input is `extraction.input` and nothing is produced. A State Compiler binding with `select: latest` that reads a type an extraction marks `multi: true` is the warning `compiler.multi-latest`; such types are read with `select: all`.
