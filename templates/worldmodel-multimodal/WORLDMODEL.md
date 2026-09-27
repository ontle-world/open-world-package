# Multimodal Action World Model

## Role

This package demonstrates how a multimodal/VLA-style artifact can be grounded to a World without standardizing checkpoint bytes.

## Inputs

- RGB observations
- language task context
- proprioception
- action history

## Outputs

- latent/current state estimate
- predicted observations
- trajectory/action
- uncertainty or validity diagnostics where supported

## Compatibility

Declare a compatible World, World View(s), State Compiler(s), and representation adapter. A single artifact may implement multiple model roles.
