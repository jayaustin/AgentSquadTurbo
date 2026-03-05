# Backlog Governance

## Canonical Header

`| Task ID | Title | Description | Owner | Milestone | Status | Dependencies |`

## Rules

1. `Owner` is a single role ID from the role registry.
2. `Status` must be one of: `Todo`, `In Progress`, `Blocked`, `In Validation`, `Done`.
3. `Dependencies` is a comma-separated list of task IDs or empty.
4. Operator and non-operator roles can create and update tasks via machine-validated contracts.
5. Task selection policy is dependency-first, FIFO second.
6. Backlog execution is forbidden until project initialization gate passes.
7. `operator_plan` output must be persisted to `backlog.md` before Operator reports
   plan completion.
8. Returning task JSON in chat/console without updating `backlog.md` is invalid.
9. After backlog changes, refresh dashboard snapshot so `Tasks` view stays in sync.

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
