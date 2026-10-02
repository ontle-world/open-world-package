# 10-minute Quickstart

## 1. Install

```bash
python -m pip install -e .
ontle --version
```

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
examples/basic.yaml
.ontle/project.yaml
```

Start with `WORLD.md` and `owp.yaml`. The generated project declares `conformance.profile: stateful`; the default View and State Compiler make `World -> View -> EWS` explicit and can stay unchanged until your task requires specialization. A reference or taxonomy World that never compiles state can remove them and declare `descriptive`. `ontle inspect` shows the declared and the actually satisfied profile.

## 3. Validate and inspect

```bash
ontle validate .
ontle inspect .
```

## 4. Add only what you need

An asset is a YAML file that says what it is with `apiVersion` and `kind`. Add one by creating the file; `owp.yaml` does not change:

```yaml
# views/sales-manager.yaml
apiVersion: openworld/v1alpha1
kind: WorldViewProfile
metadata:
  name: sales-manager
spec:
  worldRef: self
  purpose: {task: qualify_opportunities, objective: focus_on_likely_wins}
  projection: {include: [account, opportunity, activity]}
```

`ontle validate .` picks it up. YAML files without an OWP `apiVersion` (CI configuration, for example) are ordinary files and are not checked as assets. Sample data that is not an asset (an `ObservationSet`, an expected EWS) is listed in `spec.assets` as a `PackageExample`.

`ontle new <Kind> <path>` writes the same kind of file as a skeleton. It starts with a `# yaml-language-server: $schema=...` line, so editors with the YAML extension validate and complete it:

```bash
ontle new StateCompilerProfile state/sales-manager.yaml
```

## 5. Build a deterministic package archive

```bash
ontle pack .
```

The default artifact is written under `dist/` as `*.owp.zip` and includes an `owp.lock.json` with content hashes.

Verify it:

```bash
ontle verify dist/<artifact>.owp.zip
```


## 6. Create an Ontology or World Model package

```bash
ontle init enterprise-core --template ontology --namespace example
```

## 7. Create a World Model package

```bash
ontle init quality-model --template worldmodel --namespace example --world ./my-world
ontle init embodied-model --template worldmodel-multimodal --namespace example --world example/robot-world@0.1.0
```

`--world` grounds the model in a World and adds it to `spec.dependencies`: a World directory supplies its identity, default View, and default State Compiler; a `<namespace>/<name>@<version>` reference assumes the starter's `views/default.yaml` and `state/default-compiler.yaml`. Without it, replace the `replace-with-...` placeholders yourself.

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

## 9. Describe who does the work (experimental)

Add these as asset files like any other: `ActorProfile`, `RoleProfile`, `DelegationProfile`, `CapabilityContract`, `TaskSetProfile`, `WorkPatternProfile`, `ArtifactContract`, and `ConsumerRepresentationProfile`. Then see how they connect:

```bash
ontle inspect . --graph    # who does what, with which View, producing which artifact
```

These kinds are experimental (spec Appendix C): problems in them are warnings, not errors. `examples/research/assay-optimization-world` is a small complete example.

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

Consumers resolve with `--source index:<url-or-path>` or `--source oci:<reference>`.
