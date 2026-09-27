# Mobile Manipulation World

A portable World contract for a mobile robot that observes a workspace, navigates/manipulates objects, and pursues a declared task outcome under safety constraints.

Sensor frames and raw video are observation artifacts, not the World itself. The World contract supplies identity, semantics, observation/action meaning, constraints, and reusable task views.

## Conformance

Declared profile: `action-ready` — a World View, a State Compiler with a concrete EWS schema, and action/commit/effect-verification interfaces.

## Adjacent standards

OWP does not replace these standards; it records how they relate inside this World and View.

- Scene: OpenUSD (`environment/reference-environment.yaml`, unbound in this example)
- Observation/action interfaces: ROS 2 message and action types (`interfaces/`)
- Episodes: LeRobot dataset format (`datasets/manipulation-episodes.yaml`, unbound in this example)
