# End-to-end demos

Two demos run the full chain on sample data and record the result as evidence:

```text
World -> View -> State Compiler -> EWS -> Representation Adapter -> model stub -> CompatibilityEvidence
```

OWP standardizes the World, View, State Compiler, EWS, and evidence documents. The adapter and the model stub are runtime code, written here only to make the chain concrete; the stubs are baselines, not trained models.

| Demo | Data | World / World Model | Stub | Evidence |
|---|---|---|---|---|
| `physical-ai/` | episode 0 of the LeRobot dataset the World binds (`k-chan-l/lekiwi_pick_and_place2` at a pinned commit, Apache-2.0), one frame per second | `mobile-manipulation-world` / `multimodal-action-world-model` | hold position | `offline-action-replay@0.1.0`: error against the recorded teleoperation commands |
| `business-ai/` | sample MES/QMS records (`records/*.csv`, illustrative) mapped through the World's ISA-95 binding | `manufacturing-quality-world` / `quality-transition-world-model` | claim-escalation rule | `quality-basic@0.1.0`: traceability to the production lot, declared uncertainty |

Each demo compiles one EWS per step and checks it against the output contract (spec 12.1), then writes:

- `expected-ews.yaml`: the EWS at the last step;
- `evidence.yaml`: a CompatibilityEvidence published outside the package (spec 9.1);
- `<world model>-0.1.0.owp.zip`: the World Model archive the evidence binds to by `subjectDigest`.

## Run

```bash
python demos/physical-ai/run.py          # or --check to compare with the committed files
python demos/business-ai/map_records.py  # records -> observations.yaml
python demos/business-ai/run.py
pip install -e ".[demo]" && python demos/physical-ai/extract.py   # re-download the episode (network)
```

## Checked by both implementations

- Python: `tests/test_demos.py` reruns every script with `--check`.
- TypeScript: `implementations/typescript/scripts/check-demos.mjs` (`npm run demos`) compiles the observations to `expected-ews.yaml`, checks it, and checks `evidence.yaml` against the archive.

The archives are snapshots: after changing a World Model example, rerun its demo to repack the archive and update the evidence digest.
