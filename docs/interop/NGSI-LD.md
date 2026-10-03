# OWP and NGSI-LD

[NGSI-LD](https://cim.etsi.org/NGSI-LD/official/front-page.html) (ETSI GS CIM 009) serves the current state of entities through a context broker. The NGSI-LD model is close to the EWS. The difference is in what each one decides:

- **NGSI-LD** stores and serves whatever a producer writes.
- **An EWS** is compiled from observations by a declared State Compiler, and records what is unresolved, what is missing, and where each value came from.

Compile with OWP, then serve with NGSI-LD.

## Mapping

| EWS | NGSI-LD |
|---|---|
| Subject of a per-subject field | One entity per subject key, whatever observation types its fields come from. Its `id` comes from the first `subjects` rule (by observation type name) of those types, and is `urn:ngsi-ld:Subject:{percent-encoded key}` when none has a rule. Its `type` is the observation types' classes (a list when there are several). |
| Field value | Property, named by the bound property's IRI. A field without a binding is named after the field, with `.` replaced by `_`. |
| Coded value with `values` | VocabProperty, whose `vocab` is the concept IRI, or the list of IRIs for a list value (NGSI-LD 1.7 and later). A code without a concept is refused, as in `--rdf`. |
| `unresolved` alternatives | One attribute instance per alternative, each with its own `datasetId` (`urn:ngsi-ld:Dataset:alternative-{n}`). The disagreement stays visible instead of one value being picked. |
| `provenance` | `provenance` sub-property listing observation ids, and `observedAt` set to the newest observation time. |
| `derivation` | `derivation` sub-property: estimate, aggregate, classify. |
| Fields that are not per subject | Attributes of one `EffectiveWorldState` entity for the View. |
| `missing` | Not written. NGSI-LD has no attribute for an absent value. |

The `@context` holds the binding's prefixes and field IRIs, followed by the NGSI-LD core context.

## Tooling

```bash
ontle ews compile <world> --observations <obs.yaml> --as-of <time> --ngsi-ld --source <packages>
```

This prints entities in normalized form, ready for a batch upsert (`POST /ngsi-ld/v1/entityOperations/upsert`). It needs the World's SemanticBinding and dependency ontologies, so pass `--source` as for `--rdf`.

## Smart Data Models

[Smart Data Models](https://smartdatamodels.org) publish NGSI-LD entity types with JSON-LD contexts. To produce entities of such a type, bind the World's observation types and fields to the model's terms in the SemanticBinding.
