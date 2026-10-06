# Public Alpha Index

Start here:

1. `README.md`
2. `ROADMAP.md`
3. `docs/QUICKSTART.md`
4. `spec/OWP_SPEC.md` (core; profiles in `spec/OWP_SEMANTICS.md`, `spec/OWP_EVALUATION_AND_STATE.md`, `spec/OWP_WORK_AND_ACTORS.md`, `spec/OWP_EXPERIMENTAL.md`; reference forms in `docs/REFERENCES.md`)
5. `docs/CONCEPTS.md`
   - `docs/GLOSSARY.md` — terms OWP keeps apart (actor, role, capability, permission, authority, ...)
   - `docs/PROFILE_PROMOTION.md` — gates for promoting experimental profiles
6. `docs/EXAMPLE_CONVENTIONS.md`
7. `examples/` — business, physical AI, research, and ontology packages; the README lists each one's size
8. `CONTRIBUTING.md` — development setup, and how the Python and TypeScript implementations stay in step
9. `docs/HUGGINGFACE_INTEROP.md`
10. `docs/RUNTIME_INTEGRATION.md`
11. `docs/STANDARDS_INTEROP.md`
12. `starters/github-world-repo/`
13. `docs/interop/` — notes on MCP, NGSI-LD, and AAS
14. `demos/` — end to end on sample data, from records to evidence

On the project site: the [package catalog](https://ontle-world.github.io/open-world-package/catalog/) (every example with its report, and an index to resolve from) and the [Playground](https://ontle-world.github.io/open-world-package/playground/) (check a package in the browser).

Implementation:

- `src/ontle/`
- `src/ontle/templates/` — `ontle init` starter templates (single source; shipped as package data)
- `schemas/`
- `spec/rule-ids.yaml` — registry of every rule id
- `vocab/`
- `tests/`
- `conformance/` — language-neutral suite for independent implementations
- `implementations/typescript/` — independent TypeScript implementation (validator, resolver, EWS, report; a browser build for the Playground)
- `schemas/package-report.schema.json` — the PackageReport `ontle inspect --report` prints (informative)
- `scripts/golden_smoke.sh` — every example and CLI command end to end
- `scripts/site_catalog.py`, `scripts/site_playground.py` — the catalog and Playground pages of the site

Core package chain:

```text
World -> WorldViewProfile -> StateCompilerProfile -> EffectiveWorldState
      -> RepresentationAdapterProfile -> WorldModel
```
