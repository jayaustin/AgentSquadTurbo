# AgentSquadTurbo README

AgentSquadTurbo is a local-server orchestration framework for IDE-based agent workflows.
It is an evolution of the original AgentSquad project: [jayaustin/AgentSquad](https://github.com/jayaustin/AgentSquad).

## 1. Overview

AgentSquad puts you in the role of a CEO or Executive Producer managing a team
of expert agents. You define what should be built, and `Operator` (your project
manager) decomposes that intent into right-sized backlog work, coordinates role
handoffs, and keeps execution moving in dependency-safe order.

Key ideas and value:

- Global framework assets live under `steering/`, `agents/`, and `superpowers/`.
- Project-specific state and outputs live under `project/`.
- `Operator` is the only role that interfaces directly with the human request.
- `Operator` acts as planner/orchestrator and does not own or execute backlog tasks.
- Roles run sequentially with strict context load order:
  `steering -> role -> project -> role-override -> recent-activity`.
- Each role maintains `agents/roles/<role-id>/recent_activity.md` with a
  rolling summary of its latest five tasks for fresh-context continuity.
- Backlog (`backlog.md`) is the source of truth for work ownership/status.
- Contracts are machine-validated JSON (`operator_plan`, `agent_result`) with retry-then-halt behavior.
- Persisted project truth is file-based (`.md`, `.yaml`, `.jsonl`) and surfaced through a local dashboard server (with optional static snapshots).

Execution model clarity:

- Agent turns are real adapter CLI invocations, not fake/simulated role labels.
- In the current setup, non-operator role threads can read/write project files
  if the host tool grants those permissions.
- The orchestrator still performs canonical writes for core framework artifacts
  such as backlog/state/log/dashboard updates.

## 2. Start A New Project

To use this framework for a new project:

1. Clone this repository into a new project directory.
2. Install and start the local server:

```bash
npm install
npm run dev
```

This launches the dashboard and API at `http://127.0.0.1:4173`.
3. Open the dashboard URL and complete the **Initialize** tab:
   - Fill all required project details fields and submit.
   - Optional: adjust settings and enable/disable agents in the **Project** tab.
4. Confirm your IDE assistant is supported by a functional adapter in
   [`runner/adapters/`](runner/adapters/) (look for a real implementation, not a stub).
5. Keep project/product files you want agents to manage inside this cloned
   `AgentSquad` directory (for example under `project/`, `docs/`, or another
   in-repo folder).
6. Open the cloned folder in your IDE agent environment.
7. Start a fresh IDE agent thread and use this short prompt:

```text
Read AGENTS.md and initialize this thread as AgentSquad Operator
```

8. The IDE agent should run required bootstrap commands automatically:
   - generate `project/state/operator-bootstrap.md`
   - load and follow that packet
9. Complete Operator role enablement review:
   - Operator proposes roles to disable (all roles are enabled by default)
   - You confirm one of: `apply-recommendations`, `keep-all`, or `custom`
   - Operator records confirmation in `project/config/project.yaml` (`roles.review_confirmed: true`)
10. After initialization reaches `READY`, provide your first project request.

Note: in an ideal environment, users should not manually run bootstrap CLI
steps. Initialization should be handled by the IDE agent thread.

## 3. Dashboard

AgentSquad runs a local Python dashboard server with live updates. The dashboard includes:

- `Project`: project-details form for first-run setup before IDE initialization
- `Settings`: project summary, execution policy, role counts, state/halt info
- `Documents`: browser-friendly rendering of included markdown deliverables
- `Tasks`: backlog table with sort/filter controls and live updates
- `Activity Log`: global timeline across all roles with live updates
- `Agents`: per-role tabs with role context and individual activity timeline
- `Project Settings`: direct apply to `project/config/project.yaml` (including role enable/disable)

Color accents are role-specific and configurable in
`project/config/project.yaml` under `dashboard.agent_colors`.

Structured activity events are written to:

- `project/state/activity-log.jsonl` (global)
- `project/workspaces/<role-id>/activity.jsonl` (per role)

Markdown run journals remain in `project/workspaces/<role-id>/runs/`.

Primary dashboard URL:

- `http://127.0.0.1:4173/`

Optional static export path (for offline snapshot sharing):

- `project/state/dashboard.html`

## 4. Settings Reference

This section documents the settings editable in the **Settings** tab.

### 4.1 Role Controls

- `roles.enabled` / `roles.disabled`
  - Type: list of role IDs
  - Purpose: controls which specialist agents are available for orchestration.
  - Behavior:
    - Roles in `enabled` and not in `disabled` are selectable owners for tasks.
    - Roles in `disabled` are excluded from execution selection.
    - `operator` is required and cannot be disabled.

### 4.2 Host Settings

- `host.primary_adapter`
  - Type: string enum
  - UI values:
    - `antigravity`
    - `claude-code`
    - `cline`
    - `codex`
    - `continue`
    - `cursor`
    - `gemini-code-assist`
    - `github-copilot`
    - `kiro`
    - `roo`
    - `windsurf`
  - Purpose: selects which adapter implementation the orchestrator uses for role invocations.
  - Current practical support:
    - functional: `codex`
    - others are registered but stubbed unless you implement the adapter.

- `host.adapter_command`
  - Type: string (required)
  - Purpose: shell command used to invoke the selected adapter.
  - Scope note:
    - The flag guidance below is for `host.primary_adapter: codex`.
    - Other adapter providers may use different flag names and invocation semantics.
  - Behavior:
    - must be non-empty.
    - incorrect command/value will cause invocation failures and possible orchestration halt.
  - How `exec` is handled in AgentSquadTurbo (`codex` adapter):
    - If your string includes `exec`, everything before `exec` is treated as base command args and everything after `exec` is treated as default exec args.
    - If your string omits `exec`, AgentSquadTurbo inserts `exec` automatically at runtime.
    - Backward compatibility: if `--ephemeral` is placed before `exec`, the adapter moves it into exec-args position.
    - Runtime-managed flags (`resume`, `--json`, `--output-last-message`) are appended by the adapter and should not be manually embedded in `host.adapter_command`.
  - Project default string:
    - `codex --sandbox workspace-write --ask-for-approval never exec --ephemeral`
    - What it does:
      - `codex`: selects the Codex CLI executable.
      - `--sandbox workspace-write`: allows file writes inside the workspace/repo.
      - `--ask-for-approval never`: disables interactive approval prompts.
      - `exec`: runs in non-interactive execution mode.
      - `--ephemeral`: uses ephemeral sessions for role invocations.
  - Common flags you may use (Codex-style):
    - `--sandbox workspace-write`: workspace-limited editing.
    - `--ask-for-approval never`: unattended operation without approval prompts.
    - `exec`: explicit split point between base args and exec args.
    - `--ephemeral`: fresh/ephemeral execution sessions.
    - `--add-dir <path>`: grants adapter access to an additional directory outside the repo.
    - `--dangerously-bypass-approvals-and-sandbox`: disables sandboxing and approvals entirely (extremely dangerous; use only in externally sandboxed environments).
  - Complete example command strings:
    - Default project command:
      - `codex --sandbox workspace-write --ask-for-approval never exec --ephemeral`
    - Same style with extra external directory access:
      - `codex --sandbox workspace-write --ask-for-approval never exec --ephemeral --add-dir ../shared-specs`
    - Backward-compatible style (no explicit `exec`; runtime inserts it):
      - `codex --sandbox workspace-write --ask-for-approval never --ephemeral`
    - Minimal explicit exec form (less constrained than default):
      - `codex exec --ephemeral`
    - Dangerous full-bypass example (not recommended):
      - `codex --dangerously-bypass-approvals-and-sandbox exec --ephemeral`

- `host.session_mode`
  - Type: string enum
  - Values:
    - `per-role-threads`: preserves thread/session continuity per role.
    - `stateless`: treats each invocation as isolated.
  - Purpose: controls context/session persistence strategy.

- `host.context_rot_guardrails.max_turns_per_role_session`
  - Type: integer > 0
  - Purpose: forces session turnover after N turns per role to limit stale-context drift.

- `host.context_rot_guardrails.max_session_age_minutes`
  - Type: integer > 0
  - Purpose: forces session turnover after time threshold to reduce long-lived context drift.

- `host.context_rot_guardrails.force_reload_on_context_change`
  - Type: boolean
  - Values:
    - `true`: reloads role context manifest when context inputs change.
    - `false`: allows reuse without forced reload on context-file updates.
  - Purpose: controls strictness of context freshness.

### 4.3 Execution Settings

- `execution.mode`
  - Type: string enum
  - Value:
    - `sequential`
  - Purpose: defines global orchestration execution style.
  - Note: current framework constrains execution to sequential mode.

- `execution.handoff_authority`
  - Type: string enum
  - Value:
    - `operator-mediated`
  - Purpose: requires Operator to coordinate/mediate handoff and task planning updates.

- `execution.selection_policy`
  - Type: string enum
  - Value:
    - `dependency-fifo`
  - Purpose: selects the next executable task based on dependency satisfaction and FIFO order.

- `execution.unexpected_event_policy`
  - Type: string enum
  - Values:
    - `errors-only`: continue through warnings, halt on errors.
    - `errors-or-warnings`: halt on warnings and errors.
    - `proceed`: continue despite warnings/errors unless another hard-stop condition triggers.
  - Purpose: controls strictness when unexpected events are emitted by role execution.

### 4.4 Dashboard Settings

- `dashboard.output_file`
  - Type: string path (required)
  - Purpose: target path for static dashboard rendering output.
  - Typical value:
    - `project/state/dashboard.html`

- `dashboard.refresh_policy`
  - Type: string enum
  - Value:
    - `after-every-step`
  - Purpose: controls snapshot refresh cadence for static dashboard output.

- `dashboard.failure_mode`
  - Type: string enum
  - Value:
    - `non-blocking-log`
  - Purpose: controls how dashboard write failures are handled.
  - Behavior:
    - logs warning/failure without hard-stopping orchestration.

## 5. CLI

Recommended npm commands from repository root:

```bash
npm run dev
npm run validate
npm run step
npm run run -- --request "your request"
npm run resume
```

Equivalent Python commands are still available:

```bash
python -m runner.orchestrator init
python -m runner.server
python -m runner.orchestrator bootstrap-operator --print-packet
python -m runner.orchestrator validate
python -m runner.orchestrator render-dashboard
python -m runner.orchestrator run --request "your request"
python -m runner.orchestrator step
python -m runner.orchestrator resume
```

These commands are intentionally available for manual control/troubleshooting.
In an ideal setup, most invocation is performed by Operator and role agents, not
the human.

## 6. Host Adapter

This framework was built and tested using OpenAI Codex CLI as the host adapter.
It can theoretically work with other providers if they support similar
local-CLI invocation semantics and session behavior.

Configuration:

- `host.primary_adapter` (adapter ID)
- `host.adapter_command` (local command executable)

Current adapter support status:

- Functional implementation: `codex`
- Registered stubs (not implemented): `roo`, `kiro`, `claude-code`,
  `antigravity`, `cursor`, `github-copilot`, `continue`, `cline`, `windsurf`,
  `gemini-code-assist`

If you use a non-Codex provider, you must implement and test its adapter first.

The runner passes prompt data through:

- `STDIN`
- `AGENTSQUAD_PROMPT` environment variable

## 7. Threaded Role Sessions

AgentSquad supports persistent per-role threads so context is not rebuilt from
scratch every turn.

Configure in `project/config/project.yaml`:

- `host.session_mode`: `per-role-threads` or `stateless`
- `host.context_rot_guardrails.max_turns_per_role_session`
- `host.context_rot_guardrails.max_session_age_minutes`
- `host.context_rot_guardrails.force_reload_on_context_change`
- `execution.unexpected_event_policy`: `errors-only` | `errors-or-warnings` | `proceed`

How it works:

1. Orchestrator selects the next role/task.
2. Adapter invokes that role thread via local CLI.
3. JSON contract is validated.
4. Orchestrator persists canonical state updates.
5. Dashboard/logs are refreshed.

File access behavior:

- Non-operator role threads can read/write project files in this setup (subject
  to host tool permissions/sandbox).
- Operator is not the only writer.
- Orchestrator still owns critical framework writes and validation pathways for
  backlog/state/log/dashboard consistency.
- Keeping managed files outside the `AgentSquad` repository can cause access
  failures under adapter sandbox defaults and can reduce audit visibility.
- External-path workflows may require relaxed adapter flags (`--add-dir`,
  sandbox bypass, approval changes), which increases safety and reproducibility
  risk.
- After initialization is `READY`, edits to `project/config/**`,
  `project/context/**`, and `steering/**` require explicit human approval.
- Operator invocations force full context reload (no Operator session reuse) and
  emit explicit `context_reload` log events to reduce context-rot risk.

## 8. Validation Guarantees

Validation and runtime guardrails are designed to keep orchestration safe,
deterministic, and auditable.

Framework/config integrity checks include:

- required scaffold files exist
- role files exist for enabled roles
- role frontmatter contract keys are present
- referenced superpower IDs are valid
- backlog header schema is exact
- execution policy keys are constrained (`sequential`, `operator-mediated`, `dependency-fifo`)
- unexpected-event policy value is constrained
- dashboard config shape is validated

Runtime contract and execution safeguards include:

- strict context load order enforcement
- one retry for invalid JSON, then halt with reason
- initialization gate must pass before work execution
- role review confirmation is required before initialization can become `READY`
- task ownership forbids `owner: operator`
- `operator_plan` must actually modify `backlog.md` or is rejected
- operator-mediated reassignment for invalid/disabled ownership conditions
- journaling/state persistence on each step
- best-effort dashboard refresh after key events and halt paths
