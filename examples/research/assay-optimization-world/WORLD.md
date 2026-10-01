# Assay Optimization World

A laboratory World for improving a screening assay: plates, reagents, instruments, experiment runs, and measurements.

The principal investigator (a person) designs and approves protocols. A planning agent proposes experiment runs under a time-limited delegation and cannot approve protocols. A lab robot executes runs. The work follows a design → run → measure → evaluate loop (`patterns/design-test-learn.yaml`) and produces a protocol and a results table. `eval/assay-validation.yaml` validates the assay with a Z-factor threshold, and `scenarios/reagent-change.yaml` asks what happens if a reagent lot changes.

All task, work, artifact, actor, and scenario assets are experimental (spec Appendix C). The data is illustrative.
