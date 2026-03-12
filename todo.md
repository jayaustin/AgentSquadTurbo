# AgentSquad Local Server Migration TODO (Draft for Approval)

## Requested Changes To Implement
- [ ] Replace the current serverless snapshot flow with a local Python server that drives orchestration and dashboard data.
- [ ] Make onboarding npm-first so a new user can run `npm install` and an `npm run` command to get started.
- [ ] Change Project tab Settings so changes are applied directly from the dashboard (no copy/paste prompt to Operator).
- [ ] Support direct enable/disable of agent roles from dashboard settings and persist those changes to `project/config/project.yaml`.
- [ ] Make Tasks and Activity Log tabs update live as files change (no waiting for `project/state/dashboard.html` regeneration).

## Current-State Findings (from code/doc review)
- [ ] `runner/dashboard.py` builds a static payload and writes a full snapshot HTML file.
- [ ] `runner/templates/dashboard.html` boots from embedded constant `DATA = {{DASHBOARD_PAYLOAD_JSON}}`.
- [ ] Project settings UI currently validates in browser and only generates a "Prompt for Operator"; it does not write config files.
- [ ] Orchestrator persists canonical state in files (`backlog.md`, `project/state/orchestrator-state.yaml`, JSONL logs) and then calls best-effort dashboard render.
- [ ] Activity and workspace logs are file-backed (`project/state/activity-log.jsonl`, `project/workspaces/<role>/activity.jsonl`) and suitable for server-side streaming/polling.

## Proposed Implementation Plan

### Phase 1: Introduce a Local Python Server Layer
- [ ] Add a new server entrypoint (e.g., `runner/server.py`) using Python stdlib HTTP server + JSON API.
- [ ] Add read endpoints to serve live data from current files:
  - [ ] `GET /api/project`
  - [ ] `GET /api/tasks`
  - [ ] `GET /api/activity`
  - [ ] `GET /api/agents`
  - [ ] `GET /api/settings`
- [ ] Add write endpoint for direct settings apply:
  - [ ] `PATCH /api/settings` (updates `project/config/project.yaml`, including `roles.enabled` + `roles.disabled`)
- [ ] Add orchestration control endpoints (initially minimal):
  - [ ] `POST /api/orchestrator/validate`
  - [ ] `POST /api/orchestrator/step`
  - [ ] `POST /api/orchestrator/run`
  - [ ] `POST /api/orchestrator/resume`
- [ ] Add request serialization/locking so settings writes and orchestration steps do not race.

### Phase 2: Live Update Channel
- [ ] Add live event stream endpoint (SSE) e.g., `GET /api/events`.
- [ ] Emit/poll change events when these files change:
  - [ ] `backlog.md`
  - [ ] `project/state/activity-log.jsonl`
  - [ ] `project/state/orchestrator-state.yaml`
  - [ ] `project/config/project.yaml`
  - [ ] `project/workspaces/*/activity.jsonl`
- [ ] Define event types (`tasks_changed`, `activity_changed`, `state_changed`, `settings_changed`) and payload shape.

### Phase 3: Convert Dashboard Frontend to Server-Driven Mode
- [ ] Update `runner/templates/dashboard.html` to fetch initial data from API instead of relying only on embedded snapshot data.
- [ ] Add client-side EventSource subscription to `/api/events`.
- [ ] On events, refresh only affected sections:
  - [ ] Tasks tab on `tasks_changed`
  - [ ] Activity Log tab on `activity_changed`
  - [ ] Project/Agents metadata on `state_changed` or `settings_changed`
- [ ] Replace "Prompt for Operator" settings flow with direct apply flow:
  - [ ] Add "Apply Settings" button
  - [ ] Send validated payload to `PATCH /api/settings`
  - [ ] Display success/failure inline status
  - [ ] Keep role toggles wired into same apply operation

### Phase 4: npm-First Developer Experience
- [ ] Add `package.json` at repo root with scripts for new users.
- [ ] Add a Node launcher script (cross-platform) that starts Python server module.
- [ ] Provide npm scripts (proposed):
  - [ ] `npm run dev` -> start local dashboard/orchestration server
  - [ ] `npm run validate` -> run framework validation
  - [ ] `npm run step` -> execute one orchestration step
  - [ ] `npm run run -- --request "..."` -> start full run
- [ ] Keep Python dependency footprint minimal (prefer stdlib).
- [ ] Update README quickstart to: clone -> `npm install` -> `npm run dev`.

### Phase 5: Compatibility + Quality Gates
- [ ] Preserve existing CLI commands and file formats (backward compatibility).
- [ ] Keep `python -m runner.orchestrator render-dashboard` as optional static export path.
- [ ] Add basic tests for settings apply validation and API payload integrity.
- [ ] Add a manual smoke checklist for:
  - [ ] settings apply updates `project/config/project.yaml`
  - [ ] role toggles persist
  - [ ] tasks update in UI after step/run
  - [ ] activity events appear without page reload

## Suggested Execution Order
- [ ] 1) Server scaffolding + read APIs
- [ ] 2) Settings write API + validation + locking
- [ ] 3) Dashboard frontend API integration
- [ ] 4) SSE live updates
- [ ] 5) npm scripts + README refresh
- [ ] 6) Testing and stabilization

## Risks / Watchouts
- [ ] Concurrent writes between server-triggered orchestration and manual CLI runs can conflict; enforce lock strategy.
- [ ] Large activity logs may require paging/limits in API for performance.
- [ ] Settings writes must preserve existing config constraints enforced by `runner/validators.py`.
- [ ] Windows path handling and shell quoting must be tested in npm launch scripts.
