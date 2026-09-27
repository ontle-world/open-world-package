# Multimodal / VLM / VLA World Models

Do not create a new package kind for every current architecture name (VLM, VLA, video world model, latent world model, etc.). Use `WorldModelPackage` plus typed roles and modalities.

Example roles:

```text
perception
semantic_grounding
state_estimation
latent_state_encoding
dynamics_prediction
observation_prediction
trajectory_prediction
action_policy
planner
```

Example modalities:

```text
rgb
depth
video
language
proprioception
action_history
audio
point_cloud
structured_state
```

A single artifact may implement multiple roles. OWP standardizes how that artifact is grounded to a World/View, what inputs/outputs mean, where it is valid, and how it was evaluated; it does not prescribe a checkpoint format.

## View / State compilation contract

World Models bind to a World through explicit compatible World View and State Compiler references. The World package owns reusable View/Compiler profiles; EWS is produced at runtime and is not a package-time snapshot by default.
