# Business and Enterprise AI with OWP

The same package model applies to enterprise Worlds.

```text
ManufacturingQualityWorld
├─ enterprise and quality semantics
├─ ERP/MES/QMS/DMS source bindings
├─ task-specific World Views
├─ state compilation contract
└─ action/commit/effect bindings

QualityTransitionWorldModel
├─ grounded_in -> ManufacturingQualityWorld
├─ valid_for -> quality incident / RCA views
├─ inputs -> compiled effective state
├─ outputs -> transition/outcome/risk/uncertainty
└─ evaluation -> benchmark and acceptance cases
```

Business applications do not need to copy every enterprise record into one graph. Source schemas may remain in their native stores and be mapped through explicit interface contracts.


## Common package skeleton

Business and Physical AI use the same World/WorldModel package skeleton. The `interfaces/` contents differ by domain; see `EXAMPLE_CONVENTIONS.md`.

## View / State compilation contract

World Models bind to a World through explicit compatible World View and State Compiler references. The World package owns reusable View/Compiler profiles; EWS is produced at runtime and is not a package-time snapshot by default.
