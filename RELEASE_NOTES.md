# Public Alpha Release Notes

This source tree is prepared for an initial GitHub public release of ONTLE Open World tooling and the Open World Package (OWP) public-alpha specification.

This revision closes the package-level semantic execution chain:

```text
WorldPackage
-> WorldViewProfile
-> StateCompilerProfile
-> EffectiveWorldState (runtime)
-> RepresentationAdapterProfile
-> WorldModelPackage
```

A World Model is no longer valid with only a `worldRef`; compatible View and State Compiler contracts are required. A World itself declares how far along this chain it goes through a conformance profile (`descriptive` through `action-ready`).

## Included

- `ontle` CLI: init, add, validate, inspect, pack, verify, resolve, ews compile/check
- `owp.yaml` public manifest contract
- deterministic `.owp.zip` archive profile with SHA-256 lock verification
- minimal / enterprise World, ontology, generic World Model, and multimodal World Model generators
- generated default World View + State Compiler profiles for World starters
- mandatory WorldModel View/State-Compiler/EWS/Adapter compatibility declarations
- Business AI World + World Model examples
- Physical AI World + multimodal/VLA-style World Model examples
- OWP manifest JSON Schema, CompatibilityEvidence JSON Schema, and public asset-kind vocabulary
- WorldPackage conformance profiles
- evaluation lineage and evidence binding (pinned EvaluationProfile/Verifier versions)
- language-neutral `conformance/` suite for independent implementations (validation, resolution, EWS compile/check)
- registry-free dependency resolution from directories, `.owp.zip` archives, and git tags
- standard Effective World State document, output-contract checks, and a reference declarative State Compiler
- GitHub CI/release workflows
- standalone GitHub World repository starter
- Apache-2.0 code/schema licensing and CC BY 4.0 docs/spec licensing

## Explicitly not claimed

- hosted ONTLE Registry production service
- production enterprise/robot write connectors
- production AX Guard / durable execution runtime
- generic ML checkpoint standardization
- automatic World/View/WorldModel composition
- a second implementation maintained by an independent party (`implementations/typescript/` was written clean-room from the spec and passes the suite, but it lives in this repository and is not published to npm)
- evaluation execution, triage, or promotion workflows

These can be layered on top of the package contract without changing the minimal authoring surface.
