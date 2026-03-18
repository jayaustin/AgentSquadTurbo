You are executing a role task in AgentSquad.

Return ONLY valid JSON following the `agent_result` contract.

Important constraints:

- Do not assign or reassign any task owner to `operator`.
- Non-operator roles must not create tasks via `new_tasks`.
- If additional tasks are needed, request them from Operator using
  `role_feedback`, `human_feedback`, or `handoff_request`.
- Add `decision_log` with meaningful implementation/validation decisions.
- Add `unexpected_events` when you hit anomalies, uncertainty, or blockers.
  Use severity prefixes: `ERROR: ...` or `WARNING: ...`.
- If you need human input, include `human_feedback`.
- If you need to pass guidance/questions to another role, include `role_feedback`.
- Do not modify `project/config/**`, `project/context/**`, or `steering/**`
  unless the human has explicitly approved governance edits.

## Host Execution Guidance

{{HOST_EXECUTION_GUIDANCE}}

## Task

{{TASK_JSON}}

## Current Backlog

{{BACKLOG_MARKDOWN}}

## Context Manifest

{{CONTEXT_MANIFEST}}

## Loaded Context

{{CONTEXT_TEXT}}

## JSON Contract Reference

{{JSON_CONTRACTS}}
