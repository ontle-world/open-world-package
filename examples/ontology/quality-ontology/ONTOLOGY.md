# Manufacturing Quality Ontology

## Scope
Classes and properties for quality incidents, claims, production lots, equipment, inspections, and corrective and preventive actions (CAPA). Used by `examples/business/manufacturing-quality-world` through a SemanticBinding.

## Sources
- ISA-95: `mappings/isa95.sssom.tsv` maps `q:Lot` and `q:Equipment` to ISA-95 object names (`skos:closeMatch`, manual curation).
- SHACL: `semantics/shapes.ttl` holds one shape, for claim status.
- No other ontology is imported.

## Use it for
- Bind a World's names, EWS fields, observation types, and actions to shared terms through a SemanticBinding.
- Serve as the T-box for a plant knowledge graph of claims, lots, equipment, and parts.
- Check that a claim has exactly one status out of open, investigating, and closed (`semantics/shapes.ttl`).
- Line up lots and equipment with ISA-95 object names.

## Limitations
- The IRI is illustrative and is not resolvable.
- The SHACL shapes cover claim status only.
- Only lots and equipment are mapped to ISA-95.
- `q:Decision`, `q:Outcome`, and `q:Constraint` have no properties yet.

## Versions
- 0.1.0: first public example.

## Namespaces
`q:` = `https://w3id.org/openworld-examples/quality#`. The IRI is illustrative and is not resolvable.

## Files
- `semantics/core.yaml` — schema in the OWP YAML format (SemanticProfile)
- `semantics/shapes.ttl` — SHACL shapes
- `mappings/isa95.sssom.tsv` — SSSOM mappings to ISA-95 object names

## Compatibility
The ISA-95 mappings use object names only; no ISA-95 artifact is bundled.
