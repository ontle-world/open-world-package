"""Reference World Models for a scenario of a World, and a harness that runs and evaluates them.

    python models/run.py --baselines                                  # the four deterministic baselines
    python models/run.py --baselines --evaluate examples/observed-outcome.yaml
    python models/run.py --model llm                                  # the LLM minimum bar
    python models/run.py --baselines --entrypoint my_model.py#predict # your model next to the baselines
    python models/run.py --baselines --ews my-ews.yaml --scenario my-scenario.yaml

Inputs. A model reads an EWS and a ScenarioProfile; history-based models also read the ObservationSet and the
State Compiler. By default all four come from openworld-examples/manufacturing-quality-world (its quality-hold
scenario and the EWS that scenario names). --ews and --scenario replace them with your own files; without
--world, a model then gets no observations and no compiler.

Entrypoint contract. A model is a function `fn(ews, scenario, observations, compiler) -> dict`: `ews` and
`scenario` are the documents' `spec` mappings, `observations` is the ObservationSet document ({} when absent),
`compiler` the State Compiler `spec` (None when absent). It returns any of `expected_outcome` {variable: number},
`range` {variable: interval}, `risk`, `uncertainty`, `predicted_transition` {field: {at_horizon: {state: p}}};
the harness adds `model` and `provides` (the keys it filled). A ModelArtifact names it with `spec.entrypoint`.

The baselines run on a CPU with the standard library and are deterministic (Monte Carlo uses a fixed seed). The
LLM model needs the `anthropic` package and Claude credentials, and reports `skipped` without them. This is
runtime code: OWP describes the models (models/*.yaml), it does not standardize how they run.
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import yaml

HERE = Path(__file__).resolve().parent
DEFAULT_WORLD = HERE.parents[1] / "manufacturing-quality-world"
DEFAULT_WORLD_REF = "openworld-examples/manufacturing-quality-world@0.1.0"
SCENARIO = "scenarios/quality-hold.yaml"
OBSERVATIONS = "examples/observations.yaml"
LLM_MODEL = "claude-opus-5-5"


def load(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def inputs(world: Path | None, scenario_path: Path | None, ews_path: Path | None,
           observations_path: Path | None) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any] | None, str]:
    """(EWS spec, scenario spec, observations, State Compiler spec or None, scenario label)."""
    if world is None and not (scenario_path and ews_path):
        world = DEFAULT_WORLD
    scenario_file = scenario_path or world / SCENARIO
    scenario = load(scenario_file)["spec"]
    if ews_path is None and world is None:
        raise SystemExit("give --ews, or --world so the scenario's baselineStateRef can be read")
    ews = load(ews_path or world / scenario["baselineStateRef"])["spec"]
    compiler = None
    if world is not None and (world / ews["stateCompiler"].partition("#")[2]).is_file():
        compiler = load(world / ews["stateCompiler"].partition("#")[2])["spec"]
    obs_file = observations_path or (world / OBSERVATIONS if world is not None else None)
    observations = load(obs_file) if obs_file is not None and obs_file.is_file() else {}
    label = f"{DEFAULT_WORLD_REF}#{SCENARIO}" if scenario_path is None and world == DEFAULT_WORLD else str(scenario_file)
    return ews, scenario, observations, compiler, label


def ranges(scenario: dict[str, Any]) -> dict[str, dict[str, float]]:
    """Scenario variables as {low, mode, high}; a missing mode is the midpoint (convention, see WORLDMODEL.md)."""
    out = {}
    for name, r in sorted((scenario.get("uncertainty") or {}).items()):
        low, high = float(r["low"]), float(r["high"])
        out[name] = {"low": low, "mode": float(r.get("mode", (low + high) / 2)), "high": high}
    return out


def risk_from(position: float) -> str:
    """Risk of a bad outcome from where an estimate sits in its range (0 = best, 1 = worst)."""
    return "high" if position >= 0.6 else "medium" if position >= 0.3 else "low"


OUTPUT_KEYS = ("expected_outcome", "range", "risk", "uncertainty", "predicted_transition")


def answer(model: str, **fields: Any) -> dict[str, Any]:
    """A model's result: the output keys it filled, listed in `provides`, plus anything else it reports."""
    out = {"model": model, "provides": [k for k in OUTPUT_KEYS if fields.get(k) not in (None, {}, [])]}
    out.update({k: v for k, v in fields.items() if v not in (None, {}, [])})
    return out


