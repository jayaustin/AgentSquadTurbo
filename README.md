# AgentSquadTurbo

**Run a local AI org chart instead of babysitting one chat thread.**

AgentSquadTurbo turns your CLI-based or IDE-embedded AI coding assistant into an `Operator` that manages a large team of specialized agents, maintains a dependency-aware backlog, and streams the whole project into a live dashboard. You stay in charge. The bot team handles planning, routing, execution, logging, and handoffs.

Under the hood, this is a **local CLI orchestration framework** paired with **CLI and IDE agent workflows**. The local Python server/orchestrator runs on your machine, while the human-facing `Operator` can be used from a CLI agent session such as Codex CLI or from an IDE-embedded agent environment such as VS Code.

This is the pitch in plain English:

- You act like the CEO of your own team of bots.
- Work is driven through a real backlog instead of disappearing into chat history.
- A local dashboard shows what every agent did, what changed, and what happens next.

AgentSquadTurbo is local-first, file-based, and built for serious multi-agent project execution. The framework currently ships with **166 built-in agent roles** across design, UX, spec writing, architecture, engineering, QA, security, localization, and audio. That roster is a starting point, not a fixed ceiling: agent roles are fully customizable, you can extend the behavior of existing agents, and you can develop your own new agents to match your workflow.

Important reality check: this project was built and tested around **OpenAI Codex CLI**. In theory it can work with other CLI-based providers, including options like **Claude Code**, but only after the matching adapter in `runner/adapters/` is actually implemented and validated. Right now, non-Codex adapters should be treated as stubs and extension points, not drop-in replacements.

## Why It Feels Different

- `One human-facing control plane.` `Operator` is your project manager. You talk to one role; it coordinates the rest.
- `A real project ledger.` `backlog.md` is the source of truth for ownership, status, milestones, and dependencies.
- `Live visibility.` The dashboard exposes setup state, settings, documents, tasks, cross-role activity, and per-agent history.
- `Auditable output.` State is persisted in Markdown, YAML, and JSONL files inside the repo.
- `Extensible by design.` Roles are fully customizable. Built-in agents live in `agents/roles/`, reusable guidance lives in `superpowers/`, and adapters live in `runner/adapters/`.

## How It Runs

AgentSquadTurbo works as a hybrid system:

- `CLI layer`: the local Python orchestrator, validation commands, and dashboard server run from the command line.
- `Operator layer`: you can work with the `Operator` agent from a CLI session or from inside an embedded agent environment in your editor, for example VS Code with Codex.
- `Adapter layer`: specialized agent invocations are routed through `host.primary_adapter` and `host.adapter_command`, which define which assistant CLI is used behind the scenes.

That means this project is not just a prompt pack for an IDE plugin, and it is not just a headless CLI runner either. It is designed to connect both:

- local files, logs, backlog, and dashboard on disk
- a CLI or IDE-resident Operator workflow for human collaboration
- CLI-driven role execution through an adapter

## Quick Start

### Requirements

- Python 3
- Node.js and npm
- Python packages from `requirements.txt`
- One AI coding assistant with a working adapter integration
  - `Codex` is the default and tested path, so OpenAI Codex CLI should work out of the box once installed.
  - Other assistants such as `Claude Code`, `Cline`, `Cursor`, and similar tools can be used too, but only after you implement and configure a working adapter in `runner/adapters/`.
- A CLI workflow, an IDE-embedded agent workflow, or both, depending on how you want to interact with `Operator`

Best results come from keeping the files you want agents to manage **inside this repository**. External paths can fail under sandbox defaults and reduce audit/dashboard coverage.

### Setup

1. Clone this repository into a new project directory.
2. Install the local launcher dependencies:

```bash
python -m pip install -r requirements.txt
npm install
```

3. Start the local server:

```bash
npm run dev
```

4. Open the dashboard in your browser:

```text
http://127.0.0.1:4173/
```

5. Complete project setup in the dashboard:
   - In `Project`, fill in `project.id`, `project.name`, `Project goals`, `Target users`, `Key constraints`, `Primary deliverables`, and `Acceptance criteria`, then click `Submit Project Details`.
   - In `Settings`, review the adapter settings, decide which agents should stay enabled for this project, disable the roles you do not need, and click `Apply Settings` to confirm role review.
   - Remember that all built-in agents are enabled by default, and you can also customize those roles or add your own later.
