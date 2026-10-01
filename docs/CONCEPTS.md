# Core Concepts

## Target reality and explicit representation

`World (in real)` is the actual or conceptual target. It is not a database or registry object.

`World (in data schema)` is an intentionally incomplete, explicit representation used for identity, semantics, relations, state meaning, provenance, validity, source references, and reusable projections.

## Interface boundary

Inbound examples: database rows, APIs, sensors, images, video, documents, human observations.

Outbound examples: API calls, workflow commits, approvals, robot actions, equipment controls.

Keep these distinctions:

```text
Source Record != Observation != State
API/Tool Success != Business Commit != Realized World Change
```

## World View

A task-, actor-, objective-, authority-, scale-, resolution-, and time-conditioned projection of a World representation. OWP packages this as a reusable `WorldViewProfile`. A WorldPackage at the `viewable` profile or above carries at least one.

## State Compiler

A packaged `StateCompilerProfile` defines how a compatible World View is reconciled, authority/freshness checked, and materialized into runtime state. A WorldPackage at the `stateful` profile or above carries at least one; at `model-ready` each compiler also declares a concrete EWS schema (`outputSchema`).

## Effective World State (EWS)

A runtime-ready materialization of a World View for one execution/evaluation context. EWS is not a new World and is not automatically a registry asset.

## World Model

A World Model is semantically grounded in a World, MUST name one or more compatible World View contracts and State Compiler contracts, and consumes the resulting EWS through a declared Representation Adapter at runtime.

## Conformance profiles

A World does not need a World Model to be useful. A WorldPackage declares how far along the chain it goes:

```text
descriptive -> viewable -> stateful -> model-ready -> action-ready
```

See `spec/OWP_SPEC.md` section 6.1.

## Ontologies and semantic binding

An OntologyPackage publishes classes and properties with a namespace IRI, prefixes, and typed entrypoints (schema, shapes, mappings). A World binds its own names and EWS fields to those terms with a SemanticBinding, so two Worlds that both bind `claim.status` to the same property mean the same thing. See `spec/OWP_SPEC.md` sections 3.1 and 14.

## Work, artifacts, and consumers (experimental)

A Task Set bundles domain work: which work patterns it follows (prioritize, diagnose, ...), which Views and knowledge it needs, and which artifacts it produces. Each actor has its own World View, often specializing a shared base View. A Consumer Representation Profile says how a View reaches one kind of actor: a person receives an artifact such as a board or report, an agent receives a structured context with tool and memory scope, a model receives EWS through its Representation Adapter. These kinds are experimental; see `spec/OWP_SPEC.md` Appendix C.

## Extensions

Publishers add their own asset kinds and fields without changing the standard. A package declares each extension it uses as a dependency with a local name, then uses that name for kinds (`acme-quality:LineBalancingProfile`) and for data in `extensions` blocks. Any other unknown key is an error, so typos are caught. See `spec/OWP_SPEC.md` section 13.

## Evaluation lineage

A score only means something together with the exact EvaluationProfile, Verifier, View, State Compiler, and environment that produced it. OWP records that binding (`CompatibilityEvidence`); running and evolving evaluations is a runtime/registry concern. See `spec/OWP_SPEC.md` section 9.
