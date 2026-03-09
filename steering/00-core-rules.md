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
8. After initialization is `READY`, no agent (including Operator) may change
   project definitions, project config, or steering files without explicit human
   permission. Protected paths:
   - `project/context/**`
   - `project/config/**`
   - `steering/**`
9. Treat file persistence as part of completion: critical outputs are not complete
   until written to the required `.md` files.
10. After critical file updates, regenerate `project/state/dashboard.html` so the
   browser view reflects current project truth.
11. Operator acts as project manager/orchestrator and never executes specialist
    backlog tasks.
12. Task ownership `owner: operator` is forbidden for all roles.

## Logging Requirements

1. Every backlog modification must be logged with task-level detail describing
   what changed.
2. Every file modification must produce a dedicated log line with:
   - file path
   - brief explanation of what changed
3. Operator must log role dispatch (`role + task`) and role return
   (`role + resulting status/summary`) for each execution turn.
4. If a role needs human input, the role must write a local feedback artifact
   file and log the artifact path.
   - Artifact file path: `project/workspaces/<source-role>/feedback/<timestamp>-<task-id>-to-human.md`
   - Log locations: `project/state/activity-log.jsonl` and
     `project/workspaces/<source-role>/activity.jsonl`
5. If a role needs to pass feedback/questions to another role, it must write a
   local feedback artifact file and log the artifact path.
   - Artifact file path:
     `project/workspaces/<source-role>/feedback/<timestamp>-<task-id>-to-<target-role>.md`
   - Log locations: `project/state/activity-log.jsonl` and
     `project/workspaces/<source-role>/activity.jsonl`
6. Unexpected events must be logged explicitly as warnings/errors.
7. Unexpected-event return behavior is controlled by:
   - `project/config/project.yaml` -> `execution.unexpected_event_policy`
   - Allowed values:
     - `errors-only`: return control to user on errors, continue on warnings.
     - `errors-or-warnings`: return control to user on errors or warnings.
     - `proceed`: proceed when possible and only log warnings/errors.
8. Decision logs should capture meaningful decisions, assumptions, and tradeoff
   choices made during task execution.
9. All logged date-time values use `YYYY-MM-DD HH:MM:SS`.

## Project Initialization Gate

Before any agent work can start, Operator must confirm:

1. `project/context/project-context.md` has concrete values for:
   `Project goals`, `Target users`, `Key constraints`, `Primary deliverables`,
   and `Acceptance criteria`.
2. `project/config/project.yaml` has project-specific values for `project.id`
   and `project.name`.
3. `host.adapter_command` is configured to a working local command.
4. At least one role is enabled in `roles.enabled`.
5. If initialization answers are present but too brief/ambiguous, Operator should
   run optional deep-dive intake questions before planning to reduce avoidable
   backlog churn and rework.
6. Operator must perform role enablement review and obtain explicit user
   confirmation before initialization is `READY`:
   - all roles start enabled by default
   - based on project description, Operator should recommend which roles to disable
   - `roles.review_confirmed` must be set to `true` after confirmation

## Persistence Requirement

For Operator turns that produce plans, tasks, or governance decisions:

1. Update canonical files first (for example `backlog.md` and context/spec docs).
2. Confirm those writes succeeded.
3. Regenerate dashboard snapshot (`python -m runner.orchestrator render-dashboard`).
4. Only then report completion to the user with a summary and reference
   `project/state/dashboard.html`.
