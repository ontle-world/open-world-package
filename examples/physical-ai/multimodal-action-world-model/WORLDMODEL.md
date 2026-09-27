# Multimodal Action World Model

This package demonstrates a VLM/VLA/world-model-style contract without introducing architecture-specific package kinds.

One artifact may provide semantic grounding, state estimation, dynamics/observation prediction, and action policy roles. OWP standardizes grounding, compatible World View/State Compiler contracts, interfaces, validity, lineage, and evaluation while leaving checkpoint format implementation-defined.

## Evaluation lineage

`eval/evidence-reference-sim.yaml` binds a result to exact versions: EvaluationProfile `manipulation-basic@0.2.0`, Verifier `pick-place-effect-verifier@0.1.0`, the `pick-place-task` View, the `pick-place-compiler` State Compiler, and the reference environment. `manipulation-basic@0.2.0` supersedes `0.1.0`, so results produced under the older profile must not be read as current performance.
