"""Local HTTP server for AgentSquad orchestration and live dashboard updates."""

from __future__ import annotations

import argparse
import copy
import json
import mimetypes
import queue
import re
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from . import dashboard, validators


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 4173
SSE_HEARTBEAT_SECONDS = 15
WATCH_INTERVAL_SECONDS = 1.0
UNSET_VALUE_MARKERS = {"", "tbd", "todo", "n/a", "na", "unknown"}
REQUIRED_CONTEXT_FIELDS = (
    "Project goals",
    "Target users",
    "Key constraints",
    "Primary deliverables",
    "Acceptance criteria",
)
OPTIONAL_CONTEXT_FIELDS = ("Non-goals",)
OPERATOR_INIT_PROMPT = "Read AGENTS.md and initialize this thread as AgentSquad Operator"
ROLE_REVIEW_CONFIRMATION_KEY = "review_confirmed"
ROLE_REVIEW_PENDING_MESSAGE = (
    "Role enablement review is pending. Open the Settings tab, review enabled/disabled roles, "
    "then click Apply Settings to confirm."
)


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _file_signature(path: Path) -> tuple[int, int] | None:
    if not path.exists():
        return None
    try:
        stat = path.stat()
    except OSError:
        return None
    return (int(stat.st_mtime_ns), int(stat.st_size))


def _workspace_activity_signature(root: Path) -> tuple[tuple[str, tuple[int, int] | None], ...]:
    workspace_root = root / "project" / "workspaces"
    if not workspace_root.exists():
        return tuple()
    signatures: list[tuple[str, tuple[int, int] | None]] = []
    for activity_file in sorted(workspace_root.glob("*/activity.jsonl")):
        rel = activity_file.relative_to(root).as_posix()
        signatures.append((rel, _file_signature(activity_file)))
    return tuple(signatures)


@dataclass
class EventBroker:
    """In-process publish/subscribe broker for SSE clients."""

    _lock: threading.Lock = field(default_factory=threading.Lock)
    _subscribers: set[queue.Queue[dict[str, Any]]] = field(default_factory=set)
    _next_event_id: int = 0

    def subscribe(self) -> queue.Queue[dict[str, Any]]:
        subscriber: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=256)
        with self._lock:
            self._subscribers.add(subscriber)
        return subscriber

    def unsubscribe(self, subscriber: queue.Queue[dict[str, Any]]) -> None:
        with self._lock:
            self._subscribers.discard(subscriber)

    def publish(self, event_type: str, payload: dict[str, Any] | None = None) -> None:
        payload = payload or {}
        with self._lock:
            self._next_event_id += 1
            event = {
                "id": self._next_event_id,
                "event": event_type,
                "ts_utc": utc_now(),
                "payload": payload,
            }
            subscribers = list(self._subscribers)
        for subscriber in subscribers:
            try:
                subscriber.put_nowait(event)
            except queue.Full:
                try:
                    subscriber.get_nowait()
                except queue.Empty:
                    pass
                try:
                    subscriber.put_nowait(event)
                except queue.Full:
                    # If a client still cannot keep up, drop event for that client.
                    continue


class FileChangeWatcher(threading.Thread):
    """Polls key project files and publishes coarse-grained change events."""

    def __init__(self, root: Path, broker: EventBroker, stop_event: threading.Event) -> None:
        super().__init__(daemon=True)
        self._root = root
        self._broker = broker
        self._stop_event = stop_event
        self._last_snapshot: dict[str, Any] = {}

    def _snapshot(self) -> dict[str, Any]:
        return {
            "tasks_changed": _file_signature(self._root / "backlog.md"),
            "activity_changed": (
                _file_signature(self._root / "project" / "state" / "activity-log.jsonl"),
                _workspace_activity_signature(self._root),
            ),
            "state_changed": _file_signature(
                self._root / "project" / "state" / "orchestrator-state.yaml"
            ),
            "settings_changed": _file_signature(self._root / "project" / "config" / "project.yaml"),
        }

    def run(self) -> None:
        self._last_snapshot = self._snapshot()
        while not self._stop_event.wait(WATCH_INTERVAL_SECONDS):
            current = self._snapshot()
            changed_events = [
                event_type
                for event_type, current_signature in current.items()
                if self._last_snapshot.get(event_type) != current_signature
            ]
            self._last_snapshot = current
            for event_type in changed_events:
                self._broker.publish(
                    event_type,
                    {"source": "file-watch"},
                )


