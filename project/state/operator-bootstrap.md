# Operator Bootstrap Packet

- Project ID: `sample-project`
- Project Name: `Sample Project`
- Primary Adapter: `codex`

## Mandatory Context Load Order

1. `C:/Users/jayau/Desktop/Code/AgentSquad/steering/00-core-rules.md`
1. `C:/Users/jayau/Desktop/Code/AgentSquad/steering/01-context-lifecycle.md`
1. `C:/Users/jayau/Desktop/Code/AgentSquad/steering/02-backlog-governance.md`
1. `C:/Users/jayau/Desktop/Code/AgentSquad/steering/03-handoff-protocol.md`
1. `C:/Users/jayau/Desktop/Code/AgentSquad/agents/roles/operator/agent-role.md`
1. `C:/Users/jayau/Desktop/Code/AgentSquad/project/context/project-context.md`
1. `C:/Users/jayau/Desktop/Code/AgentSquad/agents/roles/operator/recent_activity.md`

## Initialization Gate Status

Status: `BLOCKED`

Complete these items before invoking any non-Operator role:

- project/config/project.yaml: set project.id to a real project identifier.
- project/config/project.yaml: set project.name to the real project name.
- project/context/project-context.md: fill 'Project goals' with project-specific content.
- project/context/project-context.md: fill 'Target users' with project-specific content.
- project/context/project-context.md: fill 'Key constraints' with project-specific content.
- project/context/project-context.md: fill 'Primary deliverables' with project-specific content.
- project/context/project-context.md: fill 'Acceptance criteria' with project-specific content.

## What To Send Next (Copy/Paste Template)

Reply with values for all 7 fields below. Keep each answer specific and concrete.
Avoid placeholders such as `TBD`, `N/A`, or `Unknown`.

```text
project.id: <your-project-id>
project.name: <your-project-name>
Project goals: <fill-this>
Target users: <fill-this>
Key constraints: <fill-this>
Primary deliverables: <fill-this>
Acceptance criteria: <fill-this>
```

### Field Guidance

- `project.id`: A short stable ID used in logs and files. Use lowercase kebab-case. Example: `acme-subscription-optimizer`
- `project.name`: Human-readable project name shown in prompts and dashboard. Example: `Acme Subscription Optimizer`
- `Project goals`: What business or product outcomes must this project achieve? Example: `Increase paid conversions by 15% within Q3 while reducing onboarding drop-off.`
- `Target users`: Who this project is for. Include primary audience and key traits. Example: `SMB owners managing recurring billing with minimal technical staff.`
- `Key constraints`: Hard limits to respect (time, budget, tech stack, policy, compliance, etc.). Example: `Must ship in 6 weeks, no paid third-party APIs, Python + PowerShell only.`
- `Primary deliverables`: Concrete outputs expected from the framework (docs, code, tests, assets). Example: `Technical spec, UX spec, localization plan, implementation backlog, validated scripts.`
- `Acceptance criteria`: How you will decide the project is done; include measurable checks. Example: `All P1 tasks Done, QA sign-off complete, localization covers EN/ES/FR, docs approved.`

After you reply, Operator should write the values into `project/config/project.yaml` and `project/context/project-context.md`, then run role enablement review and continue initialization to `READY` after user confirmation.

## Optional Deep-Dive Intake (Recommended)

If you want stronger planning quality, ask the user for richer detail now. Use this when answers are short, ambiguous, or likely to cause rework.

### Drill Into `Project goals`
- Which measurable outcomes matter most (for example conversion, retention, revenue, quality), and what target values define success?
- What is the target timeline or milestone window for those outcomes?

### Drill Into `Target users`
- Who is the primary audience segment, and what critical problem are they trying to solve?
- What user segments are explicitly out of scope for v1?

### Drill Into `Key constraints`
- List hard constraints (time, budget, policy, compliance, integrations, tech stack) that must not be violated.
- Which tradeoffs are acceptable if conflicts occur between scope, quality, and timeline?

### Drill Into `Primary deliverables`
- List the required artifacts and outputs (specs, code, tests, dashboards, launch assets) expected for v1.
- Which deliverables are mandatory for sign-off versus optional stretch outputs?

### Drill Into `Acceptance criteria`
- What objective checks prove completion (for example tests passing, metric thresholds, stakeholder approvals)?
- Who approves completion and what evidence must be provided?

Current responses are thin for: `Project goals`, `Target users`, `Key constraints`, `Primary deliverables`, `Acceptance criteria`.
Operator should collect deeper answers before starting planning, unless the user explicitly chooses a quick-start path.

### Optional Deep-Dive Reply Template

```text
deep_intake: yes
Project goals.detail: <metrics + timeline + business outcome>
Target users.detail: <primary segment + pains + out-of-scope segments>
Key constraints.detail: <hard constraints + acceptable tradeoffs>
Primary deliverables.detail: <mandatory outputs + optional outputs>
Acceptance criteria.detail: <objective checks + approver + evidence>
```

## Role Enablement Review

All roles are enabled by default. Operator should recommend a smaller active role set for this project and wait for explicit user confirmation before proceeding.

- Current enabled roles: `166`
- Current disabled roles: `0`
- Review confirmed (`roles.review_confirmed`): `false`

Role recommendations are deferred until required project fields are complete.
After goals/users/constraints/deliverables/acceptance criteria are filled, Operator should run role review and collect user confirmation.


## Operator Procedure

