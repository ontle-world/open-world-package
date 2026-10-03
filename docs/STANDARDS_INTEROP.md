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

## OWP vocabulary and alignments

OWP's own concepts have RDF terms in `vocab/owp` (namespace `https://w3id.org/owp/ns#`, OWL 2 DL, CC BY 4.0). The vocabulary defines only what other vocabularies lack, and reuses PROV-O, XSD, DCTERMS, and DCAT for provenance, time, licensing, and catalogs. OWP's core takes no position on upper ontologies.

Alignments are separate OntologyPackages under `alignments/`. Each holds OWL axioms (`align.ttl`) and an SSSOM mapping set with justification and confidence. They are informative: OWP conformance never depends on them.

| Package | Aligns OWP to | Notes |
|---|---|---|
| `owp-align-prov` | PROV-O (2013-04-30) | documents, observations and values are `prov:Entity`; a compilation is a `prov:Activity`; a State Compiler is a `prov:Plan` |
| `owp-align-bfo` | BFO 2020 (ISO/IEC 21838-2) and IAO | documents are IAO documents; values and observations are information content entities; a compilation is a BFO process; a World is not aligned, since it may be designed or simulated |
| `owp-align-dul` | DOLCE+DnS Ultralite | documents are InformationObjects that express Descriptions (a View) or Methods (a State Compiler); an EWS is about a Situation; a compilation is an Action |

Cross-standard links that are not subclass axioms use SKOS match predicates, never `owl:equivalentClass`. Examples: an OWP observation record is a `skos:closeMatch` of `sosa:Observation`, because it need not be an act of observing.

`scripts/check_alignments.sh` reasons over the vocabulary and each alignment with HermiT, through ROBOT. It uses the upstream ontologies pinned by digest in each package's `externalImports`. Each check is run with the sample data and against deliberately wrong inputs. CI runs it.

## Binding convention

Asset YAML files tie their parts to standards under `spec.standardBindings` (spec section 5.3): each named binding has a `standard`, and `terms` (local names to the standard's type names), a `ref` to an artifact, or both. Each `ref` uses the ExternalRef shape of spec section 5.1. Unbound references say so explicitly instead of pointing at an invented artifact:

```yaml
kind: EnvironmentProfile
spec:
  standardBindings:
    scene:
      standard: openusd
      ref:
        status: unbound
```

A bound reference names the provider, the artifact, and how it is pinned, and the binding declares the artifact's license:

```yaml
    episodes:
      standard: lerobot
      license: Apache-2.0
      ref:
        provider: huggingface
        uri: hf://datasets/organization/name
        revision: <commit hash>
```

The examples use this convention:

- `examples/physical-ai/mobile-manipulation-world` — OpenUSD scene, ROS 2 message/action types, LeRobot episodes
- `examples/business/manufacturing-quality-world` — ISA-95 object models, OPC UA information model

Both implementations check `standardBindings` in every local asset: the binding shape, the ExternalRef, pinning (`standard.unpinned`), and the license of a bound artifact (`standard.license`). Domain validators may layer checks on top, for example that a `ros2` term names a real message type.

## Evidence of interoperability

Interoperability is shown by implementations agreeing, not by one toolchain reading its own packages:

1. a clean-room TypeScript validator passes `conformance/` alongside the Python reference;
2. both compile the same View into the same EWS (`ewsCases`) and record the same resolution revisions;
3. `demos/` runs Physical AI and Business AI data over the bound external references into evidence that both implementations check.
