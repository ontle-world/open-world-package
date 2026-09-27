# OWP and Adjacent Standards

OWP does not replace existing standards. Each of them answers part of the question below; OWP connects the answers in one package graph.

> Which World does this model assume, through which View and state representation does it see that World, through which interfaces does it observe and act, where is it valid, and what verified that?

| Standard | Stays authoritative for | OWP records |
|---|---|---|
| OpenUSD | scene description and composition | which scene backs an `EnvironmentProfile` |
| ASAM OpenSCENARIO | dynamic scenarios (entities, actions, triggers) | which scenario file a `ScenarioProfile` binds |
| ROS 2 | typed messages, services, actions | which interface type carries each observation/action in a World |
| LeRobot | episodic robotics datasets | which View a `Dataset` of episodes belongs to |
| ISA-95 | enterprise-control object models and exchange | which ISA-95 objects a source schema maps to |
| OPC UA companion specs | industrial information models | which information model an equipment source uses |
| Hugging Face cards | model/dataset discovery, intended use, provenance | the World/View grounding the card cannot express |
| MLflow model signature | input/output/parameter schemas | the semantic origin of those inputs (View, EWS contract, adapter) |
| OCI | content addressing, manifests, referrers | nothing new; OCI can transport `.owp.zip` archives |

## Binding convention

Asset YAML files carry external references under `standardBindings`. Unbound references say so explicitly instead of pointing at an invented artifact:

```yaml
kind: EnvironmentProfile
spec:
  standardBindings:
    scene:
      standard: openusd
      ref: null
      status: unbound
```

The examples use this convention:

- `examples/physical-ai/mobile-manipulation-world` — OpenUSD scene, ROS 2 message/action types, LeRobot episodes
- `examples/business/manufacturing-quality-world` — ISA-95 object models, OPC UA information model

`standardBindings` is not validated by the reference validator in this alpha; domain validators may layer checks on top.

## What is still missing

Interoperability is demonstrated by independent implementations, not by one toolchain reading its own packages. The next evidence needed is:

1. an independent parser/validator passing `conformance/`;
2. two runtimes that compile the same View into the same EWS contract and bind the same World Model;
3. end-to-end Physical AI and Business AI demos with bound (not placeholder) external references.
