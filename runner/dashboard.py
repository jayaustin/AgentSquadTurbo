"""Dashboard payload builder and static snapshot renderer."""

from __future__ import annotations

import hashlib
import html
import json
import posixpath
import re
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlsplit, urlunsplit

try:
    import bleach
except Exception:  # noqa: BLE001
    bleach = None

try:
    import markdown as markdown_lib
except Exception:  # noqa: BLE001
    markdown_lib = None

from . import backlog_store, validators


DEFAULT_FALLBACK_COLORS = [
    "#22D3EE",
    "#A78BFA",
    "#34D399",
    "#F472B6",
    "#FACC15",
    "#60A5FA",
    "#FB7185",
    "#2DD4BF",
]
MARKDOWN_EXTENSIONS = ("extra", "sane_lists", "md_in_html")
MARKDOWN_ALLOWED_TAGS = sorted(
    set((bleach.sanitizer.ALLOWED_TAGS if bleach else [])).union(
        {
            "abbr",
            "blockquote",
            "br",
            "code",
            "dd",
            "del",
            "details",
            "div",
            "dl",
            "dt",
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
            "hr",
            "img",
            "li",
            "ol",
            "p",
            "pre",
            "span",
            "sub",
            "summary",
            "sup",
            "table",
            "tbody",
            "td",
            "tfoot",
            "th",
            "thead",
            "tr",
            "ul",
        }
    )
)
MARKDOWN_ALLOWED_ATTRIBUTES: dict[str, list[str]] = {
    "*": ["class", "id"],
    "a": ["href", "title"],
    "img": ["src", "alt", "title"],
    "ol": ["start"],
    "td": ["align", "colspan", "rowspan"],
    "th": ["align", "colspan", "rowspan"],
}
TABLE_BLOCK_PATTERN = re.compile(r"(<table>.*?</table>)", flags=re.DOTALL | re.IGNORECASE)
RESOURCE_URL_PATTERN = re.compile(
    r'(<(?P<tag>a|img)\b[^>]*?\b(?P<attr>href|src)=")(?P<url>[^"]+)(")',
    flags=re.IGNORECASE,
)
UNSAFE_BLOCK_PATTERN = re.compile(
    r"<(?P<tag>script|style|iframe|object|embed)\b.*?>.*?</(?P=tag)>",
    flags=re.DOTALL | re.IGNORECASE,
)


def _canonical_primary_adapter(value: Any) -> str:
    adapter = str(value or "").strip()
    if adapter == "codex":
        return "codex-vscode-agent"
    return adapter


def _format_utc_timestamp(timestamp: float | int | None) -> str:
    if timestamp is None:
        return ""
    try:
        return datetime.fromtimestamp(float(timestamp), tz=timezone.utc).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
    except (TypeError, ValueError, OSError, OverflowError):
        return ""


def _strip_frontmatter(markdown_text: str) -> str:
    match = re.match(r"^---\n.*?\n---\n?", markdown_text, flags=re.DOTALL)
    if match:
        return markdown_text[match.end() :].lstrip()
    return markdown_text


