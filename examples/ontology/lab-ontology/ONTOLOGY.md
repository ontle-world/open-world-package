# Laboratory Assay Ontology

## Scope
Classes and properties for assay plates and their wells: the campaign a plate belongs to, the control role of each well, and the reagent lot used. Used by `examples/research/assay-optimization-world` as the T-box of its plate graph.

## Sources
The terms are defined in this package (`semantics/core.yaml`). No other ontology is imported or mapped.

## Use it for
- Serve as the T-box for a plate graph of plates and wells.
- Find the wells on a campaign's plates, with each well's control role and reagent lot.
- Give the plate graph and the World a shared name for plates, wells, campaigns, controls, and reagent lots.

## Limitations
- The IRI is illustrative and is not resolvable.
- Only plates and wells are covered. Assays, instruments, experiment runs, measurements, and protocols have no terms here.
- No SHACL shapes or mappings to other vocabularies are included.

## Versions
- 0.1.0: first public example.

## Namespaces
`l:` = `https://w3id.org/openworld-examples/lab#`. The IRI is illustrative and is not resolvable.

## Files
- `semantics/core.yaml` — schema in the OWP YAML format (SemanticProfile)