# --- deterministic baselines -------------------------------------------------------------------------

def persistence(ews: dict[str, Any], scenario: dict[str, Any], observations: dict[str, Any], compiler: dict[str, Any] | None) -> dict[str, Any]:
    """Nothing changes over the horizon: every resolved scalar value is kept. The floor every model must beat.

    A per-subject field (spec 12.3) gives one entry per subject, keyed <field>[<subject>].
    """
    keep: dict[str, Any] = {}
    for f, v in sorted((ews.get("state") or {}).items()):
        items = sorted(v.items()) if isinstance(v, dict) else [(None, v)]
        for subject, value in items:
            if not isinstance(value, (list, dict)):
                keep[f if subject is None else f"{f}[{subject}]"] = {"from": value, "at_horizon": {str(value): 1.0}}
    return answer("persistence",
                  predicted_transition=keep,
                  uncertainty={"method": "none", "note": "assumes no change; unresolved fields stay unresolved"})


def three_point(ews: dict[str, Any], scenario: dict[str, Any], observations: dict[str, Any], compiler: dict[str, Any] | None) -> dict[str, Any]:
    """Best, base, and worst cases from the scenario's {low, mode, high}; the expectation is the PERT mean."""
    rs = ranges(scenario)
    expected = {n: round((r["low"] + 4 * r["mode"] + r["high"]) / 6, 3) for n, r in rs.items()}
    positions = [(expected[n] - r["low"]) / (r["high"] - r["low"]) for n, r in rs.items() if r["high"] > r["low"]]
    return answer("three_point",
                  expected_outcome=expected,
                  range={n: {"best": r["low"], "base": r["mode"], "worst": r["high"]} for n, r in rs.items()},
                  risk=risk_from(max(positions, default=0.0)),
                  uncertainty={"method": "three_point", "distribution": "PERT mean of low, mode, high"})


def monte_carlo(ews: dict[str, Any], scenario: dict[str, Any], observations: dict[str, Any], compiler: dict[str, Any] | None,
                runs: int = 2000, seed: int = 20261003) -> dict[str, Any]:
    """Seeded draws from a triangular distribution per variable; reports mean and P10/P50/P90."""
    rng = random.Random(seed)
    rs = ranges(scenario)
    draws = {n: sorted(rng.triangular(r["low"], r["high"], r["mode"]) for _ in range(runs)) for n, r in rs.items()}

    def pct(xs: list[float], q: float) -> float:
        return round(xs[min(len(xs) - 1, int(q * len(xs)))], 3)

    expected = {n: round(sum(xs) / len(xs), 3) for n, xs in draws.items()}
    p90 = {n: pct(xs, 0.9) for n, xs in draws.items()}
    positions = [(p90[n] - r["low"]) / (r["high"] - r["low"]) for n, r in rs.items() if r["high"] > r["low"]]
    return answer("monte_carlo",
                  expected_outcome=expected,
                  range={n: {"p10": pct(xs, 0.1), "p50": pct(xs, 0.5), "p90": pct(xs, 0.9)} for n, xs in draws.items()},
                  risk=risk_from(max(positions, default=0.0) - 0.2),  # judged on the P90 tail, so shifted down
                  uncertainty={"method": "monte_carlo", "distribution": "triangular(low, mode, high)", "runs": runs, "seed": seed})