def _markdown_to_html_fallback(markdown_text: str) -> str:
    """Minimal markdown renderer using only stdlib."""

    def inline_markup(text: str) -> str:
        escaped = html.escape(text, quote=False)
        escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
        escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
        escaped = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", escaped)
        escaped = re.sub(
            r"\[([^\]]+)\]\(([^)]+)\)",
            lambda m: f'<a href="{html.escape(m.group(2), quote=True)}">{m.group(1)}</a>',
            escaped,
        )
        return escaped

    lines = markdown_text.splitlines()
    out: list[str] = []
    in_code = False
    list_tag: str | None = None
    paragraph: list[str] = []

    def flush_paragraph() -> None:
        nonlocal paragraph
        if not paragraph:
            return
        text = " ".join(item.strip() for item in paragraph if item.strip())
        if text:
            out.append(f"<p>{inline_markup(text)}</p>")
        paragraph = []

    def close_list() -> None:
        nonlocal list_tag
        if list_tag:
            out.append(f"</{list_tag}>")
            list_tag = None

    def ensure_list(tag: str) -> None:
        nonlocal list_tag
        if list_tag == tag:
            return
        close_list()
        out.append(f"<{tag}>")
        list_tag = tag

    for line in lines:
        stripped = line.rstrip()
        if stripped.startswith("```"):
            flush_paragraph()
            close_list()
            if in_code:
                out.append("</code></pre>")
                in_code = False
            else:
                language = stripped[3:].strip()
                class_attr = (
                    f' class="language-{html.escape(language, quote=True)}"' if language else ""
                )
                out.append(f"<pre><code{class_attr}>")
                in_code = True
            continue

        if in_code:
            out.append(html.escape(stripped, quote=False))
            continue

        if not stripped:
            flush_paragraph()
            close_list()
            continue

        heading = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if heading:
            flush_paragraph()
            close_list()
            level = len(heading.group(1))
            out.append(f"<h{level}>{inline_markup(heading.group(2))}</h{level}>")
            continue

        unordered = re.match(r"^\s*[-*+]\s+(.*)$", stripped)
        if unordered:
            flush_paragraph()
            ensure_list("ul")
            out.append(f"<li>{inline_markup(unordered.group(1).strip())}</li>")
            continue

        ordered = re.match(r"^\s*\d+\.\s+(.*)$", stripped)
        if ordered:
            flush_paragraph()
            ensure_list("ol")
            out.append(f"<li>{inline_markup(ordered.group(1).strip())}</li>")
            continue

        paragraph.append(stripped)

    flush_paragraph()
    close_list()
    if in_code:
        out.append("</code></pre>")
    return "\n".join(out)


def _rewrite_relative_resource_url(raw_url: str, source_path: str) -> str:
    parsed = urlsplit(str(raw_url or "").strip())
    if parsed.scheme or parsed.netloc:
        return raw_url
    if raw_url.startswith(("#", "/")):
        return raw_url

    base_dir = PurePosixPath(source_path).parent.as_posix()
    normalized_path = posixpath.normpath(posixpath.join(base_dir, parsed.path))
    if normalized_path in {"", "."}:
        normalized_path = parsed.path
    if normalized_path == ".." or normalized_path.startswith("../"):
        return raw_url
    rewritten_path = (
        normalized_path[2:] if normalized_path.startswith("./") else normalized_path
    )
    return urlunsplit(("", "", rewritten_path, parsed.query, parsed.fragment))


def _rewrite_markdown_resource_urls(rendered_html: str, source_path: str) -> str:
    if not source_path:
        return rendered_html

    def _replace(match: re.Match[str]) -> str:
        rewritten = _rewrite_relative_resource_url(match.group("url"), source_path)
        return f"{match.group(1)}{html.escape(rewritten, quote=True)}{match.group(5)}"

    return RESOURCE_URL_PATTERN.sub(_replace, rendered_html)


def _wrap_markdown_tables(rendered_html: str) -> str:
    return TABLE_BLOCK_PATTERN.sub(r'<div class="markdown-table-wrap">\1</div>', rendered_html)


def _strip_unsafe_html_blocks(rendered_html: str) -> str:
    return UNSAFE_BLOCK_PATTERN.sub("", rendered_html)


def _markdown_to_html(markdown_text: str, *, source_path: str = "") -> str:
    if markdown_lib is None or bleach is None:
        return _markdown_to_html_fallback(markdown_text)

    try:
        rendered = markdown_lib.markdown(
            markdown_text,
            extensions=list(MARKDOWN_EXTENSIONS),
            output_format="html5",
        )
    except Exception:  # noqa: BLE001
        return _markdown_to_html_fallback(markdown_text)

    rendered = _strip_unsafe_html_blocks(rendered)
    rendered = _rewrite_markdown_resource_urls(rendered, source_path)
    rendered = _wrap_markdown_tables(rendered)
    return bleach.clean(
        rendered,
        tags=MARKDOWN_ALLOWED_TAGS,
        attributes=MARKDOWN_ALLOWED_ATTRIBUTES,
        protocols=set(bleach.sanitizer.ALLOWED_PROTOCOLS),
        strip=True,
    )


