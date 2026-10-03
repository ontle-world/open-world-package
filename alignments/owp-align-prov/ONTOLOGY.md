# OWP to PROV-O

Informative alignment of the OWP vocabulary to PROV-O (W3C Recommendation 2013-04-30): `align.ttl` holds the OWL axioms, and `mappings.sssom.tsv` holds the same correspondences plus weaker SKOS matches, with justification and confidence. OWP conformance never depends on this package.

Checked with HermiT, through ROBOT, against the pinned upstream files: `scripts/check_alignments.sh`. The alignment and the OWP vocabulary are consistent, with no unsatisfiable classes, both with and without the sample data.

License: CC BY 4.0. The upstream ontologies keep their own licenses and are referenced, not copied.
