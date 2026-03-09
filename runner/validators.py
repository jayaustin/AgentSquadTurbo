"""Framework validation and lightweight YAML support."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from . import backlog_store


class ValidationFailure(ValueError):
    """Raised when data cannot be parsed or validated."""


DASHBOARD_AGENT_COLOR_DEFAULTS = {
    "operator": "#3B82F6",
}

DASHBOARD_DEFAULTS = {
    "enabled": True,
    "output_file": "project/state/dashboard.html",
    "refresh_policy": "after-every-step",
    "failure_mode": "non-blocking-log",
    "docs": {
        "include_paths": ["project/docs", "docs", "project/context"],
        "exclude_globs": [
            "superpowers/**",
            "steering/**",
            "runner/templates/**",
            "project/workspaces/**/runs/**",
            "project/workspaces/**/notes.md",
        ],
        "primary_name_keywords": [
            "design",
            "technical",
            "architecture",
            "spec",
            "qa",
            "localization",
            "ux",
            "audio",
            "security",
            "validation",
        ],
    },
    "agent_colors": DASHBOARD_AGENT_COLOR_DEFAULTS,
}

HEX_COLOR_PATTERN = re.compile(r"^#[0-9A-Fa-f]{6}$")


def _strip_line_comment(raw_line: str) -> str:
    line = raw_line.rstrip("\n")
    if "#" not in line:
        return line
    in_single = False
    in_double = False
    result: list[str] = []
    for ch in line:
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        if ch == "#" and not in_single and not in_double:
            break
        result.append(ch)
    return "".join(result).rstrip()


def _parse_inline_list(raw: str) -> list[Any]:
    content = raw.strip()[1:-1].strip()
    if not content:
        return []
    parts = [part.strip() for part in content.split(",")]
    return [_parse_scalar(part) for part in parts if part]


def _parse_scalar(raw: str) -> Any:
    text = raw.strip()
    lowered = text.lower()
    if lowered == "null":
        return None
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if re.fullmatch(r"-?\d+", text):
        return int(text)
    if text.startswith("[") and text.endswith("]"):
        return _parse_inline_list(text)
    if (text.startswith('"') and text.endswith('"')) or (text.startswith("'") and text.endswith("'")):
        return text[1:-1]
    return text


def _load_yaml_lines(text: str) -> list[tuple[int, str]]:
    parsed: list[tuple[int, str]] = []
    for raw_line in text.splitlines():
        stripped_comment = _strip_line_comment(raw_line)
        if not stripped_comment.strip():
            continue
        if "\t" in stripped_comment:
            raise ValidationFailure("Tabs are not supported in YAML parser.")
        indent = len(stripped_comment) - len(stripped_comment.lstrip(" "))
        parsed.append((indent, stripped_comment.strip()))
    return parsed


def _parse_yaml_block(lines: list[tuple[int, str]], index: int, indent: int) -> tuple[Any, int]:
    if index >= len(lines):
        return {}, index

    current_indent, current_text = lines[index]
    if current_indent < indent:
        return {}, index

    if current_text == "-" or current_text.startswith("- "):
        items: list[Any] = []
        while index < len(lines):
            line_indent, line_text = lines[index]
            if line_indent != indent or not (line_text == "-" or line_text.startswith("- ")):
                break
            value_text = "" if line_text == "-" else line_text[2:].strip()
            index += 1
            if value_text:
                items.append(_parse_scalar(value_text))
                continue
            child, index = _parse_yaml_block(lines, index, indent + 2)
            items.append(child)
        return items, index

    mapping: dict[str, Any] = {}
    while index < len(lines):
        line_indent, line_text = lines[index]
        if line_indent < indent:
            break
        if line_indent > indent:
            raise ValidationFailure(f"Unexpected indentation near '{line_text}'.")
        if line_text == "-" or line_text.startswith("- "):
            break
        if ":" not in line_text:
            raise ValidationFailure(f"Invalid YAML line '{line_text}'. Expected key: value.")
        key, value = line_text.split(":", 1)
        key = key.strip()
        value = value.strip()
        index += 1
        if value:
            mapping[key] = _parse_scalar(value)
            continue
        child, index = _parse_yaml_block(lines, index, indent + 2)
        mapping[key] = child
    return mapping, index


def parse_yaml_text(text: str) -> dict[str, Any]:
    lines = _load_yaml_lines(text)
    if not lines:
        return {}
    parsed, index = _parse_yaml_block(lines, 0, lines[0][0])
    if index != len(lines):
        raise ValidationFailure("YAML parse did not consume all lines.")
    if not isinstance(parsed, dict):
        raise ValidationFailure("Top-level YAML object must be a mapping.")
    return parsed


def _yaml_quote(text: str) -> str:
    if text == "":
        return '""'
    if re.fullmatch(r"[A-Za-z0-9._\-/]+", text):
        lowered = text.lower()
        if lowered not in {"true", "false", "null"}:
            return text
    return json.dumps(text, ensure_ascii=True)


def _dump_yaml_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        return _yaml_quote(value)
    if isinstance(value, list) and not value:
        return "[]"
    if isinstance(value, dict) and not value:
        return "{}"
    raise ValidationFailure(f"Unsupported scalar type for YAML dump: {type(value)}")


def dump_yaml_text(data: Any, indent: int = 0) -> str:
    prefix = " " * indent
    if isinstance(data, dict):
        lines: list[str] = []
        for key, value in data.items():
            if isinstance(value, (dict, list)) and value:
                lines.append(f"{prefix}{key}:")
                lines.append(dump_yaml_text(value, indent + 2))
            else:
                lines.append(f"{prefix}{key}: {_dump_yaml_scalar(value)}")
        return "\n".join(lines)
    if isinstance(data, list):
        lines = []
        for item in data:
            if isinstance(item, (dict, list)):
                lines.append(f"{prefix}-")
                lines.append(dump_yaml_text(item, indent + 2))
            else:
                lines.append(f"{prefix}- {_dump_yaml_scalar(item)}")
        return "\n".join(lines)
    return f"{prefix}{_dump_yaml_scalar(data)}"


def load_data_file(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    stripped = text.strip()
    if not stripped:
        return {}
    if stripped.startswith("{"):
        parsed_json = json.loads(stripped)
        if isinstance(parsed_json, dict):
            return parsed_json
        raise ValidationFailure(f"JSON data in {path} must be an object.")
    return parse_yaml_text(text)


def write_yaml_file(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dump_yaml_text(data) + "\n", encoding="utf-8")


def extract_frontmatter(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---\n?", text, flags=re.DOTALL)
    if not match:
        return {}
    return parse_yaml_text(match.group(1))


def load_project_config(root: Path) -> dict[str, Any]:
    path = root / "project" / "config" / "project.yaml"
    if not path.exists():
        raise ValidationFailure("Missing project/config/project.yaml")
    config = load_data_file(path)
    if not isinstance(config, dict):
        raise ValidationFailure("project/config/project.yaml must be an object.")
    return config


def load_registry(root: Path) -> dict[str, Any]:
    path = root / "agents" / "registry.yaml"
    if not path.exists():
        raise ValidationFailure("Missing agents/registry.yaml")
    registry = load_data_file(path)
    if not isinstance(registry, dict):
        raise ValidationFailure("agents/registry.yaml must be an object.")
    if "roles" not in registry or not isinstance(registry["roles"], dict):
        raise ValidationFailure("agents/registry.yaml must include roles mapping.")
    return registry


def collect_superpower_ids(root: Path) -> set[str]:
    ids: set[str] = set()
    for file_path in sorted((root / "superpowers").glob("*.md")):
        frontmatter = extract_frontmatter(file_path)
        name = str(frontmatter.get("name", "")).strip()
        if name:
            ids.add(name)
    return ids


def _normalize_str_list(value: Any, fallback: list[str]) -> list[str]:
    if not isinstance(value, list):
        return list(fallback)
    normalized: list[str] = []
    for item in value:
        text = str(item).strip()
        if text:
            normalized.append(text)
    return normalized or list(fallback)


def dashboard_config_with_defaults(config: dict[str, Any]) -> dict[str, Any]:
    dashboard = config.get("dashboard", {})
    if not isinstance(dashboard, dict):
        dashboard = {}

    docs_input = dashboard.get("docs", {})
    if not isinstance(docs_input, dict):
        docs_input = {}

    colors = dict(DASHBOARD_DEFAULTS["agent_colors"])
    raw_colors = dashboard.get("agent_colors", {})
    if isinstance(raw_colors, dict):
        for role_id, color in raw_colors.items():
            role_key = str(role_id).strip()
            color_value = str(color).strip()
            if role_key and color_value:
                colors[role_key] = color_value

    enabled_value = dashboard.get("enabled", DASHBOARD_DEFAULTS["enabled"])
    enabled = enabled_value if isinstance(enabled_value, bool) else bool(DASHBOARD_DEFAULTS["enabled"])

    return {
        "enabled": enabled,
        "output_file": str(
            dashboard.get("output_file", DASHBOARD_DEFAULTS["output_file"])
        ).strip()
        or str(DASHBOARD_DEFAULTS["output_file"]),
        "refresh_policy": str(
            dashboard.get("refresh_policy", DASHBOARD_DEFAULTS["refresh_policy"])
        ).strip()
        or str(DASHBOARD_DEFAULTS["refresh_policy"]),
        "failure_mode": str(
            dashboard.get("failure_mode", DASHBOARD_DEFAULTS["failure_mode"])
        ).strip()
        or str(DASHBOARD_DEFAULTS["failure_mode"]),
        "docs": {
            "include_paths": _normalize_str_list(
                docs_input.get("include_paths"),
                list(DASHBOARD_DEFAULTS["docs"]["include_paths"]),
            ),
            "exclude_globs": _normalize_str_list(
                docs_input.get("exclude_globs"),
                list(DASHBOARD_DEFAULTS["docs"]["exclude_globs"]),
            ),
            "primary_name_keywords": _normalize_str_list(
                docs_input.get("primary_name_keywords"),
                list(DASHBOARD_DEFAULTS["docs"]["primary_name_keywords"]),
            ),
        },
        "agent_colors": colors,
    }


def _validate_dashboard_config(config: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    dashboard = config.get("dashboard")
    if dashboard is None:
        return errors
    if not isinstance(dashboard, dict):
        return ["dashboard must be an object if provided."]

    if "enabled" in dashboard and not isinstance(dashboard["enabled"], bool):
        errors.append("dashboard.enabled must be boolean.")

    output_file = dashboard.get("output_file")
    if output_file is not None and (not isinstance(output_file, str) or not output_file.strip()):
        errors.append("dashboard.output_file must be a non-empty string.")

    refresh_policy = dashboard.get("refresh_policy")
    if refresh_policy is not None and refresh_policy != "after-every-step":
        errors.append("dashboard.refresh_policy must be 'after-every-step'.")

    failure_mode = dashboard.get("failure_mode")
    if failure_mode is not None and failure_mode != "non-blocking-log":
        errors.append("dashboard.failure_mode must be 'non-blocking-log'.")

    docs = dashboard.get("docs")
    if docs is not None:
        if not isinstance(docs, dict):
            errors.append("dashboard.docs must be an object if provided.")
        else:
            for key in ("include_paths", "exclude_globs", "primary_name_keywords"):
                value = docs.get(key)
                if value is None:
                    continue
                if not isinstance(value, list) or not all(
                    isinstance(item, str) and item.strip() for item in value
                ):
                    errors.append(f"dashboard.docs.{key} must be a list of non-empty strings.")

    colors = dashboard.get("agent_colors")
    if colors is not None:
        if not isinstance(colors, dict):
            errors.append("dashboard.agent_colors must be an object if provided.")
        else:
            seen_values: dict[str, str] = {}
            for role_id, color in colors.items():
                role_name = str(role_id).strip()
                if not role_name:
                    errors.append("dashboard.agent_colors keys must be non-empty role IDs.")
                    continue
                if not isinstance(color, str) or not HEX_COLOR_PATTERN.fullmatch(color):
                    errors.append(
                        f"dashboard.agent_colors['{role_name}'] must be a hex color like #1A2B3C."
                    )
                    continue
                lowered = color.lower()
                previous = seen_values.get(lowered)
                if previous and previous != role_name:
                    errors.append(
                        "dashboard.agent_colors must use unique colors per role. "
                        f"Duplicate: '{role_name}' and '{previous}' both use '{color}'."
                    )
                seen_values[lowered] = role_name

    return errors


def _validate_project_config(config: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    required_toplevel = {"project", "host", "roles", "execution", "backlog"}
    for key in required_toplevel:
        if key not in config:
            errors.append(f"project/config/project.yaml missing top-level key '{key}'.")

    project = config.get("project", {})
    host = config.get("host", {})
    roles = config.get("roles", {})
    execution = config.get("execution", {})
    backlog = config.get("backlog", {})

    if not isinstance(project, dict) or "id" not in project or "name" not in project:
        errors.append("project config must include project.id and project.name.")
    if not isinstance(host, dict) or "primary_adapter" not in host or "adapter_command" not in host:
        errors.append("project config must include host.primary_adapter and host.adapter_command.")
    if not isinstance(roles, dict) or "enabled" not in roles or "disabled" not in roles:
        errors.append("project config must include roles.enabled and roles.disabled.")
    if isinstance(roles, dict) and "review_confirmed" in roles:
        if not isinstance(roles["review_confirmed"], bool):
            errors.append("roles.review_confirmed must be boolean when provided.")
    if execution.get("mode") != "sequential":
        errors.append("execution.mode must be 'sequential'.")
    if execution.get("handoff_authority") != "operator-mediated":
        errors.append("execution.handoff_authority must be 'operator-mediated'.")
    if execution.get("selection_policy") != "dependency-fifo":
        errors.append("execution.selection_policy must be 'dependency-fifo'.")
    unexpected_policy = execution.get("unexpected_event_policy", "errors-only")
    if unexpected_policy not in {"errors-only", "errors-or-warnings", "proceed"}:
        errors.append(
            "execution.unexpected_event_policy must be one of "
            "['errors-only', 'errors-or-warnings', 'proceed']."
        )

    session_mode = host.get("session_mode", "per-role-threads")
    if session_mode not in {"per-role-threads", "stateless"}:
        errors.append("host.session_mode must be 'per-role-threads' or 'stateless'.")

    guardrails = host.get("context_rot_guardrails", {})
    if guardrails is not None and not isinstance(guardrails, dict):
        errors.append("host.context_rot_guardrails must be an object if provided.")
        guardrails = {}
    if isinstance(guardrails, dict):
        max_turns = guardrails.get("max_turns_per_role_session", 8)
        max_age = guardrails.get("max_session_age_minutes", 240)
        reload_on_change = guardrails.get("force_reload_on_context_change", True)
        if not isinstance(max_turns, int) or max_turns <= 0:
            errors.append("host.context_rot_guardrails.max_turns_per_role_session must be > 0.")
        if not isinstance(max_age, int) or max_age <= 0:
            errors.append("host.context_rot_guardrails.max_session_age_minutes must be > 0.")
        if not isinstance(reload_on_change, bool):
            errors.append(
                "host.context_rot_guardrails.force_reload_on_context_change must be boolean."
            )

    statuses = backlog.get("statuses", [])
    expected_statuses = ["Todo", "In Progress", "Blocked", "In Validation", "Done"]
    if statuses != expected_statuses:
        errors.append(f"backlog.statuses must equal {expected_statuses}.")
    errors.extend(_validate_dashboard_config(config))
    return errors


def _validate_role_frontmatter(
    role_id: str, frontmatter: dict[str, Any], known_superpowers: set[str]
) -> list[str]:
    errors: list[str] = []
    required = {
        "role_id",
        "display_name",
        "mission",
        "authority_level",
        "must_superpowers",
        "optional_superpowers",
        "inputs",
        "outputs",
        "handoff_rules",
    }
    missing = [field for field in required if field not in frontmatter]
    if missing:
        errors.append(f"{role_id} missing frontmatter fields: {missing}")
        return errors

    if frontmatter.get("role_id") != role_id:
        errors.append(f"{role_id} frontmatter role_id mismatch.")
    must_superpowers = frontmatter.get("must_superpowers")
    optional_superpowers = frontmatter.get("optional_superpowers")
    if not isinstance(must_superpowers, list):
        errors.append(f"{role_id} must_superpowers must be a list.")
        must_superpowers = []
    if not isinstance(optional_superpowers, list):
        errors.append(f"{role_id} optional_superpowers must be a list.")
        optional_superpowers = []

    for power in list(must_superpowers) + list(optional_superpowers):
        if str(power) not in known_superpowers:
            errors.append(f"{role_id} references unknown superpower '{power}'.")
    return errors


def validate_framework(root: Path) -> list[str]:
    errors: list[str] = []

    required_paths = [
        root / "README.md",
        root / "backlog.md",
        root / "project" / "context" / "project-context.md",
        root / "project" / "state" / "orchestrator-state.yaml",
        root / "runner" / "orchestrator.py",
        root / "runner" / "dashboard.py",
        root / "runner" / "templates" / "dashboard.html",
    ]
    for path in required_paths:
        if not path.exists():
            errors.append(f"Missing required path: {path.as_posix()}")

    steering_files = sorted((root / "steering").glob("*.md"))
    if not steering_files:
        errors.append("steering/ must contain at least one markdown file.")

    backlog_path = root / "backlog.md"
    if backlog_path.exists():
        first_line = backlog_path.read_text(encoding="utf-8").splitlines()[0:1]
        expected = backlog_store.BACKLOG_HEADER
        if not first_line or first_line[0].strip() != expected:
            errors.append("backlog.md header does not match required schema.")
        else:
            try:
                backlog_tasks = backlog_store.read_backlog(backlog_path)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"backlog.md could not be parsed: {exc}")
                backlog_tasks = []
            for task in backlog_tasks:
                owner = str(task.get("owner", "")).strip()
                task_id = str(task.get("task_id", "")).strip() or "<unknown-task-id>"
                if owner == "operator":
                    errors.append(
                        "backlog.md contains forbidden owner 'operator' "
                        f"for task '{task_id}'. Reassign to a non-operator role."
                    )
    else:
        errors.append("Missing backlog.md.")

    try:
        config = load_project_config(root)
    except Exception as exc:  # noqa: BLE001
        errors.append(str(exc))
        config = {}
    else:
        errors.extend(_validate_project_config(config))

    try:
        registry = load_registry(root)
    except Exception as exc:  # noqa: BLE001
        errors.append(str(exc))
        registry = {"roles": {}}

    known_superpowers = collect_superpower_ids(root)
    if not known_superpowers:
        errors.append("No superpower IDs found in superpowers/*.md")

    roles = registry.get("roles", {})
    role_ids = set(roles.keys())
    if not role_ids:
        errors.append("agents/registry.yaml has no roles.")

    enabled = set()
    disabled = set()
    if config:
        roles_config = config.get("roles", {})
        enabled = set(roles_config.get("enabled", []))
        disabled = set(roles_config.get("disabled", []))
        unknown_enabled = sorted(enabled - role_ids)
        if unknown_enabled:
            errors.append(f"roles.enabled contains unknown roles: {unknown_enabled}")
        unknown_disabled = sorted(disabled - role_ids)
        if unknown_disabled:
            errors.append(f"roles.disabled contains unknown roles: {unknown_disabled}")
        overlap = sorted(enabled & disabled)
        if overlap:
            errors.append(f"roles.enabled and roles.disabled overlap: {overlap}")

    for role_id, role_meta in roles.items():
        role_file = role_meta.get("role_file") if isinstance(role_meta, dict) else None
        if not role_file:
            errors.append(f"registry role '{role_id}' missing role_file.")
            continue
        role_path = root / str(role_file)
        if not role_path.exists():
            errors.append(f"Missing role file for '{role_id}': {role_path.as_posix()}")
            continue
        frontmatter = extract_frontmatter(role_path)
        errors.extend(_validate_role_frontmatter(role_id, frontmatter, known_superpowers))

    for role_id in enabled:
        notes = root / "project" / "workspaces" / role_id / "notes.md"
        runs_dir = root / "project" / "workspaces" / role_id / "runs"
        if not notes.exists():
            errors.append(f"Missing workspace notes for enabled role '{role_id}'.")
        if not runs_dir.exists() or not runs_dir.is_dir():
            errors.append(f"Missing workspace runs directory for enabled role '{role_id}'.")

    return errors
