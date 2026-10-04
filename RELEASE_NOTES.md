# Public Alpha Release Notes — 0.2.0-alpha.3

This is the first tagged public alpha of the Open World Package (OWP) specification (`openworld/v1alpha1`) and of `ontle`, its Python reference CLI. The full list of changes is in `CHANGELOG.md`.

OWP is a package format for Worlds and the models that work on them:

```text
OntologyPackage            what things are (T-box)
WorldPackage               a World: Views, State Compilers, bindings, knowledge, work and actors
  -> WorldViewProfile      a projection of the World for a purpose
  -> StateCompilerProfile  how observations become state
  -> EffectiveWorldState   the state at a time, with provenance, unresolved values, and missing fields
WorldModelPackage          a model that consumes that state, with evaluation lineage and evidence
```

## Install

```bash
pip install "ontle-open-world[rdf] @ https://github.com/ontle-world/open-world-package/releases/download/v0.2.0-alpha.3/ontle_open_world-0.2.0a3-py3-none-any.whl"
ontle --version
```

Or install from a checkout with `pip install -e ".[rdf]"`. The package is not on PyPI yet. Python 3.11 or later is required.

## Included

- **Specification:**
  - `spec/OWP_SPEC.md` (core).
  - `OWP_SEMANTICS.md`: ontologies and semantic binding.
  - `OWP_EVALUATION_AND_STATE.md`: evaluation, evidence, and EWS.
  - `OWP_WORK_AND_ACTORS.md`: work, actors, artifacts, and knowledge.
  - `OWP_EXPERIMENTAL.md`.
- **Schemas and registries:** JSON Schemas for every document kind; the rule-id registry `spec/rule-ids.yaml`; the asset-kind and value-set vocabularies.
- **`ontle` CLI:**
  - Authoring: init, add, sync.
  - Checking: validate (with `--resolve`), inspect.
  - Packaging: pack, verify, lock, fetch, sign.
  - Distribution: resolve, push, index, evidence.
  - State: ews compile and check, with `--jsonld`, `--rdf`, and `--ngsi-ld` output.
  - Knowledge: ontology index, export, kg check and extract, interop mcp.
- **TypeScript implementation:** `implementations/typescript/`, written clean-room from the spec. It is not published to npm.
- **Conformance suite:** `conformance/`, language-neutral, with the reference ids both implementations report.
- **Examples:**
  - Business: manufacturing quality, sales prioritization.
  - Research: assay optimization.
  - Physical AI: mobile manipulation.
  - World Models: runnable reference models, including baseline and LLM World Models.
  - End-to-end demos.
- **OWP vocabulary and alignments:** at `https://w3id.org/owp/ns`, with PROV-O, BFO 2020, and DUL alignments checked with HermiT.

## Not claimed

- A hosted ONTLE Registry service, or PyPI and npm packages.
- Production enterprise or robot write connectors, or an AX Guard / durable execution runtime.
- Generic ML checkpoint standardization, or automatic World/View/World Model composition.
- An implementation maintained by an independent party.
- Evaluation execution, triage, or promotion workflows.
- Stability: this is an alpha. Documents, rule ids, and CLI options may change before `v1beta1`.

## Licensing

Code, the CLI, schemas, templates, and examples are Apache-2.0; `spec/`, `docs/`, and the OWP vocabulary are CC BY 4.0. See `LICENSE`, `LICENSES/CC-BY-4.0.txt`, and `NOTICE`.
