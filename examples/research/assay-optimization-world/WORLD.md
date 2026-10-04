# Assay Optimization World

A laboratory World for improving a screening assay: plates, reagents, instruments, experiment runs, and measurements.

## Scope

Included: `assay`, `plate`, `reagent`, `instrument`, `experiment_run`, `measurement`, `protocol`.

Excluded: `lims_implementation`, `instrument_control_software`.

## Sources

- Ontology: `openworld-examples/lab-ontology@0.1.0`, a dependency.
- Knowledge graph: `knowledge/plate-graph.yaml` (`kg/plates.ttl`), an illustrative plate layout graph.
- Procedures: `knowledge/sop-library.yaml`, which points at `docs/plate-handling-sop.md` (illustrative).

## Use it for

- Does the assay separate positive and negative controls well enough (`eval/assay-validation.yaml`: Z-factor threshold 0.5, control CV threshold 10%)?
- Should the assay be requalified when the detection antibody lot changes (`scenarios/reagent-change.yaml`)?
- Which wells on a campaign's plates are controls, and which reagent lot did each use (`extraction/campaign-wells.yaml`)?
- Who may propose experiment runs, and who approves protocols (`delegations/plan-runs.yaml`)?

## Limitations

- Illustrative example; no real laboratory data. Uses experimental asset kinds (spec Appendix C).
- Declared profile `viewable`: the package has World Views but no State Compiler.

## Versions

- 0.1.0: first public example.

## Work

The principal investigator (a person) designs and approves protocols. A planning agent proposes experiment runs under a time-limited delegation and cannot approve protocols. A lab robot executes runs. The work follows a design → run → measure → evaluate loop (`patterns/design-test-learn.yaml`) and produces a protocol and a results table. `eval/assay-validation.yaml` validates the assay with a Z-factor threshold, and `scenarios/reagent-change.yaml` asks what happens if a reagent lot changes.

All task, work, artifact, actor, and scenario assets are experimental (spec Appendix C). The data is illustrative.
