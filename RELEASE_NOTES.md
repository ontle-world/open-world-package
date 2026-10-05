# Public Alpha Release Notes — 0.2.0-alpha.5

This is the third tagged public alpha, and the first on PyPI, of the Open World Package (OWP) specification (`openworld/v1alpha1`) and of `ontle`, its Python reference CLI. The full list of changes is in `CHANGELOG.md`.

OWP is a package format for Worlds and the models that work on them:

```text
OntologyPackage            what things are (T-box)
WorldPackage               a World: Views, State Compilers, bindings, knowledge, work and actors
  -> WorldViewProfile      a projection of the World for a purpose
  -> StateCompilerProfile  how observations become state
  -> EffectiveWorldState   the state at a time, with provenance, unresolved values, and missing fields
WorldModelPackage          a model that consumes that state, with evaluation lineage and evidence
```

## New in 0.2.0-alpha.5

- **On PyPI as `ontle`.** The Python distribution is renamed from `ontle-open-world` to `ontle`, so the package, the import, and the command share one name. Releases are published from the release workflow with Trusted Publishing.

## New in 0.2.0-alpha.4

- **Package reports.** `ontle inspect <dir|zip> --report` prints a `PackageReport` (`schemas/package-report.schema.json`, informative): verdict, declared and satisfied profile, assets by kind, EWS fields with a binding, external references and how many are pinned, evidence, and hints for catalog pages. The TypeScript implementation gives the same report (`owp-validate report`), checked in CI on every package in the repository.
- **Read-only MCP server.** `ontle mcp <package>` serves a package to agents over stdio: its manifest, card, Views, State Compilers, and EWS, and the tools `world_describe`, `view_get`, `term_lookup`, `ews_compile`, and `package_report`.
- **World View composition** (experimental). `spec.composes` lists local Views; the View's include is their union. Filtering (`projection.exclude`) and overriding (`specializes`) already existed.
- **Cards.** Templates and examples start with `Scope`, `Sources`, `Use it for`, `Limitations`, and `Versions`, and carry `metadata.description`.
- **Standards.** SKOS value sets at `https://w3id.org/owp/vs/`, SHACL shapes for EWS RDF output, and schema.org mappings.
- **Fix.** An ExternalRef with `status: null` is bound, and the lock records it.

## Install

```bash
pip install --pre "ontle[rdf]"
ontle --version
```

`--pre` is needed while releases are alpha. `ontle[rdf]` adds RDF tooling; plain `ontle` is enough for validation. Or install from a checkout with `pip install -e ".[rdf]"`. Python 3.11 or later is required.

## Included

- **Specification:**
  - `spec/OWP_SPEC.md` (core).
  - `OWP_SEMANTICS.md`: ontologies and semantic binding.
  - `OWP_EVALUATION_AND_STATE.md`: evaluation, evidence, and EWS.
  - `OWP_WORK_AND_ACTORS.md`: work, actors, artifacts, and knowledge.
  - `OWP_EXPERIMENTAL.md`.
- **Schemas and registries:** JSON Schemas for every document kind; the rule-id registry `spec/rule-ids.yaml`; the asset-kind and value-set vocabularies.
- **`ontle` CLI:**
  - Authoring: init, new, add.
  - Checking: validate (with `--resolve`), inspect (with `--report`).
  - Packaging: pack, verify, lock, fetch, sign.
  - Distribution: resolve, push, index, evidence.
  - State: ews compile and check, with `--jsonld`, `--rdf`, and `--ngsi-ld` output.
  - Knowledge: ontology index, export, kg check and extract, interop mcp.
  - Agents: mcp, a read-only MCP server for one package.
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

- A hosted ONTLE Registry service, or an npm package of the TypeScript implementation.
- Production enterprise or robot write connectors, or an AX Guard / durable execution runtime.
- Generic ML checkpoint standardization, or automatic World or World Model composition (World View composition is declared, experimental).
- An implementation maintained by an independent party.
- Evaluation execution, triage, or promotion workflows.
- Stability: this is an alpha. Documents, rule ids, and CLI options may change before `v1beta1`.

## Licensing

Code, the CLI, schemas, templates, and examples are Apache-2.0; `spec/`, `docs/`, and the OWP vocabulary are CC BY 4.0. See `LICENSE`, `LICENSES/CC-BY-4.0.txt`, and `NOTICE`.