@dataclass
class ServerState:
    root: Path
    lock: threading.RLock = field(default_factory=threading.RLock)
    broker: EventBroker = field(default_factory=EventBroker)
    stop_event: threading.Event = field(default_factory=threading.Event)
    watcher: FileChangeWatcher | None = None

    def build_dashboard_payload(self) -> dict[str, Any]:
        with self.lock:
            return dashboard.build_payload(
                self.root,
                repo_root_relative_prefix=".",
                output_path="project/state/dashboard.html",
            )

    def render_dashboard_html(self) -> str:
        with self.lock:
            return dashboard.render_dashboard_html(
                self.root,
                repo_root_relative_prefix=".",
                output_path="project/state/dashboard.html",
            )

    def start_watcher(self) -> None:
        self.watcher = FileChangeWatcher(self.root, self.broker, self.stop_event)
        self.watcher.start()

    def stop_watcher(self) -> None:
        self.stop_event.set()
        if self.watcher and self.watcher.is_alive():
            self.watcher.join(timeout=2.0)


def _normalize_role_list(raw: Any, *, field_name: str, errors: list[str]) -> list[str]:
    if not isinstance(raw, list):
        errors.append(f"{field_name} must be a list of role IDs.")
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for item in raw:
        role_id = str(item).strip()
        if not role_id:
            continue
        if role_id in seen:
            continue
        seen.add(role_id)
        normalized.append(role_id)
    return normalized


def _parse_bool(value: Any, *, field_name: str, errors: list[str]) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered == "true":
            return True
        if lowered == "false":
            return False
    errors.append(f"{field_name} must be boolean.")
    return False


def _parse_positive_int(value: Any, *, field_name: str, errors: list[str]) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        errors.append(f"{field_name} must be an integer greater than 0.")
        return 0
    if parsed <= 0:
        errors.append(f"{field_name} must be an integer greater than 0.")
        return 0
    return parsed


def _is_value_defined(raw_value: str) -> bool:
    normalized = str(raw_value or "").strip().lower()
    return normalized not in UNSET_VALUE_MARKERS


def _extract_context_value(context_text: str, field_label: str) -> str:
    pattern = rf"^- {re.escape(field_label)}:[ \t]*(.*)$"
    match = re.search(pattern, context_text, flags=re.MULTILINE)
    if not match:
        return ""
    return match.group(1).strip()


def _context_field_values(root: Path) -> dict[str, str]:
    labels = [*REQUIRED_CONTEXT_FIELDS, *OPTIONAL_CONTEXT_FIELDS]
    values = {label: "" for label in labels}
    context_path = root / "project" / "context" / "project-context.md"
    if not context_path.exists():
        return values
    context_text = context_path.read_text(encoding="utf-8")
    for label in labels:
        values[label] = _extract_context_value(context_text, label)
    return values


def _read_notes_section(root: Path) -> str:
    context_path = root / "project" / "context" / "project-context.md"
    if not context_path.exists():
        return ""
    text = context_path.read_text(encoding="utf-8")
    marker = "## Notes"
    index = text.find(marker)
    if index == -1:
        return ""
    notes = text[index + len(marker) :].strip()
    return notes


def _role_review_confirmed(config: dict[str, Any]) -> bool:
    roles_cfg = config.get("roles", {})
    if not isinstance(roles_cfg, dict):
        return False
    return bool(roles_cfg.get(ROLE_REVIEW_CONFIRMATION_KEY, False))


