# Changelog

## Unreleased

## 0.2.0-alpha.6 — Catalog, Pilot Fixes, Aggregate Filters, Binding Checks

Highlights:
- **Package catalog** on the project site: a page per example package from its report, and a PackageIndex to resolve from.
- **From records to state**: `ontle observations csv`, aggregate filters (`where`), and `ews check --observations`, which compares an expected EWS by value.
- **Binding meaning checks**: rule-based warnings when a binding uses a property on the wrong class or maps a code outside an enum, from the ontology's own declarations.
- **Fixes from a new-user pilot**, including `evidence check` version binding and `pack --output <directory>`.
- **Conformance.** 252 validation, 37 resolution, 34 EWS compile, 24 EWS check, 13 extraction, and 5 detached evidence cases.

Changes:

- Aggregate filters (spec 12.4): an `aggregate` binding may declare `where`, a mapping from a key of the observation's `values` to the conditions a classification rule uses (`eq`, `in`, `gt`, `gte`, `lt`, `lte`). Only observations that have every key and meet every condition are candidates, and the EWS derivation records `where`. For example `where: {result: {in: [fail, rework]}}` counts failed inspections without a separate observation type. Both implementations; 1 EWS case and 4 validation cases.
- Binding meaning checks (spec 14), rule-based on what the dependency ontologies' `owp-yaml` schemas declare:
  - `binding.path-domain` (warning): a field path step on a class the schema does not declare the property on (parents through `subClassOf` count).
  - `binding.value-range` (warning): a `values.map` code outside the enum range of the field's property.
  - Terms the schemas do not declare are not judged. Both implementations; 4 resolution cases.
  - Tools: `ontle kg check --bindings` makes the same checks against the RDF T-box (RDF schema entrypoints included), and `ontle ews check --source` warns about EWS values outside an enum the ontology declares.
- The example quality ontology's `IncidentStatus` is `open, under_investigation, closed`, the values the manufacturing World's data uses; the new check found the mismatch.

- Fixes and improvements from a new-user pilot (PyPI `ontle`, a World from raw MES/QMS records, and a World Model with detached evidence):
  - Fix: `ontle evidence check` compares the EvaluationProfile and VerifierProfile versions the evidence names with the ones the archive packages (`evidence.version-mismatch`), as validation does inside a package. Spec section 9.1 says so; both implementations; a new evidence conformance case.
  - Fix: `ontle pack --output <directory>` writes the default file name into the directory instead of failing.
  - When a dependency does not resolve, `validate` prints the first `grounding.prefix-unknown` error per package and counts the rest, instead of one line per term.
  - `--source <file>.json` says to use `index:<file>`.
  - Report hints: a `metadata.description` or card that still has template text, and a card that names package files that are not there. Both implementations.
  - The report's `state.boundFields` is now `state.withBinding`, and `semanticCoverage.boundFields` is `semanticCoverage.boundToTerms`, so the two counts are not confused.
  - `ontle mcp` tools reject unknown arguments, and `ews_compile` points at `observationsPath` when `observations` is not a document.
  - `ontle new CompatibilityEvidence` fills `subject` and `scope` from the package.
  - `ontle observations csv <file> --type --subject --time [--number] [--list]` turns a CSV of one record type into an ObservationSet.
  - `ontle ews check <ews> --world <w> --observations <file>` also compiles the observations and reports every field whose value differs, so an expected EWS can be kept current in CI. Before, `ews check` checked only the shape.
  - `ontle mcp --source` resolves the package's dependencies, and `term_lookup` searches the labels (every language), CURIEs, and IRIs of the ontologies among them.
  - Docs: STATE_COMPILATION.md shows how to turn CSV records into an ObservationSet; QUICKSTART shows a SemanticBinding, how to publish and check detached evidence, and what declared and satisfied profiles mean.

- Package catalog (registry step P0) on the project site, `https://ontle-world.github.io/open-world-package/catalog/`: a page per example package with its card, report, assets, dependencies and dependents, and verified archive, plus a filterable list. Every number comes from `ontle inspect --report`. The catalog's `index.json` is a PackageIndex with a term index, so `--source index:https://ontle-world.github.io/open-world-package/catalog/index.json` resolves the examples. A package identifier page (`https://w3id.org/owp/pkg/...`) links to the package's catalog page when there is one.

## 0.2.0-alpha.5 — On PyPI

The first release on PyPI: `pip install --pre ontle`. No changes to the spec, the suite, or verdicts since 0.2.0-alpha.4.

- The Python distribution is renamed `ontle` (was `ontle-open-world`), so the package, the import, and the command share one name: `pip install --pre ontle`. Extras are `ontle[rdf]`, `ontle[shacl]`, and so on.
- The release workflow publishes to PyPI with Trusted Publishing (no stored token) after the GitHub release, and checks with `twine check` that the README renders there. The README links are absolute so they work on PyPI.
- `pyproject.toml` lists project URLs, keywords, and more classifiers.

## 0.2.0-alpha.4 — Registry Readiness, View Composition

Python reference CLI `ontle` 0.2.0a4; the TypeScript implementation passes the same suite with the same rule ids, and now gives the same package report.

Highlights:
- **Package reports.** `ontle inspect --report` (and `owp-validate report`) derive what a catalog or registry shows for a package: verdict, profile, asset counts, binding coverage, pinned references, evidence, and card hints. Both implementations agree on all 265 packages in the repository.
- **Agents.** `ontle mcp` serves one package read-only over the Model Context Protocol.
- **World View composition.** `spec.composes` (experimental) gives a View the union of other Views; with `exclude` and `specializes`, the basic operations are in place.
- **Standards.** SKOS value sets, SHACL shapes for EWS RDF output, and schema.org mappings.
- **Conformance.** 248 validation, 33 resolution, 33 EWS compile, 24 EWS check, 13 extraction, and 4 detached evidence cases.

Changes:

- Standards relations, the rest of step P3:
  - The value sets are published as SKOS concept schemes: `vocab/owp/value-sets.ttl`, at `https://w3id.org/owp/vs/<set>#<value>`. `scripts/build_value_sets.py` generates the file, and a test keeps it current.
  - `vocab/owp/shapes.ttl` holds SHACL shapes for EWS RDF output. A test validates `--rdf` output against them, including a broken document they must reject. The new `shacl` extra installs pySHACL.
  - `alignments/owp-align-schemaorg` has SKOS matches to schema.org for catalogs.
  - `check_alignments.sh` also checks that package's OWL 2 DL profile.
  - The site publishes all three.
