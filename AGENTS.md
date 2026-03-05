# AgentSquad Thread Bootstrap

When a user says:

`Initialize this thread as AgentSquad Operator`

do the following before any planning or task execution:

1. Run:
   - `py -3 -m runner.orchestrator bootstrap-operator --print-packet`
2. Read:
   - `project/state/operator-bootstrap.md`
3. Load all context files listed in that packet in order.
4. Enforce initialization gate requirements from the packet.
5. Do not invoke non-Operator roles until the initialization gate is `READY`.
6. Do not ask the user to run CLI bootstrap commands manually; the agent must run
   required bootstrap CLI steps itself.
7. If bootstrap command execution fails, report the exact failure and propose the
   minimum corrective action.
