# 10-minute Quickstart

The five-minute path, from nothing to a checked archive:

```bash
python3 -m venv .venv && . .venv/bin/activate && python -m pip install --pre ontle
ontle init my-world --namespace acme          # prints the project path, then the next steps
ontle validate my-world
ontle inspect my-world --report               # what a catalog would show, with hints
ontle pack my-world && ontle verify my-world/dist/acme-my-world-0.1.0.owp.zip
```

The sections below explain each step and what to add next.

## 1. Install

In a virtual environment (Python 3.11+):

```bash
python3 -m venv .venv && . .venv/bin/activate
python -m pip install --pre ontle      # alpha releases need --pre
ontle --version
```

`ontle[rdf]` adds RDF tooling (ontology index for RDF entrypoints, `kg check`, SPARQL extraction). To work on ONTLE itself, install from a clone with `python -m pip install -e .`.

## 2. Create a World

```bash
ontle init sales-opportunity --namespace example
cd sales-opportunity
```

Generated:

```text
WORLD.md
owp.yaml
views/default.yaml
state/default-compiler.yaml
examples/observations.yaml
examples/expected-ews.yaml
.ontle/project.yaml
```

Start with `WORLD.md` and `owp.yaml`. The generated project declares `conformance.profile: stateful`; the default View and State Compiler make `World -> View -> EWS` explicit and can stay unchanged until your task requires specialization. A reference or taxonomy World that never compiles state can remove them and declare `descriptive`. `ontle inspect` shows the declared and the actually satisfied profile.

## 3. Validate, compile state, inspect

```bash
ontle validate .
ontle ews compile . --observations examples/observations.yaml --as-of 2026-01-02T00:00:00Z > ews.yaml
ontle ews check ews.yaml --world .
ontle inspect .
ontle inspect . --report
```

`inspect --report` prints the `PackageReport` ([schema](../schemas/package-report.schema.json)): the verdict, the declared and satisfied profile, assets by kind, how many EWS fields have a binding, external references and how many are pinned, evidence, and `hints`. A catalog or registry builds its badges and filters from this report, so authors never write statistics by hand. The hints are not validation findings: they point at what a catalog page would miss, such as a missing `metadata.description` (the one-line summary on a package card) or a card without the recommended sections `Scope`, `Sources`, `Use it for`, `Limitations`, and `Versions`. The templates' cards start with these sections.

The starter compiles as generated: its State Compiler has one observed field, one aggregate, and one classification, each with a value per item, and `examples/expected-ews.yaml` is what the sample observations compile to. Replace the `item` fields and observations with your own; [STATE_COMPILATION.md](STATE_COMPILATION.md) shows how to write fields and bindings.

## 4. Add only what you need

An asset is a YAML file that says what it is with `apiVersion` and `kind`. Add one by creating the file; `owp.yaml` does not change:

```yaml
# views/sales-manager.yaml
apiVersion: openworld/v1alpha1
kind: WorldViewProfile
metadata:
  name: sales-manager
spec:
  purpose: {task: qualify_opportunities, objective: focus_on_likely_wins}
  projection: {include: [account, opportunity, activity]}
```

`ontle validate .` picks it up. YAML files without an OWP `apiVersion` (CI configuration, for example) are ordinary files and are not checked as assets. Sample data that is not an asset (an `ObservationSet`, an expected EWS) is listed in `spec.assets` as a `PackageExample`.

To keep files out of the package, such as drafts or local notes, list them in `.owpignore` at the package root. It uses gitignore patterns. Excluded files are not read as assets and are left out of `ontle pack`:

```text
drafts/
*.wip.yaml
```

`ontle new <Kind> <path>` writes the same kind of file as a skeleton. It starts with a `# yaml-language-server: $schema=...` line, so editors with the YAML extension validate and complete it:

```bash
ontle new StateCompilerProfile state/sales-manager.yaml
```

## 5. Build a deterministic package archive

```bash
ontle pack .
```

The default artifact is written under `dist/` as `*.owp.zip` and includes an `owp.lock.json` with content hashes. `ontle pack . --list` previews the files an archive would contain, without writing it. Paths that start with `.` (`.env`, `.git`, `.ontle`) and `dist/` are never packed; exclude anything else with `.owpignore`.