6. Invoke `Operator` from either workflow:
   - `CLI workflow`: Initialize a fresh agent thread rooted in this repo and send:
   - `IDE workflow`: Open this project's directory and start a fresh agent thread:

```text
Read AGENTS.md and initialize this thread as AgentSquad Operator
```

7. Explain your project to `Operator` and ask it to turn your goals into backlog tasks with clear ownership, statuses, milestones, and dependencies.
8. When you're satisfied with the backlog, instruct `Operator` to dispatch specialized agents to execute that backlog while you monitor progress in real time through the dashboard `Tasks`, `Activity Log`, and `Agents` views.

Example first request for either CLI or IDE use:

```text
Plan and execute a v1 implementation backlog for this project. Break the work into clear tasks, assign the right specialized agents, and keep the dashboard updated as the team progresses.
```

## What Happens After Initialization

1. `Operator` runs the bootstrap flow, loads the required context files, and checks the initialization gate.
2. Your request is turned into backlog work owned by non-operator specialized agents.
3. The orchestrator selects the next executable task based on dependencies and enabled roles.
4. Specialized agents execute sequentially, return structured results, and hand control back to `Operator`.
5. The framework validates contracts, writes canonical state updates, and refreshes logs/dashboard output.

`Operator` is the only role that talks directly to the human, but it does **not** own backlog implementation tasks.

## The Three Big Selling Points

### 1. Be The CEO Of Your Own Bot Team

AgentSquadTurbo ships with a large built-in roster of specialized agents. Out of the box you have roles for:

- product and design
- UX research and UX writing
- architecture and technical planning
- implementation across many stacks
- QA and release readiness
- security and privacy
- localization and audio

All roles are enabled by default. The `Settings` tab is where you trim the roster down to the team your project actually needs. You are not locked into the included catalog either: the built-in agents are editable, their instructions can be extended, and you can create entirely new agents for project-specific workflows.

### 2. Manage The Project Through A Structured Backlog

The framework runs on `backlog.md`, not vague memory. Each task row uses this schema:

```text
Task ID | Title | Description | Owner | Milestone | Status | Dependencies
```

That gives you a simple but useful control surface:

- every task has an explicit owner
- tasks can be dependency-blocked until upstream work is `Done`
- statuses are normalized to `Todo`, `In Progress`, `Blocked`, `In Validation`, and `Done`
- `Operator` mediates handoffs instead of letting roles silently re-route work

### 3. See What Your Agents Actually Did

The local dashboard gives you a clear view of how the framework is operating:

- `Project`: first-run intake and initialization status
- `Settings`: adapter config, role selection, execution policy, and dashboard settings
- `Documents`: rendered Markdown from `README.md`, `project/context`, `project/docs`, and `docs`
- `Tasks`: sortable/filterable backlog view
- `Activity Log`: cross-role timeline backed by JSONL logs
- `Agents`: per-role context plus individual activity history

Live updates are pushed over `SSE` at `/api/events`. Useful JSON endpoints include:

- `/api/dashboard`
- `/api/project`
- `/api/tasks`
- `/api/activity`
- `/api/agents`
- `/api/settings`
- `/api/init/status`

Structured activity is persisted to:

- `project/state/activity-log.jsonl`
- `project/workspaces/<role-id>/activity.jsonl`

For `codex-cli` and `codex-vscode-agent`, native Codex subagent lifecycle events are now mirrored into those activity logs so the dashboard can show subagent spawn and completion alongside the parent role run.

Per-role run journals are written under:

- `project/workspaces/<role-id>/runs/`

The normal dashboard is the live local server. Static export to `project/state/dashboard.html` is optional.

## Settings That Matter

Most of the settings you actually care about live in `project/config/project.yaml`.