def _format_context_markdown(values: dict[str, str], notes: str) -> str:
    non_goals = str(values.get("Non-goals", "")).strip()
    notes_text = str(notes).strip()
    if not notes_text:
        notes_text = "Add evolving context here as work progresses."
    lines = [
        'This file tracks project specific context that is shared across all agent roles as the orchestration engine runs. This file must be initialized before orchestration can begin. To modify project context later, use the "Project" tab.',
        "",
        "## Summary",
        "",
        f"- Project goals: {str(values.get('Project goals', '')).strip()}",
        f"- Target users: {str(values.get('Target users', '')).strip()}",
        f"- Key constraints: {str(values.get('Key constraints', '')).strip()}",
        f"- Non-goals: {non_goals}",
        "",
        "## Deliverables",
        "",
        f"- Primary deliverables: {str(values.get('Primary deliverables', '')).strip()}",
        f"- Acceptance criteria: {str(values.get('Acceptance criteria', '')).strip()}",
        "",
        "## Notes",
        "",
        notes_text,
        "",
    ]
    return "\n".join(lines)


def _initialization_state(root: Path) -> dict[str, Any]:
    config = validators.load_project_config(root)
    project_cfg = config.get("project", {})
    roles_cfg = config.get("roles", {})
    if not isinstance(roles_cfg, dict):
        roles_cfg = {}
    context_values = _context_field_values(root)
    project_id = str(project_cfg.get("id", "")).strip()
    project_name = str(project_cfg.get("name", "")).strip()

    missing_fields: list[str] = []
    if not _is_value_defined(project_id) or project_id == "sample-project":
        missing_fields.append("project.id")
    if not _is_value_defined(project_name) or project_name.lower() == "sample project":
        missing_fields.append("project.name")
    for field in REQUIRED_CONTEXT_FIELDS:
        if not _is_value_defined(context_values.get(field, "")):
            missing_fields.append(field)
    project_setup_complete = len(missing_fields) == 0
    role_review_complete = _role_review_confirmed(config)
    pending_items: list[str] = []
    if not project_setup_complete:
        pending_items.append("Project details are incomplete on the Project tab.")
    if project_setup_complete and not role_review_complete:
        pending_items.append(ROLE_REVIEW_PENDING_MESSAGE)

    return {
        "is_ready": project_setup_complete and role_review_complete,
        "project_setup_complete": project_setup_complete,
        "role_review_complete": role_review_complete,
        "missing_fields": missing_fields,
        "pending_items": pending_items,
        "operator_init_prompt": OPERATOR_INIT_PROMPT,
        "fields": {
            "project_id": project_id if project_id != "sample-project" else "",
            "project_name": project_name if project_name.lower() != "sample project" else "",
            "project_goals": context_values.get("Project goals", ""),
            "target_users": context_values.get("Target users", ""),
            "key_constraints": context_values.get("Key constraints", ""),
            "primary_deliverables": context_values.get("Primary deliverables", ""),
            "acceptance_criteria": context_values.get("Acceptance criteria", ""),
            "non_goals": context_values.get("Non-goals", ""),
            "notes": _read_notes_section(root),
        },
    }


