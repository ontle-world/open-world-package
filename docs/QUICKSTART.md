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

```bash
ontle add view sales-manager
ontle add compiler sales-manager-state
ontle add source crm
ontle add scenario qualification
ontle add test basic
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
ontle init quality-model --template worldmodel --namespace example
ontle init embodied-model --template worldmodel-multimodal --namespace example
```

Both templates expose the same `ModelArtifact + RepresentationAdapter + EvaluationProfile` skeleton. Every World Model must also declare its compatible World View(s) and State Compiler(s) as `<worldRef>#<asset path>`; the multimodal variant additionally declares modality and temporal contracts.
