# Mobile Manipulation World

A portable World contract for a mobile robot that observes a workspace, navigates/manipulates objects, and pursues a declared task outcome under safety constraints.

## Scope

Included: `robot`, `workspace`, `target_object`, `target_zone`, `task`, `observations`, `action_space`, `safety_constraints`, `task_outcome`.

Excluded: `specific_robot_firmware`, `specific_simulator_runtime`.

Sensor frames and raw video are observation artifacts, not the World itself. The World contract supplies identity, semantics, observation/action meaning, constraints, and reusable task views.

## Sources

- Observation and action interfaces: ROS 2 message and action types (`interfaces/observations.yaml`, `interfaces/actions.yaml`).
- Scene: an OpenUSD warehouse scene on Hugging Face (`environment/reference-environment.yaml`).
- Episodes: a LeRobot dataset on Hugging Face (`datasets/manipulation-episodes.yaml`).

Details, pins, and licenses are under Adjacent standards.

## Use it for

- What are the robot's joint and gripper state, the target object's pose, the target zone, and the active safety constraints right now?
- Did a grasp really move the object into the target zone, beyond the controller accepting the command (`interfaces/effect-verification.yaml`, `interfaces/commit.yaml`)?
- Which ROS 2 action type carries each robot command (navigate, reach, grasp, release)?
- Run the pick-and-place scenario in the reference simulation environment (`scenarios/pick-place.yaml`).

## Limitations

- Reference semantics and interfaces only.
- The environment's runtime binding is unspecified. The scene's full layer closure is about 10 GB, so it is referenced, not fetched in CI.
- The episode dataset is a personal repository; the State Compiler reads only its metadata and parquet data, not the videos.

## Versions

- 0.1.0: first public example.

## Conformance

Declared profile: `action-ready` — a World View, a State Compiler with a concrete EWS schema, and action/commit/effect-verification interfaces.

## Adjacent standards

OWP does not replace these standards; it records how they relate inside this World and View.

- Scene: OpenUSD (`environment/reference-environment.yaml`): NVIDIA Physical AI SimReady Warehouse 01 on Hugging Face, pinned by commit; CC-BY-4.0, by NVIDIA Corporation
- Observation/action interfaces: ROS 2 message and action types (`interfaces/`)
- Episodes: LeRobot dataset format (`datasets/manipulation-episodes.yaml`): `k-chan-l/lekiwi_pick_and_place2` on Hugging Face, pinned by commit; Apache-2.0. It is a personal repository; `lerobot/droid_100` (MIT) is an official-organization alternative without a mobile base
