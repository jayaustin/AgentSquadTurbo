# AgentSquad v1

AgentSquad is a non-API orchestration framework for IDE-based agent workflows.
It separates global framework assets from project-specific state, and runs a
sequential, operator-mediated execution loop.

## Start a New Project

To use this framework for a new project:

1. Clone this repository into a new project directory.
2. Open the cloned folder in your IDE agent environment (for example Codex, Roo, or Kiro).
3. Start a fresh agent thread and paste this prompt:

```text
Initialize this thread as AgentSquad Operator.

Do the following in order:
1) Load and apply context from:
   - steering/00-core-rules.md
   - steering/01-context-lifecycle.md
   - steering/02-backlog-governance.md
   - steering/03-handoff-protocol.md
   - agents/roles/operator/agent-role.md
   - project/context/project-context.md
   - project/context/role-overrides/operator.md (only if it exists)
2) Validate required files exist; halt and report any missing file.
3) Read project/config/project.yaml and backlog.md.
4) Confirm active role is `operator` and summarize operating constraints.
5) Ask for my project request, then produce `operator_plan` JSON only using runner/templates/json-contracts.md.
```

After this bootstrap prompt, provide your project request in the next message.

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
python -m runner.orchestrator validate
python -m runner.orchestrator run --request "your request"
python -m runner.orchestrator step
python -m runner.orchestrator resume
```

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
