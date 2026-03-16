"""AgentSquad orchestration CLI."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import backlog_store, context_loader, contracts, dashboard, logging_store, validators
from .adapters import AdapterError, build_adapter


DEFAULT_STATUSES = ["Todo", "In Progress", "Blocked", "In Validation", "Done"]
INITIALIZATION_REQUIRED_CONTEXT_FIELDS = (
    "Project goals",
    "Target users",
    "Key constraints",
    "Primary deliverables",
    "Acceptance criteria",
)
INITIALIZATION_INTAKE_GUIDANCE: tuple[tuple[str, str, str], ...] = (
    (
        "project.id",
        "A short stable ID used in logs and files. Use lowercase kebab-case.",
        "acme-subscription-optimizer",
    ),
    (
        "project.name",
        "Human-readable project name shown in prompts and dashboard.",
        "Acme Subscription Optimizer",
    ),
    (
        "Project goals",
        "What business or product outcomes must this project achieve?",
        "Increase paid conversions by 15% within Q3 while reducing onboarding drop-off.",
    ),
    (
        "Target users",
        "Who this project is for. Include primary audience and key traits.",
        "SMB owners managing recurring billing with minimal technical staff.",
    ),
    (
        "Key constraints",
        "Hard limits to respect (time, budget, tech stack, policy, compliance, etc.).",
        "Must ship in 6 weeks, no paid third-party APIs, Python + PowerShell only.",
    ),
    (
        "Primary deliverables",
        "Concrete outputs expected from the framework (docs, code, tests, assets).",
        "Technical spec, UX spec, localization plan, implementation backlog, validated scripts.",
    ),
    (
        "Acceptance criteria",
        "How you will decide the project is done; include measurable checks.",
        "All P1 tasks Done, QA sign-off complete, localization covers EN/ES/FR, docs approved.",
    ),
)
INITIALIZATION_DETAIL_MIN_WORDS = 8
INITIALIZATION_DETAIL_MIN_CHARS = 48
INITIALIZATION_DEEP_DIVE_QUESTIONS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "Project goals",
        (
            "Which measurable outcomes matter most (for example conversion, retention, revenue, quality), and what target values define success?",
            "What is the target timeline or milestone window for those outcomes?",
        ),
    ),
    (
        "Target users",
        (
            "Who is the primary audience segment, and what critical problem are they trying to solve?",
            "What user segments are explicitly out of scope for v1?",
        ),
    ),
    (
        "Key constraints",
        (
            "List hard constraints (time, budget, policy, compliance, integrations, tech stack) that must not be violated.",
            "Which tradeoffs are acceptable if conflicts occur between scope, quality, and timeline?",
        ),
    ),
    (
        "Primary deliverables",
        (
            "List the required artifacts and outputs (specs, code, tests, dashboards, launch assets) expected for v1.",
            "Which deliverables are mandatory for sign-off versus optional stretch outputs?",
        ),
    ),
    (
        "Acceptance criteria",
        (
            "What objective checks prove completion (for example tests passing, metric thresholds, stakeholder approvals)?",
            "Who approves completion and what evidence must be provided?",
        ),
    ),
)
ROLE_REVIEW_CONFIRMATION_KEY = "review_confirmed"
ROLE_REVIEW_PENDING_ISSUE = (
    "project/config/project.yaml: roles.review_confirmed must be true after Operator "
    "presents role enable/disable recommendations and receives explicit user confirmation."
)
ROLE_REVIEW_CORE_KEEP = {"operator"}
UNEXPECTED_EVENT_POLICY_VALUES = {"errors-only", "errors-or-warnings", "proceed"}
DEFAULT_UNEXPECTED_EVENT_POLICY = "errors-only"
PROTECTED_GOVERNANCE_PATH_PREFIXES = (
    "project/config/",
    "project/context/",
    "steering/",
)
GOVERNANCE_EDIT_APPROVAL_PATTERNS = (
    r"(?i)\[allow-governance-edits\]",
    r"(?i)\bgovernance_file_edits_approved\s*:\s*(true|yes)\b",
    r"(?i)\bapprove\.governance_file_edits\s*:\s*(true|yes)\b",
)
ROLE_REVIEW_TOKEN_STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "that",
    "this",
    "from",
    "into",
    "your",
    "their",
    "about",
    "must",
    "should",
    "will",
    "have",
    "need",
    "needs",
    "work",
    "works",
    "project",
    "role",
    "roles",
    "agent",
    "agents",
    "team",
    "user",
    "users",
    "using",
    "based",
    "across",
    "through",
    "while",
    "before",
    "after",
    "into",
    "only",
}
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
    }
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
        "Load order: steering -> role -> project -> role-override -> recent-activity.\n"
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
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


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
        "governance_file_edits_approved": False,
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


def _seed_role_definitions(root: Path) -> dict[str, dict[str, Any]]:
    def _normalized_list(value: Any, fallback: list[str]) -> list[str]:
        if isinstance(value, list):
            normalized = [str(item).strip() for item in value if str(item).strip()]
            if normalized:
                return normalized
        return list(fallback)

    registry_path = root / "agents" / "registry.yaml"
    if not registry_path.exists():
        return dict(ROLE_DEFINITIONS)

    try:
        registry = validators.load_registry(root)
    except Exception:  # noqa: BLE001
        return dict(ROLE_DEFINITIONS)

    roles = registry.get("roles", {})
    if not isinstance(roles, dict) or not roles:
        return dict(ROLE_DEFINITIONS)

    definitions: dict[str, dict[str, Any]] = {}
    for role_id, role_meta in roles.items():
        role_key = str(role_id).strip()
        if not role_key:
            continue
        role_meta_dict = role_meta if isinstance(role_meta, dict) else {}
        role_file = str(role_meta_dict.get("role_file", "")).strip()
        role_path = root / role_file if role_file else root / "agents" / "roles" / role_key / "agent-role.md"
        frontmatter = validators.extract_frontmatter(role_path) if role_path.exists() else {}
        if not isinstance(frontmatter, dict):
            frontmatter = {}

        fallback_meta = ROLE_DEFINITIONS.get(role_key, {})
        display_name = str(
            role_meta_dict.get(
                "display_name",
                frontmatter.get(
                    "display_name",
                    fallback_meta.get("display_name", role_key.replace("-", " ").title()),
                ),
            )
        ).strip() or role_key.replace("-", " ").title()

        definition = {
            "display_name": display_name,
            "mission": str(
                frontmatter.get(
                    "mission",
                    fallback_meta.get(
                        "mission",
                        "Define role mission and execution boundaries for assigned work.",
                    ),
                )
            ).strip()
            or "Define role mission and execution boundaries for assigned work.",
            "authority_level": str(
                frontmatter.get(
                    "authority_level",
                    fallback_meta.get("authority_level", "domain-owner"),
                )
            ).strip()
            or "domain-owner",
            "must_superpowers": _normalized_list(
                frontmatter.get("must_superpowers"),
                list(fallback_meta.get("must_superpowers", ["brainstorming", "writing-plans"])),
            ),
            "optional_superpowers": _normalized_list(
                frontmatter.get("optional_superpowers"),
                list(fallback_meta.get("optional_superpowers", ["requesting-code-review"])),
            ),
            "inputs": _normalized_list(
                frontmatter.get("inputs"),
                list(fallback_meta.get("inputs", ["assigned_backlog_task"])),
            ),
            "outputs": _normalized_list(
                frontmatter.get("outputs"),
                list(fallback_meta.get("outputs", ["task_updates"])),
            ),
            "handoff_rules": _normalized_list(
                frontmatter.get("handoff_rules"),
                list(
                    fallback_meta.get(
                        "handoff_rules",
                        ["request_operator_mediation_when_blocked"],
                    )
                ),
            ),
        }
        definitions[role_key] = definition

    if not definitions:
        return dict(ROLE_DEFINITIONS)
    if "operator" not in definitions:
        definitions["operator"] = dict(ROLE_DEFINITIONS["operator"])
    return definitions


def _registry_seed(role_definitions: dict[str, dict[str, Any]]) -> str:
    lines = ["roles:"]
    for role_id, meta in role_definitions.items():
        lines.append(f"  {role_id}:")
        lines.append(f"    display_name: {meta['display_name']}")
        lines.append(f"    role_file: agents/roles/{role_id}/agent-role.md")
    return "\n".join(lines) + "\n"


def _recent_activity_seed_content(role_id: str) -> str:
    return "\n".join(
        [
            f"# Recent Activity: {role_id}",
            "",
            "High-level summary of the most recent tasks this role has worked on.",
            "Updated (UTC): `never`",
            "",
            "## Latest 5 Tasks",
            "",
            "- No role activity has been recorded yet.",
            "",
        ]
    )


def _project_config_seed(role_definitions: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return {
        "project": {"id": "sample-project", "name": "Sample Project"},
        "host": {
            "primary_adapter": "codex-cli",
            "adapter_command": "codex --sandbox workspace-write --ask-for-approval never exec --ephemeral",
            "session_mode": "stateless",
            "context_rot_guardrails": {
                "max_turns_per_role_session": 8,
                "max_session_age_minutes": 240,
                "force_reload_on_context_change": True,
            },
        },
        "roles": {
            "enabled": list(role_definitions.keys()),
            "disabled": [],
            ROLE_REVIEW_CONFIRMATION_KEY: False,
        },
        "execution": {
            "mode": "sequential",
            "handoff_authority": "operator-mediated",
            "selection_policy": "dependency-fifo",
            "unexpected_event_policy": DEFAULT_UNEXPECTED_EVENT_POLICY,
        },
        "backlog": {"statuses": DEFAULT_STATUSES},
        "dashboard": validators.dashboard_config_with_defaults({}),
    }


def _canonical_primary_adapter(value: Any) -> str:
    adapter = str(value or "").strip()
    if adapter == "codex":
        return "codex-vscode-agent"
    return adapter


def seed_scaffold(root: Path) -> list[Path]:
    created: list[Path] = []
    root.mkdir(parents=True, exist_ok=True)
    role_definitions = _seed_role_definitions(root)

    if _write_if_missing(root / "README.md", "# AgentSquad v1\n"):
        created.append(root / "README.md")
    if _write_if_missing(root / "backlog.md", backlog_store.render_backlog([])):
        created.append(root / "backlog.md")

    for file_name, content in STEERING_SEEDS.items():
        path = root / "steering" / file_name
        if _write_if_missing(path, content):
            created.append(path)

    registry_path = root / "agents" / "registry.yaml"
    if _write_if_missing(registry_path, _registry_seed(role_definitions)):
        created.append(registry_path)

    for role_id, meta in role_definitions.items():
        role_path = root / "agents" / "roles" / role_id / "agent-role.md"
        if _write_if_missing(role_path, _role_frontmatter_content(role_id, meta)):
            created.append(role_path)
        recent_activity_path = root / "agents" / "roles" / role_id / "recent_activity.md"
        if _write_if_missing(recent_activity_path, _recent_activity_seed_content(role_id)):
            created.append(recent_activity_path)

    project_config_path = root / "project" / "config" / "project.yaml"
    if not project_config_path.exists():
        validators.write_yaml_file(project_config_path, _project_config_seed(role_definitions))
        created.append(project_config_path)

    project_context_path = root / "project" / "context" / "project-context.md"
    if _write_if_missing(
        project_context_path,
        (
            "This file tracks project specific context that is shared across all agent roles as the orchestration engine runs. "
            'This file must be initialized before orchestration can begin. To modify project context later, use the "Project" tab.\n\n'
            "## Summary\n\n"
            "- Project goals:\n"
            "- Target users:\n"
            "- Key constraints:\n"
            "- Non-goals:\n\n"
            "## Deliverables\n\n"
            "- Primary deliverables:\n"
            "- Acceptance criteria:\n\n"
            "## Notes\n\n"
            "Add evolving context here as work progresses.\n"
        ),
    ):
        created.append(project_context_path)

    role_overrides_keep = root / "project" / "context" / "role-overrides" / ".gitkeep"
    if _write_if_missing(role_overrides_keep, "\n"):
        created.append(role_overrides_keep)

    state_path = root / "project" / "state" / "orchestrator-state.yaml"
    if not state_path.exists():
        validators.write_yaml_file(state_path, _default_state())
        created.append(state_path)
    activity_log_path = root / "project" / "state" / "activity-log.jsonl"
    if _write_if_missing(activity_log_path, ""):
        created.append(activity_log_path)

    for role_id, meta in role_definitions.items():
        notes_path = root / "project" / "workspaces" / role_id / "notes.md"
        if _write_if_missing(
            notes_path,
            f"# {meta['display_name']} Notes\n\nProject-specific notes for `{role_id}`.\n",
        ):
            created.append(notes_path)
        runs_keep = root / "project" / "workspaces" / role_id / "runs" / ".gitkeep"
        if _write_if_missing(runs_keep, "\n"):
            created.append(runs_keep)
        role_activity = root / "project" / "workspaces" / role_id / "activity.jsonl"
        if _write_if_missing(role_activity, ""):
            created.append(role_activity)

    template_files = {
        "operator-plan-prompt.md": "Return operator_plan JSON only.\n",
        "agent-task-prompt.md": "Return agent_result JSON only.\n",
        "json-contracts.md": "# JSON Contracts\n",
        "dashboard.html": "<html><body>{{DASHBOARD_PAYLOAD_JSON}}</body></html>\n",
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
    state["governance_file_edits_approved"] = bool(
        state.get("governance_file_edits_approved", False)
    )
    return state


def save_state(root: Path, state: dict[str, Any]) -> None:
    validators.write_yaml_file(_state_path(root), state)


def halt_with_reason(root: Path, state: dict[str, Any], reason: str) -> None:
    state["halted"] = True
    state["halt_reason"] = reason
    state["history"].append({"ts": utc_now(), "event": "halt", "reason": reason})
    active_role = str(state.get("active_role") or "operator").strip() or "operator"
    known_roles = set(ROLE_DEFINITIONS.keys())
    try:
        registry_roles = validators.load_registry(root).get("roles", {})
        if isinstance(registry_roles, dict) and registry_roles:
            known_roles = set(registry_roles.keys())
    except Exception:  # noqa: BLE001
        pass
    if active_role not in known_roles:
        active_role = "operator"
    logging_store.write_activity_event(
        root=root,
        role_id=active_role,
        task_id="",
        event_type="unexpected_halt",
        summary=f"Orchestration halted unexpectedly: {reason}",
        status="Error",
        metadata={"source": "orchestrator"},
    )
    save_state(root, state)


def _render_template(template_text: str, replacements: dict[str, str]) -> str:
    rendered = template_text
    for key, value in replacements.items():
        rendered = rendered.replace(f"{{{{{key}}}}}", value)
    return rendered


def _load_template(root: Path, file_name: str) -> str:
    return (root / "runner" / "templates" / file_name).read_text(encoding="utf-8")


def _safe_segment(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in value).strip("-")


def _clone_tasks(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    clone: list[dict[str, Any]] = []
    for task in tasks:
        item = dict(task)
        item["dependencies"] = list(task.get("dependencies", []))
        clone.append(item)
    return clone


def _dependencies_text(value: Any) -> str:
    deps = backlog_store.normalize_task({"dependencies": value})["dependencies"]
    return ", ".join(deps) if deps else "(none)"


def _describe_task_changes(
    before: list[dict[str, Any]],
    after: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    before_map = {task["task_id"]: task for task in before}
    changes: list[dict[str, Any]] = []
    tracked_fields = ("title", "description", "owner", "milestone", "status", "dependencies")

    for task in after:
        task_id = task["task_id"]
        previous = before_map.get(task_id)
        if previous is None:
            detail = (
                f"created '{task_id}' "
                f"(owner={task['owner']}, status={task['status']}, milestone={task['milestone']}, "
                f"dependencies={_dependencies_text(task['dependencies'])})"
            )
            changes.append(
                {
                    "task_id": task_id,
                    "action": "created",
                    "detail": detail,
                    "field_changes": {},
                }
            )
            continue

        field_changes: dict[str, dict[str, str]] = {}
        details: list[str] = []
        for field in tracked_fields:
            before_value: Any = previous.get(field, "")
            after_value: Any = task.get(field, "")
            if field == "dependencies":
                before_text = _dependencies_text(before_value)
                after_text = _dependencies_text(after_value)
                if before_text == after_text:
                    continue
                field_changes[field] = {"before": before_text, "after": after_text}
                details.append(f"dependencies {before_text} -> {after_text}")
            else:
                before_text = str(before_value).strip()
                after_text = str(after_value).strip()
                if before_text == after_text:
                    continue
                field_changes[field] = {"before": before_text, "after": after_text}
                details.append(f"{field} '{before_text}' -> '{after_text}'")
        if field_changes:
            changes.append(
                {
                    "task_id": task_id,
                    "action": "updated",
                    "detail": f"updated '{task_id}': " + "; ".join(details),
                    "field_changes": field_changes,
                }
            )
    return changes


def _capture_file_snapshot(root: Path) -> dict[str, tuple[int, int]]:
    snapshot: dict[str, tuple[int, int]] = {}
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        if rel.startswith(".git/"):
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        snapshot[rel] = (int(stat.st_size), int(stat.st_mtime_ns))
    return snapshot


def _diff_file_snapshots(
    before: dict[str, tuple[int, int]],
    after: dict[str, tuple[int, int]],
) -> dict[str, list[str]]:
    before_keys = set(before.keys())
    after_keys = set(after.keys())
    created = sorted(after_keys - before_keys)
    deleted = sorted(before_keys - after_keys)
    modified = sorted(key for key in (before_keys & after_keys) if before[key] != after[key])
    return {"created": created, "modified": modified, "deleted": deleted}


def _has_governance_edit_permission(request_text: str) -> bool:
    raw = str(request_text or "").strip()
    if not raw:
        return False
    return any(re.search(pattern, raw) for pattern in GOVERNANCE_EDIT_APPROVAL_PATTERNS)


def _is_protected_governance_path(rel_path: str) -> bool:
    normalized = str(rel_path).strip().replace("\\", "/")
    return any(normalized.startswith(prefix) for prefix in PROTECTED_GOVERNANCE_PATH_PREFIXES)


def _collect_protected_governance_changes(
    file_changes: dict[str, list[str]],
) -> list[dict[str, str]]:
    changes: list[dict[str, str]] = []
    for action in ("created", "modified", "deleted"):
        for rel_path in file_changes.get(action, []):
            if not _is_protected_governance_path(rel_path):
                continue
            changes.append({"action": action, "path": rel_path})
    return changes


def _enforce_protected_governance_edit_guardrail(
    root: Path,
    role_id: str,
    task_id: str,
    protected_changes: list[dict[str, str]],
    governance_permission_granted: bool,
) -> None:
    if not protected_changes:
        return

    changed_paths = sorted({item["path"] for item in protected_changes})
    details = ", ".join(f"{item['action']}:{item['path']}" for item in protected_changes)
    if governance_permission_granted:
        logging_store.write_activity_event(
            root=root,
            role_id=role_id,
            task_id=task_id,
            event_type="governance_edit_approved",
            summary=(
                f"{role_id} changed protected governance files with explicit human permission: "
                f"{', '.join(changed_paths)}."
            ),
            status="Approved",
            metadata={"changes": protected_changes},
        )
        return

    guidance = (
        "Explicit human approval is required. Include one of: "
        "`[ALLOW-GOVERNANCE-EDITS]`, "
        "`governance_file_edits_approved: true`, or "
        "`approve.governance_file_edits: true` in the request."
    )
    summary = (
        f"{role_id} changed protected governance files without explicit human approval: {details}. "
        f"{guidance}"
    )
    logging_store.write_activity_event(
        root=root,
        role_id=role_id,
        task_id=task_id,
        event_type="unexpected_error",
        summary=summary,
        status="Error",
        metadata={"changes": protected_changes},
    )
    raise OrchestrationHalt(
        "Governance edit guardrail triggered. "
        f"Protected files changed without explicit human approval: {', '.join(changed_paths)}. "
        f"{guidance}"
    )


def _unexpected_event_policy(runtime: dict[str, Any]) -> str:
    configured = str(runtime.get("unexpected_event_policy", DEFAULT_UNEXPECTED_EVENT_POLICY)).strip().lower()
    if configured in UNEXPECTED_EVENT_POLICY_VALUES:
        return configured
    return DEFAULT_UNEXPECTED_EVENT_POLICY


def _unexpected_requires_return_to_user(
    runtime: dict[str, Any],
    has_warning: bool,
    has_error: bool,
) -> bool:
    policy = _unexpected_event_policy(runtime)
    if policy == "proceed":
        return False
    if has_error:
        return True
    if has_warning and policy == "errors-or-warnings":
        return True
    return False


def _emit_file_change_logs(
    root: Path,
    role_id: str,
    task_id: str,
    file_changes: dict[str, list[str]],
    reason: str,
) -> list[str]:
    events: list[str] = []
    for action in ("created", "modified", "deleted"):
        for rel_path in file_changes.get(action, []):
            line = f"file_{action}: `{rel_path}` ({reason}; action={action})"
            events.append(line)
            logging_store.write_activity_event(
                root=root,
                role_id=role_id,
                task_id=task_id,
                event_type=f"file_{action}",
                summary=f"{role_id} {action} file '{rel_path}' ({reason}).",
                status="Logged",
                metadata={"path": rel_path, "reason": reason},
            )
    return events


def _append_notes_update(root: Path, role_id: str, task_id: str, note_text: str) -> str:
    cleaned = str(note_text or "").strip()
    if not cleaned:
        return ""
    workspace = logging_store.ensure_workspace(root, role_id)
    notes_path = workspace / "notes.md"
    lines = [
        "",
        f"## {utc_now()} ({task_id})",
        "",
        cleaned,
        "",
    ]
    with notes_path.open("a", encoding="utf-8") as handle:
        handle.write("\n".join(lines))
    return notes_path.relative_to(root).as_posix()


def _write_feedback_file(
    root: Path,
    source_role: str,
    task_id: str,
    audience: str,
    summary: str,
    questions: list[str],
    target_role: str = "",
    requested_action: str = "",
    related_task_ids: list[str] | None = None,
    requires_response: bool = False,
) -> str:
    workspace = logging_store.ensure_workspace(root, source_role)
    feedback_dir = workspace / "feedback"
    feedback_dir.mkdir(parents=True, exist_ok=True)

    safe_task = _safe_segment(task_id or "no-task") or "no-task"
    target_segment = _safe_segment(target_role or audience) or "target"
    timestamp = logging_store.filename_timestamp_now()
    file_name = f"{timestamp}-{safe_task}-to-{target_segment}.md"
    path = feedback_dir / file_name
    suffix = 1
    while path.exists():
        file_name = f"{timestamp}-{safe_task}-to-{target_segment}-{suffix}.md"
        path = feedback_dir / file_name
        suffix += 1

    lines: list[str] = []
    lines.append(f"# Feedback: {source_role} -> {target_role or audience}")
    lines.append("")
    lines.append(f"- Timestamp: `{utc_now()}`")
    lines.append(f"- Source Role: `{source_role}`")
    lines.append(f"- Task ID: `{task_id}`")
    lines.append(f"- Audience: `{audience}`")
    if target_role:
        lines.append(f"- Target Role: `{target_role}`")
    lines.append(f"- Requires Response: `{str(bool(requires_response)).lower()}`")
    if related_task_ids:
        lines.append(f"- Related Tasks: `{', '.join(related_task_ids)}`")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(summary.strip() or "No summary provided.")
    lines.append("")
    if questions:
        lines.append("## Questions")
        lines.append("")
        for question in questions:
            lines.append(f"- {question}")
        lines.append("")
    if requested_action:
        lines.append("## Requested Action")
        lines.append("")
        lines.append(requested_action.strip())
        lines.append("")

    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return path.relative_to(root).as_posix()


def _emit_decision_logs(
    root: Path,
    role_id: str,
    task_id: str,
    decisions: list[str],
) -> list[str]:
    events: list[str] = []
    for decision in decisions:
        cleaned = str(decision).strip()
        if not cleaned:
            continue
        line = f"decision: {cleaned}"
        events.append(line)
        logging_store.write_activity_event(
            root=root,
            role_id=role_id,
            task_id=task_id,
            event_type="decision_note",
            summary=cleaned,
            status="Logged",
            metadata={},
        )
    return events


def _emit_unexpected_logs(
    root: Path,
    role_id: str,
    task_id: str,
    unexpected_entries: list[str],
) -> tuple[list[str], bool, bool]:
    events: list[str] = []
    has_warning = False
    has_error = False
    for item in unexpected_entries:
        cleaned = str(item).strip()
        if not cleaned:
            continue
        severity = "warning"
        message = cleaned
        if re.match(r"(?i)^\s*(error|err|fatal)\s*[:\-]\s*", message):
            severity = "error"
            message = re.sub(r"(?i)^\s*(error|err|fatal)\s*[:\-]\s*", "", message).strip() or cleaned
        elif re.match(r"(?i)^\s*(warn|warning)\s*[:\-]\s*", message):
            severity = "warning"
            message = re.sub(r"(?i)^\s*(warn|warning)\s*[:\-]\s*", "", message).strip() or cleaned

        if severity == "error":
            has_error = True
        else:
            has_warning = True

        line = f"unexpected_{severity}: {message}"
        events.append(line)
        logging_store.write_activity_event(
            root=root,
            role_id=role_id,
            task_id=task_id,
            event_type=f"unexpected_{severity}",
            summary=message,
            status="Error" if severity == "error" else "Warning",
            metadata={"severity": severity},
        )
    return events, has_warning, has_error


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
    mode = runtime.get("session_mode", "stateless")
    if role_id == "operator":
        reasons = ["operator-forced-full-context-reload"]
        if mode != "per-role-threads":
            reasons.append("stateless-mode")
        return {
            "mode": mode,
            "reuse": False,
            "session_id": None,
            "refresh_reasons": reasons,
            "full_context_required": True,
        }

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
                parsed = contracts.validate_agent_result(
                    payload,
                    statuses,
                    known_roles,
                    invoking_role=role_id,
                )
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
    dashboard_config = validators.dashboard_config_with_defaults(config)
    config["dashboard"] = dashboard_config
    registry = validators.load_registry(root)
    roles_map = registry["roles"]
    known_roles = set(roles_map.keys())
    enabled_roles = set(config["roles"]["enabled"])
    disabled_roles = set(config["roles"]["disabled"])
    statuses = list(config["backlog"]["statuses"])
    adapter_name = str(config["host"]["primary_adapter"])
    adapter_command = str(config["host"]["adapter_command"])
    session_mode = str(config["host"].get("session_mode", "stateless"))
    context_rot_guardrails = config["host"].get("context_rot_guardrails", {})
    unexpected_event_policy = str(
        config.get("execution", {}).get("unexpected_event_policy", DEFAULT_UNEXPECTED_EVENT_POLICY)
    ).strip().lower()
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
        "unexpected_event_policy": (
            unexpected_event_policy
            if unexpected_event_policy in UNEXPECTED_EVENT_POLICY_VALUES
            else DEFAULT_UNEXPECTED_EVENT_POLICY
        ),
        "dashboard": dashboard_config,
    }


def _render_dashboard_best_effort(
    root: Path,
    runtime: dict[str, Any] | None,
    trigger: str,
) -> None:
    try:
        if runtime is not None:
            dash_cfg = runtime.get("dashboard", {})
        else:
            config = validators.load_project_config(root)
            dash_cfg = validators.dashboard_config_with_defaults(config)
        if not bool(dash_cfg.get("enabled", True)):
            return
        output_path = dashboard.render_dashboard(root)
        print(f"Dashboard updated ({trigger}): {output_path.as_posix()}")
        logging_store.write_activity_event(
            root=root,
            role_id="operator",
            task_id="",
            event_type="file_modified",
            summary=f"Operator regenerated dashboard file '{output_path.relative_to(root).as_posix()}'.",
            status="Logged",
            metadata={"trigger": trigger, "path": output_path.relative_to(root).as_posix()},
        )
    except Exception as exc:  # noqa: BLE001
        print(f"Dashboard render warning ({trigger}): {exc}")
        logging_store.write_activity_event(
            root=root,
            role_id="operator",
            task_id="",
            event_type="unexpected_event",
            summary=f"Dashboard render warning ({trigger}): {exc}",
            status="Warning",
            metadata={"trigger": trigger},
        )


def _is_value_defined(raw_value: str) -> bool:
    normalized = (raw_value or "").strip().lower()
    return normalized not in UNSET_VALUE_MARKERS


def _extract_project_context_value(context_text: str, field_label: str) -> str:
    pattern = rf"^- {re.escape(field_label)}:[ \t]*(.*)$"
    match = re.search(pattern, context_text, flags=re.MULTILINE)
    if not match:
        return ""
    return match.group(1).strip()


def _project_context_values(root: Path) -> dict[str, str]:
    values = {label: "" for label in INITIALIZATION_REQUIRED_CONTEXT_FIELDS}
    context_path = root / "project" / "context" / "project-context.md"
    if not context_path.exists():
        return values
    context_text = context_path.read_text(encoding="utf-8")
    for label in INITIALIZATION_REQUIRED_CONTEXT_FIELDS:
        values[label] = _extract_project_context_value(context_text, label)
    return values


def _role_review_confirmed(config: dict[str, Any]) -> bool:
    roles = config.get("roles", {})
    if not isinstance(roles, dict):
        return False
    return bool(roles.get(ROLE_REVIEW_CONFIRMATION_KEY, False))


def _role_review_project_tokens(root: Path, config: dict[str, Any]) -> set[str]:
    project = config.get("project", {})
    project_values = _project_context_values(root)
    text_parts = [
        str(project.get("id", "")),
        str(project.get("name", "")),
        *[project_values[label] for label in INITIALIZATION_REQUIRED_CONTEXT_FIELDS],
    ]
    raw = " ".join(text_parts).lower()
    tokens: set[str] = set()
    for token in re.findall(r"[a-z0-9][a-z0-9\-]{1,}", raw):
        normalized = token.strip("-")
        if len(normalized) < 3:
            continue
        if normalized in ROLE_REVIEW_TOKEN_STOPWORDS:
            continue
        tokens.add(normalized)
    return tokens


def _role_review_role_tokens(
    root: Path,
    role_id: str,
    role_meta: dict[str, Any],
) -> set[str]:
    role_file = str(role_meta.get("role_file", "")).strip()
    role_path = root / role_file if role_file else None
    frontmatter: dict[str, Any] = {}
    if role_path and role_path.exists():
        try:
            frontmatter = validators.extract_frontmatter(role_path)
        except Exception:  # noqa: BLE001
            frontmatter = {}

    text_parts: list[str] = [
        role_id.replace("-", " "),
        str(role_meta.get("display_name", "")),
        str(frontmatter.get("display_name", "")),
        str(frontmatter.get("mission", "")),
    ]
    for field_name in ("inputs", "outputs", "handoff_rules"):
        value = frontmatter.get(field_name)
        if isinstance(value, list):
            text_parts.extend(str(item) for item in value)

    raw = " ".join(text_parts).lower()
    tokens: set[str] = set()
    for token in re.findall(r"[a-z0-9][a-z0-9\-]{1,}", raw):
        normalized = token.strip("-")
        if len(normalized) < 3:
            continue
        if normalized in ROLE_REVIEW_TOKEN_STOPWORDS:
            continue
        tokens.add(normalized)
    return tokens


def _role_review_recommendations(
    root: Path,
    config: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    try:
        registry_roles = validators.load_registry(root).get("roles", {})
    except Exception:  # noqa: BLE001
        registry_roles = {}

    if not isinstance(registry_roles, dict):
        registry_roles = {}

    roles_cfg = config.get("roles", {})
    enabled_roles = roles_cfg.get("enabled", [])
    if not isinstance(enabled_roles, list):
        enabled_roles = []

    project_tokens = _role_review_project_tokens(root, config)
    scored: list[dict[str, Any]] = []
    for raw_role_id in enabled_roles:
        role_id = str(raw_role_id).strip()
        if not role_id:
            continue
        role_meta = registry_roles.get(role_id, {})
        if not isinstance(role_meta, dict):
            role_meta = {}
        role_tokens = _role_review_role_tokens(root, role_id, role_meta)
        overlap = sorted(project_tokens & role_tokens)
        scored.append(
            {
                "role_id": role_id,
                "score": len(overlap),
                "overlap": overlap[:6],
            }
        )

    if not scored:
        return [], []

    disable_candidates = [
        item
        for item in scored
        if item["role_id"] not in ROLE_REVIEW_CORE_KEEP and item["score"] == 0
    ]
    disable_candidates.sort(key=lambda item: item["role_id"])

    if not disable_candidates:
        low_overlap = [
            item
            for item in sorted(scored, key=lambda item: (item["score"], item["role_id"]))
            if item["role_id"] not in ROLE_REVIEW_CORE_KEEP and item["score"] <= 1
        ]
        limit = min(8, max(3, len(low_overlap) // 4))
        disable_candidates = low_overlap[:limit]

    keep_candidates = [
        item
        for item in sorted(scored, key=lambda item: (-item["score"], item["role_id"]))
        if item["score"] > 0
    ]
    return disable_candidates, keep_candidates


def _project_initialization_base_issues(root: Path, runtime: dict[str, Any]) -> list[str]:
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
        enabled_roles = []
    if "operator" not in enabled_roles:
        issues.append("project/config/project.yaml: roles.enabled must include 'operator'.")
    non_operator_enabled = [role_id for role_id in enabled_roles if str(role_id).strip() != "operator"]
    if not non_operator_enabled:
        issues.append(
            "project/config/project.yaml: no non-operator roles are enabled. "
            "AgentSquad requires Operator plus at least one non-operator role to execute work."
        )

    context_values = _project_context_values(root)
    context_path = root / "project" / "context" / "project-context.md"
    if not context_path.exists():
        issues.append("project/context/project-context.md is missing.")
        return issues

    for field_label in INITIALIZATION_REQUIRED_CONTEXT_FIELDS:
        value = context_values.get(field_label, "")
        if not _is_value_defined(value):
            issues.append(
                "project/context/project-context.md: "
                f"fill '{field_label}' with project-specific content."
            )

    return issues


def _project_initialization_issues(root: Path, runtime: dict[str, Any]) -> list[str]:
    issues = _project_initialization_base_issues(root, runtime)
    if issues:
        return issues
    config = runtime["config"]
    if not _role_review_confirmed(config):
        issues.append(ROLE_REVIEW_PENDING_ISSUE)
    return issues


def _initialization_prompt_default(field_name: str, current_value: str) -> str:
    if _is_value_defined(current_value):
        return current_value
    if field_name == "project.id":
        return "<your-project-id>"
    if field_name == "project.name":
        return "<your-project-name>"
    return "<fill-this>"


def _is_initialization_value_thin(value: str) -> bool:
    if not _is_value_defined(value):
        return True
    cleaned = " ".join(str(value).strip().split())
    words = [token for token in cleaned.split(" ") if token]
    return (
        len(words) < INITIALIZATION_DETAIL_MIN_WORDS
        or len(cleaned) < INITIALIZATION_DETAIL_MIN_CHARS
    )


def _bootstrap_deep_intake_lines(values: dict[str, str]) -> list[str]:
    lines: list[str] = []
    lines.append("## Optional Deep-Dive Intake (Recommended)")
    lines.append("")
    lines.append(
        "If you want stronger planning quality, ask the user for richer detail now. "
        "Use this when answers are short, ambiguous, or likely to cause rework."
    )
    lines.append("")

    thin_fields: list[str] = []
    for field_name, prompts in INITIALIZATION_DEEP_DIVE_QUESTIONS:
        value = values.get(field_name, "")
        if not _is_initialization_value_thin(value):
            continue
        thin_fields.append(field_name)
        lines.append(f"### Drill Into `{field_name}`")
        for prompt in prompts:
            lines.append(f"- {prompt}")
        lines.append("")

    if thin_fields:
        lines.append(
            "Current responses are thin for: "
            + ", ".join(f"`{item}`" for item in thin_fields)
            + "."
        )
        lines.append(
            "Operator should collect deeper answers before starting planning, "
            "unless the user explicitly chooses a quick-start path."
        )
    else:
        lines.append(
            "Current responses appear detailed enough; deep-dive intake is optional."
        )
    lines.append("")
    lines.append("### Optional Deep-Dive Reply Template")
    lines.append("")
    lines.append("```text")
    lines.append("deep_intake: yes")
    lines.append("Project goals.detail: <metrics + timeline + business outcome>")
    lines.append("Target users.detail: <primary segment + pains + out-of-scope segments>")
    lines.append("Key constraints.detail: <hard constraints + acceptable tradeoffs>")
    lines.append("Primary deliverables.detail: <mandatory outputs + optional outputs>")
    lines.append("Acceptance criteria.detail: <objective checks + approver + evidence>")
    lines.append("```")
    lines.append("")
    return lines


def _bootstrap_intake_lines(root: Path, config: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    project = config.get("project", {})
    project_id = str(project.get("id", "")).strip()
    project_name = str(project.get("name", "")).strip()
    if project_id == "sample-project":
        project_id = ""
    if project_name.lower() == "sample project":
        project_name = ""

    context_values = _project_context_values(root)

    values: dict[str, str] = {"project.id": project_id, "project.name": project_name}
    values.update(context_values)

    lines.append("## What To Send Next (Copy/Paste Template)")
    lines.append("")
    lines.append(
        "First, direct the user to the dashboard `Project` tab to complete setup fields. "
        "Offer to draft candidate text for any field if they want help."
    )
    lines.append("")
    lines.append("Reply with values for all 7 fields below. Keep each answer specific and concrete.")
    lines.append("Avoid placeholders such as `TBD`, `N/A`, or `Unknown`.")
    lines.append("")
    lines.append("```text")
    lines.append(
        f"project.id: {_initialization_prompt_default('project.id', values.get('project.id', ''))}"
    )
    lines.append(
        f"project.name: {_initialization_prompt_default('project.name', values.get('project.name', ''))}"
    )
    for label in INITIALIZATION_REQUIRED_CONTEXT_FIELDS:
        lines.append(f"{label}: {_initialization_prompt_default(label, values.get(label, ''))}")
    lines.append("```")
    lines.append("")
    lines.append("### Field Guidance")
    lines.append("")
    for field_name, description, example in INITIALIZATION_INTAKE_GUIDANCE:
        lines.append(f"- `{field_name}`: {description} Example: `{example}`")
    lines.append("")
    lines.append(
        "After you reply, Operator should write the values into "
        "`project/config/project.yaml` and `project/context/project-context.md`, "
        "then run role enablement review and continue initialization to `READY` "
        "after user confirmation."
    )
    lines.append("")
    lines.extend(_bootstrap_deep_intake_lines(values))
    return lines


def _bootstrap_initialization_checklist_lines(
    config: dict[str, Any],
    base_init_issues: list[str],
) -> list[str]:
    lines: list[str] = []
    project_setup_complete = len(base_init_issues) == 0
    review_confirmed = _role_review_confirmed(config)
    role_review_complete = project_setup_complete and review_confirmed

    lines.append("### Initialization Checklist")
    lines.append("")
    lines.append(
        f"- Project setup complete (dashboard `Project` tab): "
        f"`{'yes' if project_setup_complete else 'no'}`"
    )
    if not project_setup_complete:
        lines.append(
            "  - Required fields are still missing. Direct the user to `Project` tab and "
            "offer to draft text for required fields."
        )
    lines.append(
        f"- Role review complete (dashboard `Settings` tab): "
        f"`{'yes' if role_review_complete else 'no'}`"
    )
    if project_setup_complete and not role_review_complete:
        lines.append(
            "  - Ask the user to review enabled/disabled roles on `Settings` tab, then confirm "
            "apply-recommendations, keep-all, or custom."
        )
        lines.append(
            "  - Offer to generate role recommendations from project goals/users/constraints/deliverables."
        )
    if role_review_complete:
        lines.append("  - Role review confirmation is recorded and initialization can proceed.")
    lines.append("")
    return lines


def _bootstrap_role_review_lines(
    root: Path,
    config: dict[str, Any],
    base_ready: bool,
) -> list[str]:
    lines: list[str] = []
    roles_cfg = config.get("roles", {})
    enabled_roles = roles_cfg.get("enabled", [])
    disabled_roles = roles_cfg.get("disabled", [])
    if not isinstance(enabled_roles, list):
        enabled_roles = []
    if not isinstance(disabled_roles, list):
        disabled_roles = []
    review_confirmed = _role_review_confirmed(config)

    lines.append("## Role Enablement Review")
    lines.append("")
    lines.append(
        "Direct the user to the dashboard `Settings` tab for role enable/disable review."
    )
    lines.append(
        "Offer to recommend a disable list from project goals/users/constraints/deliverables."
    )
    lines.append("")
    lines.append(
        "All roles are enabled by default. Operator should recommend a smaller active role set "
        "for this project and wait for explicit user confirmation before proceeding."
    )
    lines.append("")
    lines.append(f"- Current enabled roles: `{len(enabled_roles)}`")
    lines.append(f"- Current disabled roles: `{len(disabled_roles)}`")
    lines.append(f"- Review confirmed (`roles.{ROLE_REVIEW_CONFIRMATION_KEY}`): `{str(review_confirmed).lower()}`")
    lines.append("")

    if not base_ready:
        lines.append(
            "Role recommendations are deferred until required project fields are complete."
        )
        lines.append(
            "After goals/users/constraints/deliverables/acceptance criteria are filled, "
            "Operator should run role review and collect user confirmation."
        )
        lines.append("")
        return lines

    disable_recs, keep_recs = _role_review_recommendations(root, config)
    if disable_recs:
        lines.append("### Suggested Roles To Disable")
        lines.append("")
        for item in disable_recs:
            role_id = item["role_id"]
            score = item["score"]
            overlap = item.get("overlap", [])
            if overlap:
                reason = f"low relevance score `{score}` (matched tokens: {', '.join(overlap)})"
            else:
                reason = "no direct match to current project goals/deliverables/constraints"
            lines.append(f"- `{role_id}`: {reason}")
        lines.append("")
    else:
        lines.append(
            "No clear low-relevance roles were detected from current project context."
        )
        lines.append("")

    if keep_recs:
        lines.append("### High-Relevance Roles To Keep Enabled")
        lines.append("")
        for item in keep_recs:
            role_id = item["role_id"]
            score = item["score"]
            overlap = item.get("overlap", [])
            evidence = ", ".join(overlap) if overlap else "context fit"
            lines.append(f"- `{role_id}`: relevance score `{score}` ({evidence})")
        lines.append("")

    if review_confirmed:
        lines.append("Role review is already confirmed.")
        lines.append("")
        return lines

    lines.append("### User Confirmation Required (Copy/Paste Template)")
    lines.append("")
    lines.append("```text")
    lines.append("role_review.confirmed: yes")
    lines.append("role_review.decision: apply-recommendations | keep-all | custom")
    lines.append("roles.disable: <comma-separated role IDs to disable or leave blank>")
    lines.append("roles.enable: <comma-separated role IDs to force-enable or leave blank>")
    lines.append("```")
    lines.append("")
    lines.append(
        "After user confirmation, Operator should update `project/config/project.yaml`:"
    )
    lines.append("- set `roles.disabled` and `roles.enabled` per confirmed decision")
    lines.append(f"- set `roles.{ROLE_REVIEW_CONFIRMATION_KEY}: true`")
    lines.append("")
    return lines


def _operator_bootstrap_packet(
    root: Path,
    config: dict[str, Any],
    init_issues: list[str],
    base_init_issues: list[str],
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
    lines.append(f"- Primary Adapter: `{_canonical_primary_adapter(host.get('primary_adapter', ''))}`")
    lines.append("")
    lines.append("## Mandatory Context Load Order")
    lines.append("")
    for path in manifest_paths:
        lines.append(f"1. `{path}`")
    lines.append("")
    lines.append("## Initialization Gate Status")
    lines.append("")
    lines.extend(_bootstrap_initialization_checklist_lines(config, base_init_issues))
    if init_issues:
        lines.append("Status: `BLOCKED`")
        lines.append("")
        lines.append("Complete these items before invoking any non-Operator role:")
        lines.append("")
        for issue in init_issues:
            lines.append(f"- {issue}")
        lines.append("")
        if base_init_issues:
            lines.extend(_bootstrap_intake_lines(root, config))
        else:
            lines.append(
                "Project details are already defined. Complete role enablement review "
                "confirmation to clear the final initialization gate."
            )
            lines.append("")
        lines.extend(_bootstrap_role_review_lines(root, config, base_ready=not base_init_issues))
    else:
        lines.append("Status: `READY`")
        lines.append("")
        lines.append("Project context and mandatory config are complete.")
        lines.append("")
        lines.extend(_bootstrap_role_review_lines(root, config, base_ready=True))
    lines.append("")
    lines.append("## Operator Procedure")
    lines.append("")
    lines.append("1. Load mandatory context in the order above.")
    lines.append("2. Check initialization checklist status before planning:")
    lines.append("   - Project setup complete (dashboard `Project` tab)")
    lines.append("   - Role review complete (dashboard `Settings` tab)")
    lines.append("3. If project setup is incomplete, direct user to `Project` tab and offer drafting help.")
    lines.append("4. If project setup is complete but role review is pending:")
    lines.append("   - direct user to `Settings` tab")
    lines.append("   - propose role enable/disable recommendations")
    lines.append("   - wait for explicit confirmation")
    lines.append(
        f"5. Update `roles.{ROLE_REVIEW_CONFIRMATION_KEY}: true` after confirmation."
    )
    lines.append(
        "6. If required fields are present but thin, run optional deep-dive intake "
        "questions before planning."
    )
    lines.append(
        "7. After initialization is READY, do not edit `project/config/**`, "
        "`project/context/**`, or `steering/**` without explicit human approval "
        "(`governance_file_edits_approved: true` or `[ALLOW-GOVERNANCE-EDITS]`)."
    )
    lines.append("8. Do not invoke work agents until gate is `READY`.")
    lines.append("9. Once ready, collect user request and produce `operator_plan` JSON only.")
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
    runtime_stub = {"config": config}
    base_init_issues = _project_initialization_base_issues(root, runtime_stub)
    init_issues = _project_initialization_issues(root, runtime_stub)
    manifest = context_loader.build_manifest(root, "operator")
    manifest_paths = context_loader.manifest_paths(manifest)

    packet = _operator_bootstrap_packet(
        root,
        config,
        init_issues,
        base_init_issues,
        manifest_paths,
    )
    output_path = root / args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(packet, encoding="utf-8")

    print(f"Operator bootstrap packet written to: {output_path.as_posix()}")
    if init_issues:
        print(f"Initialization gate: BLOCKED ({len(init_issues)} item(s))")
    else:
        print("Initialization gate: READY")
    print("Recommended short prompt:")
    print("Read AGENTS.md and initialize this thread as AgentSquad Operator")

    if args.print_packet:
        print("")
        print(packet)
    return 0


def _upsert_backlog_from_operator(
    root: Path,
    existing: list[dict[str, Any]],
    plan_payload: dict[str, Any],
) -> tuple[list[dict[str, Any]], bool]:
    backlog_path = root / "backlog.md"
    before_render = backlog_store.render_backlog(existing)
    updated = backlog_store.upsert_tasks(existing, plan_payload["tasks"])
    after_render = backlog_store.render_backlog(updated)
    changed = after_render != before_render
    if changed:
        backlog_store.write_backlog(backlog_path, updated)
    return updated, changed


def _invoke_operator(
    root: Path,
    runtime: dict[str, Any],
    state: dict[str, Any],
    human_request: str,
    mode_label: str,
) -> list[dict[str, Any]]:
    backlog_path = root / "backlog.md"
    current_tasks = backlog_store.read_backlog(backlog_path)
    current_tasks_snapshot = _clone_tasks(current_tasks)
    backlog_before = backlog_store.render_backlog(current_tasks)

    manifest = _load_role_context(root, state, "operator")
    context_hash = context_loader.manifest_hash(manifest)
    session_plan = _resolve_role_session_plan(
        runtime=runtime,
        state=state,
        role_id="operator",
        context_hash=context_hash,
    )
    manifest_paths = context_loader.manifest_paths(manifest)
    refresh_reasons = list(session_plan.get("refresh_reasons", []))
    logging_store.write_activity_event(
        root=root,
        role_id="operator",
        task_id=f"operator-{mode_label}",
        event_type="context_reload",
        summary=(
            "Operator reloaded full context manifest before invocation "
            f"({len(manifest_paths)} files)."
        ),
        status="Loaded",
        metadata={
            "mode": mode_label,
            "refresh_reasons": refresh_reasons,
            "manifest_hash": context_hash,
            "manifest_paths": manifest_paths,
        },
    )
    if session_plan["full_context_required"]:
        context_text = context_loader.compose_context_text(manifest)
    else:
        context_text = (
            "Reuse existing operator thread context. "
            "Load context files again only if inconsistency is detected."
        )
    manifest_text = "\n".join(f"- {path}" for path in manifest_paths)
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

    before_files = _capture_file_snapshot(root)
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
    after_files = _capture_file_snapshot(root)
    invocation_file_changes = _diff_file_snapshots(before_files, after_files)
    file_change_events = _emit_file_change_logs(
        root=root,
        role_id="operator",
        task_id=f"operator-{mode_label}",
        file_changes=invocation_file_changes,
        reason="during operator thread invocation",
    )
    protected_changes = _collect_protected_governance_changes(invocation_file_changes)
    _enforce_protected_governance_edit_guardrail(
        root=root,
        role_id="operator",
        task_id=f"operator-{mode_label}",
        protected_changes=protected_changes,
        governance_permission_granted=bool(state.get("governance_file_edits_approved", False)),
    )

    updated_tasks, backlog_changed = _upsert_backlog_from_operator(
        root,
        current_tasks,
        parsed,
    )
    if not backlog_changed:
        raise OrchestrationHalt(
            "Operator plan rejected: backlog.md was not modified. "
            "Operator must return an operator_plan that creates or updates at least one backlog task."
        )

    backlog_after = backlog_store.render_backlog(updated_tasks)
    backlog_task_changes = _describe_task_changes(current_tasks_snapshot, updated_tasks)
    state["role_sequence"] = parsed["initial_role_sequence"]
    state["history"].append(
        {
            "ts": utc_now(),
            "event": "operator-invoke",
            "mode": mode_label,
            "tasks_generated": len(parsed["tasks"]),
        }
    )

    run_events: list[str] = [f"mode={mode_label}", "operator_plan parsed"]
    run_events.append(
        "context_reload: operator loaded full context manifest "
        f"({len(manifest_paths)} files); reasons={', '.join(refresh_reasons)}"
    )
    run_events.extend(session_events)
    run_events.extend(file_change_events)
    run_events.extend(
        _emit_decision_logs(
            root=root,
            role_id="operator",
            task_id=f"operator-{mode_label}",
            decisions=parsed.get("decision_log", []),
        )
    )
    unexpected_events, unexpected_warning, unexpected_error = _emit_unexpected_logs(
        root=root,
        role_id="operator",
        task_id=f"operator-{mode_label}",
        unexpected_entries=parsed.get("unexpected_events", []),
    )
    run_events.extend(unexpected_events)

    for change in backlog_task_changes:
        detail = change["detail"]
        run_events.append(f"backlog_change: {detail}")
        logging_store.write_activity_event(
            root=root,
            role_id="operator",
            task_id=change["task_id"],
            event_type="backlog_task_update",
            summary=f"Operator {detail}",
            status="Planned",
            metadata={
                "mode": mode_label,
                "action": change["action"],
                "field_changes": change["field_changes"],
            },
        )

    run_events.append("file_modified: `backlog.md` (operator persisted plan/task updates)")
    logging_store.write_activity_event(
        root=root,
        role_id="operator",
        task_id=f"operator-{mode_label}",
        event_type="file_modified",
        summary="Operator modified file 'backlog.md' while persisting operator_plan.",
        status="Logged",
        metadata={"path": "backlog.md", "mode": mode_label},
    )

    human_feedback = parsed.get("human_feedback")
    if human_feedback:
        feedback_path = _write_feedback_file(
            root=root,
            source_role="operator",
            task_id=f"operator-{mode_label}",
            audience="human",
            summary=human_feedback.get("summary", ""),
            questions=human_feedback.get("questions", []),
            requires_response=bool(human_feedback.get("requires_response", False)),
        )
        run_events.append(
            "return_to_human: operator requested questions/feedback "
            f"via `{feedback_path}`"
        )
        run_events.append(f"file_modified: `{feedback_path}` (operator feedback artifact)")
        logging_store.write_activity_event(
            root=root,
            role_id="operator",
            task_id=f"operator-{mode_label}",
            event_type="operator_human_feedback",
            summary="Operator returned to human for questions/feedback.",
            status="Needs Input",
            metadata={"path": feedback_path, "feedback": human_feedback},
        )
        logging_store.write_activity_event(
            root=root,
            role_id="operator",
            task_id=f"operator-{mode_label}",
            event_type="file_modified",
            summary=f"Operator modified file '{feedback_path}' for human feedback.",
            status="Logged",
            metadata={"path": feedback_path},
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
        events=run_events,
        event_type="operator_plan",
        summary=parsed.get("summary") or f"Operator created plan for mode '{mode_label}'.",
        status="Planned",
        metadata={
            "mode": mode_label,
            "tasks_generated": len(parsed.get("tasks", [])),
            "backlog_task_changes": backlog_task_changes,
            "unexpected_warning": unexpected_warning,
            "unexpected_error": unexpected_error,
        },
    )
    _render_dashboard_best_effort(root, runtime, f"operator-{mode_label}")
    if _unexpected_requires_return_to_user(runtime, unexpected_warning, unexpected_error):
        policy = _unexpected_event_policy(runtime)
        raise OrchestrationHalt(
            "Operator returned unexpected events and policy requires human control handoff. "
            f"policy='{policy}', has_warning={unexpected_warning}, has_error={unexpected_error}."
        )
    return updated_tasks


def _apply_agent_result(
    tasks: list[dict[str, Any]],
    result: dict[str, Any],
    statuses: list[str],
    known_roles: set[str],
    actor_role: str,
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
    if target["owner"] == "operator":
        raise OrchestrationHalt(
            "Invalid owner after updates: 'operator' is forbidden for backlog task ownership."
        )

    if result.get("new_tasks"):
        if actor_role != "operator":
            raise OrchestrationHalt(
                f"Task creation via agent_result.new_tasks is forbidden for non-operator role "
                f"'{actor_role}'. Request new tasks through Operator mediation."
            )
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


def _handle_operator_owner_if_needed(
    root: Path,
    runtime: dict[str, Any],
    state: dict[str, Any],
    tasks: list[dict[str, Any]],
) -> bool:
    """Ensure no active backlog task is owned by Operator."""
    for task in tasks:
        if task["status"] not in {"Todo", "In Progress"}:
            continue
        if task["owner"] != "operator":
            continue
        request = (
            f"Task '{task['task_id']}' is owned by forbidden role 'operator'. "
            "Reassign this task to a non-operator role and update dependencies/sequence as needed."
        )
        _invoke_operator(root, runtime, state, request, "operator-owner-mediation")
        return True
    return False


def execute_one_step(root: Path, runtime: dict[str, Any], state: dict[str, Any]) -> bool:
    backlog_path = root / "backlog.md"
    tasks = backlog_store.read_backlog(backlog_path)
    if not tasks:
        raise OrchestrationHalt("Backlog is empty. Operator must create tasks first.")
    if backlog_store.all_done(tasks):
        return False

    if _handle_operator_owner_if_needed(root, runtime, state, tasks):
        save_state(root, state)
        return True

    if _handle_disabled_owner_if_needed(root, runtime, state, tasks):
        save_state(root, state)
        return True

    next_task = backlog_store.select_next_task(
        tasks=tasks,
        enabled_roles=set(runtime["enabled_roles"]) - {"operator"},
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
    if owner == "operator":
        raise OrchestrationHalt(
            f"Task '{task_id}' cannot be executed: owner 'operator' is forbidden for backlog tasks."
        )
    if owner not in runtime["enabled_roles"]:
        raise OrchestrationHalt(
            f"Task '{task_id}' owner '{owner}' is not enabled and could not be mediated."
        )

    backlog_before = backlog_store.render_backlog(tasks)
    if next_task["status"] == "Todo":
        previous_status = next_task["status"]
        next_task["status"] = "In Progress"
        backlog_store.write_backlog(backlog_path, tasks)
        logging_store.write_activity_event(
            root=root,
            role_id="operator",
            task_id=task_id,
            event_type="backlog_task_update",
            summary=(
                f"Operator updated '{task_id}' status "
                f"from '{previous_status}' to 'In Progress' for execution dispatch."
            ),
            status="In Progress",
            metadata={"field_changes": {"status": {"before": previous_status, "after": "In Progress"}}},
        )
        logging_store.write_activity_event(
            root=root,
            role_id="operator",
            task_id=task_id,
            event_type="file_modified",
            summary="Operator modified file 'backlog.md' while dispatching next task.",
            status="Logged",
            metadata={"path": "backlog.md"},
        )

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

    logging_store.write_activity_event(
        root=root,
        role_id="operator",
        task_id=task_id,
        event_type="operator_role_invoke",
        summary=f"Operator invoked role '{owner}' for task '{task_id}'.",
        status="In Progress",
        metadata={"target_role": owner},
    )

    before_files = _capture_file_snapshot(root)
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
    after_files = _capture_file_snapshot(root)
    invocation_file_changes = _diff_file_snapshots(before_files, after_files)
    file_change_events = _emit_file_change_logs(
        root=root,
        role_id=owner,
        task_id=task_id,
        file_changes=invocation_file_changes,
        reason="during role thread invocation",
    )
    protected_changes = _collect_protected_governance_changes(invocation_file_changes)
    _enforce_protected_governance_edit_guardrail(
        root=root,
        role_id=owner,
        task_id=task_id,
        protected_changes=protected_changes,
        governance_permission_granted=bool(state.get("governance_file_edits_approved", False)),
    )

    logging_store.write_activity_event(
        root=root,
        role_id="operator",
        task_id=task_id,
        event_type="operator_role_return",
        summary=(
            f"Role '{owner}' handed control back to Operator for task '{task_id}' "
            f"with status '{parsed['status']}'."
        ),
        status=parsed.get("status", ""),
        metadata={
            "target_role": owner,
            "role_summary": parsed.get("summary", ""),
            "handoff_requested": bool(parsed.get("handoff_request")),
        },
    )

    tasks_before_apply = _clone_tasks(tasks)
    updated_tasks = _apply_agent_result(
        tasks,
        parsed,
        runtime["statuses"],
        runtime["known_roles"],
        actor_role=owner,
    )
    backlog_store.write_backlog(backlog_path, updated_tasks)
    backlog_task_changes = _describe_task_changes(tasks_before_apply, updated_tasks)
    for change in backlog_task_changes:
        logging_store.write_activity_event(
            root=root,
            role_id=owner,
            task_id=change["task_id"],
            event_type="backlog_task_update",
            summary=f"{owner} {change['detail']}",
            status=parsed.get("status", ""),
            metadata={
                "action": change["action"],
                "field_changes": change["field_changes"],
            },
        )
    logging_store.write_activity_event(
        root=root,
        role_id=owner,
        task_id=task_id,
        event_type="file_modified",
        summary=f"{owner} modified file 'backlog.md' through agent_result persistence.",
        status="Logged",
        metadata={"path": "backlog.md"},
    )

    notes_events: list[str] = []
    notes_path = _append_notes_update(root, owner, task_id, parsed.get("notes_update", ""))
    if notes_path:
        notes_events.append(f"notes_update: wrote `{notes_path}`")
        notes_events.append(f"file_modified: `{notes_path}` (notes update)")
        logging_store.write_activity_event(
            root=root,
            role_id=owner,
            task_id=task_id,
            event_type="notes_update",
            summary=f"{owner} appended task notes to '{notes_path}'.",
            status="Logged",
            metadata={"path": notes_path},
        )
        logging_store.write_activity_event(
            root=root,
            role_id=owner,
            task_id=task_id,
            event_type="file_modified",
            summary=f"{owner} modified file '{notes_path}' while writing notes_update.",
            status="Logged",
            metadata={"path": notes_path},
        )

    feedback_events: list[str] = []
    internal_unexpected_warning = False
    internal_unexpected_error = False
    human_feedback = parsed.get("human_feedback")
    if human_feedback:
        human_feedback_path = _write_feedback_file(
            root=root,
            source_role=owner,
            task_id=task_id,
            audience="human",
            summary=human_feedback.get("summary", ""),
            questions=human_feedback.get("questions", []),
            requires_response=bool(human_feedback.get("requires_response", False)),
        )
        feedback_events.append(
            "feedback_to_human: wrote "
            f"`{human_feedback_path}` and returned for questions/feedback"
        )
        feedback_events.append(
            f"file_modified: `{human_feedback_path}` (human feedback artifact)"
        )
        logging_store.write_activity_event(
            root=root,
            role_id=owner,
            task_id=task_id,
            event_type="human_feedback_written",
            summary=f"{owner} wrote human feedback/questions to '{human_feedback_path}'.",
            status="Needs Input",
            metadata={"path": human_feedback_path, "feedback": human_feedback},
        )
        logging_store.write_activity_event(
            root=root,
            role_id=owner,
            task_id=task_id,
            event_type="file_modified",
            summary=f"{owner} modified file '{human_feedback_path}' for human feedback.",
            status="Logged",
            metadata={"path": human_feedback_path},
        )

    role_feedback_entries = parsed.get("role_feedback", [])
    for role_feedback in role_feedback_entries:
        target_role = role_feedback.get("target_role", "")
        if target_role == owner:
            internal_unexpected_warning = True
            feedback_events.append(
                f"unexpected: ignored role_feedback targeting self role '{owner}'"
            )
            logging_store.write_activity_event(
                root=root,
                role_id=owner,
                task_id=task_id,
                event_type="unexpected_event",
                summary=f"Ignored role_feedback targeting same role '{owner}'.",
                status="Warning",
                metadata={"role_feedback": role_feedback},
            )
            continue

        role_feedback_path = _write_feedback_file(
            root=root,
            source_role=owner,
            task_id=task_id,
            audience="role",
            target_role=target_role,
            summary=role_feedback.get("summary", ""),
            questions=role_feedback.get("questions", []),
            requested_action=role_feedback.get("requested_action", ""),
            related_task_ids=role_feedback.get("related_task_ids", []),
            requires_response=True,
        )
        feedback_events.append(
            f"feedback_to_role: wrote `{role_feedback_path}` for `{target_role}`"
        )
        feedback_events.append(
            f"file_modified: `{role_feedback_path}` (role feedback artifact)"
        )
        logging_store.write_activity_event(
            root=root,
            role_id=owner,
            task_id=task_id,
            event_type="role_feedback_written",
            summary=(
                f"{owner} wrote role feedback for '{target_role}' "
                f"to '{role_feedback_path}'."
            ),
            status="Needs Review",
            metadata={"path": role_feedback_path, "role_feedback": role_feedback},
        )
        logging_store.write_activity_event(
            root=root,
            role_id=owner,
            task_id=task_id,
            event_type="file_modified",
            summary=f"{owner} modified file '{role_feedback_path}' for role feedback.",
            status="Logged",
            metadata={"path": role_feedback_path},
        )
        logging_store.write_activity_event(
            root=root,
            role_id="operator",
            task_id=task_id,
            event_type="operator_role_feedback_received",
            summary=(
                f"Operator received feedback relay from '{owner}' to '{target_role}'. "
                f"See '{role_feedback_path}'."
            ),
            status="Queued",
            metadata={"path": role_feedback_path, "source_role": owner, "target_role": target_role},
        )

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
    events.extend(file_change_events)
    events.extend(
        _emit_decision_logs(
            root=root,
            role_id=owner,
            task_id=task_id,
            decisions=parsed.get("decision_log", []),
        )
    )
    unexpected_events, unexpected_warning, unexpected_error = _emit_unexpected_logs(
        root=root,
        role_id=owner,
        task_id=task_id,
        unexpected_entries=parsed.get("unexpected_events", []),
    )
    events.extend(unexpected_events)
    overall_unexpected_warning = unexpected_warning or internal_unexpected_warning
    overall_unexpected_error = unexpected_error or internal_unexpected_error
    for change in backlog_task_changes:
        events.append(f"backlog_change: {change['detail']}")
    events.append("file_modified: `backlog.md` (agent_result persisted)")
    events.extend(notes_events)
    events.extend(feedback_events)
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
        event_type="agent_result",
        summary=parsed.get("summary") or f"{owner} updated task '{task_id}'.",
        status=parsed.get("status", ""),
        metadata={
            "handoff_requested": bool(parsed.get("handoff_request")),
            "backlog_task_changes": backlog_task_changes,
            "role_feedback_count": len(role_feedback_entries),
            "human_feedback": bool(human_feedback),
            "unexpected_warning": overall_unexpected_warning,
            "unexpected_error": overall_unexpected_error,
        },
    )

    if parsed["status"] == "Done":
        state["last_completed_task_id"] = task_id
    state["history"].append(
        {"ts": utc_now(), "event": "task-step", "task_id": task_id, "owner": owner}
    )
    _render_dashboard_best_effort(root, runtime, f"task-step-{task_id}")
    if _unexpected_requires_return_to_user(
        runtime,
        overall_unexpected_warning,
        overall_unexpected_error,
    ):
        policy = _unexpected_event_policy(runtime)
        raise OrchestrationHalt(
            "Role returned unexpected events and policy requires human control handoff. "
            f"policy='{policy}', task_id='{task_id}', owner='{owner}', "
            f"has_warning={overall_unexpected_warning}, has_error={overall_unexpected_error}."
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


def cmd_render_dashboard(args: argparse.Namespace) -> int:
    root = repo_root()
    try:
        output_path = dashboard.render_dashboard(root)
        print(f"Dashboard rendered: {output_path.as_posix()}")
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"Dashboard render failed: {exc}")
        return 1


def _prepare_runtime_or_exit(root: Path) -> dict[str, Any]:
    errors = validators.validate_framework(root)
    if errors:
        joined = "\n".join(f"- {item}" for item in errors)
        raise OrchestrationHalt(f"Validation failed before execution:\n{joined}")
    runtime = _runtime(root)
    enabled_roles = set(runtime.get("enabled_roles", set()))
    non_operator_enabled = {role_id for role_id in enabled_roles if role_id != "operator"}
    if "operator" not in enabled_roles or not non_operator_enabled:
        raise OrchestrationHalt(
            "No executable specialist roles are enabled. "
            "AgentSquad requires Operator plus at least one non-operator role."
        )
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
    state["governance_file_edits_approved"] = _has_governance_edit_permission(args.request)
    save_state(root, state)

    runtime: dict[str, Any] | None = None
    try:
        runtime = _prepare_runtime_or_exit(root)
        _invoke_operator(root, runtime, state, args.request, "initial-plan")
        executed = execute_loop(root, runtime, state, max_steps=None)
        save_state(root, state)
        print(f"Run completed. Steps executed: {executed}")
        return 0
    except KeyboardInterrupt:
        halt_with_reason(root, state, "Interrupted by user.")
        _render_dashboard_best_effort(root, runtime, "run-halt-keyboardinterrupt")
        print("Run interrupted and state persisted.")
        return 1
    except (OrchestrationHalt, AdapterError, contracts.ContractError, context_loader.ContextLoadError) as exc:
        halt_with_reason(root, state, str(exc))
        _render_dashboard_best_effort(root, runtime, "run-halt-error")
        print(f"Run halted: {exc}")
        return 1


def cmd_step(args: argparse.Namespace) -> int:
    root = repo_root()
    state = load_state(root)
    state["governance_file_edits_approved"] = bool(
        state.get("governance_file_edits_approved", False)
        or _has_governance_edit_permission(str(state.get("current_request", "")))
    )
    runtime: dict[str, Any] | None = None
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
        _render_dashboard_best_effort(root, runtime, "step-halt-error")
        print(f"Step halted: {exc}")
        return 1


def cmd_resume(args: argparse.Namespace) -> int:
    root = repo_root()
    state = load_state(root)
    state["governance_file_edits_approved"] = bool(
        state.get("governance_file_edits_approved", False)
        or _has_governance_edit_permission(str(state.get("current_request", "")))
    )
    runtime: dict[str, Any] | None = None
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
        _render_dashboard_best_effort(root, runtime, "resume-halt-keyboardinterrupt")
        print("Resume interrupted and state persisted.")
        return 1
    except (OrchestrationHalt, AdapterError, contracts.ContractError, context_loader.ContextLoadError) as exc:
        halt_with_reason(root, state, str(exc))
        _render_dashboard_best_effort(root, runtime, "resume-halt-error")
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

    render_dashboard_parser = sub.add_parser(
        "render-dashboard",
        help="Build the static project dashboard snapshot.",
    )
    render_dashboard_parser.set_defaults(func=cmd_render_dashboard)

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
