# Mobile Manipulation World

A portable World contract for a mobile robot that observes a workspace, navigates/manipulates objects, and pursues a declared task outcome under safety constraints.

Sensor frames and raw video are observation artifacts, not the World itself. The World contract supplies identity, semantics, observation/action meaning, constraints, and reusable task views.

## Conformance

Declared profile: `action-ready` — a World View, a State Compiler with a concrete EWS schema, and action/commit/effect-verification interfaces.

## Adjacent standards

OWP does not replace these standards; it records how they relate inside this World and View.

- Scene: OpenUSD (`environment/reference-environment.yaml`): NVIDIA Physical AI SimReady Warehouse 01 on Hugging Face, pinned by commit; CC-BY-4.0, by NVIDIA Corporation
- Observation/action interfaces: ROS 2 message and action types (`interfaces/`)
- Episodes: LeRobot dataset format (`datasets/manipulation-episodes.yaml`): `k-chan-l/lekiwi_pick_and_place2` on Hugging Face, pinned by commit; Apache-2.0. It is a personal repository; `lerobot/droid_100` (MIT) is an official-organization alternative without a mobile base
