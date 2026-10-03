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
- Every value in `terms`, `observationTypes`, and `actions`, and every `class` and `path` entry in `fields`, is a CURIE `<prefix>:<local name>`.
- Every key of `fields` is an EWS field (section 12.1) of some local State Compiler.
- Every key of `subjects` is listed in `observationTypes`, and its value is `{base: <absolute IRI prefix>}` (the subject is appended) or `{iri: true}` (the subject already is an IRI) (`binding.subjects`). With it, a per-subject EWS field becomes statements about individuals: the reference CLI's `ontle ews compile --jsonld` adds an `@graph` with one node per subject, typed with the observation type's class, and `ontle kg check` can compare those individuals with a knowledge graph.
- A `terms` key that is neither in `spec.world.boundary.included` nor in the resolved `projection.include` of a local World View is a warning. When neither list exists, the check is skipped.
- SemanticBinding documents contain only the fields of `schemas/semantic-binding.schema.json` and `extensions` blocks.

Cross-package rules (section 11), for every package in the closure that has SemanticBinding assets:

- The prefixes of all dependency OntologyPackages are merged. Two ontologies that declare the same prefix with different IRIs are an error.
- Every CURIE expands with a merged prefix, and the expanded IRI is a term of one of those ontologies (section 3.1).

The reference CLI reports `semanticCoverage` (bound fields out of compiler fields) in `ontle inspect`, and `ontle ews compile --jsonld` prints an EWS document with a JSON-LD `@context` built from the binding. Neither changes the EWS document.