def _apply_initialization_submission(
    root: Path,
    payload: dict[str, Any],
) -> tuple[bool, dict[str, Any]]:
    if not isinstance(payload, dict):
        return False, {"errors": ["Request body must be a JSON object."]}

    errors: list[str] = []
    project_payload = payload.get("project", {})
    context_payload = payload.get("context", {})
    if project_payload is None:
        project_payload = {}
    if context_payload is None:
        context_payload = {}
    if not isinstance(project_payload, dict):
        errors.append("project must be an object.")
        project_payload = {}
    if not isinstance(context_payload, dict):
        errors.append("context must be an object.")
        context_payload = {}

    project_id = str(project_payload.get("id", "")).strip()
    project_name = str(project_payload.get("name", "")).strip()
    field_map = {
        "Project goals": str(context_payload.get("project_goals", "")).strip(),
        "Target users": str(context_payload.get("target_users", "")).strip(),
        "Key constraints": str(context_payload.get("key_constraints", "")).strip(),
        "Primary deliverables": str(context_payload.get("primary_deliverables", "")).strip(),
        "Acceptance criteria": str(context_payload.get("acceptance_criteria", "")).strip(),
        "Non-goals": str(context_payload.get("non_goals", "")).strip(),
    }
    notes = str(context_payload.get("notes", "")).strip()

    if not _is_value_defined(project_id):
        errors.append("project.id is required.")
    if not _is_value_defined(project_name):
        errors.append("project.name is required.")
    for label in REQUIRED_CONTEXT_FIELDS:
        if not _is_value_defined(field_map.get(label, "")):
            errors.append(f"{label} is required.")
    if errors:
        return False, {"errors": errors}

    config = validators.load_project_config(root)
    updated = copy.deepcopy(config)
    project_cfg = updated.setdefault("project", {})
    if not isinstance(project_cfg, dict):
        project_cfg = {}
        updated["project"] = project_cfg
    project_cfg["id"] = project_id
    project_cfg["name"] = project_name
    roles_cfg = updated.setdefault("roles", {})
    if not isinstance(roles_cfg, dict):
        roles_cfg = {}
        updated["roles"] = roles_cfg
    # Project details changed, so role review must be reconfirmed against updated context.
    roles_cfg[ROLE_REVIEW_CONFIRMATION_KEY] = False

    config_errors = validators.validate_project_config_data(updated)
    if config_errors:
        return False, {"errors": config_errors}

    validators.write_yaml_file(root / "project" / "config" / "project.yaml", updated)
    context_markdown = _format_context_markdown(field_map, notes)
    context_path = root / "project" / "context" / "project-context.md"
    context_path.parent.mkdir(parents=True, exist_ok=True)
    context_path.write_text(context_markdown, encoding="utf-8")
    return True, {"initialization": _initialization_state(root)}


