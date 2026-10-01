# Contributing

Thank you for contributing to ONTLE / OWP public-alpha tooling.

## Development setup

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e .   # installs the runtime dependency PyYAML
python -m unittest discover -s tests -v
./scripts/golden_smoke.sh
```

Starter templates live only in `src/ontle/templates/` and ship as package data; edit them there.

## Design rules

1. Keep the default authoring surface small.
2. Do not expose registry-internal complexity as mandatory authoring files.
3. `owp.yaml` is the single machine-readable package manifest.
4. `WORLD.md`, `WORLDMODEL.md`, and `ONTOLOGY.md` are human-readable cards by package kind.
5. Package identity and semantic identity are related but not identical.
6. Runtime state, especially Effective World State, is not automatically a registry asset.
7. A package or fixture never overrides semantic meaning; it tests or instantiates a contract.
8. Add deterministic validation where possible. Keep model-specific execution optional.

## Pull requests

Please include:
- the problem being solved,
- compatibility impact,
- tests or fixtures,
- documentation changes when the public contract changes.

For manifest/schema changes, include at least one positive and one negative case.
