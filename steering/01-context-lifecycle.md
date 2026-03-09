# Context Lifecycle

## Mandatory Load Order

1. `steering/*.md` (sorted lexicographically)
2. `agents/roles/<role-id>/agent-role.md`
3. `project/context/project-context.md`
4. `project/context/role-overrides/<role-id>.md` (if present)
5. `agents/roles/<role-id>/recent_activity.md`

The project phase in this load order means project files relevant to the active
role invocation, including `project-context.md` and optional role overrides.

## Invariants

1. A role invocation must record the full load manifest before execution.
2. Existing active role context must be unloaded before loading a new role.
3. If any required context file is missing, execution halts immediately.
4. Context switches must be logged to role run journals and orchestration state.
5. `recent_activity.md` must contain a high-level summary of the five most
   recent tasks handled by that role.
6. `recent_activity.md` is refreshed after each role invocation and is loaded
   as the final context artifact to reduce context-rot risk for fresh sessions.
7. Operator must reload full context before every Operator invocation (no
   Operator session reuse) and log each reload event.

## Contract Source and Validation

1. Contracts are defined in `runner/templates/json-contracts.md`.
2. During invocation prompt assembly, this contracts document is loaded and
   injected into the active prompt.
3. Returned JSON is machine-validated by `runner/contracts.py`.
4. If payload parsing/validation fails, the runner retries once and then halts
   with an explicit reason in orchestration state.

## Post-Invocation Write Order

After an invocation returns a valid contract, Operator must execute writes in this order:

1. Persist critical markdown artifacts (`backlog.md`, context/spec docs as applicable).
2. Persist workspace/run logs.
3. Regenerate dashboard snapshot at `project/state/dashboard.html`.
4. Respond to the user with persisted outcomes (not console-only output).

## Preconditions Before First Invocation

1. Operator must run the project initialization gate before creating an
   `operator_plan`.
2. If required project context fields are empty or placeholder values, halt.
3. If mandatory config values are not project-specific, halt.
