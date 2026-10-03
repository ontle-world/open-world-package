# Interop Notes

These notes show how OWP fits next to runtime standards that cover part of the same ground. OWP does not replace them. It sits above them: it says what a World is, how observations become its state, and which actions change it. These standards then carry that state and those actions to where they are used.

| Standard | What it carries | OWP side | Tooling |
|---|---|---|---|
| [MCP](MCP.md) | Context and tools for AI agents | World, Views, EWS → resources; actions → tools | `ontle interop mcp` |
| [NGSI-LD](NGSI-LD.md) | Current state of entities | EWS → entities and attributes | `ontle ews compile --ngsi-ld` |
| [AAS](AAS.md) | Asset data and its dictionary semantics | Observations from submodels; `semanticIds` | — |

The notes are informative. Conformance is defined only by the specification.

For example: a World of a plant line takes observations from AAS submodels, serves its EWS as NGSI-LD entities, and exposes its Views and actions to an agent through MCP.
