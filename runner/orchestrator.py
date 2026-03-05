"""AgentSquad orchestration CLI."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import backlog_store, context_loader, contracts, logging_store, validators
from .adapters import AdapterError, build_adapter


DEFAULT_STATUSES = ["Todo", "In Progress", "Blocked", "In Validation", "Done"]
INITIALIZATION_REQUIRED_CONTEXT_FIELDS = (
    "Project goals",
    "Target users",
    "Key constraints",
    "Primary deliverables",
    "Acceptance criteria",
)
UNSET_VALUE_MARKERS = {"", "tbd", "todo", "n/a", "na", "unknown"}
DEFAULT_OPERATOR_BOOTSTRAP_PACKET = "project/state/operator-bootstrap.md"

ROLE_DEFINITIONS: dict[str, dict[str, Any]] = {
    "operator": {
        "display_name": "Operator",
        "mission": "Translate human requests into executable task plans and orchestrate role execution.",
        "authority_level": "primary-interface",
        "must_superpowers": [
            "brainstorming",
            "writing-plans",
            "subagent-driven-development",
            "requesting-code-review",
        ],
        "optional_superpowers": ["systematic-debugging", "using-git-worktrees"],
        "inputs": ["human_request", "backlog_snapshot", "orchestration_state"],
        "outputs": ["operator_plan", "backlog_updates"],
        "handoff_rules": ["mediate_all_handoffs", "enforce_sequential_execution"],
    },
    "designer-acquisition": {
        "display_name": "Designer Acquisition",
        "mission": "Optimize design decisions for user acquisition outcomes.",
        "authority_level": "domain-owner",
        "must_superpowers": ["brainstorming", "writing-plans"],
        "optional_superpowers": ["requesting-code-review", "systematic-debugging"],
        "inputs": ["acquisition_goals", "user_research", "current_experience"],
        "outputs": ["design_recommendations", "prioritized_tasks"],
        "handoff_rules": ["request_operator_mediation_when_blocked"],
    },
    "designer-engagement": {
        "display_name": "Designer Engagement",
        "mission": "Optimize design for sustained user activity and repeat usage.",
        "authority_level": "domain-owner",
        "must_superpowers": ["brainstorming", "writing-plans"],
        "optional_superpowers": ["requesting-code-review", "systematic-debugging"],
        "inputs": ["engagement_goals", "behavioral_signals", "current_experience"],
        "outputs": ["engagement_design_recommendations", "prioritized_tasks"],
        "handoff_rules": ["request_operator_mediation_when_blocked"],
    },
    "art-director": {
        "display_name": "Art Director",
        "mission": "Maintain artistic coherence and approve visual direction.",
        "authority_level": "top-level-authority",
        "must_superpowers": ["brainstorming", "writing-plans"],
        "optional_superpowers": ["requesting-code-review"],
        "inputs": ["brand_direction", "visual_assets", "design_proposals"],
        "outputs": ["art_requirements", "approvals_or_revisions"],
        "handoff_rules": ["request_operator_mediation_when_blocked"],
    },
    "technical-architect": {
        "display_name": "Technical Architect",
        "mission": "Define and govern technical architecture and constraints.",
        "authority_level": "top-level-authority",
        "must_superpowers": ["brainstorming", "writing-plans", "requesting-code-review"],
        "optional_superpowers": ["systematic-debugging", "using-git-worktrees"],
        "inputs": ["product_requirements", "system_constraints", "engineering_feedback"],
        "outputs": ["architecture_decisions", "technical_task_breakdown"],
        "handoff_rules": ["request_operator_mediation_when_blocked"],
    },
    "development-engineer-python": {
        "display_name": "Development Engineer Python",
        "mission": "Implement and maintain Python deliverables with strong quality controls.",
        "authority_level": "implementation-owner",
        "must_superpowers": [
            "test-driven-development",
            "requesting-code-review",
            "systematic-debugging",
        ],
        "optional_superpowers": ["writing-plans", "subagent-driven-development"],
        "inputs": ["technical_spec", "assigned_backlog_task", "test_requirements"],
        "outputs": ["code_changes", "test_results"],
        "handoff_rules": ["request_operator_mediation_when_blocked"],
    },
    "development-engineer-powershell": {
        "display_name": "Development Engineer PowerShell",
        "mission": "Implement and maintain PowerShell deliverables with strong quality controls.",
        "authority_level": "implementation-owner",
        "must_superpowers": [
            "test-driven-development",
            "requesting-code-review",
            "systematic-debugging",
        ],
        "optional_superpowers": ["writing-plans", "subagent-driven-development"],
        "inputs": ["technical_spec", "assigned_backlog_task", "test_requirements"],
        "outputs": ["script_changes", "test_results"],
        "handoff_rules": ["request_operator_mediation_when_blocked"],
    },
    "qa-manager": {
        "display_name": "QA Manager",
        "mission": "Own validation strategy, test coverage, and release confidence.",
        "authority_level": "top-level-authority",
        "must_superpowers": [
            "test-driven-development",
            "requesting-code-review",
            "systematic-debugging",
        ],
        "optional_superpowers": ["writing-plans"],
        "inputs": ["implementation_artifacts", "acceptance_criteria", "risk_assessment"],
        "outputs": ["validation_results", "release_readiness"],
        "handoff_rules": ["request_operator_mediation_when_blocked"],
    },
    "localization-engineer": {
        "display_name": "Localization Engineer",
        "mission": "Define localization strategy and ensure language readiness.",
        "authority_level": "domain-owner",
        "must_superpowers": ["brainstorming", "writing-plans", "requesting-code-review"],
        "optional_superpowers": ["systematic-debugging"],
        "inputs": ["content_inventory", "target_locales", "release_plan"],
        "outputs": ["localization_plan", "localization_tasks"],
        "handoff_rules": ["request_operator_mediation_when_blocked"],
    },
    "product-manager": {
        "display_name": "Product Manager",
        "mission": "Own product strategy, business priorities, and monetization direction.",
        "authority_level": "top-level-authority",
        "must_superpowers": ["brainstorming", "writing-plans"],
        "optional_superpowers": ["requesting-code-review"],
        "inputs": ["market_goals", "business_constraints", "user_feedback"],
        "outputs": ["product_plan", "prioritized_business_tasks"],
        "handoff_rules": ["request_operator_mediation_when_blocked"],
    },
    "data-analyst": {
        "display_name": "Data Analyst",
        "mission": "Analyze available data and provide actionable cross-role recommendations.",
        "authority_level": "domain-owner",
        "must_superpowers": ["brainstorming", "writing-plans", "systematic-debugging"],
        "optional_superpowers": ["requesting-code-review"],
        "inputs": ["analytics_data", "operational_metrics", "experiment_results"],
        "outputs": ["analytical_findings", "recommended_actions"],
        "handoff_rules": ["request_operator_mediation_when_blocked"],
    },
}

STEERING_SEEDS = {
    "00-core-rules.md": (
        "# Core Rules\n\n"
        "1. Follow backlog ownership and dependency constraints.\n"
        "2. Keep execution sequential.\n"
        "3. Use operator-mediated handoffs.\n"
    ),
    "01-context-lifecycle.md": (
        "# Context Lifecycle\n\n"
        "Load order: steering -> role -> project -> role-override.\n"
    ),
    "02-backlog-governance.md": (
        "# Backlog Governance\n\n"
        "Use canonical backlog schema and allowed statuses only.\n"
    ),
    "03-handoff-protocol.md": (
        "# Handoff Protocol\n\n"
        "Handoffs must be mediated by Operator.\n"
    ),
}


class OrchestrationHalt(RuntimeError):
    """Raised when orchestration must halt."""


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def repo_root() -> Path:
    return Path.cwd()


def _default_state() -> dict[str, Any]:
    return {
        "run_id": "",
        "active_role": None,
        "context_manifest": [],
        "role_sequence": [],
        "last_completed_task_id": "",
        "current_request": "",
        "halted": False,
        "halt_reason": "",
        "role_sessions": {},
        "history": [],
    }


def _write_if_missing(path: Path, content: str) -> bool:
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True


def _role_frontmatter_content(role_id: str, meta: dict[str, Any]) -> str:
    def block_list(items: list[str]) -> str:
        return "\n".join(f"  - {item}" for item in items)

    return (
        "---\n"
        f"role_id: {role_id}\n"
        f"display_name: {meta['display_name']}\n"
        f"mission: {meta['mission']}\n"
        f"authority_level: {meta['authority_level']}\n"
        "must_superpowers:\n"
        f"{block_list(meta['must_superpowers'])}\n"
        "optional_superpowers:\n"
        f"{block_list(meta['optional_superpowers'])}\n"
        "inputs:\n"
        f"{block_list(meta['inputs'])}\n"
        "outputs:\n"
        f"{block_list(meta['outputs'])}\n"
        "handoff_rules:\n"
        f"{block_list(meta['handoff_rules'])}\n"
        "---\n\n"
        f"# {meta['display_name']} Role\n\n"
        f"{meta['mission']}\n"
    )


def _registry_seed() -> str:
    lines = ["roles:"]
    for role_id, meta in ROLE_DEFINITIONS.items():
        lines.append(f"  {role_id}:")
        lines.append(f"    display_name: {meta['display_name']}")
        lines.append(f"    role_file: agents/roles/{role_id}/agent-role.md")
    return "\n".join(lines) + "\n"


def _project_config_seed() -> dict[str, Any]:
    return {
        "project": {"id": "sample-project", "name": "Sample Project"},
        "host": {
            "primary_adapter": "codex",
            "adapter_command": "codex",
            "session_mode": "per-role-threads",
            "context_rot_guardrails": {
                "max_turns_per_role_session": 8,
                "max_session_age_minutes": 240,
                "force_reload_on_context_change": True,
            },
        },
        "roles": {"enabled": list(ROLE_DEFINITIONS.keys()), "disabled": []},
        "execution": {
            "mode": "sequential",
            "handoff_authority": "operator-mediated",
            "selection_policy": "dependency-fifo",
        },
        "backlog": {"statuses": DEFAULT_STATUSES},
    }


def seed_scaffold(root: Path) -> list[Path]:
    created: list[Path] = []
    root.mkdir(parents=True, exist_ok=True)

    if _write_if_missing(root / "README.md", "# AgentSquad v1\n"):
        created.append(root / "README.md")
    if _write_if_missing(root / "backlog.md", backlog_store.render_backlog([])):
        created.append(root / "backlog.md")

    for file_name, content in STEERING_SEEDS.items():
        path = root / "steering" / file_name
        if _write_if_missing(path, content):
            created.append(path)

    registry_path = root / "agents" / "registry.yaml"
    if _write_if_missing(registry_path, _registry_seed()):
        created.append(registry_path)

    for role_id, meta in ROLE_DEFINITIONS.items():
        role_path = root / "agents" / "roles" / role_id / "agent-role.md"
        if _write_if_missing(role_path, _role_frontmatter_content(role_id, meta)):
            created.append(role_path)

    project_config_path = root / "project" / "config" / "project.yaml"
    if not project_config_path.exists():
        validators.write_yaml_file(project_config_path, _project_config_seed())
        created.append(project_config_path)

    project_context_path = root / "project" / "context" / "project-context.md"
    if _write_if_missing(
        project_context_path,
        "# Project Context\n\nUse this file for project-specific context shared by all roles.\n",
    ):
        created.append(project_context_path)

    role_overrides_keep = root / "project" / "context" / "role-overrides" / ".gitkeep"
    if _write_if_missing(role_overrides_keep, "\n"):
        created.append(role_overrides_keep)

    state_path = root / "project" / "state" / "orchestrator-state.yaml"
    if not state_path.exists():
        validators.write_yaml_file(state_path, _default_state())
        created.append(state_path)

    for role_id, meta in ROLE_DEFINITIONS.items():
        notes_path = root / "project" / "workspaces" / role_id / "notes.md"
        if _write_if_missing(
            notes_path,
            f"# {meta['display_name']} Notes\n\nProject-specific notes for `{role_id}`.\n",
        ):
            created.append(notes_path)
        runs_keep = root / "project" / "workspaces" / role_id / "runs" / ".gitkeep"
        if _write_if_missing(runs_keep, "\n"):
            created.append(runs_keep)

    template_files = {
        "operator-plan-prompt.md": "Return operator_plan JSON only.\n",
        "agent-task-prompt.md": "Return agent_result JSON only.\n",
        "json-contracts.md": "# JSON Contracts\n",
    }
    for file_name, content in template_files.items():
        template_path = root / "runner" / "templates" / file_name
        if _write_if_missing(template_path, content):
            created.append(template_path)

    return created


def _state_path(root: Path) -> Path:
    return root / "project" / "state" / "orchestrator-state.yaml"


def load_state(root: Path) -> dict[str, Any]:
    state = _default_state()
    path = _state_path(root)
    if not path.exists():
        return state
    loaded = validators.load_data_file(path)
    if not isinstance(loaded, dict):
        return state
    state.update(loaded)
    if not isinstance(state.get("context_manifest"), list):
        state["context_manifest"] = []
    if not isinstance(state.get("role_sequence"), list):
        state["role_sequence"] = []
    if not isinstance(state.get("role_sessions"), dict):
        state["role_sessions"] = {}
    if not isinstance(state.get("history"), list):
        state["history"] = []
    return state


def save_state(root: Path, state: dict[str, Any]) -> None:
    validators.write_yaml_file(_state_path(root), state)


def halt_with_reason(root: Path, state: dict[str, Any], reason: str) -> None:
    state["halted"] = True
    state["halt_reason"] = reason
    state["history"].append({"ts": utc_now(), "event": "halt", "reason": reason})
    save_state(root, state)


def _render_template(template_text: str, replacements: dict[str, str]) -> str:
    rendered = template_text
    for key, value in replacements.items():
        rendered = rendered.replace(f"{{{{{key}}}}}", value)
    return rendered


def _load_template(root: Path, file_name: str) -> str:
    return (root / "runner" / "templates" / file_name).read_text(encoding="utf-8")


def _parse_utc(value: str | None) -> datetime | None:
    if not value:
        return None
    raw = value.strip()
    if not raw:
        return None
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        parsed = datetime.fromisoformat(raw)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def _session_guardrails(runtime: dict[str, Any]) -> dict[str, Any]:
    defaults = {
        "max_turns_per_role_session": 8,
        "max_session_age_minutes": 240,
        "force_reload_on_context_change": True,
    }
    configured = runtime.get("context_rot_guardrails", {})
    if not isinstance(configured, dict):
        configured = {}
    merged = dict(defaults)
    merged.update(configured)
    return merged


def _resolve_role_session_plan(
    runtime: dict[str, Any],
    state: dict[str, Any],
    role_id: str,
    context_hash: str,
) -> dict[str, Any]:
    mode = runtime.get("session_mode", "per-role-threads")
    if mode != "per-role-threads":
        return {
            "mode": mode,
            "reuse": False,
            "session_id": None,
            "refresh_reasons": ["stateless-mode"],
            "full_context_required": True,
        }

    role_sessions = state.setdefault("role_sessions", {})
    session_record = role_sessions.get(role_id, {})
    session_id = str(session_record.get("session_id", "")).strip()
    if not session_id:
        return {
            "mode": mode,
            "reuse": False,
            "session_id": None,
            "refresh_reasons": ["missing-session"],
            "full_context_required": True,
        }

    guardrails = _session_guardrails(runtime)
    reasons: list[str] = []
    if bool(guardrails.get("force_reload_on_context_change", True)):
        previous_hash = str(session_record.get("context_hash", "")).strip()
        if previous_hash and previous_hash != context_hash:
            reasons.append("context-changed")

    max_turns = int(guardrails.get("max_turns_per_role_session", 8))
    turn_count = int(session_record.get("turn_count", 0) or 0)
    if max_turns > 0 and turn_count >= max_turns:
        reasons.append("max-turns-reached")

    max_age_minutes = int(guardrails.get("max_session_age_minutes", 240))
    created_at = _parse_utc(str(session_record.get("created_at", "")))
    if max_age_minutes > 0 and created_at is not None:
        age_minutes = (datetime.now(timezone.utc) - created_at).total_seconds() / 60.0
        if age_minutes >= max_age_minutes:
            reasons.append("max-age-reached")

    reuse = not reasons
    return {
        "mode": mode,
        "reuse": reuse,
        "session_id": session_id if reuse else None,
        "refresh_reasons": reasons if reasons else ["session-reuse"],
        "full_context_required": not reuse,
    }


def _persist_role_session(
    state: dict[str, Any],
    role_id: str,
    session_id: str | None,
    context_hash: str,
    reused_existing: bool,
) -> None:
    if not session_id:
        return
    role_sessions = state.setdefault("role_sessions", {})
    previous = role_sessions.get(role_id, {})
    now = utc_now()
    previous_turns = int(previous.get("turn_count", 0) or 0)
    created_at = previous.get("created_at") if reused_existing else now
    turn_count = previous_turns + 1 if reused_existing else 1
    role_sessions[role_id] = {
        "session_id": session_id,
        "created_at": created_at,
        "last_used_at": now,
        "turn_count": turn_count,
        "context_hash": context_hash,
    }


def _load_role_context(root: Path, state: dict[str, Any], role_id: str) -> list[context_loader.ContextEntry]:
    active_role = state.get("active_role")
    manifest = state.get("context_manifest", [])
    if active_role and not manifest:
        raise OrchestrationHalt(
            "Context state inconsistent: active_role is set while context_manifest is empty."
        )
    if active_role is not None and active_role != role_id:
        state["active_role"] = None
        state["context_manifest"] = []
        if state.get("active_role") is not None:
            raise OrchestrationHalt("Failed to unload prior role context.")

    built_manifest = context_loader.build_manifest(root, role_id)
    state["active_role"] = role_id
    state["context_manifest"] = context_loader.manifest_paths(built_manifest)
    if state.get("active_role") != role_id or not state.get("context_manifest"):
        raise OrchestrationHalt("Failed to load role context.")
    return built_manifest


def _invoke_with_retry(
    runtime: dict[str, Any],
    state: dict[str, Any],
    role_id: str,
    prompt: str,
    contract_type: str,
    statuses: list[str],
    known_roles: set[str],
    context_hash: str,
    session_plan: dict[str, Any],
) -> tuple[dict[str, Any], str, list[str]]:
    strict_suffix = (
        "\n\nSTRICT RETRY: return exactly one JSON object with no markdown, no prose, "
        "and no trailing text."
    )
    last_exc: Exception | None = None
    last_raw = ""
    adapter = runtime["adapter"]
    command = runtime["adapter_command"]
    session_id = session_plan.get("session_id")
    refresh_reasons = list(session_plan.get("refresh_reasons", []))
    reused_existing = bool(session_plan.get("reuse", False))

    for attempt in (1, 2):
        candidate_prompt = prompt if attempt == 1 else prompt + strict_suffix
        result = adapter.invoke_with_session(
            command=command,
            prompt=candidate_prompt,
            session_id=session_id,
        )
        raw = result.output
        last_raw = raw
        if result.session_id:
            session_id = result.session_id
        try:
            payload = contracts.parse_json_payload(raw)
            if contract_type == "operator_plan":
                parsed = contracts.validate_operator_plan(payload, statuses, known_roles)
            elif contract_type == "agent_result":
                parsed = contracts.validate_agent_result(payload, statuses, known_roles)
            else:
                raise ValueError(f"Unknown contract_type '{contract_type}'.")
            if runtime.get("session_mode") == "per-role-threads":
                _persist_role_session(
                    state=state,
                    role_id=role_id,
                    session_id=session_id,
                    context_hash=context_hash,
                    reused_existing=reused_existing,
                )
            session_events = []
            if runtime.get("session_mode") == "per-role-threads":
                if session_id:
                    session_events.append(f"session_id={session_id}")
                session_events.extend([f"session_policy={reason}" for reason in refresh_reasons])
            else:
                session_events.append("session_policy=stateless-mode")
            return parsed, raw, session_events
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
    raise OrchestrationHalt(
        f"Invalid {contract_type} after one retry: {last_exc}. Raw output: {last_raw}"
    )


def _runtime(root: Path) -> dict[str, Any]:
    config = validators.load_project_config(root)
    registry = validators.load_registry(root)
    roles_map = registry["roles"]
    known_roles = set(roles_map.keys())
    enabled_roles = set(config["roles"]["enabled"])
    disabled_roles = set(config["roles"]["disabled"])
    statuses = list(config["backlog"]["statuses"])
    adapter_name = str(config["host"]["primary_adapter"])
    adapter_command = str(config["host"]["adapter_command"])
    session_mode = str(config["host"].get("session_mode", "per-role-threads"))
    context_rot_guardrails = config["host"].get("context_rot_guardrails", {})
    adapter = build_adapter(adapter_name)
    return {
        "config": config,
        "roles_map": roles_map,
        "known_roles": known_roles,
        "enabled_roles": enabled_roles,
        "disabled_roles": disabled_roles,
        "statuses": statuses,
        "adapter": adapter,
        "adapter_command": adapter_command,
        "session_mode": session_mode,
        "context_rot_guardrails": context_rot_guardrails,
    }


def _is_value_defined(raw_value: str) -> bool:
    normalized = (raw_value or "").strip().lower()
    return normalized not in UNSET_VALUE_MARKERS


def _extract_project_context_value(context_text: str, field_label: str) -> str:
    pattern = rf"^- {re.escape(field_label)}:[ \t]*(.*)$"
    match = re.search(pattern, context_text, flags=re.MULTILINE)
    if not match:
        return ""
    return match.group(1).strip()


def _project_initialization_issues(root: Path, runtime: dict[str, Any]) -> list[str]:
    issues: list[str] = []

    config = runtime["config"]
    project = config.get("project", {})
    project_id = str(project.get("id", "")).strip()
    project_name = str(project.get("name", "")).strip()
    if not _is_value_defined(project_id) or project_id == "sample-project":
        issues.append("project/config/project.yaml: set project.id to a real project identifier.")
    if not _is_value_defined(project_name) or project_name.lower() == "sample project":
        issues.append("project/config/project.yaml: set project.name to the real project name.")

    host = config.get("host", {})
    adapter_command = str(host.get("adapter_command", "")).strip()
    if not _is_value_defined(adapter_command) or "REPLACE_WITH_LOCAL_ASSISTANT_COMMAND" in adapter_command:
        issues.append(
            "project/config/project.yaml: set host.adapter_command to a working local command."
        )

    roles = config.get("roles", {})
    enabled_roles = roles.get("enabled", [])
    if not isinstance(enabled_roles, list) or not enabled_roles:
        issues.append("project/config/project.yaml: roles.enabled must include at least one role.")

    context_path = root / "project" / "context" / "project-context.md"
    if not context_path.exists():
        issues.append("project/context/project-context.md is missing.")
        return issues

    context_text = context_path.read_text(encoding="utf-8")
    for field_label in INITIALIZATION_REQUIRED_CONTEXT_FIELDS:
        value = _extract_project_context_value(context_text, field_label)
        if not _is_value_defined(value):
            issues.append(
                "project/context/project-context.md: "
                f"fill '{field_label}' with project-specific content."
            )

    return issues


def _operator_bootstrap_packet(
    root: Path,
    config: dict[str, Any],
    init_issues: list[str],
    manifest_paths: list[str],
) -> str:
    project = config.get("project", {})
    host = config.get("host", {})
    roles = config.get("roles", {})
    lines: list[str] = []
    lines.append("# Operator Bootstrap Packet")
    lines.append("")
    lines.append(f"- Project ID: `{project.get('id', '')}`")
    lines.append(f"- Project Name: `{project.get('name', '')}`")
    lines.append(f"- Primary Adapter: `{host.get('primary_adapter', '')}`")
    lines.append("")
    lines.append("## Mandatory Context Load Order")
    lines.append("")
    for path in manifest_paths:
        lines.append(f"1. `{path}`")
    lines.append("")
    lines.append("## Initialization Gate Status")
    lines.append("")
    if init_issues:
        lines.append("Status: `BLOCKED`")
        lines.append("")
        lines.append("Complete these items before invoking any non-Operator role:")
        lines.append("")
        for issue in init_issues:
            lines.append(f"- {issue}")
    else:
        lines.append("Status: `READY`")
        lines.append("")
        lines.append("Project context and mandatory config are complete.")
    lines.append("")
    lines.append("## Operator Procedure")
    lines.append("")
    lines.append("1. Load mandatory context in the order above.")
    lines.append("2. If gate is blocked, ask targeted questions and update:")
    lines.append("   - `project/context/project-context.md`")
    lines.append("   - `project/config/project.yaml`")
    lines.append("3. Do not invoke work agents until gate is `READY`.")
    lines.append("4. Once ready, collect user request and produce `operator_plan` JSON only.")
    lines.append("")
    lines.append("## Enabled Roles")
    lines.append("")
    enabled_roles = roles.get("enabled", [])
    if isinstance(enabled_roles, list) and enabled_roles:
        for role_id in enabled_roles:
            lines.append(f"- `{role_id}`")
    else:
        lines.append("- None")
    lines.append("")
    return "\n".join(lines) + "\n"


def cmd_bootstrap_operator(args: argparse.Namespace) -> int:
    root = repo_root()
    errors = validators.validate_framework(root)
    if errors:
        print("Validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    config = validators.load_project_config(root)
    init_issues = _project_initialization_issues(root, {"config": config})
    manifest = context_loader.build_manifest(root, "operator")
    manifest_paths = context_loader.manifest_paths(manifest)

    packet = _operator_bootstrap_packet(root, config, init_issues, manifest_paths)
    output_path = root / args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(packet, encoding="utf-8")

    print(f"Operator bootstrap packet written to: {output_path.as_posix()}")
    if init_issues:
        print(f"Initialization gate: BLOCKED ({len(init_issues)} item(s))")
    else:
        print("Initialization gate: READY")
    print("Recommended short prompt:")
    print("Initialize this thread as AgentSquad Operator")

    if args.print_packet:
        print("")
        print(packet)
    return 0


def _upsert_backlog_from_operator(root: Path, plan_payload: dict[str, Any]) -> list[dict[str, Any]]:
    backlog_path = root / "backlog.md"
    existing = backlog_store.read_backlog(backlog_path)
    updated = backlog_store.upsert_tasks(existing, plan_payload["tasks"])
    backlog_store.write_backlog(backlog_path, updated)
    return updated


def _invoke_operator(
    root: Path,
    runtime: dict[str, Any],
    state: dict[str, Any],
    human_request: str,
    mode_label: str,
) -> list[dict[str, Any]]:
    backlog_path = root / "backlog.md"
    current_tasks = backlog_store.read_backlog(backlog_path)
    backlog_before = backlog_store.render_backlog(current_tasks)

    manifest = _load_role_context(root, state, "operator")
    context_hash = context_loader.manifest_hash(manifest)
    session_plan = _resolve_role_session_plan(
        runtime=runtime,
        state=state,
        role_id="operator",
        context_hash=context_hash,
    )
    if session_plan["full_context_required"]:
        context_text = context_loader.compose_context_text(manifest)
    else:
        context_text = (
            "Reuse existing operator thread context. "
            "Load context files again only if inconsistency is detected."
        )
    manifest_text = "\n".join(f"- {path}" for path in context_loader.manifest_paths(manifest))
    template = _load_template(root, "operator-plan-prompt.md")
    contracts_doc = _load_template(root, "json-contracts.md")

    prompt = _render_template(
        template,
        {
            "HUMAN_REQUEST": human_request,
            "BACKLOG_MARKDOWN": backlog_before,
            "CONTEXT_MANIFEST": manifest_text,
            "CONTEXT_TEXT": context_text,
            "JSON_CONTRACTS": contracts_doc,
        },
    )

    parsed, raw_output, session_events = _invoke_with_retry(
        runtime=runtime,
        state=state,
        role_id="operator",
        prompt=prompt,
        contract_type="operator_plan",
        statuses=runtime["statuses"],
        known_roles=runtime["known_roles"],
        context_hash=context_hash,
        session_plan=session_plan,
    )

    updated_tasks = _upsert_backlog_from_operator(root, parsed)
    backlog_after = backlog_store.render_backlog(updated_tasks)
    state["role_sequence"] = parsed["initial_role_sequence"]
    state["history"].append(
        {
            "ts": utc_now(),
            "event": "operator-invoke",
            "mode": mode_label,
            "tasks_generated": len(parsed["tasks"]),
        }
    )
    logging_store.write_run_journal(
        root=root,
        role_id="operator",
        task_id=f"operator-{mode_label}",
        prompt_template="operator-plan-prompt.md",
        context_manifest=context_loader.manifest_paths(manifest),
        raw_output=raw_output,
        parsed_result=parsed,
        backlog_before=backlog_before,
        backlog_after=backlog_after,
        events=[f"mode={mode_label}", "operator_plan parsed"] + session_events,
    )
    return updated_tasks


def _apply_agent_result(
    tasks: list[dict[str, Any]],
    result: dict[str, Any],
    statuses: list[str],
    known_roles: set[str],
) -> list[dict[str, Any]]:
    status_set = set(statuses)
    task_id = result["task_id"]
    target = None
    for task in tasks:
        if task["task_id"] == task_id:
            target = task
            break
    if target is None:
        raise OrchestrationHalt(f"agent_result references unknown task_id '{task_id}'.")

    target["status"] = result["status"]
    updates = result.get("updates", {})
    if updates:
        for key in ("title", "description", "owner", "milestone", "status", "dependencies"):
            if key not in updates:
                continue
            if key == "dependencies":
                target["dependencies"] = backlog_store.normalize_task(
                    {"dependencies": updates[key]}
                )["dependencies"]
                continue
            target[key] = str(updates[key]).strip()

    if target["status"] not in status_set:
        raise OrchestrationHalt(f"Invalid status after updates: '{target['status']}'.")
    if target["owner"] not in known_roles:
        raise OrchestrationHalt(f"Invalid owner after updates: '{target['owner']}'.")

    if result.get("new_tasks"):
        tasks = backlog_store.upsert_tasks(tasks, result["new_tasks"])
    return tasks


def _handle_disabled_owner_if_needed(
    root: Path,
    runtime: dict[str, Any],
    state: dict[str, Any],
    tasks: list[dict[str, Any]],
) -> bool:
    task_index = backlog_store.index_by_task_id(tasks)
    for task in tasks:
        if task["status"] not in {"Todo", "In Progress"}:
            continue
        if task["owner"] not in runtime["disabled_roles"]:
            continue
        if not backlog_store.dependencies_satisfied(task, task_index):
            continue
        request = (
            f"Task '{task['task_id']}' currently owned by disabled role '{task['owner']}'. "
            "Reassign ownership and update dependencies as needed."
        )
        _invoke_operator(root, runtime, state, request, "disabled-owner-mediation")
        return True
    return False


def execute_one_step(root: Path, runtime: dict[str, Any], state: dict[str, Any]) -> bool:
    backlog_path = root / "backlog.md"
    tasks = backlog_store.read_backlog(backlog_path)
    if not tasks:
        raise OrchestrationHalt("Backlog is empty. Operator must create tasks first.")
    if backlog_store.all_done(tasks):
        return False

    if _handle_disabled_owner_if_needed(root, runtime, state, tasks):
        save_state(root, state)
        return True

    next_task = backlog_store.select_next_task(
        tasks=tasks,
        enabled_roles=runtime["enabled_roles"],
        role_priority=state.get("role_sequence", []),
    )
    if next_task is None:
        remaining = backlog_store.remaining_not_done(tasks)
        if remaining:
            raise OrchestrationHalt(
                "No executable tasks found. Remaining tasks are blocked by dependencies or role availability."
            )
        return False

    task_id = next_task["task_id"]
    owner = next_task["owner"]
    if owner not in runtime["enabled_roles"]:
        raise OrchestrationHalt(
            f"Task '{task_id}' owner '{owner}' is not enabled and could not be mediated."
        )

    backlog_before = backlog_store.render_backlog(tasks)
    if next_task["status"] == "Todo":
        next_task["status"] = "In Progress"
        backlog_store.write_backlog(backlog_path, tasks)

    manifest = _load_role_context(root, state, owner)
    context_hash = context_loader.manifest_hash(manifest)
    session_plan = _resolve_role_session_plan(
        runtime=runtime,
        state=state,
        role_id=owner,
        context_hash=context_hash,
    )
    if session_plan["full_context_required"]:
        context_text = context_loader.compose_context_text(manifest)
    else:
        context_text = (
            "Reuse existing role thread context. "
            "Reload full role context only when guardrails trigger refresh."
        )
    manifest_text = "\n".join(f"- {path}" for path in context_loader.manifest_paths(manifest))
    template = _load_template(root, "agent-task-prompt.md")
    contracts_doc = _load_template(root, "json-contracts.md")
    prompt = _render_template(
        template,
        {
            "TASK_JSON": json.dumps(next_task, indent=2),
            "BACKLOG_MARKDOWN": backlog_before,
            "CONTEXT_MANIFEST": manifest_text,
            "CONTEXT_TEXT": context_text,
            "JSON_CONTRACTS": contracts_doc,
        },
    )

    parsed, raw_output, session_events = _invoke_with_retry(
        runtime=runtime,
        state=state,
        role_id=owner,
        prompt=prompt,
        contract_type="agent_result",
        statuses=runtime["statuses"],
        known_roles=runtime["known_roles"],
        context_hash=context_hash,
        session_plan=session_plan,
    )

    updated_tasks = _apply_agent_result(tasks, parsed, runtime["statuses"], runtime["known_roles"])
    backlog_store.write_backlog(backlog_path, updated_tasks)

    if parsed.get("handoff_request"):
        handoff = parsed["handoff_request"]
        request = (
            f"Handoff requested by '{owner}' for task '{task_id}'. "
            f"Target role: '{handoff['target_role']}'. Reason: {handoff['reason']}."
        )
        updated_tasks = _invoke_operator(root, runtime, state, request, "handoff-mediation")
        backlog_store.write_backlog(backlog_path, updated_tasks)

    backlog_after = backlog_store.render_backlog(backlog_store.read_backlog(backlog_path))
    events = [f"task={task_id}", f"owner={owner}", f"status={parsed['status']}"]
    if parsed.get("handoff_request"):
        events.append("handoff mediated by operator")
    events.extend(session_events)
    logging_store.write_run_journal(
        root=root,
        role_id=owner,
        task_id=task_id,
        prompt_template="agent-task-prompt.md",
        context_manifest=context_loader.manifest_paths(manifest),
        raw_output=raw_output,
        parsed_result=parsed,
        backlog_before=backlog_before,
        backlog_after=backlog_after,
        events=events,
    )

    if parsed["status"] == "Done":
        state["last_completed_task_id"] = task_id
    state["history"].append(
        {"ts": utc_now(), "event": "task-step", "task_id": task_id, "owner": owner}
    )
    save_state(root, state)
    return True


def execute_loop(root: Path, runtime: dict[str, Any], state: dict[str, Any], max_steps: int | None) -> int:
    executed = 0
    while True:
        if max_steps is not None and executed >= max_steps:
            break
        tasks = backlog_store.read_backlog(root / "backlog.md")
        if tasks and backlog_store.all_done(tasks):
            state["halted"] = False
            state["halt_reason"] = ""
            save_state(root, state)
            break
        progressed = execute_one_step(root, runtime, state)
        if not progressed:
            break
        executed += 1
    return executed


def cmd_init(args: argparse.Namespace) -> int:
    root = repo_root()
    created = seed_scaffold(root)
    print(f"Initialized scaffold. Created {len(created)} paths.")
    for path in created:
        print(path.as_posix())
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    root = repo_root()
    errors = validators.validate_framework(root)
    if errors:
        print("Validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("Validation passed.")
    return 0


def _prepare_runtime_or_exit(root: Path) -> dict[str, Any]:
    errors = validators.validate_framework(root)
    if errors:
        joined = "\n".join(f"- {item}" for item in errors)
        raise OrchestrationHalt(f"Validation failed before execution:\n{joined}")
    runtime = _runtime(root)
    init_issues = _project_initialization_issues(root, runtime)
    if init_issues:
        joined = "\n".join(f"- {item}" for item in init_issues)
        raise OrchestrationHalt(
            "Project initialization is incomplete. Operator cannot invoke agent work yet.\n"
            "Complete required project context/config first:\n"
            f"{joined}"
        )
    return runtime


def cmd_run(args: argparse.Namespace) -> int:
    root = repo_root()
    state = load_state(root)
    state["run_id"] = utc_now()
    state["halted"] = False
    state["halt_reason"] = ""
    state["current_request"] = args.request
    save_state(root, state)

    try:
        runtime = _prepare_runtime_or_exit(root)
        _invoke_operator(root, runtime, state, args.request, "initial-plan")
        executed = execute_loop(root, runtime, state, max_steps=None)
        save_state(root, state)
        print(f"Run completed. Steps executed: {executed}")
        return 0
    except KeyboardInterrupt:
        halt_with_reason(root, state, "Interrupted by user.")
        print("Run interrupted and state persisted.")
        return 1
    except (OrchestrationHalt, AdapterError, contracts.ContractError, context_loader.ContextLoadError) as exc:
        halt_with_reason(root, state, str(exc))
        print(f"Run halted: {exc}")
        return 1


def cmd_step(args: argparse.Namespace) -> int:
    root = repo_root()
    state = load_state(root)
    try:
        runtime = _prepare_runtime_or_exit(root)
        if not state.get("current_request") and not backlog_store.read_backlog(root / "backlog.md"):
            raise OrchestrationHalt("No active request and backlog is empty. Use run --request first.")
        state["halted"] = False
        state["halt_reason"] = ""
        save_state(root, state)
        executed = execute_loop(root, runtime, state, max_steps=1)
        save_state(root, state)
        print(f"Step completed. Steps executed: {executed}")
        return 0
    except (OrchestrationHalt, AdapterError, contracts.ContractError, context_loader.ContextLoadError) as exc:
        halt_with_reason(root, state, str(exc))
        print(f"Step halted: {exc}")
        return 1


def cmd_resume(args: argparse.Namespace) -> int:
    root = repo_root()
    state = load_state(root)
    try:
        runtime = _prepare_runtime_or_exit(root)
        state["halted"] = False
        state["halt_reason"] = ""
        save_state(root, state)
        executed = execute_loop(root, runtime, state, max_steps=None)
        save_state(root, state)
        print(f"Resume completed. Steps executed: {executed}")
        return 0
    except KeyboardInterrupt:
        halt_with_reason(root, state, "Interrupted by user.")
        print("Resume interrupted and state persisted.")
        return 1
    except (OrchestrationHalt, AdapterError, contracts.ContractError, context_loader.ContextLoadError) as exc:
        halt_with_reason(root, state, str(exc))
        print(f"Resume halted: {exc}")
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AgentSquad orchestrator CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    init_parser = sub.add_parser("init", help="Create missing scaffold files.")
    init_parser.set_defaults(func=cmd_init)

    bootstrap_parser = sub.add_parser(
        "bootstrap-operator",
        help="Generate Operator bootstrap packet for short-prompt initialization.",
    )
    bootstrap_parser.add_argument(
        "--output",
        default=DEFAULT_OPERATOR_BOOTSTRAP_PACKET,
        help="Output markdown packet path relative to repository root.",
    )
    bootstrap_parser.add_argument(
        "--print-packet",
        action="store_true",
        help="Print generated bootstrap packet to stdout.",
    )
    bootstrap_parser.set_defaults(func=cmd_bootstrap_operator)

    validate_parser = sub.add_parser("validate", help="Validate framework integrity.")
    validate_parser.set_defaults(func=cmd_validate)

    run_parser = sub.add_parser("run", help="Run full orchestration from a human request.")
    run_parser.add_argument("--request", required=True, help="Human request text.")
    run_parser.set_defaults(func=cmd_run)

    step_parser = sub.add_parser("step", help="Execute one orchestration step.")
    step_parser.set_defaults(func=cmd_step)

    resume_parser = sub.add_parser("resume", help="Resume orchestration from persisted state.")
    resume_parser.set_defaults(func=cmd_resume)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
