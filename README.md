# ONTLE Open World — Public Alpha

ONTLE is a reference toolchain for authoring, validating, packaging, and inspecting **Open World Packages (OWP)**.

OWP is a portable package contract for publishing a reusable **World**, its compatible **World Models**, and related assets such as source/interface bindings, scenarios, datasets, evaluation profiles, and operational artifacts.

The public surface is intentionally small:

```text
WORLD.md | WORLDMODEL.md | ONTOLOGY.md   human-readable package card
owp.yaml                              machine-readable OWP manifest
views/ / state/                         generated World View + State Compiler defaults (profile-dependent)
examples/ / models/ / interfaces/ ...    only the additional assets the package actually needs
```

The registry and internal asset graph may be much richer. Authors should not need to manually create registry records, digests, lineage metadata, or derived build state.

## Why

A model hub tells you which model artifact exists. A tool hub tells you which tool can be called. OWP adds a missing layer:

> What world is being represented, what observations and actions mean in that world, what model is valid for which view of it, and what evidence shows that the package works?

This applies to both Physical AI and business/enterprise AI.

```text
Physical AI
World -> sensors/actions/environment -> World Model/VLA -> trajectory/action/eval

Business AI
World -> ERP/MES/QMS/docs -> World Model/solver -> decision/action/eval
```

## Quick start

Requires Python 3.11+ (tested on 3.11–3.14).

```bash
python -m pip install -e .

ontle init my-world --namespace acme
cd my-world

# Start with WORLD.md and owp.yaml. Generated views/default.yaml and
# state/default-compiler.yaml keep the World -> View -> EWS contract explicit.
ontle validate .
ontle inspect .
ontle pack .
```

The generated project contains only the authoring surface. `.ontle/` is generator-owned metadata and can be ignored by most users.

## Starter templates

```bash
ontle init my-world --template minimal
ontle init my-enterprise-world --template enterprise
ontle init my-ontology --template ontology
ontle init my-world-model --template worldmodel
ontle init my-vla-world-model --template worldmodel-multimodal
```

Progressive scaffolding:

```bash
ontle add view manager-view
ontle add compiler manager-state
ontle add source mes
ontle add observation quality-events
ontle add action propose-capa
ontle add commit qms-approval
ontle add effect verified-outcome
ontle add scenario claim-rca
ontle add adapter state-adapter
ontle add eval baseline
ontle add verifier outcome-check
ontle add test smoke
ontle add asset sop-template
ontle add extension acme/quality-extension@1.2.0   # declare a publisher extension

# experimental (spec Appendix C)
ontle add view regional-view --specializes views/default.yaml
ontle add task account-priority
ontle add pattern prioritize
ontle add artifact priority-board
ontle add consumer sales-manager
ontle add knowledge win-loss-playbook
ontle inspect . --graph --resolved-views

# ontology packages
ontle ontology index        # write the term index (RDF entrypoints: pip install 'ontle-open-world[rdf]')
ontle export --format turtle
```

## Examples

- `examples/business/manufacturing-quality-world` — business/manufacturing World package
- `examples/business/quality-transition-world-model` — World Model bound to a business World
- `examples/ontology/quality-ontology` — ontology package (owp-yaml schema, SHACL shapes, SSSOM mappings) used by the manufacturing World
- `examples/business/sales-prioritization-world` — actor-specialized Views, tasks, artifacts, and consumers (experimental kinds)
- `examples/physical-ai/mobile-manipulation-world` — Physical AI World package
- `examples/physical-ai/multimodal-action-world-model` — multimodal/VLA-style World Model package

Conformance suite for independent implementations: `conformance/` (see `conformance/README.md`). An independent TypeScript implementation written from the spec alone lives in `implementations/typescript/` and passes the same suite.

Resolve dependencies and check World Model grounding across packages, without a hosted registry:

```bash
ontle resolve examples/physical-ai/multimodal-action-world-model --source examples
ontle validate --resolve --source examples examples/physical-ai/multimodal-action-world-model
# sources: directories, *.owp.zip, git+<url>@<tag>[#subdir=<path>]; ONTLE_PATH is also read
```

Compile and check Effective World State with the reference declarative compiler:

```bash
W=examples/business/manufacturing-quality-world
ontle ews compile $W --compiler state/quality-incident-compiler.yaml \
  --observations $W/examples/observations.yaml --as-of 2026-09-05T00:00:00Z > ews.yaml
ontle ews check ews.yaml --world $W
```

Validate all examples:

```bash
./scripts/golden_smoke.sh
```

## Core separation

```text
World (in real)
   <-> interface: observation / source / action / commit
World (in data schema)
   -> World View (packaged reusable contract)
   -> State Compiler (packaged reusable contract)
   -> Effective World State (runtime-derived)
   -> representation adapter
   -> World Model / solver / simulator
   -> decision / governed action
```

`World (in real)` is not a package artifact. OWP packages explicit representations and contracts about it.

A World does not need a World Model to be useful. WorldPackages declare a cumulative conformance profile — `descriptive`, `viewable`, `stateful`, `model-ready`, `action-ready` — while every WorldModelPackage must name the Views and State Compilers it is valid for.

## Evaluation lineage

"Model A scored 92" is not reusable. "Model A scored 92 under EvaluationProfile 3.1, Verifier 1.4, View X, Environment Y" is. OWP binds results to exact evaluation versions through `CompatibilityEvidence`; running and evolving evaluations stays in runtimes and registries.

## Position relative to other standards

OWP does not replace OpenUSD, ROS 2, LeRobot, ASAM OpenSCENARIO, ISA-95, OPC UA, Hugging Face cards, MLflow signatures, or OCI. It records how their artifacts relate inside one World, View, and model applicability scope. See `docs/STANDARDS_INTEROP.md`.

## Naming

- **Open World Package (OWP)** is the packaging/interoperability standard.
- **`owp.yaml`** is the public manifest filename.
- **ONTLE** is the reference authoring/package-manager/registry client.
- **`ontle`** is the CLI.

## Status

Planned changes, in order, are in `ROADMAP.md`.


This repository is a public-alpha reference implementation. It is suitable for authoring, validation, deterministic package creation, archive verification, and examples. A hosted registry protocol/client is a subsequent layer and is not claimed as production-ready here.

## Licensing

- Code, CLI, schemas, templates, examples: Apache-2.0
- `spec/` and `docs/`: CC BY 4.0
- Trademarks: not granted by either license

See `LICENSE`, `LICENSES/CC-BY-4.0.txt`, and `NOTICE`.
