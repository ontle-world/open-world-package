# Enterprise World

## Definition

An intentionally incomplete enterprise representation designed for reusable task views and explicit source/action bindings.

## Interface boundary

Inbound sources can include ERP, MES, QMS, CRM, documents, APIs, events, and human observations.

Outbound bindings can include controlled API writes, approvals, workflows, notifications, and business commits.

Keep:

```text
Source Record != Observation != State
API Success != Business Commit != Realized World Change
```

## Validity and limitations

This package does not require copying all enterprise data into a single graph or database.

## Default World View

The starter includes `views/default.yaml` and `state/default-compiler.yaml` so enterprise task projections and state compilation remain explicit without forcing authors to design them from scratch.
