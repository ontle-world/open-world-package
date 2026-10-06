# OWP — Ontologies and semantic binding

Part of the Open World Package specification; section numbers are shared across its documents (see the document map in `OWP_SPEC.md`). Read this when a package publishes an ontology or binds its names to ontology terms.

## 3.1 Ontology contract

```yaml
spec:
  ontology:
    description: ONTOLOGY.md
    iri: https://w3id.org/acme/quality#              # namespace IRI of the ontology
    prefixes:
      q: https://w3id.org/acme/quality#
    entrypoints:
    - {path: semantics/core.yaml, format: owp-yaml, role: schema}
    - {path: semantics/shapes.ttl, format: turtle, role: shapes}
    - {path: mappings/isa95.sssom.tsv, format: sssom-tsv, role: mappings}
    termIndex: semantics/terms.yaml                  # required when no schema entrypoint is owp-yaml
    externalImports:                                 # ontologies outside OWP, pinned (section 5.1)
    - iri: http://qudt.org/schema/qudt/
      ref: {provider: https, uri: https://qudt.org/2.1/schema/qudt, digest: "sha256:..."}
  conformance:
    profile: mapped
```

- Ontology packages this ontology builds on are listed in `spec.dependencies`; there is no separate import list. Under resolution (section 11), an identifier an `owp-yaml` schema uses (a `subClassOf`, `domain`, or `range`) that falls in the `iri` namespace of a dependency OntologyPackage MUST be a term that package defines (`ontology.dependency-term`).
- `iri` and every `prefixes` value are absolute IRIs; prefix names match `[A-Za-z][A-Za-z0-9_-]*`.
- Each entrypoint has a package-relative `path` naming an existing file inside the package, a `format` (`owp-yaml`, `turtle`, `jsonld`, `rdf-xml` (RDF/XML, as most `.owl` and `.rdf` files are), `owl-xml` (the OWL 2 XML serialization), `ntriples`, `linkml`, `sssom-tsv`), and a `role` (`schema`, `shapes`, `mappings`, `labels`).
- An `owp-yaml` entrypoint is a `SemanticProfile` document (`schemas/semantic-profile.schema.json`): `types` (each with `id`, optional `label`, `subClassOf`, `enum`, and `properties` with `id` and `range`) and `relations` (`id`, `domain`, `range`). Identifiers are CURIEs whose prefixes are declared in `prefixes`, or absolute IRIs.
- `termIndex` names an `OntologyTermIndex` document inside the package (`schemas/ontology-term-index.schema.json`) listing term IRIs with a type (`class`, `property`, `individual`, `datatype`, `concept`). The reference CLI writes it with `ontle ontology index`, and `ontle pack` writes it when it is required and missing and the optional RDF tooling is installed.
- Validation reads only the manifest, OWP YAML documents, and file existence. RDF, LinkML, and SSSOM content is not parsed for validity, so every implementation reaches the same verdict. Tooling may check that content and report it separately.

**T-box and A-box.** An OntologyPackage holds the T-box: classes, properties, relations, and the constraints on them. Facts about individual things (this lot, that machine) are an A-box and belong in a World package, as a graph KnowledgeAsset that names its OntologyPackage in `spec.conformsTo.ontology` (section 19.1), or as observations. A term index MAY list `individual` terms only for fixed members of the vocabulary itself, such as enumeration values.

**RDF meaning of owp-yaml (informative).** Tooling that exports an `owp-yaml` schema as RDF (`ontle export`) produces OWL 2 DL:

| owp-yaml | OWL 2 / RDFS |
|---|---|
| type | `owl:Class`; `subClassOf` (one identifier or a list) gives `rdfs:subClassOf` |
| type with `enum` | `rdfs:Datatype` equivalent to `owl:oneOf` over the literal values (the values stay strings, as in EWS) |
| property with a datatype range (`xsd:`, `rdf:langString`, `rdfs:Literal`, an enum type) or no range | `owl:DatatypeProperty` |
| property with a class range, and every relation | `owl:ObjectProperty` |
| a property declared under several types | `rdfs:domain` is their `owl:unionOf` (two plain `rdfs:domain` triples would mean the intersection) |
| a class used from another ontology | declared `owl:Class` |

The terms an ontology defines are the expanded identifiers of its `owp-yaml` schema entrypoints (types, their properties, and relations) together with the terms in its `termIndex`.

**Ontology conformance profiles.** An OntologyPackage MAY declare `spec.conformance`; when present, its `profile` MUST be one of the profiles below. Profiles are cumulative; when `spec.conformance` is absent, no profile is required, and a validator SHOULD still report the highest satisfied profile.

| Profile | Adds |
|---|---|
| `vocabulary` | `iri` and at least one entrypoint |
| `schema` | an entrypoint with role `schema`; if none of them is `owp-yaml`, a `termIndex` |
| `constrained` | an entrypoint with role `shapes` (for example SHACL) |
| `mapped` | an entrypoint with role `mappings` (for example SSSOM) |


## 14. Semantic binding

A SemanticBinding connects the names a World uses to terms of the ontologies it depends on, so two packages can be compared by meaning rather than by spelling.