def markov(ews: dict[str, Any], scenario: dict[str, Any], observations: dict[str, Any], compiler: dict[str, Any] | None) -> dict[str, Any]:
    """Status distributions at the horizon from a daily transition matrix.

    The matrix is the assumed prior in models/markov-transitions.yaml, updated with the daily transitions
    observed per subject up to the EWS asOf. The chain starts from the EWS value; an unresolved field starts
    split evenly over its candidates. The horizon is the scenario's timeHorizon in steps.
    """
    params = load(HERE / "markov-transitions.yaml")
    step = duration_days(params["step"])
    steps = round(duration_days(scenario.get("timeHorizon") or params["step"]) / step)
    as_of = parse_time((ews.get("context") or {}).get("asOf"))
    bindings = (compiler or {}).get("bindings") or {}
    result = {}
    for field, spec in params["fields"].items():
        states = spec["states"]
        counts = daily_counts(observations, (bindings.get(field) or {}), states, step, as_of)
        matrix = [[(params["strength"] * spec["rows"][a].get(b, 0.0) + counts[i][j]) / (params["strength"] + sum(counts[i]))
                   for j, b in enumerate(states)] for i, a in enumerate(states)]
        start = initial(ews, field, states)
        if start is None:
            continue
        dist = start
        for _ in range(steps):
            dist = [sum(dist[i] * matrix[i][j] for i in range(len(states))) for j in range(len(states))]
        result[field] = {
            "from": {s: round(p, 3) for s, p in zip(states, start) if p},
            "at_horizon": {s: round(p, 3) for s, p in zip(states, dist) if round(p, 3)},
            "observed_transitions": sum(map(sum, counts)),
        }
    return answer("markov", predicted_transition=result,
                  uncertainty={"method": "markov_chain", "step": params["step"], "steps": steps,
                               "matrix": f"{params['source']} prior (strength {params['strength']}) updated with observed daily transitions"})


def duration_days(text: str) -> float:
    """Days in a day/hour ISO 8601 duration (P14D, PT12H, P1DT6H)."""
    m = re.fullmatch(r"P(?:(\d+)D)?(?:T(?:(\d+)H)?)?", text)
    if not m or not any(m.groups()):
        raise ValueError(f"unsupported duration {text!r}")
    return int(m.group(1) or 0) + int(m.group(2) or 0) / 24


def parse_time(text: Any) -> datetime | None:
    return datetime.fromisoformat(str(text).replace("Z", "+00:00")) if text else None


def initial(ews: dict[str, Any], field: str, states: list[str]) -> list[float] | None:
    """Start distribution: the EWS value, or an even split over unresolved candidates in the state list."""
    value = (ews.get("state") or {}).get(field)
    candidates = [value] if value is not None else list((ews.get("unresolved") or {}).get(field) or [])
    known = [c for c in candidates if c in states]
    if not known:
        return None
    return [known.count(s) / len(known) for s in states]


def daily_counts(observations: dict[str, Any], binding: dict[str, Any], states: list[str],
                 step: float, as_of: datetime | None) -> list[list[int]]:
    """Transitions between consecutive steps of each subject's status, up to asOf (no peeking past it).

    A subject's status at a step is its latest observed value; observations sharing a timestamp have no
    order, so a subject is skipped from the first such tie on.
    """
    counts = [[0] * len(states) for _ in states]
    seqs: dict[str, list[tuple[datetime, str]]] = {}
    for o in (observations.get("spec") or {}).get("observations") or []:
        value = (o.get("values") or {}).get(binding.get("value"))
        at = parse_time(o.get("observedAt"))
        if o.get("type") == binding.get("from") and o.get("subject") and value in states and at and (as_of is None or at <= as_of):
            seqs.setdefault(o["subject"], []).append((at, value))
    for seq in seqs.values():
        seq.sort(key=lambda x: x[0])
        times = [at for at, _ in seq]
        cut = next((i for i in range(1, len(seq)) if times[i] == times[i - 1]), len(seq))
        seq = seq[:cut - 1] if cut < len(seq) else seq
        if not seq:
            continue
        end = as_of or seq[-1][0]
        day, k, prev = seq[0][0], 0, None
        while day <= end:
            while k + 1 < len(seq) and seq[k + 1][0] <= day:
                k += 1
            cur = states.index(seq[k][1])
            if prev is not None:
                counts[prev][cur] += 1
            prev, day = cur, day + timedelta(days=step)
    return counts


