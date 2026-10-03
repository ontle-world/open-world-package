# Quality Scenario World Model

Reference World Models for one decision in `openworld-examples/manufacturing-quality-world`: whether to hold lots L-1 and L-2 (`scenarios/quality-hold.yaml`), and a harness (`models/run.py`) that runs them, runs your own model next to them, and scores them against a recorded outcome.

## Models

| Model | Asset | Status | Provides |
|---|---|---|---|
| Persistence | `models/persistence.yaml` | baseline | `predicted_transition`: every resolved value stays as it is. The floor for state prediction. |
| Three-point | `models/three-point.yaml` | baseline | `expected_outcome` (PERT mean), `range` (best/base/worst from the scenario's `low`, `mode`, `high`), `risk` |
| Monte Carlo | `models/monte-carlo.yaml` | baseline | `expected_outcome` (mean of 2,000 seeded triangular draws), `range` (P10/P50/P90), `risk` |
| Markov | `models/markov.yaml` | baseline | `predicted_transition`: status distributions after 14 daily steps of an assumed transition matrix updated with observed history |
| LLM | `models/llm.yaml` | minimum bar | `expected_outcome`, `range` (low/high), `risk`, with a rationale and its assumptions. Claude (`claude-opus-5-5`) reads the EWS, the scenario, and the baselines' answers, constrained to a JSON schema. |

Each result lists the output keys it filled in `provides`; a model fills only what it can predict. The baselines run on a CPU with the standard library and PyYAML and are deterministic, so their outputs and scores are reproducible (`examples/baseline-outputs.yaml`). The LLM model is the minimum a production World Model is held to: a learned or simulation model replaces it only when it scores better under `eval/scenario-outcome.yaml`.

## Run

```bash
python models/run.py --baselines                                   # the four baselines
python models/run.py --baselines --evaluate examples/observed-outcome.yaml
pip install anthropic && python models/run.py --model llm         # needs Claude credentials; reports `skipped` without them
```

By default the inputs come from the manufacturing World: the scenario, the EWS it names (`baselineStateRef`), the World's observations, and the EWS's State Compiler. Persistence, three-point, and Monte Carlo work on any EWS and scenario; give your own with `--ews` and `--scenario`.

## Bring your own model

A model is a Python function:

```python
def predict(ews, scenario, observations, compiler):
    """ews, scenario: the documents' spec mappings; observations: the ObservationSet ({} when absent);
    compiler: the State Compiler spec (None when absent)."""
    return {"expected_outcome": {"escapedDefects": 1.0}, "uncertainty": {"method": "my_method"}}
```

It returns any of `expected_outcome` `{variable: number}`, `range` `{variable: {low, high}}`, `risk`, `uncertainty`, and `predicted_transition` `{field: {at_horizon: {state: probability}}}`. Run and score it next to the baselines:

```bash
python models/run.py --baselines --entrypoint my_model.py#predict --evaluate examples/observed-outcome.yaml
```

To package it, add the file and a ModelArtifact whose `spec.entrypoint` names it (`models/my_model.py#predict`), as the artifacts here do; `ontle validate` checks that the file is in the package (the function name is not checked).

## Evaluation

`eval/scenario-outcome.yaml` defines four checks; `run.py --evaluate <outcome>` computes them for every result that provides the input:

| Check | Uses | Meaning |
|---|---|---|
| `range_contains_observed_outcome` | `range` | the outer interval (best..worst, P10..P90, low..high) contains the observed value |
| `expected_outcome_error` | `expected_outcome` | absolute error |
| `beats_base_case` | `expected_outcome` | smaller error than the scenario's base case (the `mode` of its range) |
| `probability_of_observed_state` | `predicted_transition` | probability given at the horizon to the status observed |

`examples/observed-outcome.yaml` is an illustrative outcome, not a real record; replace it with what happened at the end of the horizon.

## Scenario ranges

The scenario gives each outcome variable as `{low, mode, high}` in `spec.uncertainty` (a missing `mode` reads as the midpoint). For quality-hold: escaped defects 0 / 1 / 3, delivery delay 1 / 2 / 5 days.

## Markov transition matrix

`models/markov-transitions.yaml` gives a daily transition matrix per EWS status field. The matrix is an assumption, marked `source: assumption`: each row counts as `strength` (10) observed days. The model adds the daily transitions observed in the World up to the EWS `asOf`, so as history accumulates the observed rates replace the assumed ones; `observed_transitions` in the output says how much history was used. The chain starts from the EWS value, and an unresolved field (here `capa.status`: proposed or approved) starts split evenly over its candidates. Observations sharing a timestamp have no order and are not counted. Fields the matrix file does not name are skipped, so on another World the model predicts nothing until you give it a matrix.

## Limitations

- The Markov matrix is mostly assumption: the example World holds two observed days of history, so the prior dominates. The matrix does not depend on the intervention; a hold-aware model would give one matrix per action.
- The LLM model's answer depends on the model version, which is recorded in its output; its runs are not reproducible the way the baselines are.
