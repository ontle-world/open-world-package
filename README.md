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
python3 -m venv .venv && . .venv/bin/activate
python -m pip install -e .

ontle init my-world --namespace acme
cd my-world

# The starter compiles: a View, a State Compiler, sample observations, and the EWS they give.
ontle validate .
ontle ews compile . --observations examples/observations.yaml --as-of 2026-01-02T00:00:00Z
ontle pack . --list
```

The generated project contains only the authoring surface. `.ontle/` is generator-owned metadata and can be ignored by most users.

### Where to go next

| You want to | Read | Then try |
|---|---|---|
| Describe a World: what exists, what is observed, what state a task needs | [docs/QUICKSTART.md](docs/QUICKSTART.md), [docs/STATE_COMPILATION.md](docs/STATE_COMPILATION.md) | `examples/business/manufacturing-quality-world` |
| Build or compare a World Model for a World | [docs/QUICKSTART.md §7](docs/QUICKSTART.md#7-create-a-world-model-package), [quality-scenario-world-model](examples/business/quality-scenario-world-model/WORLDMODEL.md) | `python examples/business/quality-scenario-world-model/models/run.py --baselines` |
| Run packages in your own runtime | [docs/RUNTIME_INTEGRATION.md](docs/RUNTIME_INTEGRATION.md), [demos/](demos/) | `python demos/business-ai/run.py` |
| Look up a term | [docs/CONCEPTS.md](docs/CONCEPTS.md), [docs/GLOSSARY.md](docs/GLOSSARY.md) | |

## Starter templates

```bash
ontle init my-world --template minimal
ontle init my-enterprise-world --template enterprise
ontle init my-ontology --template ontology
ontle init my-world-model --template worldmodel --world ./my-world
ontle init my-vla-world-model --template worldmodel-multimodal
```

## Adding assets

An asset is a YAML file that says what it is. Put it anywhere in the package; `owp.yaml` does not list it.

```yaml
# views/manager.yaml
apiVersion: openworld/v1alpha1
kind: WorldViewProfile
metadata:
  name: manager
spec:
  purpose: {task: assign_accounts, objective: balance_territories}
  projection: {include: [account, territory]}
```

`ontle validate .` finds it by its `apiVersion` and `kind`. To start from a skeleton with editor schema hints, run `ontle new WorldViewProfile views/manager.yaml`; it works for any asset kind.

More commands:

```bash
ontle inspect . --graph --resolved-views
ontle add extension acme/quality-extension@1.2.0   # declare a publisher extension in owp.yaml

# knowledge graphs (needs the rdf extra)
ontle kg check . --source ../ontologies      # does the graph (A-box) use only its ontology's (T-box) classes and properties?
ontle kg extract . --profile extraction/claim-context.yaml --param claimId=C-102 > kg.yaml
ontle ews compile . --compiler state/quality-incident-compiler.yaml --observations observations.yaml --observations kg.yaml --as-of 2026-09-05T00:00:00Z

# distribution
ontle lock .                                   # pin https external references
ontle fetch . --into fetched/                  # download and verify external content
ontle pack . --vendor                          # include pinned https content in the archive
ontle index build dist/*.owp.zip --base dist --output dist/index.json
ontle validate --resolve --source index:dist/index.json .
ontle push dist/acme-line-world-0.1.0.owp.zip ghcr.io/acme/line-world:0.1.0   # needs oras
ontle sign dist/acme-line-world-0.1.0.owp.zip                                 # needs cosign
ontle catalog . --format dcat

# ontology packages
ontle ontology index        # write the term index (RDF entrypoints: pip install 'ontle-open-world[rdf]')
ontle export --format turtle
```

## Examples

- `examples/business/manufacturing-quality-world` — business/manufacturing World package
- `examples/business/quality-transition-world-model` — World Model bound to a business World
- `examples/business/quality-scenario-world-model` — runnable reference World Models for one scenario: persistence, three-point, Monte Carlo, and Markov baselines on a CPU, and an LLM model as the minimum bar (`python models/run.py --baselines`)
- `examples/ontology/lab-ontology`, `examples/ontology/sales-ontology` — T-boxes of the assay and sales example graphs
- `vocab/owp` — the OWP vocabulary (RDF terms for OWP's own concepts); `alignments/` — informative alignments to PROV-O, BFO 2020 + IAO, and DOLCE+DnS Ultralite (`docs/STANDARDS_INTEROP.md`)
- `examples/ontology/quality-ontology` — ontology package (owp-yaml schema, SHACL shapes, SSSOM mappings) used by the manufacturing World
- `examples/research/assay-optimization-world` — laboratory World with actors, roles, delegation, a design-test-learn work pattern, evaluation, and a scenario
- `examples/business/sales-prioritization-world` — actor-specialized Views, tasks, artifacts, and consumers
- `examples/physical-ai/mobile-manipulation-world` — Physical AI World package
- `examples/physical-ai/multimodal-action-world-model` — multimodal/VLA-style World Model package

End-to-end demos on sample data, from observations to evidence: `demos/` (see `demos/README.md`).

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