Verify it:

```bash
ontle verify dist/<artifact>.owp.zip
ontle inspect dist/<artifact>.owp.zip --report   # the report of the archive, with its digest and size
```

`ontle pack` warns when an archive is over 50 MB. Registries set their own upload limits; keep large data outside the package as an `ExternalRef` (spec section 5.1).


## 6. Create an Ontology package

```bash
ontle init enterprise-core --template ontology --namespace example
```

## 7. Create a World Model package

```bash
ontle init quality-model --template worldmodel --namespace example --world ./my-world
ontle init embodied-model --template worldmodel-multimodal --namespace example --world example/robot-world@0.1.0
```

`--world` grounds the model in a World and adds it to `spec.dependencies`: a World directory supplies its identity, default View, and default State Compiler (`--view views/<file>.yaml` picks another View and the State Compiler that compiles it); a `<namespace>/<name>@<version>` reference assumes the starter's `views/default.yaml` and `state/default-compiler.yaml`. Without it, replace the `replace-with-...` placeholders yourself.

Grounding is checked against the World itself, so `ontle validate` needs to find it. `init --world <dir>` records the World's parent directory in `.ontle/project.yaml`, and `validate` looks there, in `--source`, and in `ONTLE_PATH`. When a dependency is not found, `validate` checks the package alone and says so in a `NOTE:` line; `--resolve` turns a missing dependency into an error.

To run and compare models, see `examples/business/quality-scenario-world-model/WORLDMODEL.md`: a model is a function over an EWS and a scenario, and `models/run.py` runs yours next to reference baselines and scores them against a recorded outcome.

Both templates expose the same `ModelArtifact + RepresentationAdapter + EvaluationProfile` skeleton. Every World Model must also declare its compatible World View(s) and State Compiler(s) as `<worldRef>#<asset path>`; the multimodal variant additionally declares modality and temporal contracts.

## 8. Bind your World to an ontology

Publish shared vocabulary as an OntologyPackage, depend on it, and bind your World's names and EWS fields to its terms:

```bash
ontle init quality-terms --template ontology --namespace acme
# in the World: add the ontology to spec.dependencies, add a SemanticBinding asset,
# and point spec.world.semanticBinding at it (see examples/business/manufacturing-quality-world)
ontle validate --resolve --source .. .
ontle inspect .            # semanticCoverage shows how many EWS fields are bound
```

## 9. Describe who does the work

Add these as asset files like any other: `ActorProfile`, `RoleProfile`, `DelegationProfile`, `CapabilityContract`, `TaskSetProfile`, `WorkPatternProfile`, `ArtifactContract`, and `ConsumerRepresentationProfile`. Then see how they connect:

```bash
ontle inspect . --graph    # who does what, with which View, producing which artifact
```

These kinds are standard (spec sections 16-19, `spec/OWP_WORK_AND_ACTORS.md`). Who holds a role or task can be declared on the ActorProfile (`assignments`) or left to runtime observations; choose per World (section 17.1). Some vocabularies (work patterns, artifact types) are open: a value outside them is a warning, so you can use your own. `examples/research/assay-optimization-world` is a small complete example.

## 10. Add publisher-specific data

Declare an extension as a dependency with a local name, then use that name:

```bash
ontle add extension acme/quality-extension@1.2.0 --as acme-quality
```

```yaml
spec:
  extensions:
    acme-quality: {plantCode: P-07}
```

Any other unknown key is an error, so typos are caught early.

## 11. Publish

```bash
ontle lock .                                   # pin https external references
ontle pack .
ontle index build dist/*.owp.zip --base dist --output dist/index.json
ontle push dist/acme-demo-0.1.0.owp.zip ghcr.io/acme/demo:0.1.0   # needs oras
ontle sign dist/acme-demo-0.1.0.owp.zip                           # needs cosign
```

Consumers resolve with `--source index:<url-or-path>` or `--source oci:<reference>`. The [package catalog](https://ontle-world.github.io/open-world-package/catalog/) publishes the example packages this way: `--source index:https://ontle-world.github.io/open-world-package/catalog/index.json`.

To let an agent read a package, serve it over the Model Context Protocol: `ontle mcp .` (stdio, read-only; see [interop/MCP.md](interop/MCP.md)).
