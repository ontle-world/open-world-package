# Quality Scenario World Model

Reference World Models for one decision in `openworld-examples/manufacturing-quality-world`: whether to hold lots L-1 and L-2 (`scenarios/quality-hold.yaml`). They read the EWS of the quality-incident View and the scenario, and answer in one shape: expected outcome, range, risk, uncertainty, and predicted transitions.

## Models

| Model | Asset | Status | What it does |
|---|---|---|---|
| Persistence | `models/persistence.yaml` | baseline | Nothing changes over the horizon. The floor every model must beat. |
| Three-point | `models/three-point.yaml` | baseline | Best, base, and worst cases from the scenario's `low`, `mode`, `high`; the expectation is the PERT mean. |
| Monte Carlo | `models/monte-carlo.yaml` | baseline | 2,000 seeded draws from a triangular distribution per variable; mean and P10/P50/P90. |
| Markov | `models/markov.yaml` | baseline | Next-status probabilities counted from the status sequences observed per subject up to the EWS `asOf`. |
| LLM | `models/llm.yaml` | minimum bar | Claude (`claude-opus-5-5`) reads the EWS, the scenario, and the baselines' answers and returns the outcome with a rationale and its assumptions, constrained to a JSON schema. |

The four baselines run on a CPU with the Python standard library and PyYAML, and are deterministic: the same World gives the same answer, so their evaluation evidence is reproducible. The LLM model is the minimum a production World Model is held to; a learned or simulation model replaces it only when it does better on `eval/scenario-outcome.yaml`.

## Run

```bash
python models/run.py --baselines              # the four baselines; examples/baseline-outputs.yaml is this output
python models/run.py --model monte_carlo
pip install anthropic && python models/run.py --model llm   # needs Claude credentials; reports `skipped` without them
```

Each `ModelArtifact` names its code with `entrypoint` (`models/run.py#<function>`). The code is runtime material: OWP describes the models and their grounding, it does not standardize how they run.

## Scenario ranges

The scenario gives each outcome variable as `{low, mode, high}` in `spec.uncertainty` (a missing `mode` is read as the midpoint). For quality-hold: escaped defects 0 / 1 / 3, delivery delay 1 / 2 / 5 days.

## Limitations

- The Markov model has few sequences in the example observations; with no observed transition from the current status it predicts no change.
- The LLM model's answer depends on the model version; the version is recorded in its output, and its runs are not reproducible the way the baselines are.
- No outcome after the horizon is recorded yet, so `eval/scenario-outcome.yaml` defines the checks but no evidence is attached.
