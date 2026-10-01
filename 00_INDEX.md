# Public Alpha Index

Start here:

1. `README.md`
2. `ROADMAP.md`
3. `docs/QUICKSTART.md`
4. `spec/OWP_SPEC.md`
5. `docs/CONCEPTS.md`
6. `docs/EXAMPLE_CONVENTIONS.md`
7. `examples/business/`
8. `examples/physical-ai/`
9. `docs/HUGGINGFACE_INTEROP.md`
10. `docs/RUNTIME_INTEGRATION.md`
11. `docs/STANDARDS_INTEROP.md`
12. `starters/github-world-repo/`

Implementation:

- `src/ontle/`
- `src/ontle/templates/` — `ontle init` starter templates (single source; shipped as package data)
- `schemas/`
- `spec/rule-ids.yaml` — registry of every rule id
- `vocab/`
- `tests/`
- `conformance/` — language-neutral suite for independent implementations
- `implementations/typescript/` — independent TypeScript implementation (validator, resolver, EWS)
- `scripts/golden_smoke.sh`

Core package chain:

```text
World -> WorldViewProfile -> StateCompilerProfile -> EffectiveWorldState
      -> RepresentationAdapterProfile -> WorldModel
```