- `vocab/value-sets.yaml`: two labels contained a comma inside a flow mapping, so they were cut short and split into stray keys (`media`, `verification`). They are quoted now, and a test rejects unknown keys in value entries.
- The TypeScript implementation's package version follows the release (`0.2.0-alpha.3`), and the release workflow checks it.
- Registry readiness (reference CLI; no spec rule or verdict changes):
  - `ontle inspect --report` prints a `PackageReport` (`schemas/package-report.schema.json`, informative): verdict, declared and satisfied profile, assets by kind, EWS fields with a binding, semantic coverage, external references and how many are pinned, standards, evidence, card sections, and catalog hints. With an `.owp.zip` it adds the archive digest, size, and file count. Spec section 11.1 mentions it in one paragraph. `ontle inspect` also reads archives.
  - `ontle mcp <package>` serves one package read-only over the MCP stdio transport: the resources of `docs/interop/MCP.md` plus the card, and the tools `world_describe`, `view_get`, `term_lookup`, `ews_compile`, and `package_report`. It does not run actions.
  - `ontle init` prints the next steps on stderr; stdout is still the project path alone.
  - `ontle pack` warns when an archive is over 50 MB.
  - The template cards start with the recommended sections `Scope`, `Sources`, `Use it for`, `Limitations`, and `Versions`, and the template manifests have a `metadata.description` placeholder. The example cards follow the same sections.
  - `docs/QUICKSTART.md` opens with a five-minute path.
- The TypeScript implementation has the `PackageReport` too (`owp-validate report <dir|zip>`). `scripts/report_parity.py`, run in CI, checks that both implementations give the same report for every package in the repository (265).
- `ontle new WorldViewProfile <path> --composes <view> [--composes <view> ...]` writes a composed View skeleton.
- Fix: an ExternalRef with `status: null` counts as bound (spec section 5.1), so the lock's `externals` record it. Both implementations left it out.
- World View composition (experimental, Appendix C): a WorldViewProfile may declare `spec.composes`, a list of local Views. Its include is the union of theirs, in order, plus its own include, minus its own exclude; conditioning and the other projection keys come from the composed Views and are overridden by its own; purpose is its own. Missing entries and cycles are `experimental.reference`; a missing purpose, `composes` with `specializes`, and composed Views that disagree on a key the View does not set are `experimental.field`. Both implementations; 8 new conformance cases.

## 0.2.0-alpha.3 — Semantic Worlds, Work and Actors, Standards

The first tagged public alpha. Package format `openworld/v1alpha1`; Python reference CLI `ontle` 0.2.0a3; the TypeScript implementation in `implementations/typescript/` passes the same suite with the same rule ids.

Highlights:
- **Semantics.** OntologyPackages with a defined contract (prefixes, typed entrypoints, term index, pinned imports), SemanticBinding of World names, EWS fields, coded values, and dictionary identifiers (IRDI), `ontle kg check` and SPARQL knowledge extraction.
- **State.** Per-subject and latent EWS fields (estimate, aggregate, classify with a versioned criterion), units (UCUM), and EWS output as JSON-LD, RDF 1.2, and NGSI-LD.
- **Work and actors.** Tasks, work patterns, actors, roles, delegation, artifacts, and knowledge are standard kinds (spec sections 16–19).
- **Distribution.** Directory, `.owp.zip`, git, OCI, and static index sources; detached evidence; lock format `owp-lock/v1alpha2`.
- **Standards.** The OWP vocabulary at `https://w3id.org/owp/ns`, informative PROV-O, BFO 2020, and DUL alignments, and notes on MCP, NGSI-LD, and AAS.
- **Conformance.** 240 validation, 33 resolution, 33 EWS compile, 24 EWS check, 13 extraction, and 4 detached evidence cases. Every error id has a case, and both implementations report exactly the same ids. A mutation check in CI keeps them in agreement.

Changes:

- Second review fixes, and a parity check in CI:
  - `scripts/parity_fuzz.py` runs mutants of every conformance fixture through both implementations. A mutant is a fixture with one value changed: a wrong type, an odd string, a removed or renamed key, or a YAML tag. Both implementations must give the same verdict, the same error and warning ids, and an equal EWS, and neither may crash. A new CI job runs 3 seeds. 15 seeds (about 49,000 mutants) agree. Before these fixes, about 1 in 9 mutants disagreed, and the Python reference crashed on 4%.
  - `reference-ids.json` now also covers the EWS compile and EWS check sections, so both implementations report exactly the same ids there too.
  - The Python reference no longer crashes on wrong-typed values in any package, ObservationSet, or EWS document, and reports the ids the TypeScript implementation reports.
  - TypeScript no longer crashes on `kind: toString`, on metadata values such as `{toString: 1}`, or on table lookups by such names. Subjects and prefixes named `__proto__` or `constructor` are no longer treated as present.
  - YAML:
    - The core tags (`!!str`, `!!int`, `!!float`, `!!bool`, `!!null`, `!!map`, `!!seq`) are applied in both implementations.
    - Any other tag (`!!binary`, `!!set`, `!!timestamp`, `!!omap`, `!!pairs`, a local tag such as `!note`) is a load error.
  - Text rules:
    - SemVer, timestamps, and durations accept ASCII digits only.
    - "Whitespace" means the JavaScript whitespace set in both implementations.
    - EWS timestamps cover the years 0000–9999.
  - Field types:
    - `spec.assets` that is present but not a list (including `null`) is `asset.list`.
    - `worldModel.roles` must be a list of non-empty strings, and `world.definition` a non-empty string.
    - `extensionDefinition.description` must be a string.
    - A dependency `source` that is not a non-empty string is `manifest.dependency`.
  - `metadata.version` that is present but not a SemVer string is `manifest.version`. A missing, null, or empty version is `manifest.identity`.
  - CompatibilityEvidence:
    - A missing `metadata.name` or a spec that is not a mapping is `evidence.required`.
    - Scope fields that are not strings are `evidence.scope`.
  - EWS compile:
    - A World that is not a WorldPackage is `ews.state-compiler`.
    - A malformed `spec.bindings` is `compiler.binding`.
    - ObservationSet `apiVersion`, empty ids or types, and `.inf`, `.nan`, or integers outside ±(2^53−1) in values are `ews.input`.
  - EWS check:
    - A World that is not a WorldPackage is `ews.world-ref`, and checking stops at `ews.shape`.
    - Null sections count as absent, and `traceRequired` must be `true`.
  - Git sources:
    - Refs are matched by exact name; before, `main` could match `feature/main`.
    - Checkouts are keyed by the commit actually fetched.
    - The commit each rev last resolved to is remembered, so a cached source works offline.
  - `ontle kg check`:
    - Within one OntologyPackage, separate domain or range statements must all hold.
    - When several packages each state one for a property, one package's statements holding is enough, so a package can reuse a property for its own types.
    - T-box files outside a package are never read.
  - Output:
    - NGSI-LD entity ids are the IRIs `--rdf` gives.
    - A field named like a reserved NGSI-LD name (`type`, `id`, ...) gets a trailing `_`.
    - An empty coded list as an unresolved alternative stays valid Turtle.
    - A code `3.0` maps like `3`.
    - Spec section 14 states the percent-encoded character set (RFC 3986 unreserved).
  - Coverage:
    - The coverage test no longer counts `evidence.scope` as covered by `evidence.scope.world-ref`.
    - New cases: `evidence-scope-missing`, `manifest-kind-list`, `manifest-version-non-ascii-digit`, `asset-list-null`, `model-roles-string`, `yaml-local-tag`, and `dependency-source-not-string`; EWS cases `error-unsafe-integer` and `year-zero-timestamp`.
    - The vocabulary term-index test regenerates the indexes and compares them with the committed files.