def _read_jsonl(
    path: Path,
    *,
    use_file_order_tiebreak: bool = False,
) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    entries: list[dict[str, Any]] = []
    for index, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
        raw = line.strip()
        if not raw:
            continue
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            if use_file_order_tiebreak:
                parsed["_line_index"] = index
            entries.append(parsed)
    if use_file_order_tiebreak:
        entries.sort(
            key=lambda item: (
                str(item.get("ts_utc", "")),
                int(item.get("_line_index", -1)),
            ),
            reverse=True,
        )
        for item in entries:
            item.pop("_line_index", None)
    else:
        entries.sort(key=lambda item: str(item.get("ts_utc", "")), reverse=True)
    return entries


def _fallback_color(role_id: str) -> str:
    digest = hashlib.sha256(role_id.encode("utf-8")).hexdigest()
    index = int(digest[:8], 16) % len(DEFAULT_FALLBACK_COLORS)
    return DEFAULT_FALLBACK_COLORS[index]


def _collect_documents(root: Path, dashboard_cfg: dict[str, Any]) -> list[dict[str, Any]]:
    docs_cfg = dashboard_cfg.get("docs", {})
    include_paths = docs_cfg.get("include_paths", [])
    exclude_globs = docs_cfg.get("exclude_globs", [])
    primary_keywords = [str(keyword).lower() for keyword in docs_cfg.get("primary_name_keywords", [])]
    seen: set[str] = set()
    docs: list[dict[str, Any]] = []

    def append_markdown_document(md_path: Path, *, force_primary: bool = False) -> None:
        rel = md_path.relative_to(root).as_posix()
        if rel in seen:
            return
        pure = PurePosixPath(rel)
        if any(pure.match(pattern) for pattern in exclude_globs):
            return

        text = md_path.read_text(encoding="utf-8", errors="replace")
        title = md_path.stem.replace("-", " ").replace("_", " ").title()
        first_heading = re.search(r"^#\s+(.+)$", text, flags=re.MULTILINE)
        if first_heading:
            title = first_heading.group(1).strip()
        lower_path = rel.lower()
        primary = force_primary or any(keyword in lower_path for keyword in primary_keywords)
        try:
            stat = md_path.stat()
            created_ts = getattr(stat, "st_birthtime", None)
            if created_ts is None:
                created_ts = stat.st_ctime
            modified_ts = stat.st_mtime
        except OSError:
            created_ts = None
            modified_ts = None

        docs.append(
            {
                "id": rel.replace("/", "__"),
                "path": rel,
                "title": title,
                "is_primary": primary,
                "created_at_utc": _format_utc_timestamp(created_ts),
                "modified_at_utc": _format_utc_timestamp(modified_ts),
                "html": _markdown_to_html(text, source_path=rel),
            }
        )
        seen.add(rel)

    for include_path in include_paths:
        base = root / str(include_path)
        if not base.exists():
            continue
        for md_path in sorted(base.rglob("*.md")):
            append_markdown_document(md_path)

    # Ensure project-level README is always visible in Documents for onboarding.
    root_readme = root / "README.md"
    if root_readme.exists():
        append_markdown_document(root_readme, force_primary=True)

    docs.sort(key=lambda item: (not bool(item["is_primary"]), item["path"]))
    return docs


def _collect_known_files(root: Path) -> list[str]:
    files: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        if rel.startswith(".git/"):
            continue
        files.append(rel)
    files.sort()
    return files


