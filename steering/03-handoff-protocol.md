# Handoff Protocol

## Authority Model

Operator-mediated only.

## Flow

1. A role identifies a block, dependency issue, or feedback need.
2. The role emits a `handoff_request` in `agent_result`.
3. Runner invokes `Operator` with handoff context.
4. Operator adjusts backlog ownership/dependencies/order as needed.
5. Operator persists handoff changes to `backlog.md` and related docs.
6. Operator refreshes dashboard snapshot.
7. Runner resumes sequential execution from updated backlog state.

## Halt Conditions

1. Handoff request references unknown role.
2. Operator response is invalid JSON after one retry.
3. Reassignment still targets disabled role and no valid alternative is provided.