- Conformance cases for the 13 error ids that had none: 16 new cases, so the known-gaps list in the coverage test is empty. (`evidence.scope` was still missing; see the next entry.)
  - New sections: a new `evidenceCases` section checks CompatibilityEvidence published outside a package against its archive (`evidence/<id>/evidence.yaml`, `package.owp.zip`; spec 9.1). Both implementations run it, and its ids are in `reference-ids.json`.
  - The cases found these disagreements, now fixed:
    - TypeScript did not report a malformed dependency of a resolved package as `resolve.reference`.
    - Python reported a `stateCompiler` that names another World as `ews.state-compiler` instead of `ews.world-ref` (spec Appendix A).
    - Python added `manifest.identity` errors under a malformed `metadata`, and World Model sub-errors under a missing `spec.worldModel`.
  - Python also no longer crashes on a manifest whose `spec` is not a mapping, in `validate --resolve`, `validate`, or `inspect`.
- Review fixes for the changes above:
  - Python and TypeScript now agree:
    - TypeScript no longer treats names such as `toString` or `constructor` as bound or as having units.
    - A null `subjects`, `semanticIds`, `outputSchema.units`, or `criterion.unit` counts as absent in both.
    - Python patterns no longer accept a trailing newline.
    - Python no longer crashes on a list-valued `classify.input` or a null ontology prefix.
    - Ten new cases, plus a test that every error id has a conformance case (13 earlier ids are listed as known gaps). New cases for `knowledge.field`, `knowledge.reference`, `evaluation.evaluator-ref`, and `compiler.latent-field`.
  - EWS compilation: a `count` or `distinct_count` no longer compares its unit with the unit of what it counts.
  - Output:
    - `--rdf`, `--jsonld`, and `--ngsi-ld` percent-encode subject keys under `base`, and refuse a subject that is not an IRI under `iri: true`.
    - All three map coded list elements and numeric codes (by their decimal text), and refuse codes without a concept.
    - NGSI-LD gives one entity per subject (refined in the next entry: entity ids are the IRIs `--rdf` gives).
    - Non-finite numbers are written as `NaN`, `INF`, and `-INF`.
  - `ontle kg check`: separate `rdfs:domain` and `rdfs:range` triples must all hold, as in RDFS. Any member is enough only within an `owl:unionOf`.
  - Vocabulary:
    - The OWP vocabulary's term index includes its individuals (`owp:resolved`, `owp:unresolved`) and the `owp:Resolutions` scheme, so `values` can map to them.
    - The ten promoted value sets are `standard` with an `open` flag that the code is checked against.
  - Alignments:
    - The SSSOM metadata blocks parse as YAML, and the version is `0.1.0`.
    - `owp:World` is a `skos:relatedMatch` of BFO entity, not a broad match.
    - `check_alignments.sh` checks the OWL 2 DL profile (the PROV-O import itself is outside DL) and stops when a fetched file is missing.
  - Robustness:
    - `ontle index build --terms` never reads entrypoints outside an archive.
    - Git sources key their cache by commit, so a moved tag or branch is fetched again.
    - The site publishes the alignments' term indexes.
    - CI runs with read-only permissions.
  - Spec and docs:
    - The section 14 example cites the ECLASS manufacturer-name IRDI on a manufacturer field.
    - `extraction.input` is in section 19.2.
    - Corrected the AASX and NGSI-LD notes, and two CHANGELOG entries.
  - The Markov baseline example stops counting at a timestamp tie, and skips an LLM answer that is cut off or not JSON.
- Runtime standards (informative, `docs/interop/`):
  - MCP: `ontle interop mcp <world>` prints what an MCP server for a World exposes. The World, Views, and State Compilers become resources, the EWS at a time becomes a resource template, and actions become tools. Each tool's `_meta` links the commit contract and effect verification, since a successful call is not a commit.
  - NGSI-LD: `ontle ews compile --ngsi-ld` writes an EWS as NGSI-LD entities. Subjects become entities and fields become properties named by their bound IRIs. Coded values become VocabProperties, and each unresolved alternative becomes an attribute instance with its own `datasetId`.
  - AAS: a mapping note covering submodels as observation sources, `semanticId` as `semanticIds`, value lists as `values`, and ECLASS licensing.
- Package index term index (spec section 11.1): `ontle index build --terms` adds `terms` and `mappings`. `terms` maps each term IRI to the packages that define and use it, and `mappings` lists the indexed packages' mapping sets. Resolution ignores both.
- Coded values and dictionary identifiers (spec section 14):
  - A SemanticBinding field may tie its coded values to concepts with `values: {scheme, base, map}`. `map` wins, and `base` is used only for IRI-safe codes. `ontle ews compile --rdf` and `--jsonld` then give concept IRIs, and refuse a value they cannot map. `binding.values` covers malformed entries, and the term check covers `scheme` and `map` concepts.
  - `semanticIds` attaches external dictionary identifiers (IRDIs in canonical `#` form, or absolute IRIs) to names bound in the same section, for example the ECLASS or IEC CDD identifiers of an Asset Administration Shell. Only their syntax is checked (`binding.semantic-ids`), and licensed dictionary content stays out of packages.
  - New cases: four validation cases and one resolution case.