1. Load mandatory context in the order above.
2. If gate is blocked, ask targeted questions and update:
   - `project/context/project-context.md`
   - `project/config/project.yaml`
3. If required fields are present but thin, run optional deep-dive intake questions before planning.
4. Run role enablement review: propose disable recommendations and wait for explicit user confirmation.
5. Update `roles.review_confirmed: true` after confirmation.
6. After initialization is READY, do not edit `project/config/**`, `project/context/**`, or `steering/**` without explicit human approval (`governance_file_edits_approved: true` or `[ALLOW-GOVERNANCE-EDITS]`).
7. Do not invoke work agents until gate is `READY`.
8. Once ready, collect user request and produce `operator_plan` JSON only.

## Enabled Roles

- `operator`
- `designer-acquisition`
- `designer-engagement`
- `designer-ux`
- `designer-ui`
- `designer-gameplay`
- `designer-economy`
- `designer-monetization`
- `designer-liveops`
- `designer-retention`
- `designer-onboarding`
- `designer-social`
- `designer-community`
- `designer-narrative`
- `designer-level`
- `designer-systems`
- `designer-combat`
- `designer-progression`
- `designer-accessibility`
- `designer-platform-web`
- `designer-platform-mobile`
- `designer-platform-console`
- `ux-researcher-discovery`
- `ux-researcher-usability`
- `ux-researcher-journey`
- `design-systems-designer`
- `interaction-designer`
- `information-architect`
- `art-director`
- `visual-designer`
- `concept-artist`
- `technical-artist`
- `sound-designer`
- `audio-director`
- `audio-implementation-designer`
- `composer`
- `voice-over-director`
- `localization-engineer`
- `localization-producer`
- `internationalization-engineer`
- `translation-quality-manager`
- `culturalization-specialist`
- `localization-qa-engineer`
- `audio-localization-engineer`
- `product-spec-writer`
- `feature-spec-writer`
- `ux-spec-writer`
- `gameplay-spec-writer`
- `economy-spec-writer`
- `monetization-spec-writer`
- `liveops-spec-writer`
- `technical-spec-writer`
- `api-spec-writer`
- `integration-spec-writer`
- `security-spec-writer`
- `test-spec-writer`
- `release-spec-writer`
- `nonfunctional-requirements-writer`
- `technical-architect`
- `solution-architect-web`
- `solution-architect-mobile`
- `solution-architect-backend`
- `gameplay-architect`
- `economy-architect`
- `systems-architect`
- `data-architect`
- `security-architect`
- `platform-architect`
- `audio-systems-architect`
- `localization-architect`
- `qa-architecture-lead`
- `test-architecture-lead`
- `development-engineer-python`
- `development-engineer-powershell`
- `development-engineer-c`
- `development-engineer-cpp`
- `development-engineer-csharp`
- `development-engineer-java`
- `development-engineer-kotlin`
- `development-engineer-swift`
- `development-engineer-javascript`
- `development-engineer-typescript`
- `development-engineer-go`
- `development-engineer-rust`
- `development-engineer-php`
- `development-engineer-ruby`
- `development-engineer-scala`
- `development-engineer-web`
- `development-engineer-frontend-react`
- `development-engineer-frontend-vue`
- `development-engineer-frontend-angular`
- `development-engineer-backend-node`
- `development-engineer-backend-dotnet`
- `development-engineer-backend-spring`
- `development-engineer-backend-django`
- `development-engineer-backend-fastapi`
- `development-engineer-mobile-ios`
- `development-engineer-mobile-android`
- `development-engineer-api`
- `development-engineer-database-sql`
- `development-engineer-database-nosql`
- `development-engineer-data-pipeline`
- `development-engineer-integration`
- `development-engineer-devops`
- `development-engineer-ci-cd`
- `development-engineer-observability`
- `development-engineer-performance`
- `development-engineer-unity`
- `development-engineer-unreal`
- `development-engineer-godot`
- `development-engineer-audio`
- `development-engineer-localization`
- `development-engineer-security`
- `development-engineer-python-gameplay`
- `development-engineer-web-acquisition`
- `development-engineer-typescript-engagement`
- `development-engineer-cpp-engine`
- `qa-manager`
- `qa-functional`
- `qa-regression`
- `qa-integration`
- `qa-system`
- `qa-end-to-end`
- `qa-automation`
- `qa-performance`
- `qa-load`
- `qa-scalability`
- `qa-reliability`
- `qa-usability`
- `qa-accessibility`
- `qa-compatibility-web`
- `qa-compatibility-mobile`
- `qa-gameplay`
- `qa-economy-balance`
- `qa-monetization`
- `qa-liveops`
- `qa-localization`
- `qa-audio`
- `qa-api`
- `qa-data-quality`
- `qa-security`
- `qa-penetration`
- `qa-compliance`
- `qa-release-readiness`
- `qa-smoke`
- `qa-exploratory`
- `qa-uat-coordinator`
- `security-engineer-application`
- `security-engineer-cloud`
- `security-engineer-infrastructure`
- `security-engineer-identity`
- `security-engineer-devsecops`
- `security-analyst-threat-modeling`
- `security-analyst-vulnerability`
- `security-code-reviewer`
- `security-architecture-reviewer`
- `security-incident-responder`
- `security-penetration-tester`
- `security-compliance-engineer`
- `security-privacy-engineer`
- `security-cryptography-engineer`
- `security-secrets-management-engineer`
- `security-detection-engineer`
- `security-red-team`
- `security-blue-team`
- `security-release-gatekeeper`