```yaml
kind: SemanticBinding
metadata:
  name: quality-terms
spec:
  terms:                                   # World name -> class
    claim: q:Claim
    lot: q:Lot
  fields:                                  # EWS field -> class and property path
    claim.status: {class: q:Claim, path: [q:claimStatus]}
    lot.genealogy: {class: q:Lot, path: [q:derivedFrom]}
    line.temp: {class: q:Line, path: [q:temperature], unit: unit:DEG_C}   # unit: optional, e.g. a QUDT unit
    claim.reason:                          # coded values tied to concepts (optional)
      class: q:Claim
      path: [q:claimReason]
      values: {scheme: q:ClaimReasons, base: "https://w3id.org/acme/claim-reason/", map: {"on hold": q:OnHold}}
    line.vendor: {class: q:Line, path: [q:manufacturerName]}
  semanticIds:                             # external dictionary identifiers (optional)
    fields:
      line.vendor: ["0173-1#02-AAO677#002"]  # ECLASS: manufacturer name
  observationTypes:                        # observation type -> class
    QMS.claim: q:Claim
  actions:                                 # action name -> term
    propose-capa: q:ProposeCapa
  subjects:                                # observation type -> how its subjects become IRIs (section 12.3)
    QMS.claim: {base: "https://w3id.org/acme/plant#claim-"}
```

A WorldPackage names its binding with `spec.world.semanticBinding`, the path of a local `SemanticBinding` asset. The binding declares no prefixes: they come from the OntologyPackages in `spec.dependencies` (section 3.1).

Single-package rules:

- `spec.world.semanticBinding`, when present, is a local SemanticBinding asset.
- Every value in `terms`, `observationTypes`, and `actions`, and every `class`, `path`, and `unit` entry in `fields`, is a CURIE `<prefix>:<local name>`. A field's `unit` names its unit as an ontology term (for example from QUDT, whose units carry their UCUM codes as `qudt:ucumCode`); the State Compiler's UCUM code (section 12.5) is what compilation checks.
- Every key of `fields` is an EWS field (section 12.1) of some local State Compiler.
- Every key of `subjects` is listed in `observationTypes`, and its value is `{base: <absolute IRI prefix>}` (the subject is appended) or `{iri: true}` (the subject already is an IRI) (`binding.subjects`). With `base`, the subject is percent-encoded first: every UTF-8 byte except `A-Z a-z 0-9 - . _ ~` is written as `%XX` (RFC 3986 unreserved characters only), so a key such as `line 1` gives `<base>line%201`; with `iri: true`, tooling refuses a subject that is not an absolute IRI. With it, a per-subject EWS field becomes statements about individuals: the reference CLI's `ontle ews compile --jsonld` adds an `@graph` with one node per subject, typed with the observation type's class, and `ontle kg check` can compare those individuals with a knowledge graph.
- A field MAY tie its coded values to concepts with `values`: `scheme` (the concept scheme, a CURIE), `base` (an absolute IRI prefix; a code made only of `A-Z a-z 0-9 . _ ~ -` is appended to it), and `map` (code to concept CURIE, which wins over `base`). A numeric code with an integer value is looked up by its decimal text (`map: {"3": q:Severe}` covers the values `3` and `3.0`, which EWS equality treats as one), and each element of a list value is mapped. At least one of `base` and `map` is present (`binding.values`). The EWS keeps the codes; tooling that writes RDF or JSON-LD gives a value's concept IRI instead, and refuses a value it cannot map. The concept model is the ontology's choice (SKOS concepts, OWL individuals, classes); OWP only maps codes to IRIs.
- `semanticIds` MAY attach external dictionary identifiers to bound names, for example the ECLASS or IEC CDD identifier an Asset Administration Shell uses as a semanticId. Its sections are `terms`, `fields`, `observationTypes`, and `actions`; each key MUST be bound in the same section, and each value is a non-empty list of identifiers, each an IRDI in canonical `#` form (ISO 29002-5, such as `0173-1#02-AAO677#002`) or an absolute IRI (`binding.semantic-ids`). They are references only: they are not expanded with prefixes, need not be terms of a dependency, and do not change the meaning the CURIE binding gives. Dictionaries such as ECLASS are licensed: a package may cite their identifiers but MUST NOT copy their names, definitions, or value lists unless its publisher's license allows it.
- A `terms` key that is neither in `spec.world.boundary.included` nor in the resolved `projection.include` of a local World View is a warning. When neither list exists, the check is skipped.
- SemanticBinding documents contain only the fields of `schemas/semantic-binding.schema.json` and `extensions` blocks.

Cross-package rules (section 11), for every package in the closure that has SemanticBinding assets:

- The prefixes of all dependency OntologyPackages are merged. Two ontologies that declare the same prefix with different IRIs are an error.
- Every CURIE expands with a merged prefix, and the expanded IRI is a term of one of those ontologies (section 3.1).
- Warnings from the `owp-yaml` schema entrypoints of those ontologies (types, their `properties` and `subClassOf`, `relations` with `domain`, ranges, and enum types). A property is declared on a class when it is listed under that type, or a relation's `domain` names it.
  - `binding.path-domain`: a field's `path[0]` is a property the schemas declare, but not on its `class` or a class it is a `subClassOf` (transitively). Each later step is judged the same way against the range of the previous step, when that range is a class of the schemas.
  - `binding.value-range`: the last step's range is an enum type and the field's `values.map` has a code that is not a value of that enum.
  - A term the schemas do not declare (one from an RDF entrypoint or only in a term index) is not judged, and the steps after it are not either.
  - These are warnings, not errors. In RDFS a domain is not a constraint: using a property on another class only infers more types. A mismatch is usually a mistake, but it is not a contradiction.

The reference CLI reports `semanticCoverage` (bound fields out of compiler fields) in `ontle inspect`, and `ontle ews compile --jsonld` prints an EWS document with a JSON-LD `@context` built from the binding. Neither changes the EWS document.