- Site for `https://w3id.org/owp/`: `scripts/build_site.py` builds the vocabulary (Turtle, JSON-LD, HTML), the alignments, the specification snapshot, and a package-identifier page; `.github/workflows/pages.yml` publishes it to GitHub Pages.
- RDF output: `ontle ews compile --rdf` writes the EWS as Turtle 1.2 in the OWP vocabulary. Each value is an `owp:StateValue` that reifies the unasserted triple (subject, bound property, value) when the SemanticBinding gives the field a one-step path and its subjects IRIs, and otherwise gives `rdf:value`. Each value carries its field, its resolution, its observations (`prov:wasDerivedFrom`), and its derivation, and the EWS is `prov:wasGeneratedBy` a compilation whose plan is the State Compiler. Packages and assets get IRIs under `https://w3id.org/owp/pkg/` and `apiVersion` maps to `dct:conformsTo <https://w3id.org/owp/spec/v1alpha1>` (`docs/STANDARDS_INTEROP.md`). The `rdf` extra adds pyoxigraph, which reads RDF 1.2.
- Units (spec section 12.5): a State Compiler declares a UCUM code per field in `outputSchema.units`; observations may report units per value key (`units`); a SemanticBinding field may name the unit as an ontology term (`unit`, such as a QUDT unit). Units are never converted: a reported unit unlike the field's, or an aggregate over mixed units, is invalid input (`ews.input`); a count is dimensionless, a classification has no unit, and a criterion's unit is its input's (`compiler.unit`). EWS documents are unchanged. Four validation and three EWS compile cases.
- OWP vocabulary and alignments: `vocab/owp` publishes RDF terms for OWP's own concepts (`https://w3id.org/owp/ns#`, OWL 2 DL, CC BY 4.0), reusing PROV-O, XSD, and DCTERMS instead of redefining them. `alignments/` holds three informative OntologyPackages (`owp-align-prov`, `owp-align-bfo`, `owp-align-dul`), each with OWL axioms and an SSSOM mapping set, and with the upstream ontologies pinned by digest. `scripts/check_alignments.sh` (a new CI job) reasons over them with HermiT: each is consistent with sample data, and five deliberately wrong inputs are caught. Both validators check the packages.
- Work, actor, artifact, and knowledge kinds are standard (new `spec/OWP_WORK_AND_ACTORS.md`, sections 16-19): TaskSetProfile, WorkPatternProfile and its graph, ActorProfile, RoleProfile, DelegationProfile, ArtifactContract, ConsumerRepresentationProfile, KnowledgeAsset, and KnowledgeExtractionProfile, with View `conditioning` references, EvaluationProfile `evaluatorRef`, and CapabilityContract `outcomeRefs`. Their checks are errors: `work.field`, `work.reference`, `actor.field`, `actor.reference`, `actor.delegation-exceeds-authority`, `artifact.field`, `artifact.reference`, `knowledge.field`, `knowledge.reference`, `view.conditioning-ref`, `evaluation.evaluator-ref`. Open vocabularies (work patterns, artifact types and representations, artifact operations, knowledge roles) stay open: another value is the warning `value.unknown`; closed ones (actor types and kinds, node families, query languages, knowledge representations) are errors. `knowledge.graph-ontology` replaces `experimental.graph-ontology`. Schemas move from `schemas/experimental/` to `schemas/`. ArtifactTemplate (no example yet) and View specialization (pending View composition) stay experimental. The spec gains a document map. Thirteen conformance cases became invalid and six were renamed from `experimental-*`.
- Published ontologies, tested with SKOS, BFO 2020 (ISO/IEC 21838-2 core), and PROV-O wrapped as OntologyPackages under a BFO- and PROV-aligned domain ontology and a World that binds to all of them:
  - New entrypoint format `rdf-xml` for RDF/XML (most `.owl` and `.rdf` files); `owl-xml` now means only the OWL 2 XML serialization, which the RDF tooling does not read.
  - Under resolution, an identifier an `owp-yaml` schema uses from a dependency ontology's namespace must be a term of that ontology (`ontology.dependency-term`; resolution cases `ontology-dependency-term`, `ontology-dependency-term-unknown`).
  - `ontle ontology index` lists only the terms in the ontology's own namespace, without annotation properties (PROV-O: 101 to 80 terms).
  - `ontle kg check` checks the terms of a standard vocabulary (SKOS, PROV, ...) when an OntologyPackage that publishes it is in the closure, and reports a graph it cannot read as `kg.parse` instead of failing.
  - The RDF export keeps a `subClassOf` given as a single identifier, and is OWL 2 DL (spec section 3.1, "RDF meaning"): a property with a datatype range is an `owl:DatatypeProperty` (an `xsd:string` range used to make it an object property), an `enum` type is an `rdfs:Datatype` over its literal values, a property several types declare has their union as its domain (two `rdfs:domain` triples would mean the intersection; `ontle kg check` reads the union), and classes used from other ontologies are declared. Checked with ROBOT/HermiT: the example ontology and a BFO 2020 + PROV + SKOS aligned ontology are in the OWL 2 DL profile and consistent.
  - `ontle ontology index` and `ontle kg check` report a missing or unreadable schema entrypoint instead of failing.
- Assignments (section 17.1): an ActorProfile may declare `assignments` to a local RoleProfile or TaskSetProfile, standing or for a period, or leave them to runtime observations; the author chooses. `ontle inspect --graph` shows them as `assigned_role` and `assigned_task`. Four new cases.
- First-hour usability, from two newcomer walkthroughs:
  - The World starters (`ontle init`, `minimal` and `enterprise`, and `starters/github-world-repo`) compile as generated: the default State Compiler has an observed, an aggregate, and a classified field per item, with sample observations and the EWS they compile to (`examples/observations.yaml`, `examples/expected-ews.yaml`, replacing the placeholder `examples/basic.yaml`). `ontle ews compile` uses the World's default State Compiler when `--compiler` is omitted. New guide `docs/STATE_COMPILATION.md`.
  - `ontle validate` says what it checked. For a package with dependencies it also checks the cross-package rules when every dependency is found (in `--source`, `ONTLE_PATH`, or the World location `ontle init --world` records in `.ontle/project.yaml`), and otherwise prints a `NOTE:` that grounding was not checked. The TypeScript CLI prints the same note. A dependency found with another version is a `WARN:` naming the version found. A `grounding.world-view` error lists the World's Views. `ontle init --template worldmodel --world <dir> --view <path>` grounds the model in another View and the State Compiler that compiles it.
  - Package files no longer include paths that start with `.` (`.env`, `.git`, `.owpignore`), the rule discovery already followed (spec section 7); `ontle pack --list` previews the files an archive would contain without writing it.
  - The reference World Models take any EWS and scenario (`--ews`, `--scenario`), run your own model next to them (`--entrypoint file.py#function`, the signature in WORLDMODEL.md), list what each result `provides`, and score results against a recorded outcome (`--evaluate`; checks in `eval/scenario-outcome.yaml`, an illustrative outcome in `examples/observed-outcome.yaml`). Persistence covers per-subject fields. The output lists the input files used, and Markov says why it predicted nothing.
  - Tests: the two implementations must report exactly the same rule ids on every validation and resolution case (`conformance/reference-ids.json`, regenerated with `scripts/reference_ids.py`; the suite still lets other implementations report more). This found one difference, now aligned: an archive that fails verification also leaves its dependency `resolve.unresolved` in TypeScript, as in Python. CI installs the `rdf` extra on Python 3.14, so RDF export, `kg check`, and SPARQL extraction run in CI. `npm test` checks the TypeScript CLI (`scripts/check-cli.mjs`).
  - `ontle new ModelArtifact` writes the fields and a schema line; `ontle new ObservationSet` explains that it is a runtime document. README routes by goal (World, World Model, runtime).
