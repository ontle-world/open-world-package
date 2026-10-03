# OWP and the Asset Administration Shell

The [Asset Administration Shell](https://industrialdigitaltwin.org/en/content-hub/aasspecifications) (AAS, IEC 63278) describes an asset's data in submodels. Each element of a submodel carries a `semanticId`, usually an ECLASS or IEC CDD IRDI, that says what it means. AAS describes one asset. OWP describes a World of many assets, processes, and people for a task: how their data becomes a state, and which actions change it. A World can use AAS as a source and as a vocabulary.

## Mapping

| AAS | OWP |
|---|---|
| Submodel element values (Property, Range, MultiLanguageProperty) | Observations. A source in `interfaces/sources.yaml` reads the AAS repository API; each observation keys values by element `idShort` path, with `subject` set to the shell or asset id. |
| `semanticId` of an element (IRDI or IRI) | `semanticIds` in the SemanticBinding (spec section 14), on the bound field or term. |
| `valueId` and value lists of a property | `values` on the field: map codes to concept IRIs. |
| Unit of a property (from its concept description) | `outputSchema.units` (UCUM) in the State Compiler, and `unit` (such as QUDT) in the SemanticBinding. OWP does not convert units. |
| AASX package | Not an OWP package. An AASX holds one asset's shells and supplementary files. An OWP package holds a World's definitions and is resolved by identity and digest. |
| Operations of a submodel | Actions in an `ActionBindingProfile`, with a commit contract and effect verification. |

## Example

```yaml
# semantics/terms.yaml
spec:
  fields:
    pump.manufacturer: {class: m:Pump, path: [m:manufacturerName]}
    pump.status:
      class: m:Pump
      path: [m:operatingState]
      values: {base: "https://example.org/pump-state/"}
  semanticIds:
    fields:
      pump.manufacturer: ["0173-1#02-AAO677#002"]   # ECLASS: manufacturer name, as in the Digital Nameplate
```

OWP checks the identifier's syntax only. It does not fetch the dictionary or compare meanings.

## Licensing

ECLASS is licensed. A package may cite ECLASS identifiers. It must not copy ECLASS names, definitions, or value lists unless the publisher's license allows it. IEC CDD content has its own terms.