| Setting | What it controls | Practical note |
| --- | --- | --- |
| `host.primary_adapter` | Which CLI adapter runs role invocations | Default: `codex-cli`; use `codex-vscode-agent` for the original VS Code agent-backed adapter |
| `host.adapter_command` | The exact command used to invoke the adapter | Default: `codex --sandbox workspace-write --ask-for-approval never exec --ephemeral` |
| `host.session_mode` | Whether roles run statelessly or keep per-role session continuity | Valid values: `stateless`, `per-role-threads` |
| `host.context_rot_guardrails.*` | Session rollover guardrails | Controls max turns, max age, and forced reload on context change |
| `roles.enabled` / `roles.disabled` | Which specialized agents can own work | `operator` must remain enabled |
| `roles.review_confirmed` | Initialization gate confirmation for role review | The dashboard sets this when you apply role choices in `Settings` |
| `execution.unexpected_event_policy` | Whether warnings/errors force a return to human control | Valid values: `errors-only`, `errors-or-warnings`, `proceed` |
| `dashboard.enabled` | Whether AgentSquad writes the optional static dashboard snapshot during orchestration | Default: `false`; the live local server does not need this |
| `dashboard.docs.include_paths` / `dashboard.docs.exclude_globs` | Which Markdown files appear in `Documents` | Defaults cover `project/docs`, `docs`, and `project/context` |
| `dashboard.agent_colors` | Per-role dashboard accent colors | Must be unique hex colors |
| `dashboard.output_file` | Output path for optional static dashboard export | Default: `project/state/dashboard.html` |

Notes:

- The framework is intentionally constrained to `execution.mode: sequential`, `execution.handoff_authority: operator-mediated`, and `execution.selection_policy: dependency-fifo`.
- For the Codex adapters, runtime-managed flags like `resume`, `--json`, and `--output-last-message` are appended by the adapter. Do not hardcode them into `host.adapter_command`.
- If you want to use another provider, you need both a real CLI command and a real adapter implementation. For example, `host.primary_adapter: claude-code` is only viable after `runner/adapters/claude_code.py` is implemented instead of left as a stub.
- Static dashboard snapshot generation is disabled by default because the live local server reads current files directly and updates via API/SSE.
- If you choose to enable static snapshot generation, the refresh behavior is fixed to `after-every-step`, and snapshot write failures are intentionally non-blocking.

## Manual CLI Commands

Most day-to-day use should happen through the dashboard plus either a CLI Operator session or an IDE Operator thread, while the raw CLI commands remain useful for validation and troubleshooting.

### Python Commands

```bash
python -m runner.server
python -m runner.orchestrator bootstrap-operator --print-packet
python -m runner.orchestrator validate
python -m runner.orchestrator run --request "your request"
python -m runner.orchestrator step
python -m runner.orchestrator resume
python -m runner.orchestrator render-dashboard
```

Use `python -m runner.orchestrator render-dashboard` only when you explicitly want to refresh the static snapshot at `project/state/dashboard.html`.

### npm Shortcuts

```bash
npm run dev
npm run validate
npm run run -- --request "your request"
npm run step
npm run resume
```

## Repository Layout

```text
agents/                    role registry + role definitions
backlog.md                 canonical task ledger
project/config/            project settings
project/context/           shared project context and docs
project/state/             orchestration state, logs, dashboard snapshot
project/workspaces/        per-role notes, activity, and run journals
runner/                    orchestrator, local server, dashboard, adapters
steering/                  global execution and governance rules
superpowers/               reusable capability instructions referenced by roles
```

## Extending AgentSquadTurbo

You can extend the framework in three main directions:

1. Add or edit roles in `agents/roles/<role-id>/agent-role.md`, then register them in `agents/registry.yaml`.
2. Add reusable guidance in `superpowers/` and reference those superpower IDs from role frontmatter.
3. Implement new host adapters in `runner/adapters/` if you want to run on a non-Codex CLI such as Claude Code.

The included agents are meant to be a foundation, not a locked box. You can adjust existing role behavior, add brand-new roles, and combine that with custom adapters if you want the framework to fit a different stack or provider model.

The dashboard automatically picks up project Markdown from the configured document include paths, so project-specific docs can become visible without building a separate UI.

## Guardrails And Current Limits

- The built-in Codex adapters are `codex-cli` and `codex-vscode-agent`. The legacy adapter ID `codex` is still accepted as an alias for backward compatibility.
- Other providers can be supported in principle, but only if their adapter stubs are filled out and tested. That includes `claude-code`, which is currently registered but not implemented.
- Execution is intentionally sequential. This framework optimizes for traceability and predictable handoffs, not maximum parallelism.
- `operator` cannot own backlog tasks.
- After initialization is `READY`, edits to `project/config/**`, `project/context/**`, and `steering/**` require explicit human approval.
- Validation checks cover backlog schema, enabled-role integrity, role frontmatter, config shape, and dashboard config.
- Invalid runtime contracts trigger retry-then-halt behavior instead of silent corruption.
