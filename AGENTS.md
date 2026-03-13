# AgentSquad Thread Bootstrap

When a user says:

`Read AGENTS.md and initialize this thread as AgentSquad Operator`

or

`Initialize this thread as AgentSquad Operator`

do the following before any planning or task execution:

1. Run:
   - `python -m runner.orchestrator bootstrap-operator --print-packet`
2. Read:
   - `project/state/operator-bootstrap.md`
3. Load all context files listed in that packet in order.
4. Check initialization tasks in order and enforce gate requirements from the packet:
   - Project setup complete (Project tab fields submitted)
   - Role review complete (Settings tab reviewed + confirmed)
5. Do not invoke non-Operator roles until the initialization gate is `READY`.
6. Do not ask the user to run CLI bootstrap commands manually; the agent must run
   required bootstrap CLI steps itself.
7. If bootstrap command execution fails, report the exact failure and propose the
   minimum corrective action.
8. If the initialization gate is `BLOCKED`, do not return only a terse missing-fields
   list. Return a guided intake response with:
   - plain-language explanation of each required field
   - one concrete example value per field
   - a copy/paste reply template for all 7 required fields
   - explicit direction to open the dashboard `Project` tab
   - offer to draft candidate field text for the user
9. If the user responses are brief or ambiguous, offer an optional deep-dive intake:
   - ask targeted follow-up questions for project goals, target users, constraints,
     deliverables, and acceptance criteria
   - provide a second copy/paste template for richer detail
   - explain this improves plan quality and reduces rework
10. After project details are captured, run role enablement review before `READY`:
    - direct user to the dashboard `Settings` tab
    - propose a recommended disable list (all roles are on by default)
    - offer to generate recommendations from project goals/users/constraints/deliverables
    - ask the user to confirm: apply recommendations, keep-all, or custom set
    - wait for explicit confirmation before non-Operator role invocation
11. Ask the user to reply directly with the completed template so Operator can write
    the values and move the gate to `READY`.
12. After initialization is `READY`, do not modify `project/config/**`,
    `project/context/**`, or `steering/**` unless the human explicitly approves
    governance edits in the request (for example:
    `governance_file_edits_approved: true` or `[ALLOW-GOVERNANCE-EDITS]`).

## Dashboard Responsibility

For the local server version of AgentSquadTurbo:

1. Do **not** manually regenerate the dashboard during normal operation.
2. The local Python server provides live dashboard data via API/SSE.
3. Use `python -m runner.orchestrator render-dashboard` only when a static
   snapshot file is explicitly requested.
