# Sales Prioritization World

Accounts, opportunities, sales activity, territories, and quotas, and the priority each account receives.

## Scope

Included: `account`, `opportunity`, `activity`, `territory`, `territory_assignment`, `quota`, `priority`, `global_pipeline`.

Excluded: `complete_crm_implementation`, `pricing_engine`.

## Sources

- CRM: the State Compiler (`state/account-priority-compiler.yaml`) reads accounts, opportunities, activities, and territories from CRM records. `capabilities/crm-read.yaml` gives the agent read access in its region.
- Knowledge graph: `knowledge/account-graph.yaml` (`kg/accounts.ttl`), an illustrative account graph.
- Ontology: `openworld-examples/sales-ontology@0.1.0`, a dependency.
- Win/loss playbook: `knowledge/win-loss-playbook.yaml`.

## Use it for

- What stage is each account in, what is its open pipeline, and what recent activity does it have?
- Who owns each territory?
- Which accounts should come first this period, and why (`tasks/account-priority.yaml`, `artifacts/priority-board.yaml`)?
- Which contacts, with which titles, belong to accounts in a region (`extraction/region-contacts.yaml`)?
- What may the sales AI agent do, compared with the regional sales manager (see Actors and Views)?

## Limitations

- Illustrative example; no real CRM data. Uses experimental asset kinds (spec Appendix C).
- The State Compiler covers account stage, open pipeline, recent activity, and territory owner. Quotas and priorities are not compiled into the EWS.
- The win/loss playbook has no bound content.

## Versions

- 0.1.0: first public example.

## Actors and Views

The same accounts are seen differently by each actor:

| View | Actor | Specializes | Difference |
|---|---|---|---|
| `views/account-base.yaml` | none (shared base) | | entities every sales actor sees |
| `views/account-manager.yaml` | regional sales manager | base | adds territory assignment; may assign accounts in the region |
| `views/account-agent.yaml` | sales AI agent | base | may only propose next actions |

## Work

`tasks/account-priority.yaml` combines the Prioritize and Allocate work patterns, needs the manager View and the win/loss playbook, and produces the priority board described by `artifacts/priority-board.yaml`.

`consumers/` describes how each actor receives its View: the manager gets the board, the agent gets a structured context with CRM read access.

Task, work-pattern, artifact, knowledge, and consumer assets are experimental (spec Appendix C).
