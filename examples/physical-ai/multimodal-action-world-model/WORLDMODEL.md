# Multimodal Action World Model

This package demonstrates a VLM/VLA/world-model-style contract without introducing architecture-specific package kinds.

## Scope

One artifact may provide semantic grounding, state estimation, dynamics/observation prediction, and action policy roles. OWP standardizes grounding, compatible World View/State Compiler contracts, interfaces, validity, lineage, and evaluation while leaving checkpoint format implementation-defined.

- World: `openworld-examples/mobile-manipulation-world@0.1.0`, with its `views/pick-place-task.yaml` View and `state/pick-place-compiler.yaml` State Compiler.
- Inputs: front and wrist RGB, language, proprioception, and action history, plus the EffectiveWorldState. Front RGB and proprioception are required.
- Outputs: latent state, predicted observation, action, and trajectory.
- Time: a context window of 8 steps, a prediction window of 4 steps, and an action horizon of 4 steps.

## Sources

- `openworld-examples/mobile-manipulation-world@0.1.0`, a dependency, including its reference environment.
- `models/model-artifact.yaml`: the place to bind an immutable external model revision (Hugging Face, OCI, S3, or a local content-addressed store). No revision is bound.

## Use it for

- Write down which World, View, State Compiler, and modalities a VLM/VLA model needs before you bind its weights.
- Predict the next observations and actions for the pick-and-place task, once a model is bound.
- Evaluate pick-and-place with a verified object pose change, not controller acceptance (`eval/manipulation.yaml`, `eval/verifier.yaml`).
- Tell current results from results produced under a superseded evaluation profile (see Evaluation lineage).

## Limitations

- Example contract; no weights bundled.
- The metrics in `eval/evidence-reference-sim.yaml` are illustrative only; no evaluation was run.

## Versions

- 0.1.0: first public example.

## Evaluation lineage

`eval/evidence-reference-sim.yaml` binds a result to exact versions: EvaluationProfile `manipulation-basic@0.2.0`, Verifier `pick-place-effect-verifier@0.1.0`, the `pick-place-task` View, the `pick-place-compiler` State Compiler, and the reference environment. `manipulation-basic@0.2.0` supersedes `0.1.0`, so results produced under the older profile must not be read as current performance.
