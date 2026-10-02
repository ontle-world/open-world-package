# Management Report World

Business units, their financial results and operating KPIs, open risks, and strategic initiatives, and the monthly management report that leadership receives about them.

## Actors and Views

| View | Actor | Specializes | Difference |
|---|---|---|---|
| `views/enterprise-base.yaml` | none (shared base) | | KPIs, results, risks, and initiatives for the reporting period |
| `views/executive.yaml` | executive | base | adds targets and forecasts; may approve and publish the report |
| `views/report-agent.yaml` | report AI agent | base | excludes board-confidential items; may only draft |

## Work

`tasks/monthly-management-report.yaml` combines two work patterns:

- `patterns/synthesize.yaml` (Summarize / Synthesize): collect results, compare them with targets and the prior period, and explain variances.
- `patterns/create-report.yaml` (Create / Generate): draft the report, have the finance controller review it, and have the executive approve it before publishing.

The task needs the executive View, the KPI definitions, and the reporting policy, and produces the report described by `artifacts/management-report.yaml`. `eval/report-approval.yaml` is the approval the report must pass.

The finance controller delegates drafting to the report agent (`delegations/report-drafting.yaml`); the agent reads BI data through `capabilities/bi-read.yaml` and cannot publish.

Task, work-pattern, artifact, knowledge, actor, role, delegation, and consumer assets are experimental (spec Appendix C).
