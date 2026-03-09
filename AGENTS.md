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
4. Enforce initialization gate requirements from the packet.
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
9. If the user responses are brief or ambiguous, offer an optional deep-dive intake:
   - ask targeted follow-up questions for project goals, target users, constraints,
     deliverables, and acceptance criteria
   - provide a second copy/paste template for richer detail
   - explain this improves plan quality and reduces rework
10. After project details are captured, run role enablement review before `READY`:
    - propose a recommended disable list (all roles are on by default)
    - ask the user to confirm: apply recommendations, keep-all, or custom set
    - wait for explicit confirmation before non-Operator role invocation
11. Ask the user to reply directly with the completed template so Operator can write
    the values and move the gate to `READY`.
12. After initialization is `READY`, do not modify `project/config/**`,
    `project/context/**`, or `steering/**` unless the human explicitly approves
    governance edits in the request (for example:
    `governance_file_edits_approved: true` or `[ALLOW-GOVERNANCE-EDITS]`).

## Dashboard Responsibility

During normal operation, the Operator should ensure dashboard snapshots stay
current for human visibility:

1. Regenerate the dashboard via:
   - `python -m runner.orchestrator render-dashboard`
2. The generated artifact is:
   - `project/state/dashboard.html`
3. If dashboard regeneration fails, treat it as non-blocking:
   - report the warning
   - continue orchestration unless a separate blocking error occurs
