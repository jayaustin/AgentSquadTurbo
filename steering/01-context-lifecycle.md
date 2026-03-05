# Context Lifecycle

## Mandatory Load Order

1. `steering/*.md` (sorted lexicographically)
2. `agents/roles/<role-id>/agent-role.md`
3. `project/context/project-context.md`
4. `project/context/role-overrides/<role-id>.md` (if present)

## Invariants

1. A role invocation must record the full load manifest before execution.
2. Existing active role context must be unloaded before loading a new role.
3. If any required context file is missing, execution halts immediately.
4. Context switches must be logged to role run journals and orchestration state.

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