def _backlog_status_counts(tasks: list[dict[str, Any]], statuses: list[str]) -> dict[str, int]:
    counts = {status: 0 for status in statuses}
    for task in tasks:
        status = str(task.get("status", ""))
        if status in counts:
            counts[status] += 1
    return counts


def _build_payload(root: Path, repo_root_relative_prefix: str, output_path: str) -> dict[str, Any]:
    config = validators.load_project_config(root)
    dashboard_cfg = validators.dashboard_config_with_defaults(config)
    roles_cfg = config.get("roles", {})
    enabled_roles = list(roles_cfg.get("enabled", []))
    disabled_roles = list(roles_cfg.get("disabled", []))
    registry = validators.load_registry(root).get("roles", {})
    state = validators.load_data_file(root / "project" / "state" / "orchestrator-state.yaml")
    tasks = backlog_store.read_backlog(root / "backlog.md")
    statuses = list(config.get("backlog", {}).get("statuses", []))
    status_counts = _backlog_status_counts(tasks, statuses)
    all_known_roles = sorted(set(enabled_roles) | set(disabled_roles) | set(registry.keys()))

    configured_colors = dashboard_cfg.get("agent_colors", {})
    role_colors: dict[str, str] = {}
    for role_id in all_known_roles:
        configured = str(configured_colors.get(role_id, "")).strip()
        role_colors[role_id] = (
            configured
            if validators.HEX_COLOR_PATTERN.fullmatch(configured)
            else _fallback_color(role_id)
        )
    role_display_names = {
        role_id: registry.get(role_id, {}).get("display_name", role_id.replace("-", " ").title())
        for role_id in all_known_roles
    }

    global_log = _read_jsonl(
        root / "project" / "state" / "activity-log.jsonl",
        use_file_order_tiebreak=True,
    )
    per_role_logs = {
        role_id: _read_jsonl(root / "project" / "workspaces" / role_id / "activity.jsonl")
        for role_id in all_known_roles
    }

    enabled_set = set(enabled_roles)
    disabled_set = set(disabled_roles)
    role_entries: list[dict[str, Any]] = []
    for role_id in all_known_roles:
        role_path = root / "agents" / "roles" / role_id / "agent-role.md"
        role_text = ""
        if role_path.exists():
            role_text = _strip_frontmatter(
                role_path.read_text(encoding="utf-8", errors="replace")
            )
        role_rel_path = role_path.relative_to(root).as_posix() if role_path.exists() else ""
        role_entries.append(
            {
                "role_id": role_id,
                "display_name": role_display_names.get(role_id, role_id.replace("-", " ").title()),
                "color": role_colors.get(role_id, _fallback_color(role_id)),
                "enabled": bool(role_id in enabled_set and role_id not in disabled_set),
                "role_context_html": _markdown_to_html(role_text, source_path=role_rel_path),
                "activity": per_role_logs.get(role_id, []),
            }
        )

    project_info = config.get("project", {})
    host_info = config.get("host", {})
    execution_info = config.get("execution", {})
    guardrails = host_info.get("context_rot_guardrails", {})
    if not isinstance(guardrails, dict):
        guardrails = {}
    payload = {
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "repo_root_relative_prefix": repo_root_relative_prefix,
        "dashboard_output_path": output_path,
        "known_files": _collect_known_files(root),
        "project": {
            "id": project_info.get("id", ""),
            "name": project_info.get("name", ""),
            "primary_adapter": _canonical_primary_adapter(host_info.get("primary_adapter", "")),
            "adapter_command": host_info.get("adapter_command", ""),
            "session_mode": host_info.get("session_mode", "stateless"),
            "execution_mode": execution_info.get("mode", ""),
            "handoff_authority": execution_info.get("handoff_authority", ""),
            "selection_policy": execution_info.get("selection_policy", ""),
            "enabled_roles": enabled_roles,
            "disabled_roles": disabled_roles,
            "role_display_names": role_display_names,
            "status_counts": status_counts,
            "state": {
                "run_id": state.get("run_id", ""),
                "active_role": state.get("active_role"),
                "last_completed_task_id": state.get("last_completed_task_id", ""),
                "halted": bool(state.get("halted", False)),
                "halt_reason": state.get("halt_reason", ""),
                "current_request": state.get("current_request", ""),
            },
        },
        "settings": {
            "host": {
                "primary_adapter": _canonical_primary_adapter(host_info.get("primary_adapter", "")),
                "adapter_command": str(host_info.get("adapter_command", "")).strip(),
                "session_mode": str(host_info.get("session_mode", "stateless")).strip()
                or "stateless",
                "context_rot_guardrails": {
                    "max_turns_per_role_session": int(
                        guardrails.get("max_turns_per_role_session", 8)
                    ),
                    "max_session_age_minutes": int(
                        guardrails.get("max_session_age_minutes", 240)
                    ),
                    "force_reload_on_context_change": bool(
                        guardrails.get("force_reload_on_context_change", True)
                    ),
                },
            },
            "execution": {
                "mode": str(execution_info.get("mode", "sequential")).strip() or "sequential",
                "handoff_authority": str(
                    execution_info.get("handoff_authority", "operator-mediated")
                ).strip()
                or "operator-mediated",
                "selection_policy": str(
                    execution_info.get("selection_policy", "dependency-fifo")
                ).strip()
                or "dependency-fifo",
                "unexpected_event_policy": str(
                    execution_info.get("unexpected_event_policy", "errors-only")
                ).strip()
                or "errors-only",
            },
            "dashboard": {
                "output_file": str(dashboard_cfg.get("output_file", "")).strip()
                or "project/state/dashboard.html",
                "refresh_policy": str(dashboard_cfg.get("refresh_policy", "")).strip()
                or "after-every-step",
                "failure_mode": str(dashboard_cfg.get("failure_mode", "")).strip()
                or "non-blocking-log",
            },
        },
        "documents": _collect_documents(root, dashboard_cfg),
        "tasks": tasks,
        "activity_log": global_log,
        "agents": role_entries,
        "agent_colors": role_colors,
    }
    return payload


