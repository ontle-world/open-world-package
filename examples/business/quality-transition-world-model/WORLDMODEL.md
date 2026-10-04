# Quality Transition World Model

A reference World Model contract for quality incident state estimation, transition/outcome prediction, and decision support. It is grounded in the Manufacturing Quality World, explicitly compatible with the Quality Incident Task View and its State Compiler, and consumes the resulting EffectiveWorldState before model-native adaptation.

## Scope

Roles: state estimation, dynamics prediction, outcome prediction, and decision support. Outputs: `predicted_transition`, `expected_outcome`, `risk`, `uncertainty`. It is grounded in `openworld-examples/manufacturing-quality-world@0.1.0`, its `views/quality-incident-task.yaml` View, and its `state/quality-incident-compiler.yaml` State Compiler. The EffectiveWorldState reaches the model through `models/adapter.yaml`, which preserves semantic identity, units, temporal meaning, and uncertainty.

## Sources

- `openworld-examples/manufacturing-quality-world@0.1.0`, a dependency.
- `models/model-artifact.yaml`: the place to bind a rule, statistical, learned, solver, or external model implementation. No implementation is bound.

## Use it for

- Start a quality incident World Model from a contract that already fits the Manufacturing Quality World's View and State Compiler.
- Once a model is bound: estimate incident state and predict transitions, outcomes, and risk from the quality-incident EWS.
- Check that predictions trace to a lot and declare their uncertainty (`eval/basic.yaml`).

## Limitations

- Reference contract only (`reference_contract_only`). No model is bundled, and the model artifact is unbound.
- No evaluation evidence is included.

## Versions

- 0.1.0: first public example.
