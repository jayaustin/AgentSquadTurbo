"""Role workspace log and notes persistence."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"
FILE_TS_FORMAT = "%Y-%m-%d_%H-%M-%S"
RECENT_ACTIVITY_MAX_ITEMS = 5
RECENT_ACTIVITY_ENTRY_PATTERN = re.compile(
    r"^- `([^`]+)` \| Task `([^`]+)` \| Status `([^`]*)` \| (.*)$"
)


def _safe_segment(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in value).strip("-")


def timestamp_now() -> str:
    return datetime.now(timezone.utc).strftime(DATETIME_FORMAT)


def filename_timestamp_now() -> str:
    return datetime.now(timezone.utc).strftime(FILE_TS_FORMAT)


def ensure_workspace(root: Path, role_id: str) -> Path:
    workspace_dir = root / "project" / "workspaces" / role_id
    runs_dir = workspace_dir / "runs"
    notes_path = workspace_dir / "notes.md"
    workspace_dir.mkdir(parents=True, exist_ok=True)
    runs_dir.mkdir(parents=True, exist_ok=True)
    if not notes_path.exists():
        notes_path.write_text(
            f"# {role_id} Notes\n\nProject-specific notes for `{role_id}`.\n",
            encoding="utf-8",
        )
    return workspace_dir


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=True) + "\n")


def _recent_activity_path(root: Path, role_id: str) -> Path:
    return root / "agents" / "roles" / role_id / "recent_activity.md"


def _load_recent_activity_entries(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    entries: list[dict[str, str]] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        match = RECENT_ACTIVITY_ENTRY_PATTERN.match(raw_line.strip())
        if not match:
            continue
        entries.append(
            {
                "ts_utc": match.group(1).strip(),
                "task_id": match.group(2).strip(),
                "status": match.group(3).strip(),
                "summary": match.group(4).strip(),
            }
        )
    return entries


def _write_recent_activity_doc(root: Path, role_id: str, entries: list[dict[str, str]]) -> Path:
    path = _recent_activity_path(root, role_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    updated_ts = timestamp_now()
    lines: list[str] = []
    lines.append(f"# Recent Activity: {role_id}")
    lines.append("")
    lines.append("High-level summary of the most recent tasks this role has worked on.")
    lines.append(f"Updated (UTC): `{updated_ts}`")
    lines.append("")
    lines.append("## Latest 5 Tasks")
    lines.append("")
    if entries:
        for entry in entries[:RECENT_ACTIVITY_MAX_ITEMS]:
            lines.append(
                f"- `{entry['ts_utc']}` | Task `{entry['task_id']}` | "
                f"Status `{entry['status']}` | {entry['summary']}"
            )
    else:
        lines.append("- No role activity has been recorded yet.")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def update_recent_activity(
    root: Path,
    role_id: str,
    task_id: str,
    status: str,
    summary: str,
) -> Path:
    existing = _load_recent_activity_entries(_recent_activity_path(root, role_id))
    new_entry = {
        "ts_utc": timestamp_now(),
        "task_id": str(task_id or "no-task").strip() or "no-task",
        "status": str(status or "Logged").strip() or "Logged",
        "summary": str(summary or "No summary provided.").strip() or "No summary provided.",
    }
    merged = [new_entry, *existing]
    deduped: list[dict[str, str]] = []
    seen_task_ids: set[str] = set()
    for entry in merged:
        task_key = entry.get("task_id", "").strip()
        if task_key in seen_task_ids:
            continue
        seen_task_ids.add(task_key)
        deduped.append(entry)
        if len(deduped) >= RECENT_ACTIVITY_MAX_ITEMS:
            break
    return _write_recent_activity_doc(root, role_id, deduped)


def write_activity_event(
    root: Path,
    role_id: str,
    task_id: str,
    event_type: str,
    summary: str,
    status: str = "",
    run_journal_path: str = "",
    metadata: dict[str, Any] | None = None,
) -> None:
    workspace = ensure_workspace(root, role_id)
    payload = {
        "ts_utc": timestamp_now(),
        "role_id": role_id,
        "task_id": task_id,
        "event_type": event_type,
        "summary": str(summary).strip(),
        "run_journal_path": str(run_journal_path or "").strip(),
        "status": str(status or "").strip(),
        "metadata": metadata or {},
    }
    _append_jsonl(root / "project" / "state" / "activity-log.jsonl", payload)
    _append_jsonl(workspace / "activity.jsonl", payload)


def write_run_journal(
    root: Path,
    role_id: str,
    task_id: str,
    prompt_template: str,
    context_manifest: list[str],
    raw_output: str,
    parsed_result: dict,
    backlog_before: str,
    backlog_after: str,
    events: list[str] | None = None,
    event_type: str = "run_journal",
    summary: str = "",
    status: str = "",
    metadata: dict[str, Any] | None = None,
) -> Path:
    workspace = ensure_workspace(root, role_id)
    runs_dir = workspace / "runs"
    timestamp = timestamp_now()
    filename_stamp = filename_timestamp_now()
    safe_task = _safe_segment(task_id or "no-task")
    path = runs_dir / f"{filename_stamp}-{safe_task}.md"

    event_lines = events or []
    lines: list[str] = []
    lines.append(f"# Run Journal: {role_id} / {task_id}")
    lines.append("")
    lines.append(f"- Timestamp (UTC): `{timestamp}`")
    lines.append(f"- Prompt Template: `{prompt_template}`")
    lines.append("")
    lines.append("## Context Manifest")
    lines.append("")
    for item in context_manifest:
        lines.append(f"- `{item}`")
    lines.append("")
    lines.append("## Events")
    lines.append("")
    if event_lines:
        for event in event_lines:
            lines.append(f"- {event}")
    else:
        lines.append("- None")
    lines.append("")
    lines.append("## Backlog Snapshot (Before)")
    lines.append("")
    lines.append("```markdown")
    lines.append(backlog_before.rstrip())
    lines.append("```")
    lines.append("")
    lines.append("## Raw Model Output")
    lines.append("")
    lines.append("```text")
    lines.append(raw_output.rstrip())
    lines.append("```")
    lines.append("")
    lines.append("## Parsed Result")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(parsed_result, indent=2, ensure_ascii=True))
    lines.append("```")
    lines.append("")
    lines.append("## Backlog Snapshot (After)")
    lines.append("")
    lines.append("```markdown")
    lines.append(backlog_after.rstrip())
    lines.append("```")
    lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")

    event_summary = str(summary or parsed_result.get("summary") or "Run journal written.").strip()
    event_status = str(status or parsed_result.get("status") or "").strip()
    run_path = path.relative_to(root).as_posix()
    base_metadata: dict[str, Any] = {
        "prompt_template": prompt_template,
        "context_manifest": list(context_manifest),
        "events": list(event_lines),
    }
    if metadata:
        base_metadata.update(metadata)
    write_activity_event(
        root=root,
        role_id=role_id,
        task_id=task_id,
        event_type=event_type,
        summary=event_summary,
        run_journal_path=run_path,
        status=event_status,
        metadata=base_metadata,
    )
    recent_activity_path = update_recent_activity(
        root=root,
        role_id=role_id,
        task_id=task_id,
        status=event_status or "Logged",
        summary=event_summary,
    ).relative_to(root).as_posix()
    write_activity_event(
        root=root,
        role_id=role_id,
        task_id=task_id,
        event_type="file_modified",
        summary=(
            f"{role_id} modified file '{recent_activity_path}' to refresh recent activity "
            f"for task '{task_id}'."
        ),
        status="Logged",
        metadata={"path": recent_activity_path},
    )
    return path
