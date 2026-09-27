# Runtime Integration Boundary

ONTLE/OWP is the authoring, package, validation, integrity, and registry-facing layer. A runtime such as a simulator, agent harness, enterprise execution layer, or `axworld`-style reference runtime is a separate consumer.

```text
World authoring
  -> ontle validate
  -> ontle pack
  -> OWP package
  -> runtime resolves World / interfaces / models / scenarios
  -> runtime compiles task state
  -> model / solver / simulator
  -> action / outcome / trace
```

A runtime SHOULD preserve package references and content digests in traces so executions remain reproducible.

Runtimes exchange Effective World State in the standard document form (spec section 12). Every EWS a runtime produces can be checked against the State Compiler's output contract with `ontle ews check`. When a State Compiler declares bindings, conforming runtimes must produce the same EWS for the same observations and `asOf`; the `conformance/ews` cases test exactly that. Compilers without bindings stay runtime-specific.

Package references are resolved by exact version from directories, `.owp.zip` archives, or git tags (`ontle resolve`); no hosted registry is required.

Recommended separation:

- ONTLE owns OWP authoring, validation, packaging, dependency/asset metadata, and registry client behavior.
- A reference runtime owns simulation/execution semantics.
- Production AX Flow or another commercial runtime may implement stronger connector, transaction, governance, durability, and WorldModelOps capabilities without changing OWP package identity.

This boundary allows the same Physical AI or business World package to be consumed by different runtimes.

Evaluation follows the same split. OWP carries versioned EvaluationProfiles, Verifiers, and `CompatibilityEvidence` bound to exact versions, Views, and State Compilers. Failure triage, eval generation, golden-case accumulation, replay/regression/shadow runs, and promotion or rollback of evaluation criteria are runtime/registry responsibilities; their outputs re-enter OWP as new versions and new evidence.
