# Core Rules

## Purpose

Define universal behavior for all roles in this framework.

## Rules

1. Follow the backlog as the source of truth for work ownership and status.
2. Keep execution sequential; never run multiple roles in parallel.
3. Respect dependency order before starting a task.
4. Use operator-mediated handoff for cross-role blocking and feedback.
5. Halt execution when required context cannot be loaded.
6. Do not bypass validation for contract shape or status transitions.
7. Do not begin agent task execution until project initialization is complete.
8. Treat file persistence as part of completion: critical outputs are not complete
   until written to the required `.md` files.
9. After critical file updates, regenerate `project/state/dashboard.html` so the
   browser view reflects current project truth.

## Project Initialization Gate

Before any agent work can start, Operator must confirm:

1. `project/context/project-context.md` has concrete values for:
   `Project goals`, `Target users`, `Key constraints`, `Primary deliverables`,
   and `Acceptance criteria`.
2. `project/config/project.yaml` has project-specific values for `project.id`
   and `project.name`.
3. `host.adapter_command` is configured to a working local command.
4. At least one role is enabled in `roles.enabled`.

## Persistence Requirement

For Operator turns that produce plans, tasks, or governance decisions:

1. Update canonical files first (for example `backlog.md` and context/spec docs).
2. Confirm those writes succeeded.
3. Regenerate dashboard snapshot (`py -3 -m runner.orchestrator render-dashboard`).
4. Only then report completion to the user.
