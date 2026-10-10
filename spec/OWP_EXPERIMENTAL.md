# OWP — Experimental profiles (informative)

Part of the Open World Package specification; section numbers are shared across its documents (see the document map in `OWP_SPEC.md`). Everything here may change or be removed; checks produce warnings only.

## Appendix C. Experimental asset kinds and fields (informative)

The work, actor, artifact, and knowledge kinds that were here are standard since this alpha (sections 16-19). What remains experimental is below. A validator reports `asset.kind-experimental` for each use of an experimental kind and checks it against `schemas/experimental/` with warnings only (`experimental.field`, `experimental.value`, `experimental.reference`). Extension rules (section 13) still apply and remain errors.

| Kind | Purpose | Main fields |
|---|---|---|
| `ArtifactTemplate` | template for an artifact contract | `artifactContractRef` (ArtifactContract), `format`, `content` (`path` or ExternalRef) |

ArtifactTemplate stays experimental until it is used in example packages of three domains (`docs/PROFILE_PROMOTION.md`).

**World View specialization.** A WorldViewProfile MAY declare the experimental fields `spec.specializes` (the local path of another WorldViewProfile) and `spec.projection.exclude`. The resolved View is the base View's resolved spec with: `projection.include` = base include ∪ include − exclude; `purpose` and `conditioning` overridden key by key; other fields replaced. `specializes` naming anything other than a local WorldViewProfile, or a cycle, is `experimental.reference`. State Compilers keep binding to the specialized View's own path. The reference CLI shows resolved Views with `ontle inspect --resolved-views`.

**World View composition.** A WorldViewProfile MAY declare the experimental field `spec.composes`, a non-empty list of local WorldViewProfile paths. The resolved View has: `projection.include` = the union of the composed Views' resolved includes, in list order, ∪ its own include − its own exclude; `conditioning` and the other `projection` keys taken from the composed Views (the first View that sets a key wins), then overridden key by key by its own; `purpose` and the other fields its own. Composition is the union; filtering is `projection.exclude`, and overriding is `specializes`. Warnings: an entry that is not a local WorldViewProfile, or a cycle through `composes` and `specializes`, is `experimental.reference`; `composes` that is not a non-empty list of strings, a composed View without its own non-empty `purpose`, `composes` and `specializes` in the same View (it then resolves by `specializes`), and composed Views that disagree on a `conditioning` or `projection` key the View does not set itself, are `experimental.field`.

**Reference graph.** `ontle inspect --graph` lists the package, its assets, and the references between them with informative relation names (`contains`, `depends_on`, `uses_extension`, `grounded_in`, `valid_for_view`, `valid_for_compiler`, `uses_adapter`, `compiles_view`, `specializes`, `composes`, `uses_pattern`, `requires_view`, `requires_knowledge`, `produces_artifact`, `evaluated_by`, `template_for`, `represents_view`, `consumes_contract`, `conforms_to`, `evidences`, `for_actor`, `for_role`, `for_task`, `occupies_role`, `assigned_role`, `assigned_task`, `has_capability`, `implemented_by`, `member_of`, `delegated_by`, `delegated_to`, `produces_contract`, `evaluates`, `evaluated_by_actor`, `baseline`, `uses_engine`, `performed_by`, `may_use_scenario`). These names are not part of the package contract.

### C.1 Experimental fields of standard kinds

| Kind | Experimental fields | Checks (warnings) |
|---|---|---|
| `WorldViewProfile` | `specializes`, `projection.exclude` (View specialization, above); `composes` (View composition, above) | `specializes` and `composes` name local WorldViewProfiles, without cycles |
| `SemanticProfile` (`types[]`, `types[].properties[]`, `relations[]`), `OntologyTermIndex` (`terms[]`) | `status`, `replacedBy` (term lifecycle, below) | see below |
| `SemanticProfile`, `OntologyTermIndex` | `removed` (term lifecycle, below) | see below |
| `KnowledgeExtractionProfile` | `query.terms` (query terms, below) | see below |

View specialization stays experimental while View composition is open: a View built from several Views (union, filter, overlay) may replace or generalize it.

**Term lifecycle.** A term an ontology defines MAY declare `status`: `candidate` (published to be tried on real data, not yet stable), `stable` (the default when absent), or `deprecated` (still defined, not to be used in new data or schemas). A deprecated term MAY name the terms that replace it in `replacedBy`, an identifier or a non-empty list of them: CURIEs or absolute IRIs in an owp-yaml schema, absolute IRIs in a term index. A term marked in several places takes the strongest mark: deprecated, then candidate. The checks are warnings:

- a `status` outside the three values is `experimental.value`;
- a malformed `replacedBy`, a `replacedBy` on a term that is not deprecated, or one whose identifier does not expand is `experimental.field`;
- a `replacedBy` in the ontology's own `iri` namespace that the ontology does not define, or, under resolution, in the namespace of a dependency OntologyPackage that does not define it, is `experimental.reference`;
- under resolution, an owp-yaml schema of an OntologyPackage, a SemanticBinding (section 14), or the `query.terms` of a KnowledgeExtractionProfile that uses a term a dependency OntologyPackage deprecates or has removed is `experimental.reference`, with the replacements in the message.

**Removed terms.** A term an ontology no longer defines is removed (a major change, section 3.1); a removed term MAY be kept as a tombstone in `spec.removed`, a list in an owp-yaml schema (entries `{id, replacedBy, removedIn}`, `id` a CURIE or absolute IRI) or in the term index (entries `{iri, replacedBy, removedIn}`, absolute IRIs). `removedIn` is the version that removed it. A tombstone does not define the term: a use of it is still the error it was (for example `grounding.ontology-term`), and the warning above adds the replacements. Tombstones are kept in later versions, as OBO ontologies keep obsolete terms. A `removed` that is not a list, an entry without a valid `id` or `iri`, a tombstone for a term the ontology still defines, or a `removedIn` that is not a string is `experimental.field`; `replacedBy` is checked as above. `ontle ontology index` copies the owp-yaml tombstones into the term index and keeps those already there.

In RDF (`ontle export`, `ontle ontology index`), `deprecated` is `owl:deprecated true` with `dcterms:isReplacedBy` for each replacement, and `candidate` is `vs:term_status "testing"` (the W3C vocabulary status vocabulary); a term index built from RDF also reads `vs:term_status "unstable"` as candidate and `"archaic"` as deprecated. `ontle kg check` reports a graph's use of a candidate or deprecated term as the advice `kg.candidate` or `kg.deprecated`, and names the tombstone's replacements when a graph uses a removed term (section 19.1); `ontle diff` grades a change of status minor, marks added candidate terms, names the replacements of a removed term, and notes a removed term without a tombstone (section 3.1).

**Query terms.** A KnowledgeExtractionProfile MAY list the ontology terms its query uses in `spec.query.terms`: CURIEs, expanded with the prefixes of the package's dependency OntologyPackages, or absolute IRIs. Validation does not parse the query; the list lets the checks above reach a query, so that a term deprecated or removed from under it is reported and does not just make the query return nothing. A `query.terms` that is not a non-empty list of CURIEs or absolute IRIs is `experimental.field`; under resolution, a term whose prefix no dependency OntologyPackage declares, or one in a dependency's `iri` namespace that the dependency neither defines nor lists as removed, is `experimental.reference`. `ontle kg check` parses SPARQL queries and checks the terms they name (section 19.1).

Term lifecycle and query terms are promoted by the gates of `docs/PROFILE_PROMOTION.md`. The field names stay; the warnings become errors under `ontology.*` rule ids where a promoted rule says MUST, and the use of a deprecated term stays a warning.
