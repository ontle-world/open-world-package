# My World

## Definition

Describe what target world this package represents.

## Boundary

### Included

- Add included entities/processes/relations.

### Excluded

- Add intentional exclusions.

## Typical questions

- What should a user or agent be able to ask about this World?

## Capabilities

- Explore

## Validity and limitations

State the scope, assumptions, and known blind spots.

## State

`views/default.yaml` is the default World View and `state/default-compiler.yaml` its State Compiler. The compiler starts with three fields per item, one of each kind: an observed status, an aggregate (events in the last 24 hours), and a classification of that aggregate by a named criterion. `examples/observations.yaml` holds sample observations and `examples/expected-ews.yaml` the Effective World State they compile to.

Try it, then replace the `item` fields with your own:

```bash
ontle validate .
ontle ews compile . --observations examples/observations.yaml --as-of 2026-01-02T00:00:00Z > ews.yaml
ontle ews check ews.yaml --world .
```

Writing fields and bindings: docs/STATE_COMPILATION.md in the OWP repository.
