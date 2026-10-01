# Sales Prioritization World

Accounts, opportunities, sales activity, territories, and quotas, and the priority each account receives.

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
