# Sales Account Ontology

## Scope
Classes and properties for customer accounts and their contacts: the account's region and each contact's title. Used by `examples/business/sales-prioritization-world` as the T-box of its account graph.

## Sources
The terms are defined in this package (`semantics/core.yaml`). No other ontology is imported or mapped.

## Use it for
- Serve as the T-box for an account graph of accounts and contacts.
- Find the contacts of accounts in a region, with their titles.
- Give the account graph and the World a shared name for accounts, contacts, regions, and titles.

## Limitations
- The IRI is illustrative and is not resolvable.
- Only accounts and contacts are covered. Opportunities, activities, territories, and quotas have no terms here.
- No SHACL shapes or mappings to other vocabularies are included.

## Versions
- 0.1.0: first public example.

## Namespaces
`s:` = `https://w3id.org/openworld-examples/sales#`. The IRI is illustrative and is not resolvable.

## Files
- `semantics/core.yaml` — schema in the OWP YAML format (SemanticProfile)