BASELINES = {"persistence": persistence, "three_point": three_point, "monte_carlo": monte_carlo, "markov": markov}


# --- LLM minimum bar ---------------------------------------------------------------------------------

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "expected_outcome": {"type": "object", "additionalProperties": {"type": "number"}},
        "range": {"type": "object", "additionalProperties": {
            "type": "object",
            "properties": {"low": {"type": "number"}, "high": {"type": "number"}},
            "required": ["low", "high"], "additionalProperties": False}},
        "risk": {"type": "string", "enum": ["low", "medium", "high"]},
        "rationale": {"type": "string"},
        "assumptions": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["expected_outcome", "range", "risk", "rationale", "assumptions"],
    "additionalProperties": False,
}

SYSTEM = (
    "You are a World Model for a manufacturing quality World. You receive the Effective World State (EWS) "
    "compiled for one View, a scenario with an intervention, a time horizon, and ranges for its outcome variables, "
    "and the outputs of simpler baseline models. Predict the outcome of the intervention over the horizon. "
    "Stay inside the given ranges unless the state gives a concrete reason not to, and say so in the rationale. "
    "Treat unresolved and missing EWS fields as unknown, not as facts. List the assumptions you relied on."
)


def llm(ews: dict[str, Any], scenario: dict[str, Any], observations: dict[str, Any], compiler: dict[str, Any] | None) -> dict[str, Any]:
    """Claude predicts the scenario outcome from the EWS, the scenario, and the baselines' answers."""
    try:
        import anthropic
    except ImportError:
        return answer("llm", skipped="the anthropic package is not installed (pip install anthropic)")
    baselines = {name: fn(ews, scenario, observations, compiler) for name, fn in BASELINES.items()}
    prompt = json.dumps({"ews": ews, "scenario": scenario, "baselines": baselines}, indent=2, sort_keys=True, default=str)
    try:
        client = anthropic.Anthropic()
        response = client.beta.messages.create(
            model=LLM_MODEL,
            max_tokens=16000,
            system=SYSTEM,
            messages=[{"role": "user", "content": prompt}],
            output_config={"effort": "medium", "format": {"type": "json_schema", "schema": OUTPUT_SCHEMA}},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",  # a declined request is retried on a fallback model in the same call
        )
    except anthropic.AuthenticationError:
        return answer("llm", skipped="no Claude credentials (set ANTHROPIC_API_KEY or run `ant auth login`)")
    except anthropic.APIConnectionError as exc:
        return answer("llm", skipped=f"cannot reach the Claude API: {exc}")
    except (anthropic.AnthropicError, TypeError) as exc:  # e.g. no credential source resolved
        return answer("llm", skipped=f"Claude API unavailable: {exc}")
    if response.stop_reason == "refusal":
        return answer("llm", skipped="the request was declined")
    data = json.loads(next(b.text for b in response.content if b.type == "text"))
    return answer("llm",
                  expected_outcome=data["expected_outcome"],
                  range=data["range"],
                  risk=data["risk"],
                  uncertainty={"method": "llm_judgement", "model": response.model, "assumptions": data["assumptions"]},
                  rationale=data["rationale"])


MODELS = {**BASELINES, "llm": llm}


def load_entrypoint(spec: str):
    """A model function named as <file.py>#<function>."""
    import importlib.util
    file, _, name = spec.partition("#")
    module_spec = importlib.util.spec_from_file_location(Path(file).stem, file)
    if module_spec is None or not name:
        raise SystemExit(f"--entrypoint must be <file.py>#<function>, not {spec!r}")
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)  # type: ignore[union-attr]
    fn = getattr(module, name, None)
    if not callable(fn):
        raise SystemExit(f"{file} defines no function {name!r}")
    return fn


