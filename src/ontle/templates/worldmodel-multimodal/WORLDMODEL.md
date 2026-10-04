# Multimodal Action World Model

This package shows how a multimodal or VLA-style artifact can be grounded to a World without standardizing checkpoint bytes. Put the one-line summary in `metadata.description` in `owp.yaml`; catalogs show it on the package card.

## Scope

Inputs:

- RGB observations
- language task context
- proprioception
- action history

Outputs:

- latent or current state estimate
- predicted observations
- trajectory or action
- uncertainty or validity diagnostics where supported

## Sources

Training data and the model artifact. Declare a compatible World, World View(s), State Compiler(s), and representation adapter. A single artifact may implement multiple model roles.

## Use it for

- Three to five tasks or decisions the model supports.

## Limitations

Task, scale, resolution, temporal, and uncertainty limits, and known failure modes.

## Versions

- 0.1.0: first version.