- Runnable reference World Models (`examples/business/quality-scenario-world-model`) for the quality-hold scenario of the manufacturing World: persistence, three-point (best/base/worst, PERT), seeded Monte Carlo, and a Markov chain (an assumed daily transition matrix updated with observed transitions, run to the scenario horizon) run on a CPU with the standard library; an LLM model (Claude, structured JSON output, optional `llm` extra) is the minimum bar for production models. A ModelArtifact names its code with `spec.entrypoint` (`<path>[#<name>]`, checked as `model.entrypoint`). The quality-hold scenario gives its outcome ranges as `{low, mode, high}`. New case `model-entrypoint-missing`.
- Per-subject EWS fields (spec section 12.3): a State Compiler lists fields in `outputSchema.perSubject`, and those fields hold one value per observation `subject` (state, unresolved, and provenance become mappings keyed by subject; a candidate without a subject is invalid input). Knowledge extraction can set the subject from a result column (`subject`), and a SemanticBinding can map subjects to IRIs (`subjects`), so `ontle ews compile --jsonld` emits per-subject state as individuals. New ids `compiler.per-subject-field`, `ews.per-subject-shape`, `ews.per-subject-overlap`, `binding.subjects`.
- Latent EWS fields (spec section 12.4): `outputSchema.latent` lists fields that are not observed directly, each bound as an `estimate` (observations with `estimatedBy`, optional `uncertainty`; observation bindings ignore them), an `aggregate` (`count`, `distinct_count`, `sum`, `mean`, `min`, `max` over an optional ISO 8601 `window`), or a `classify` (rules over another field, with a `criterion` id, version, and basis). Each latent value has a `spec.derivation` record. New ids `compiler.latent-field`, `ews.derivation`. Seven EWS compile, five EWS check, five validation, and one extraction case.
- WorldViewProfile fields follow `WorldView = Project(World, ViewSpec)`: `purpose` keeps `task`, `objective`, `actorScope`; `projection` gains `scale`, `resolution`, `timeScope`; `conditioning` holds `authorityScope`, `actorRef`, `roleRefs` (was `purpose.roleRef`), and `taskRef` (standard since the promotion above; a bad reference is `view.conditioning-ref`).
- `VerifierPackage` is renamed `VerifierProfile`; `...Package` names are kept for package kinds. Dataset, AgentProfile, EnvironmentProfile, ModelArtifact, SourceSystemSchemaProfile, ObservationAcquisitionProfile, ActionBindingProfile, CommitContract, EffectVerificationProfile, and VerifierProfile get JSON Schemas with the fields in use plus `description` and `standardBindings` (examples move `note` to `description`). WorkPatternProfile and KnowledgeAsset drop the unused `worldRef`.
- New example ontologies `lab-ontology` and `sales-ontology` are the T-boxes of the assay and sales example graphs.
- Review fixes: `.owpignore` treats a `]` first in a class as literal and skips a pattern that does not compile (both implementations), splits lines the same way, and matches non-ASCII names in TypeScript; TypeScript no longer checks listed PackageExample files as Views under resolution; Python reads YAML with tabs or `%YAML` directives with the pure-Python parser, so verdicts do not depend on libyaml (cases `yaml-tab-in-flow`, `yaml-directive`); `ontle kg check` accepts a property declared under several types (a union domain or range; see the later entry for domains stated separately), ignores standard vocabularies such as RDFS, and reads named graphs in N-Quads; Python ignores a View `include` that is not a list and fields without an entity part, as TypeScript does; README and Quickstart drop View `worldRef`.
- World and World View definitions: a World is the target reality and a World package is its persistent representation; a World need not contain actors or tasks. A World View is a projection of a World for a purpose; conditioning on an actor, role, task, objective, or authority is optional, one View may serve several tasks, and a task may require several Views (spec section 6). A View belongs to the World package that contains it, so `WorldViewProfile.spec.worldRef` is removed (it could only be `self`); a WorldViewProfile outside a WorldPackage is the error `view.world-ref`, and `profile.viewable.world-ref` is gone. A View that reads other Worlds lists them in the new field `spec.externalWorldRefs` (each also a dependency) and names their content as `<world ref>#<name>` in `projection.include` (`view.external-world`; under resolution, external Worlds must be WorldPackages and the names should be in their boundary). New cases `view-in-world-model-package`, `view-external-world-undeclared`, `view-external-world-not-dependency`, and resolution case `view-external-world`; the cases `world-view-worldref-foreign`, `world-view-worldref-self`, and `world-viewable-view-without-worldref` are removed.
- Hierarchy checks (warnings; verdicts are unchanged). A View's `projection.include` selects from a declared `spec.world.boundary.included` (`view.outside-world`), and a State Compiler field `<entity>.<property>` names an entity its View includes (`compiler.field-outside-view`); spec section 6. Dependencies point down Ontology ← World ← World Model (`resolve.dependency-direction`, section 11). A graph KnowledgeAsset declares its ontology (`experimental.graph-ontology`), and spec section 3.1 states that the T-box lives in OntologyPackages and the A-box in Worlds. The manufacturing, sales, and mobile-manipulation examples and the enterprise template now keep their Views and compiler fields inside their World boundaries. New cases `view-outside-world`, `compiler-field-outside-view`, `asset-kind-reserved`, and resolution case `dependency-direction`.
- Vocabulary: a third stability, `reserved`, marks kinds that have a name but no schema or rules yet; using one is the warning `asset.kind-reserved`. Thirteen kinds move from `standard` to `reserved` (SourceAdapterProfile, IdentityResolutionProfile, ReferenceEnterpriseProfile, ReferenceIndustryProfile, SkillProfile, ToolProfile, WorkflowProfile, OperationalAsset, ReferenceFixture, NegativeFixture, BenchmarkCase, AcceptanceCase, Attestation). Six kinds that duplicated existing structure are removed: WorldDefinition and WorldModelContract (the manifest's `spec.world` and `spec.worldModel`), ResolutionProfile and AggregationCoarseGrainingProfile (a View's `projection.resolution` and `projection.scale`), MappingSpec (SemanticBinding and SSSOM mapping entrypoints), and Validator (VerifierPackage). The `descriptive` profile now requires `spec.world.definition`; case `world-descriptive-via-world-definition` is removed. SemanticBinding moves to the `semanticWorld` group.
- `ontle kg check` checks a KnowledgeAsset graph (A-box) against the ontology it `conformsTo` (T-box): classes and properties outside the ontology, and relation uses outside their domain or range (`kg.unknown-class`, `kg.unknown-property`, `kg.domain`, `kg.range`; `kg.untyped` for nodes without a type). It is tooling and does not change validation verdicts. `ontle export` now writes `rdfs:subClassOf`, which it dropped before. The dies in the manufacturing example graph are typed `q:Equipment`, the range of `q:hasPart`.
- `.owpignore` at the package root excludes paths from the package with gitignore patterns (spec section 5): excluded files are not discovered and not archived, and a listed `PackageExample` there is `asset.missing-file`. `ontle pack` refuses a package that is invalid without the excluded files. New cases `package-ignore`, `package-ignore-negation`, and `package-ignore-listed-example`.
- The Python reference parses YAML with libyaml when PyYAML has it (same YAML 1.2 core schema, checked against the pure-Python loader on every YAML file in the repository), and the resolver reads each package's assets once. On a 2.5 MB ObservationSet example, `ontle validate` goes from 28 s to 1 s and `ontle validate --resolve` from about 110 s to 7 s.
- Local assets are discovered, not listed: a package YAML file whose `apiVersion` starts with `openworld/` is an OWP document, and its `kind` says which asset it is (spec section 5). `spec.assets` lists only external references and `PackageExample` files; a `path` entry of another kind is `asset.path-or-ref`. A discovered document must declare `kind`, and an unknown kind is `asset.kind`; YAML files without an OWP `apiVersion` are ordinary files, and nested packages are not entered. Asset files must now declare `apiVersion` (it is how they are found). `asset.kind-mismatch` is removed. `ontle new <Kind> <path>` writes a skeleton asset; the per-kind `ontle add` commands and `ontle sync` are removed (`ontle add extension` remains). All examples, templates, conformance fixtures (including the archive and git-bundle sources), and demos move to discovery. New cases `asset-without-api-version`, `asset-local-path-listed`, `asset-unknown-kind`, `asset-missing-kind`, `asset-foreign-yaml`, `asset-nested-package`, and `model-grounding-dotslash-path` (the Python reference now also rejects a non-normal `<asset path>` in grounding references).
- `ontle init --template worldmodel|worldmodel-multimodal --world <World directory or reference>` fills `semanticGrounding` and `spec.dependencies` instead of leaving placeholders; `ontle init` titles the package and its card from the package name. An `outputSchemaRef` that does not resolve no longer also reports every binding as `compiler.binding`, and its message says whether the path form is wrong or the file is missing.
- Second review round: mapping keys must be strings and duplicates are compared as strings, so Python no longer merges `true`/`1` or `1`/`1.0` keys silently (new case `asset-non-string-key`); an `outputSchemaRef` file must be UTF-8 JSON without `NaN`/`Infinity` in both implementations (cases `compiler-output-schema-ref-not-json`, `compiler-output-schema-ref-not-utf8`); ExternalRef `status: null` counts as absent in Python as in TypeScript (case `ref-status-null`); with both `outputSchema.fields` and `outputSchemaRef`, the fields keep their declared order; parse errors in ObservationSets, archives, and extraction profiles are clean CLI errors; packing skips `.DS_Store` and `Thumbs.db`.
- Review fixes: `outputSchemaRef: null` and a null `license` or `terms` in a standard binding count as absent in both implementations (new cases `compiler-output-schema-ref-null`, `standard-binding-license-null`); the TypeScript probes resolve `outputSchemaRef` and run in `npm test`; demo `--check` fails when a committed World Model archive no longer matches the package; the Business AI evidence no longer reports `uncertainty_declared`, which the rule stub cannot fail, and lists it under `checksNotRun`.
- End-to-end demos (`demos/`): World -> View -> State Compiler -> EWS -> adapter -> model stub -> CompatibilityEvidence. The Physical AI demo replays episode 0 of the bound LeRobot dataset with a hold-position stub; the Business AI demo maps sample MES/QMS records through the ISA-95 binding and applies a rule stub. Each writes the last-step EWS and detached evidence bound to a World Model archive; `tests/test_demos.py` and the TypeScript `npm run demos` check them. New optional extra `demo` (pyarrow) for re-extracting the episode.
- Example standard bindings point at real, pinned artifacts: LeRobot episodes `k-chan-l/lekiwi_pick_and_place2` (Hugging Face commit, Apache-2.0), the OpenUSD scene `nvidia/PhysicalAI-SimReady-Warehouse-01` (Hugging Face commit, CC-BY-4.0), and the OPC 40001-1 Machinery 1.04.1 NodeSet with its DI 1.04.0 and IA 1.01.2 models (digest-pinned raw files at UA-Nodeset release commits, MIT).
- Standard bindings (spec section 5.3): `spec.standardBindings` in any local asset maps binding names to `{standard, ref, license, terms}`. A bound `ref` must be pinned (`standard.unpinned`) and licensed (`standard.license`); malformed bindings are `standard.binding`. The examples move to this shape (ROS 2 and ISA-95 names under `terms`). New cases `standard-binding-valid`, `standard-binding-unpinned`, `standard-binding-unlicensed`, `standard-binding-shape`.
- Valid resolution cases list `resolved`: every package of the closure except the root with its recorded revision (`sha256:<archive digest>`, `git:<commit>`, or `null` for directory sources). Both implementations compare them; spec section 11 states which revision is recorded.
- `outputSchemaRef` is resolved (spec section 12.1): it names a package-relative JSON Schema whose top-level `properties` keys are the compiler's EWS fields. Field placement, bindings, semantic bindings, EWS compilation, and `model-ready` use these fields like `outputSchema.fields`; when both are declared they must list the same fields. New errors `compiler.output-schema-ref` and `compiler.output-schema-mismatch`. The alpha-limitation case `schema-ref-only-compiler` is replaced by `schema-ref-valid` and `schema-ref-field-unknown`; new cases `compiler-output-schema-ref-missing-file`, `compiler-output-schema-ref-no-properties`, `compiler-output-schema-mismatch`, and the EWS compile case `schema-ref-fields`.
- OWP YAML documents follow the YAML 1.2 core schema (spec section 5.2), not only ObservationSet and EWS documents: the reference implementation no longer reads `yes`, `on`, `1:20`, or dates in `owp.yaml` and assets as YAML 1.1 types, and duplicate mapping keys are `manifest.load` or `asset.yaml` errors. Generated YAML quotes strings that YAML 1.1 or 1.2 would read as another type. New cases `manifest-yaml-core-scalars`, `manifest-duplicate-key`, `asset-duplicate-key`.
- The TypeScript implementation builds with TypeScript 7 and requires Node.js 24 or later; CI runs it on Node.js 24 and 26. GitHub Actions are on their current majors.
- The spec is split: `spec/OWP_SPEC.md` keeps the core (sections 1–8, 10, 11, 13, Appendices A, B); `OWP_SEMANTICS.md` (3.1, 14), `OWP_EVALUATION_AND_STATE.md` (9, 12, 15), and `OWP_EXPERIMENTAL.md` (Appendix C) hold the profiles. Section numbers are unchanged. `docs/REFERENCES.md` lists the six reference forms and where each is used.
- Asset files may omit `apiVersion` (inherited from `owp.yaml`); a different value is `asset.api-version`. Generated assets omit it.
- `ontle validate` prints errors that are likely consequences of a misspelt field under that field's error.
- Promote experimental fields used in three domains that do not depend on experimental kinds (spec section 15): EvaluationProfile `assessmentKind`, `subject`, `objective`, `criteria`, `verifierRef`, `evidenceRefs`, `validityScope`, `resultSchemaRef`; all ScenarioProfile fields; CapabilityContract `context`, `requiredInputs`, `capacity`, `maturity`, `validityScope`, `evidenceRefs`; WorldViewProfile `constraints`, `evidenceRefs`. Their checks are errors (`evaluation.*`, `scenario.*`); the value sets `assessmentKinds`, `evaluationSubjects`, `scenarioEngines` are standard.
- `asset.kind-experimental` is reported once per kind with a count.
- Generated files carry a `yaml-language-server` schema line and a one-line hint; placeholders are empty strings, so editors validate and complete them. `owp.yaml` keeps its leading comments when the CLI rewrites it.
- `ontle sync` lists asset files that `spec.assets` is missing; `ontle inspect` reports the experimental kinds and fields a package uses.
- Every experimental profile is used in at least three example domains (manufacturing, sales, research, robotics); see `docs/PROFILE_PROMOTION.md`.
- Round-trip checks: `tests/test_roundtrip.py` (pack/unpack and YAML re-serialization) and the TypeScript `scripts/check-roundtrip.mjs`.
- `schema.unknown-field` messages suggest the closest defined field. `docs/QUICKSTART.md` covers ontology binding, actors and tasks, extensions, and publishing.
- Add `docs/GLOSSARY.md` (actor, role, capability, permission, authority, responsibility, accountability, artifact type/representation/format/storage, verification/validation/evaluation/review/approval, scenario) and `docs/PROFILE_PROMOTION.md` (gates and status for experimental profiles).
- `ontle add actor|role|delegation|capability`; `ontle inspect --graph` shows actor, role, delegation, view, task, evaluation, and scenario relations.
- Examples: `research/assay-optimization-world` (third domain); `manufacturing-quality-world` and `sales-prioritization-world` gain actors, roles, delegations, capabilities, a work pattern graph, an evaluation, and a scenario.
- WorldViewProfile, EvaluationProfile, ScenarioProfile, and CapabilityContract have JSON Schemas; undefined keys are errors. Experimental fields (spec Appendix C.4): World View `purpose.actorRef`/`roleRef`/`taskRef`, `constraints`, `evidenceRefs`; Evaluation `assessmentKind` (verification, validation, evaluation, review, approval), `subject`, `objective`, `criteria`, `verifierRef`, `evaluatorRef`, `evidenceRefs`, `validityScope`, `resultSchemaRef`; Scenario `baselineStateRef`, `assumptions`, `intervention`, `engine` (value set `scenarioEngines`), `timeHorizon`, `constraints`, `uncertainty`, `confidence`, `expectedOutcome`; Capability `outcomeRefs`, `context`, `requiredInputs`, `capacity`, `maturity`, `validityScope`.
- TaskSetProfile composes actors (`requires.actors`), work patterns (`workPatternRefs`), and `mayUse.scenarios`/`skills`/`tools`.
- Experimental actors, roles, and delegation (spec Appendix C.3): `ActorProfile` (`actorType` from the value set `actorTypes`), `RoleProfile` (permissions, authorities with ceilings, responsibilities, accountabilities), and `DelegationProfile` (scope, period, revocation, escalation; the warning `experimental.delegation-exceeds-authority`). ConsumerRepresentationProfile gains `actor.ref`.
- Experimental work pattern graphs (spec Appendix C.2): nodes, transitions, guards, events, and loops; node families in the value set `workNodeFamilies`; each of the 22 work patterns names its family. WorkPatternProfile gains `objective`, `inputContracts`, `outputContracts`, `worldViewRef`, `governanceRefs`.
- ArtifactContract gains `schemaRef`, `storage`, `allowedOperations` (value set `artifactOperations`), `sourceRefs`, `evidenceRefs`, and `supersedes`.
- `scripts/generate_experimental_schemas.py` regenerates `schemas/experimental/`; `scripts/sync_rule_ids.py` regenerates `spec/rule-ids.yaml`.
- Lock format `owp-lock/v1alpha2` (spec section 7): `externals` records every bound ExternalRef; vendored content is listed with `vendoredPath`; verifiers check `externals` against the manifest.
- OCI artifact profile (spec section 7.1): artifact, config, layer, and evidence media types. `ontle push` (and `oci:`/`oci-layout:` resolver sources) use `oras`.
- Static package index (spec section 11.1, `schemas/package-index.schema.json`): `ontle index build` and the `index:` resolver source, with digest checks.
- Evidence published outside the package (spec section 9.1): `spec.subjectDigest`; `ontle evidence check` and `ontle evidence attach` (OCI referrer).
- `ontle fetch` (download and verify external content, including file lists), `ontle lock` (pin https references), `ontle pack --vendor`, `ontle sign` and `ontle verify --signature` (cosign; keyless by default, `--key` for key pairs), and `ontle catalog --format dcat|croissant|hf-card`.
- Add `schemas/owp-lock.schema.json`.
- Add knowledge extraction (spec Appendix C.1, experimental): a `KnowledgeExtractionProfile` maps query result rows over a KnowledgeAsset to an ObservationSet with a deterministic transform (ids from columns, snapshot-time default, repeated join rows collapse). EWS is unchanged. ObservationSet gains an optional `spec.provenance` (`extraction`, `parameters`, `snapshot`). Reading a `multi` type with `select: latest` is the warning `compiler.multi-latest`.
- Add `ontle kg extract` (runs SPARQL over a local RDF KnowledgeAsset with the `rdf` extra, or transforms a `--results` file) and repeatable `--observations` for `ontle ews compile`.
- Conformance: new `extractionCases` section (12 cases) and 2 validation cases.
- Example: `manufacturing-quality-world` adds a small plant knowledge graph and a `claim-context` extraction; the State Compiler and binding cover 9 fields.
- Add semantic binding (spec section 14): a `SemanticBinding` asset maps World names, EWS fields (`{class, path}`), observation types, and actions to CURIEs; a World names it with `spec.world.semanticBinding`. Prefixes come from dependency OntologyPackages; under resolution every CURIE must expand to a term they define, and conflicting prefixes are errors. Unscoped terms are a warning.
- `ontle inspect` reports `semanticCoverage`; `ontle ews compile --jsonld` prints the EWS with a JSON-LD `@context` from the binding.
- The `manufacturing-quality-world` example depends on `quality-ontology` and binds all seven EWS fields.
- Define the ontology contract (spec section 3.1): `spec.ontology` with `iri`, `prefixes`, typed `entrypoints` (`format`, `role`), `termIndex`, and pinned `externalImports`; ontology conformance profiles `vocabulary`, `schema`, `constrained`, `mapped`. Validation reads only the manifest, OWP YAML documents, and file existence; RDF content is not parsed for validity.
- Add `SemanticProfile` and `OntologyTermIndex` schemas; `OntologyTermIndex` joins the vocabulary.
- Add `ontle ontology index` (term index from schema entrypoints; RDF needs the optional `rdf` extra), `ontle export --format turtle|jsonld`, and term-index generation in `ontle pack` when it is required and missing.
- `spec.ontology` follows the new contract (the old `formats` key is rejected); the ontology template uses it. `spec.conformance` is allowed on OntologyPackages.
- Add the `examples/ontology/quality-ontology` example (owp-yaml schema, SHACL shapes, SSSOM mappings; profile `mapped`).
- Add experimental asset kinds (spec Appendix C): `TaskSetProfile`, `WorkPatternProfile`, `ArtifactContract`, `ArtifactTemplate`, `ConsumerRepresentationProfile` (one block per actor kind: `human`, `agent`, `model`, `system`), and `KnowledgeAsset`. They are checked against `schemas/experimental/` with warnings only (`experimental.field`, `experimental.value`, `experimental.reference`); extension rules stay errors.
- Add experimental value sets in `vocab/value-sets.yaml`, including 22 work patterns.
- Add experimental World View specialization: `spec.specializes` and `spec.projection.exclude`; `ontle inspect --resolved-views` shows resolved Views.
- Add `ontle inspect --graph` (reference graph with informative relation names) and `ontle add task|pattern|artifact|template|consumer|knowledge` and `ontle add view --specializes`.
- Conformance cases may list `warnings` that an implementation must report.
- Add the `sales-prioritization-world` example (actor-specialized Views, tasks, artifacts, consumers, sample observations and EWS); extend `manufacturing-quality-world` with an RCA task, knowledge, report contract, and consumer.
- Add publisher extensions (spec section 13): an extension is a `spec.dependencies` entry with `as` (and optional `mustUnderstand`); extension kinds are `<extension>:<Kind>`; extension data goes in `extensions` blocks; a package that defines an extension declares `spec.extensionDefinition`. Undeclared extension names are errors.
- Defined fields are enforced: the manifest, CompatibilityEvidence, ObservationSet, and EWS documents reject keys that are neither defined fields nor `extensions` blocks (`schema.unknown-field`). The manifest JSON Schema now lists every field already in use (`dependencies`, `worldModel.description`, `world.boundary`, `domains`, and others); all four JSON Schemas are closed.
- The conformance case `asset-namespaced-kind` is replaced by `extension-kind-declared` and `extension-kind-undeclared`.
- Restructure `vocab/asset-kinds.yaml`: camelCase groups aligned with the asset-graph families (Attestation moves to `governancePublication`) and a `stability` per kind; experimental kinds produce the warning `asset.kind-experimental`. The reference implementation reads this file instead of a copied list.
- Add `spec/rule-ids.yaml`, a machine-readable registry of every error and warning id; warnings now have ids (spec Appendix A). Tests check that the spec, the conformance suite, and both implementations use exactly the registered ids.
- Add `ontle add extension <ref> [--as <name>] [--must-understand]`; `ontle inspect` lists declared extensions.
- Add spec Appendix B (notation).
- Define ExternalRef (spec section 5.1): `provider`, `uri`, `revision`, `digest`, `mediaType`, `size`, `status` (`bound`/`unbound`); provider-specific pinning with the warning `ref.unpinned`; several files pinned through a file list in the `owp.lock.json` `files` format. The manifest's `spec.assets[].ref` is validated; examples and templates use `ref: {status: unbound}` instead of `ref: null`.
- Example: the multimodal World Model's evidence note moves from `spec.note` to `metadata.description`.
- Replace the unconditional WorldPackage View/State Compiler requirement with cumulative conformance profiles (`descriptive`, `viewable`, `stateful`, `model-ready`, `action-ready`); absent means `descriptive`. Starter templates declare `stateful`.
- `model-ready` requires a concrete EWS schema (`outputSchema.fields` or `outputSchemaRef`) on every State Compiler.
- WorldModel grounding references must have the form `<worldRef>#<asset path>`.
- Add evaluation lineage and evidence binding: versioned `EvaluationProfile`/`VerifierPackage`, `supersedes`, and pinned `CompatibilityEvidence` scoped to compatible Views/State Compilers. No new package kind.
- Add `conformance/` language-neutral suite and `schemas/compatibility-evidence.schema.json`; make the manifest schema profile-conditional.
- Add `ontle add verifier`; `ontle add compiler` generates a skeleton bound to the default View; `ontle inspect` reports declared vs satisfied profile.
- Examples: declare `action-ready`, add EWS output schemas, OpenUSD/ROS 2/LeRobot and ISA-95/OPC UA `standardBindings`, and an evaluation lineage example.
- Add `docs/STANDARDS_INTEROP.md`.
- Add `implementations/typescript/`, an independent clean-room TypeScript implementation (validator, resolver, EWS compiler/checker) that passes the full conformance suite; CI runs it.
- Add dependency resolution without a hosted registry: directory, `.owp.zip` (hash-verified), and `git+<url>@<rev>` sources; `ontle resolve` and `ontle validate --resolve` with cross-package World Model grounding checks.
- Standardize the Effective World State document and its output contract; add optional declarative State Compiler bindings (`latest`, `all`) with deterministic semantics; `ontle ews compile|check`.
- Extend `conformance/` with resolution, EWS compile, and EWS check cases.
- Add stable rule ids (spec Appendix A) to every validation, resolution, and EWS error; the conformance suite lists the rule ids each invalid case must report.
- Second review round: define the exact `owp.lock.json` format and archive layout (archives with unlocked files are rejected); timestamps are read and compared as text and must be valid calendar instants (the reference loader no longer converts unquoted YAML timestamps); JSON-data-model value equality in EWS compilation; code-point id ordering; opaque compilers are refused; dependency entries, `worldRef`, identity characters, `./` paths, and duplicate evaluation asset names are validated; hidden directories are skipped by directory sources.
- Conformance suite: 190 validation, 27 resolution (including packed `.owp.zip` and `git bundle` fixtures), 21 EWS compile, 17 EWS check, 12 extraction cases; every invalid case lists its expected rule ids.
- `PackageExample` YAML must parse (its kind is not compared); an unreadable or unverifiable package source is an error, not a fallback; git sources accept local repository and `git bundle` paths.
- Add `ROADMAP.md`.
- Require Python 3.11+ (3.10 reaches end of life in October 2026); CI tests 3.11–3.14, and release builds use 3.14.
- Tighten the spec after an independent clean-room implementation review: a default View's `worldRef` is `self` or the package identity; evidence `subject` is the package identity; local version binding is by `metadata.name` and requires a matching `metadata.version`; exact-string reference comparison; explicit legacy manifest names, typed-YAML asset rules, open asset-kind vocabulary, and error/warning severity.
- Examples: declarative bindings, sample ObservationSets, and expected EWS for both reference Worlds.

