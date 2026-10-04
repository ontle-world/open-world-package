# OWP and the Model Context Protocol

[MCP](https://modelcontextprotocol.io/specification) connects AI applications to context (resources) and actions (tools). It does not say what the context means, how it was derived, or whether an action took effect. OWP covers those questions. An MCP server is one way to serve an OWP World to an agent.

## Mapping

| OWP | MCP | Notes |
|---|---|---|
| World package | resource `https://w3id.org/owp/pkg/{ns}/{name}/{version}` | The manifest. Its description is `spec.world.definition`. |
| World View (`WorldViewProfile`) | resource | What the World looks like for one task. |
| State Compiler (`StateCompilerProfile`) | resource | How observations become the EWS. |
| EWS of a State Compiler | resource template `owp-ews://{ns}/{name}/{version}/{compiler path}?asOf={asOf}` | The state at a time. It keeps `unresolved`, `missing`, and `provenance`, so an agent sees what is uncertain and where each value came from. |
| Action (`ActionBindingProfile`) | tool | `_meta` links the commit contract and effect verification. |

The `owp-ews:` URI names a computed document, not a file. A package IRI cannot carry the time, since its fragment would swallow the query.

## Tools are not commits

An MCP tool call that returns success is not a business commit. OWP's `CommitContract` and `EffectVerificationProfile` decide whether the action took effect. The generated tool description says so. `_meta` gives:

- `owp/actionBinding`: the action binding asset.
- `owp/execution`: the binding's `execution`.
- `owp/commitContracts` and `owp/approvalRequired`: the commit contracts, and whether any of them requires approval.
- `owp/effectVerification`: the effect verification profiles.

A host can use these to ask for approval before the call, and to read the EWS again afterwards for the verified effect. Every action is marked `readOnlyHint: false` and `openWorldHint: true`.

`inputSchema` is `{"type": "object"}`, since OWP does not yet type action parameters. A server should narrow it.

## Tooling

```bash
ontle interop mcp examples/business/manufacturing-quality-world
```

This prints the server's resources, resource templates, and tools as MCP JSON shapes (protocol revision 2025-06-18). A server can serve these as they are. To answer a read of an EWS resource, it runs `ontle ews compile` with the `asOf` from the URI.

## A read-only server

```bash
ontle mcp examples/business/manufacturing-quality-world \
  --observations examples/business/manufacturing-quality-world/examples/observations.yaml
```

`ontle mcp <package>` serves one package, a directory or an `.owp.zip`, over the stdio transport. Configure it in an MCP client as a local command. It serves the resources above, plus the card. It does not serve the actions as tools, since a server that runs actions is a runtime and outside this repository. Its tools only read the package:

| Tool | Returns |
|---|---|
| `world_describe` | Identity, title, description, domains, the World's definition and boundary, its Views and State Compilers, and the card text. |
| `view_get` | A World View's purpose, projection, and conditioning, with `specializes` applied. Without `path`: the default View. |
| `term_lookup` | Matches for a name, CURIE, or IRI in the SemanticBinding, or among an OntologyPackage's terms. |
| `ews_compile` | The EWS of a State Compiler at `asOf`, from an ObservationSet given inline or by its path in the package. |
| `package_report` | The `PackageReport` (`ontle inspect --report`). |

A read of an EWS resource compiles from the files given with `--observations`. Without them, the read fails and says so; `ews_compile` with inline observations still works.