def build_payload(
    root: Path,
    *,
    repo_root_relative_prefix: str = ".",
    output_path: str = "project/state/dashboard.html",
) -> dict[str, Any]:
    """Build dashboard payload without writing output files."""
    return _build_payload(
        root=root,
        repo_root_relative_prefix=repo_root_relative_prefix,
        output_path=output_path,
    )


def render_dashboard_html(
    root: Path,
    *,
    repo_root_relative_prefix: str = ".",
    output_path: str = "project/state/dashboard.html",
) -> str:
    """Render dashboard HTML for server responses without writing snapshot files."""
    template_path = root / "runner" / "templates" / "dashboard.html"
    template = template_path.read_text(encoding="utf-8")
    payload = build_payload(
        root=root,
        repo_root_relative_prefix=repo_root_relative_prefix,
        output_path=output_path,
    )
    return template.replace(
        "{{DASHBOARD_PAYLOAD_JSON}}",
        json.dumps(payload, ensure_ascii=True).replace("</", "<\\/"),
    )


def render_dashboard(root: Path) -> Path:
    config = validators.load_project_config(root)
    dashboard_cfg = validators.dashboard_config_with_defaults(config)
    output_file = root / str(dashboard_cfg.get("output_file", "project/state/dashboard.html"))
    try:
        output_rel = output_file.relative_to(root).as_posix()
    except ValueError:
        output_rel = output_file.as_posix()

    depth = len(PurePosixPath(output_rel).parent.parts)
    repo_root_relative_prefix = "." if depth == 0 else "/".join([".."] * depth)

    rendered = render_dashboard_html(
        root=root,
        repo_root_relative_prefix=repo_root_relative_prefix,
        output_path=output_rel,
    )

    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(rendered, encoding="utf-8")
    return output_file