## 0.2.0-alpha.2 — World View / EWS Contract Alignment

- Require every `WorldPackage` to package at least one `WorldViewProfile` and one `StateCompilerProfile`.
- Add generated default View/State Compiler assets to minimal, enterprise, and standalone GitHub World starters.
- Require every `WorldModelPackage` to declare `worldRef`, `compatibleWorldViews`, and `compatibleStateCompilers`.
- Require `EffectiveWorldState` as the logical WorldModel input contract and an explicit `RepresentationAdapterProfile` binding.
- Add `ontle add view` and `ontle add compiler` progressive scaffolding.
- Align Business AI and Physical AI examples to the same World -> View -> State Compiler -> EWS -> Adapter -> WorldModel chain.
- Strengthen validation and JSON Schema coverage for the above invariants.

## 0.2.0-alpha.1 — Public Alpha Candidate

- Establish `owp.yaml` as the single public package manifest.
- Establish `ontle` as the reference CLI.
- Add minimal and enterprise World starters, an ontology starter, and generic/multimodal World Model starters.
- Add Business AI and Physical AI reference examples.
- Add deterministic `.owp.zip` reference packing with SHA-256 lock verification.
- Add progressive asset scaffolding.
- Add GitHub CI/release workflows and standalone World repository starter.
- Add public asset-graph, runtime-boundary, and multimodal World Model documentation.
