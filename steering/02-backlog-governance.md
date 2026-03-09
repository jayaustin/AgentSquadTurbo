# Backlog Governance

## Canonical Header

`| Task ID | Title | Description | Owner | Milestone | Status | Dependencies |`

## Rules

1. `Owner` is a single non-operator role ID from the role registry.
2. `Status` must be one of: `Todo`, `In Progress`, `Blocked`, `In Validation`, `Done`.
3. `Dependencies` is a comma-separated list of task IDs or empty.
4. Only Operator can create backlog tasks. Non-operator roles must send open-task
   requests to Operator, and Operator must parse each request into one or more
   backlog tasks.
5. Operator and non-operator roles can update existing tasks via machine-validated
   contracts.
6. Task selection policy is dependency-first, FIFO second.
7. Backlog execution is forbidden until project initialization gate passes.
8. `operator_plan` output must be persisted to `backlog.md` before Operator reports
   plan completion.
9. Returning task JSON in chat/console without updating `backlog.md` is invalid.
10. After backlog changes, refresh dashboard snapshot so `Tasks` view stays in sync.
11. Any attempt to set `owner: operator` (by Operator or non-Operator roles) is invalid.

## Initialization and Backlog

Operator may draft or refine backlog items during initialization discovery, but
must not invoke implementation/validation roles until required context/config
fields are complete.

## Required Persistence Checklist (Operator)

For every accepted `operator_plan`:

1. Upsert tasks into `backlog.md`.
2. Verify backlog header and statuses remain valid.
3. Record the update in run journal/workspace logs.
4. Regenerate `project/state/dashboard.html`.
5. Return a completion message that references updated files.

## Sequencing Authority

1. Operator is responsible for dependency-safe sequencing of backlog tasks.
2. Operator may request specialist-role or human feedback on sequencing when dependency
   order or milestone grouping is uncertain.
3. Sequencing decisions must be reflected in backlog dependencies and role order
   before non-operator execution continues.
