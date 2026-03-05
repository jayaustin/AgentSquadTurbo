# AgentSquad v1

AgentSquad is a non-API orchestration framework for IDE-based agent workflows.
It separates global framework assets from project-specific state, and runs a
sequential, operator-mediated execution loop.

## Start a New Project

To use this framework for a new project:

1. Clone this repository into a new project directory.
2. Open the cloned folder in your IDE agent environment (for example Codex, Roo, or Kiro).
3. Start a fresh IDE agent thread and use this short prompt:

```text
Read AGENTS.md and initialize this thread as AgentSquad Operator
```

4. The IDE agent should run all required bootstrap CLI commands automatically:
   - generate `project/state/operator-bootstrap.md`
   - load and follow the generated bootstrap packet
5. Answer the Operator's initialization questions and let it update:
   - `project/context/project-context.md`
   - `project/config/project.yaml`
   - If the gate is blocked, Operator should provide a copy/paste intake template
     with all required fields, definitions, and examples.
6. Only after initialization is complete, provide your first project request.

Note: users should not need to run command-line steps to initialize Operator.
Initialization should be fully handled by the IDE agent thread.

During orchestration, AgentSquad auto-generates a browser dashboard snapshot at:

- `project/state/dashboard.html`

Open that file directly in any browser (`file://`) to inspect project state.

## Core Ideas

- Global framework assets live under `steering/`, `agents/`, and `superpowers/`.
- Project-specific assets live under `project/`.
- `Operator` is the only role that interfaces directly with the human request.
- Roles execute sequentially with strict context load order:
  `steering -> role -> project -> role-override`.
- Backlog is the source of truth for work ownership and status.

## CLI

Run commands from repository root:

```bash
python -m runner.orchestrator init
python -m runner.orchestrator bootstrap-operator --print-packet
python -m runner.orchestrator validate
python -m runner.orchestrator render-dashboard
python -m runner.orchestrator run --request "your request"
python -m runner.orchestrator step
python -m runner.orchestrator resume
```

## Dashboard

AgentSquad renders a no-server, dark-mode dashboard snapshot after operator and
step execution events. The dashboard includes:

- `Project`: project summary, execution policy, role counts, state/halt info
- `Documents`: browser-friendly rendering of included markdown deliverables
- `Tasks`: backlog table with sort/filter controls
- `Activity Log`: global timeline across all roles
- `Agents`: per-role tabs with role context and individual activity timeline

Color accents are role-specific and configurable in
`project/config/project.yaml` under `dashboard.agent_colors`.

Structured activity events are written to:

- `project/state/activity-log.jsonl` (global)
- `project/workspaces/<role-id>/activity.jsonl` (per role)

Markdown run journals remain in `project/workspaces/<role-id>/runs/`.

## Host Adapter

This framework is API-free. It invokes a local assistant command configured in
`project/config/project.yaml` at:

- `host.primary_adapter` (`codex`, `roo`, `kiro`)
- `host.adapter_command` (shell command that reads prompt input and writes JSON)

The runner passes prompt data through:

- `STDIN`
- `AGENTSQUAD_PROMPT` environment variable

## Threaded Role Sessions

AgentSquad supports persistent per-role Codex threads so Operator does not need
to repeatedly rebuild role context every turn.

Configure in `project/config/project.yaml`:

- `host.session_mode`: `per-role-threads` or `stateless`
- `host.context_rot_guardrails.max_turns_per_role_session`
- `host.context_rot_guardrails.max_session_age_minutes`
- `host.context_rot_guardrails.force_reload_on_context_change`

When `per-role-threads` is enabled, the runner tracks role session IDs in
`project/state/orchestrator-state.yaml` and automatically refreshes sessions
when guardrails trigger (turn count, age, or context hash change).

## Validation Guarantees

- Role files exist for every enabled role.
- Role frontmatter includes required contract keys.
- Referenced superpower IDs are valid.
- Backlog header matches the required schema.
- Project config matches required keys and fixed execution policies.