def _validate_role_sets(root: Path, config: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    registry_roles = set(validators.load_registry(root).get("roles", {}).keys())
    roles_cfg = config.get("roles", {})
    enabled = set(roles_cfg.get("enabled", [])) if isinstance(roles_cfg, dict) else set()
    disabled = set(roles_cfg.get("disabled", [])) if isinstance(roles_cfg, dict) else set()
    unknown_enabled = sorted(enabled - registry_roles)
    unknown_disabled = sorted(disabled - registry_roles)
    overlap = sorted(enabled & disabled)
    if unknown_enabled:
        errors.append(f"roles.enabled contains unknown roles: {unknown_enabled}")
    if unknown_disabled:
        errors.append(f"roles.disabled contains unknown roles: {unknown_disabled}")
    if overlap:
        errors.append(f"roles.enabled and roles.disabled overlap: {overlap}")
    return errors


def _apply_settings_patch(root: Path, patch_payload: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    if not isinstance(patch_payload, dict):
        return False, {"errors": ["Request body must be a JSON object."]}

    config = validators.load_project_config(root)
    updated = copy.deepcopy(config)
    errors: list[str] = []

    settings_patch = patch_payload.get("settings", {})
    if settings_patch is None:
        settings_patch = {}
    if not isinstance(settings_patch, dict):
        errors.append("settings must be an object when provided.")
        settings_patch = {}

    roles_patch = patch_payload.get("roles")
    if roles_patch is not None and not isinstance(roles_patch, dict):
        errors.append("roles must be an object when provided.")
        roles_patch = {}

    host_patch = settings_patch.get("host", {})
    if host_patch is None:
        host_patch = {}
    if not isinstance(host_patch, dict):
        errors.append("settings.host must be an object when provided.")
        host_patch = {}
    execution_patch = settings_patch.get("execution", {})
    if execution_patch is None:
        execution_patch = {}
    if not isinstance(execution_patch, dict):
        errors.append("settings.execution must be an object when provided.")
        execution_patch = {}
    dashboard_patch = settings_patch.get("dashboard", {})
    if dashboard_patch is None:
        dashboard_patch = {}
    if not isinstance(dashboard_patch, dict):
        errors.append("settings.dashboard must be an object when provided.")
        dashboard_patch = {}

    host_cfg = updated.setdefault("host", {})
    if isinstance(host_cfg, dict):
        if "primary_adapter" in host_patch:
            host_cfg["primary_adapter"] = str(host_patch.get("primary_adapter", "")).strip()
        if "adapter_command" in host_patch:
            host_cfg["adapter_command"] = str(host_patch.get("adapter_command", "")).strip()
        if "session_mode" in host_patch:
            host_cfg["session_mode"] = str(host_patch.get("session_mode", "")).strip()
        if "context_rot_guardrails" in host_patch:
            guard_patch = host_patch.get("context_rot_guardrails", {})
            if not isinstance(guard_patch, dict):
                errors.append("settings.host.context_rot_guardrails must be an object when provided.")
            else:
                guard_cfg = host_cfg.setdefault("context_rot_guardrails", {})
                if not isinstance(guard_cfg, dict):
                    guard_cfg = {}
                    host_cfg["context_rot_guardrails"] = guard_cfg
                if "max_turns_per_role_session" in guard_patch:
                    guard_cfg["max_turns_per_role_session"] = _parse_positive_int(
                        guard_patch.get("max_turns_per_role_session"),
                        field_name="settings.host.context_rot_guardrails.max_turns_per_role_session",
                        errors=errors,
                    )
                if "max_session_age_minutes" in guard_patch:
                    guard_cfg["max_session_age_minutes"] = _parse_positive_int(
                        guard_patch.get("max_session_age_minutes"),
                        field_name="settings.host.context_rot_guardrails.max_session_age_minutes",
                        errors=errors,
                    )
                if "force_reload_on_context_change" in guard_patch:
                    guard_cfg["force_reload_on_context_change"] = _parse_bool(
                        guard_patch.get("force_reload_on_context_change"),
                        field_name=(
                            "settings.host.context_rot_guardrails.force_reload_on_context_change"
                        ),
                        errors=errors,
                    )

    execution_cfg = updated.setdefault("execution", {})
    if isinstance(execution_cfg, dict):
        if "mode" in execution_patch:
            execution_cfg["mode"] = str(execution_patch.get("mode", "")).strip()
        if "handoff_authority" in execution_patch:
            execution_cfg["handoff_authority"] = str(
                execution_patch.get("handoff_authority", "")
            ).strip()
        if "selection_policy" in execution_patch:
            execution_cfg["selection_policy"] = str(execution_patch.get("selection_policy", "")).strip()
        if "unexpected_event_policy" in execution_patch:
            execution_cfg["unexpected_event_policy"] = str(
                execution_patch.get("unexpected_event_policy", "")
            ).strip()

    dashboard_cfg = updated.setdefault("dashboard", {})
    if isinstance(dashboard_cfg, dict):
        if "output_file" in dashboard_patch:
            dashboard_cfg["output_file"] = str(dashboard_patch.get("output_file", "")).strip()
        if "refresh_policy" in dashboard_patch:
            dashboard_cfg["refresh_policy"] = str(dashboard_patch.get("refresh_policy", "")).strip()
        if "failure_mode" in dashboard_patch:
            dashboard_cfg["failure_mode"] = str(dashboard_patch.get("failure_mode", "")).strip()

    if isinstance(roles_patch, dict):
        roles_cfg = updated.setdefault("roles", {})
        if not isinstance(roles_cfg, dict):
            roles_cfg = {}
            updated["roles"] = roles_cfg
        if "enabled" in roles_patch:
            roles_cfg["enabled"] = _normalize_role_list(
                roles_patch.get("enabled"),
                field_name="roles.enabled",
                errors=errors,
            )
        if "disabled" in roles_patch:
            roles_cfg["disabled"] = _normalize_role_list(
                roles_patch.get("disabled"),
                field_name="roles.disabled",
                errors=errors,
            )

        enabled_roles = list(roles_cfg.get("enabled", []))
        disabled_roles = [role_id for role_id in roles_cfg.get("disabled", []) if role_id != "operator"]
        if "operator" not in enabled_roles:
            enabled_roles.insert(0, "operator")
        disabled_roles = [role_id for role_id in disabled_roles if role_id not in set(enabled_roles)]
        roles_cfg["enabled"] = enabled_roles
        roles_cfg["disabled"] = disabled_roles
        # Treat any settings apply with role payload as explicit role-review confirmation.
        roles_cfg[ROLE_REVIEW_CONFIRMATION_KEY] = True

    errors.extend(validators.validate_project_config_data(updated))
    errors.extend(_validate_role_sets(root, updated))
    if errors:
        return False, {"errors": errors}

    validators.write_yaml_file(root / "project" / "config" / "project.yaml", updated)
    return True, {"config": updated}


def _build_handler(state: ServerState) -> type[BaseHTTPRequestHandler]:
    class AgentSquadServerHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def _send_bytes(
            self,
            status_code: int,
            body: bytes,
            *,
            content_type: str,
            extra_headers: dict[str, str] | None = None,
        ) -> None:
            self.send_response(status_code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            if extra_headers:
                for key, value in extra_headers.items():
                    self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body)

        def _send_json(self, status_code: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
            self._send_bytes(status_code, body, content_type="application/json; charset=utf-8")

        def _read_json_body(self) -> dict[str, Any] | None:
            content_length = self.headers.get("Content-Length", "")
            if not content_length:
                return {}
            try:
                size = int(content_length)
            except ValueError:
                self._send_json(400, {"ok": False, "errors": ["Invalid Content-Length header."]})
                return None
            if size <= 0:
                return {}
            raw = self.rfile.read(size)
            try:
                decoded = json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError:
                self._send_json(400, {"ok": False, "errors": ["Request body must be valid JSON."]})
                return None
            if not isinstance(decoded, dict):
                self._send_json(400, {"ok": False, "errors": ["Request body must be a JSON object."]})
                return None
            return decoded

        def _safe_repo_file(self, request_path: str) -> Path | None:
            normalized = unquote(request_path).strip().lstrip("/")
            if not normalized:
                return None
            candidate = (state.root / normalized).resolve()
            try:
                candidate.relative_to(state.root)
            except ValueError:
                return None
            if not candidate.exists() or not candidate.is_file():
                return None
            return candidate

        def _serve_static_file(self, request_path: str) -> None:
            candidate = self._safe_repo_file(request_path)
            if not candidate:
                self._send_json(404, {"ok": False, "errors": ["Not found."]})
                return
            content_type, _ = mimetypes.guess_type(candidate.as_posix())
            if not content_type:
                content_type = "application/octet-stream"
            self._send_bytes(
                200,
                candidate.read_bytes(),
                content_type=f"{content_type}; charset=utf-8"
                if content_type.startswith("text/") or content_type in {"application/json", "application/javascript"}
                else content_type,
            )

        def _serve_events(self) -> None:
            subscriber = state.broker.subscribe()
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            try:
                self.wfile.write(b"event: connected\n")
                self.wfile.write(
                    (
                        "data: "
                        + json.dumps({"ok": True, "ts_utc": utc_now()}, ensure_ascii=True)
                        + "\n\n"
                    ).encode("utf-8")
                )
                self.wfile.flush()
                while not state.stop_event.is_set():
                    try:
                        event = subscriber.get(timeout=SSE_HEARTBEAT_SECONDS)
                    except queue.Empty:
                        try:
                            self.wfile.write(b": ping\n\n")
                            self.wfile.flush()
                        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
                            break
                        continue
                    event_name = str(event.get("event", "message"))
                    payload = {
                        "id": event.get("id"),
                        "ts_utc": event.get("ts_utc"),
                        "payload": event.get("payload", {}),
                    }
                    try:
                        self.wfile.write(f"event: {event_name}\n".encode("utf-8"))
                        self.wfile.write(
                            f"data: {json.dumps(payload, ensure_ascii=True)}\n\n".encode("utf-8")
                        )
                        self.wfile.flush()
                    except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
                        break
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
                return
            finally:
                state.broker.unsubscribe(subscriber)

        def _dashboard_sections(self) -> dict[str, Any]:
            payload = state.build_dashboard_payload()
            payload["initialization"] = _initialization_state(state.root)
            return payload

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = parsed.path or "/"

            if path in {"/", "/index.html", "/dashboard"}:
                html = state.render_dashboard_html().encode("utf-8")
                self._send_bytes(200, html, content_type="text/html; charset=utf-8")
                return
            if path == "/health":
                self._send_json(200, {"ok": True, "ts_utc": utc_now()})
                return
            if path == "/api/events":
                self._serve_events()
                return
            if path == "/api/dashboard":
                self._send_json(200, {"ok": True, "dashboard": self._dashboard_sections()})
                return
            if path == "/api/project":
                payload = self._dashboard_sections()
                self._send_json(
                    200,
                    {
                        "ok": True,
                        "generated_at_utc": payload.get("generated_at_utc"),
                        "project": payload.get("project", {}),
                    },
                )
                return
            if path == "/api/tasks":
                payload = self._dashboard_sections()
                self._send_json(
                    200,
                    {
                        "ok": True,
                        "generated_at_utc": payload.get("generated_at_utc"),
                        "tasks": payload.get("tasks", []),
                        "status_counts": payload.get("project", {}).get("status_counts", {}),
                    },
                )
                return
            if path == "/api/activity":
                payload = self._dashboard_sections()
                self._send_json(
                    200,
                    {
                        "ok": True,
                        "generated_at_utc": payload.get("generated_at_utc"),
                        "activity_log": payload.get("activity_log", []),
                    },
                )
                return
            if path == "/api/agents":
                payload = self._dashboard_sections()
                self._send_json(
                    200,
                    {
                        "ok": True,
                        "generated_at_utc": payload.get("generated_at_utc"),
                        "agents": payload.get("agents", []),
                        "agent_colors": payload.get("agent_colors", {}),
                    },
                )
                return
            if path == "/api/settings":
                payload = self._dashboard_sections()
                project = payload.get("project", {})
                self._send_json(
                    200,
                    {
                        "ok": True,
                        "generated_at_utc": payload.get("generated_at_utc"),
                        "settings": payload.get("settings", {}),
                        "roles": {
                            "enabled": project.get("enabled_roles", []),
                            "disabled": project.get("disabled_roles", []),
                        },
                    },
                )
                return
            if path == "/api/init/status":
                self._send_json(
                    200,
                    {
                        "ok": True,
                        "initialization": _initialization_state(state.root),
                    },
                )
                return

            self._serve_static_file(path)

        def do_PATCH(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path != "/api/settings":
                self._send_json(404, {"ok": False, "errors": ["Not found."]})
                return
            body = self._read_json_body()
            if body is None:
                return
            with state.lock:
                ok, details = _apply_settings_patch(state.root, body)
            if not ok:
                self._send_json(400, {"ok": False, "errors": details.get("errors", [])})
                return
            state.broker.publish("settings_changed", {"source": "api"})
            payload = state.build_dashboard_payload()
            self._send_json(
                200,
                {
                    "ok": True,
                    "generated_at_utc": payload.get("generated_at_utc"),
                    "settings": payload.get("settings", {}),
                    "project": payload.get("project", {}),
                },
            )

        def _run_orchestrator_command(
            self,
            subcommand: str,
            *,
            request_text: str = "",
        ) -> dict[str, Any]:
            command = [sys.executable, "-m", "runner.orchestrator", subcommand]
            if subcommand == "run":
                command.extend(["--request", request_text])
            result = subprocess.run(
                command,
                cwd=state.root,
                text=True,
                capture_output=True,
                check=False,
            )
            return {
                "command": command,
                "exit_code": int(result.returncode),
                "stdout": result.stdout,
                "stderr": result.stderr,
            }

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path == "/api/init/submit":
                body = self._read_json_body()
                if body is None:
                    return
                with state.lock:
                    ok, details = _apply_initialization_submission(state.root, body)
                if not ok:
                    self._send_json(400, {"ok": False, "errors": details.get("errors", [])})
                    return
                state.broker.publish("settings_changed", {"source": "api", "action": "init-submit"})
                state.broker.publish("state_changed", {"source": "api", "action": "init-submit"})
                self._send_json(
                    200,
                    {
                        "ok": True,
                        "initialization": details.get("initialization", _initialization_state(state.root)),
                    },
                )
                return

            if not parsed.path.startswith("/api/orchestrator/"):
                self._send_json(404, {"ok": False, "errors": ["Not found."]})
                return

            action = parsed.path.rsplit("/", 1)[-1]
            if action not in {"validate", "step", "run", "resume"}:
                self._send_json(404, {"ok": False, "errors": ["Unknown orchestrator action."]})
                return

            body = self._read_json_body()
            if body is None:
                return

            request_text = ""
            if action == "run":
                request_text = str(body.get("request", "")).strip()
                if not request_text:
                    self._send_json(
                        400,
                        {"ok": False, "errors": ["Field 'request' is required for /api/orchestrator/run."]},
                    )
                    return

            with state.lock:
                result = self._run_orchestrator_command(action, request_text=request_text)

            state.broker.publish("state_changed", {"source": "api", "action": action})
            if action in {"step", "run", "resume"}:
                state.broker.publish("tasks_changed", {"source": "api", "action": action})
                state.broker.publish("activity_changed", {"source": "api", "action": action})

            self._send_json(
                200,
                {
                    "ok": result["exit_code"] == 0,
                    "action": action,
                    "result": result,
                },
            )

        def log_message(self, fmt: str, *args: Any) -> None:
            message = fmt % args
            sys.stdout.write(f"[server] {self.address_string()} - {message}\n")

    return AgentSquadServerHandler


class AgentSquadHTTPServer(ThreadingHTTPServer):
    """HTTP server with quiet handling for expected client disconnects."""

    def handle_error(self, request: Any, client_address: tuple[str, int]) -> None:
        _, exc, _ = sys.exc_info()
        if isinstance(exc, (ConnectionAbortedError, ConnectionResetError, BrokenPipeError)):
            return
        if isinstance(exc, OSError) and getattr(exc, "winerror", None) in {10053, 10054}:
            return
        super().handle_error(request, client_address)


def run_server(root: Path, host: str, port: int) -> int:
    state = ServerState(root=root)
    state.start_watcher()
    handler = _build_handler(state)
    server = AgentSquadHTTPServer((host, port), handler)
    server.daemon_threads = True

    print(f"AgentSquad local server running at http://{host}:{port}")
    print(f"Repository root: {root.as_posix()}")
    print("Now open that URL in your browser and complete the Initialize tab steps.")
    print("After submitting project details, optionally tune settings/agents, then initialize Operator in your IDE.")
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        print("\nShutting down server.")
    finally:
        state.stop_watcher()
        server.shutdown()
        server.server_close()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run AgentSquad local dashboard/orchestration server.")
    parser.add_argument("--host", default=DEFAULT_HOST, help="Bind address (default: 127.0.0.1).")
    parser.add_argument("--port", default=DEFAULT_PORT, type=int, help="Bind port (default: 4173).")
    parser.add_argument(
        "--root",
        default=".",
        help="Repository root path (default: current working directory).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    if not root.exists():
        print(f"Root path does not exist: {root}")
        return 1
    return run_server(root=root, host=str(args.host), port=int(args.port))


if __name__ == "__main__":
    raise SystemExit(main())
