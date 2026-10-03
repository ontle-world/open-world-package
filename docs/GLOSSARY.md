# Glossary

Terms that OWP keeps apart. Each entry says which asset or field carries the concept. Experimental items are marked (spec Appendix C).

## World and views

| Term | Meaning | Where |
|---|---|---|
| World (in real) | The actual or conceptual target. Not a package artifact. | — |
| World | An explicit, intentionally incomplete representation of a target. | `WorldPackage`, `spec.world` |
| World View | A projection of a World for a purpose, at a scale, resolution, and time scope. Actor, role, task, objective, and authority are optional conditioning. | `WorldViewProfile` |
| Effective World State (EWS) | The state a State Compiler materializes for one View and moment. Runtime-derived. | spec section 12 |
| Operational context | EWS combined at run time with the acting actor's context, the task, available resources, and the dynamics and constraints that apply. Runtime-derived, not packaged. | — |
| World Model | A model grounded in a World through named Views and State Compilers. | `WorldModelPackage` |

## Actors and authority (experimental)

| Term | Meaning | Where |
|---|---|---|
| Actor | A person, AI agent, team, organization, external institution, or automated system that acts in a World. | `ActorProfile` |
| Role | A position an actor occupies. One actor can hold several roles. | `RoleProfile` |
| Persona | A user-experience archetype. Not modeled by OWP. | — |
| Capability | What an actor is able to achieve, under a defined context. | `CapabilityContract` |
| Permission | What an actor is allowed to do on a system, within a scope. | `RoleProfile.spec.permissions` |
| Authority | What an actor may decide, within a scope and an optional ceiling. | `RoleProfile.spec.authorities` |
| Responsibility | Work an actor must perform. | `RoleProfile.spec.responsibilities` |
| Accountability | An outcome an actor answers for. | `RoleProfile.spec.accountabilities` |
| Delegation | A bounded, time-limited transfer of permission or authority from one actor to another. | `DelegationProfile` |
| Agent implementation | How an AI agent is built and configured. Distinct from its place in the World. | `AgentProfile` (pointed to by `ActorProfile.spec.agentRef`) |

Capability is also distinct from competency (an individual's skill), resource (something used), process (a sequence of work), capacity (how much can be done), and performance (how well it was done).

## Work and artifacts (experimental)

| Term | Meaning | Where |
|---|---|---|
| Task Set | A domain task definition: which Views, actors, knowledge, patterns, and tools it needs and which artifacts it produces. | `TaskSetProfile` |
| Task instance | An actual work item in the World (quality issue 37). World state that arrives as observations; may be unassigned. Not an asset. | ObservationSet, EWS |
| Work Pattern | A domain-independent shape of work, as a graph of nodes, transitions, guards, events, and loops. | `WorkPatternProfile` |
| Runtime graph | An implementation of a work pattern in a workflow engine. Bound through an extension. | spec section 13 |
| Artifact Type | What an output is (a proposal, a report). | `ArtifactContract.spec.artifact.type` |
| Representation | Its logical structure (structured document, table, graph). | `ArtifactContract.spec.artifact.representation` |
| Format | Its serialization (DOCX, CSV, Turtle). | `ArtifactContract.spec.serialization.formats` |
| Storage | Where it is kept (object store, drive, local). | `ArtifactContract.spec.storage` |
| Delivery | Where it is sent. | `ArtifactContract.spec.delivery` |

## Assessment (EvaluationProfile, spec section 15.1)

| Term | Meaning |
|---|---|
| Verification | Checks that conditions, facts, or specifications are met. |
| Validation | Checks that the subject fits its purpose. |
| Evaluation | Judges quality or performance against criteria. |
| Review | An examination activity. |
| Approval | An authorized decision to use or execute. |

The assessed subject can be a model, agent, workflow, artifact, decision, process, capability, or environment (`EvaluationProfile.spec.subject.kind`).

## Scenarios (ScenarioProfile, spec section 15.2)

| Term | Meaning |
|---|---|
| Scenario | A baseline state, assumptions, an intervention, and an engine that yields an expected transition or outcome. Not the same as a prediction. |
| Engine | What produces the outcome: rule, score or ranking, optimization, simulation, ML prediction, world model, or LLM / agent reasoning. |

## Packaging and distribution

| Term | Meaning | Where |
|---|---|---|
| Package | A versioned distribution envelope. | `owp.yaml` |
| Asset | An independently identifiable reusable artifact: a package file that declares an OWP `apiVersion` and an asset `kind`, or an external `spec.assets` reference. | spec section 5 |
| Extension | Publisher-defined kinds, fields, and values. | spec section 13 |
| ExternalRef | A pinned reference to an artifact outside the package. | spec section 5.1 |
| Evidence | A result bound to the exact evaluation, View, and State Compiler that produced it. | `CompatibilityEvidence` |