def interval(r: dict[str, float]) -> tuple[float, float] | None:
    """The outer interval of a range, whatever its keys: best/worst, p10/p90, or low/high."""
    for lo, hi in (("best", "worst"), ("p10", "p90"), ("low", "high")):
        if lo in r and hi in r:
            return float(r[lo]), float(r[hi])
    return None


def evaluate(results: list[dict[str, Any]], scenario: dict[str, Any], outcome: dict[str, Any]) -> dict[str, Any]:
    """Score each result against an outcome recorded after the horizon (checks of eval/scenario-outcome.yaml)."""
    observed = outcome.get("outcome") or {}
    status = outcome.get("state") or {}
    base = {n: r["mode"] for n, r in ranges(scenario).items()}
    scores = {}
    for res in results:
        if "skipped" in res:
            continue
        s: dict[str, Any] = {}
        for var, actual in sorted(observed.items()):
            entry: dict[str, Any] = {}
            expected = (res.get("expected_outcome") or {}).get(var)
            if expected is not None:
                entry["expected_outcome_error"] = round(abs(float(expected) - actual), 3)
                if var in base:
                    entry["beats_base_case"] = abs(float(expected) - actual) < abs(base[var] - actual)
            span = interval((res.get("range") or {}).get(var) or {})
            if span is not None:
                entry["range_contains_observed_outcome"] = span[0] <= actual <= span[1]
            if entry:
                s[var] = entry
        for field, actual in sorted(status.items()):
            dist = ((res.get("predicted_transition") or {}).get(field) or {}).get("at_horizon")
            if isinstance(dist, dict):
                s[field] = {"probability_of_observed_state": dist.get(str(actual), 0.0)}
        scores[res["model"]] = s
    return {"outcome": outcome.get("observedAt"), "scores": scores}


class NoAliases(yaml.SafeDumper):
    """Write repeated values in full instead of YAML anchors."""

    def ignore_aliases(self, data: Any) -> bool:
        return True


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--model", action="append", default=[], choices=sorted(MODELS), help="a reference model (repeatable)")
    ap.add_argument("--baselines", action="store_true", help="the four deterministic baselines")
    ap.add_argument("--entrypoint", action="append", default=[], help="your model as <file.py>#<function> (repeatable)")
    ap.add_argument("--world", type=Path, help="World package directory (default: manufacturing-quality-world)")
    ap.add_argument("--scenario", type=Path, help="ScenarioProfile file (default: the World's scenarios/quality-hold.yaml)")
    ap.add_argument("--ews", type=Path, help="EWS file (default: the scenario's baselineStateRef in the World)")
    ap.add_argument("--observations", type=Path, help="ObservationSet file (default: the World's examples/observations.yaml)")
    ap.add_argument("--evaluate", type=Path, help="an outcome recorded after the horizon; adds per-model scores")
    args = ap.parse_args()
    names = (list(BASELINES) if args.baselines else []) + [m for m in args.model if not (args.baselines and m in BASELINES)]
    if not names and not args.entrypoint:
        ap.error("give --baselines, --model, or --entrypoint")
    ews, scenario, observations, compiler, label = inputs(args.world, args.scenario, args.ews, args.observations)
    results = [MODELS[n](ews, scenario, observations, compiler) for n in names]
    for spec in args.entrypoint:
        raw = load_entrypoint(spec)(ews, scenario, observations, compiler)
        results.append(answer(spec, **{k: v for k, v in (raw or {}).items() if k not in ("model", "provides")}))
    out: dict[str, Any] = {"scenario": label, "asOf": (ews.get("context") or {}).get("asOf"), "results": results}
    if args.evaluate:
        out["evaluation"] = evaluate(results, scenario, load(args.evaluate).get("spec") or {})
    sys.stdout.write(yaml.dump(out, Dumper=NoAliases, sort_keys=False, allow_unicode=True, width=120))
    return 0


if __name__ == "__main__":
    sys.exit(main())
