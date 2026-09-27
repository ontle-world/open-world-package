# Physical AI with OWP

A Physical AI team can publish its own representation of a manipulation, navigation, factory, or embodied environment World and then publish compatible World Models and assets against that contract.

Example graph:

```text
MobileManipulationWorld
├─ semantic object/robot/task contract
├─ camera/proprioception observation interfaces
├─ action/control space
├─ safety/constraint contract
└─ scenario profiles

MultimodalActionWorldModel
├─ grounded_in -> MobileManipulationWorld
├─ roles -> state estimation / dynamics / observation prediction / action policy
├─ modalities -> RGB / language / proprioception / action history
├─ representation adapter
├─ validity envelope
└─ evaluation profile
```

OWP does not standardize model weight bytes. A model artifact may point to Hugging Face, S3, an OCI artifact, or another content-addressed store while OWP standardizes semantic grounding, compatibility, validity, and evaluation metadata.


## Common package skeleton

Business and Physical AI use the same World/WorldModel package skeleton. The `interfaces/` contents differ by domain; see `EXAMPLE_CONVENTIONS.md`.

## View / State compilation contract

World Models bind to a World through explicit compatible World View and State Compiler references. The World package owns reusable View/Compiler profiles; EWS is produced at runtime and is not a package-time snapshot by default.
