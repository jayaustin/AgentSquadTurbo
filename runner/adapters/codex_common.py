"""Shared helpers for Codex-based adapters."""

from __future__ import annotations

import json
import os
import shlex
import shutil
from pathlib import Path
from typing import Any


def sanitize_exec_args(args: list[str]) -> list[str]:
    """Remove exec args managed by the adapter runtime."""
    cleaned: list[str] = []
    skip_next = False
    for token in args:
        if skip_next:
            skip_next = False
            continue
        if token in {"resume", "--json"}:
            continue
        if token == "--output-last-message":
            skip_next = True
            continue
        cleaned.append(token)
    return cleaned


def split_command(command: str) -> tuple[list[str], list[str]]:
    raw = (command or "").strip()
    if not raw or "REPLACE_WITH_LOCAL_ASSISTANT_COMMAND" in raw:
        return ["codex"], []

    tokens = shlex.split(raw, posix=(os.name != "nt"))
    if not tokens:
        return ["codex"], []

    if "exec" in tokens:
        exec_index = tokens.index("exec")
        base_args = tokens[:exec_index]
        exec_args = tokens[exec_index + 1 :]
    else:
        base_args = []
        exec_args = []
        for token in tokens:
            if token == "--ephemeral":
                exec_args.append(token)
                continue
            base_args.append(token)

    if not base_args:
        base_args = ["codex"]
    return base_args, sanitize_exec_args(exec_args)


def parse_jsonl_events(stdout: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line in stdout.splitlines():
        text = line.strip()
        if not text or not text.startswith("{"):
            continue
        try:
            event = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            events.append(event)
    return events


def parse_thread_id(events: list[dict[str, Any]]) -> str | None:
    for event in events:
        if event.get("type") != "thread.started":
            continue
        thread_id = str(event.get("thread_id", "")).strip()
        if thread_id:
            return thread_id
    return None


def native_binary_from_shim(shim_path: Path) -> Path | None:
    npm_root = shim_path.parent
    package_root = npm_root / "node_modules" / "@openai" / "codex"
    if not package_root.exists():
        return None

    candidates = sorted(
        package_root.glob("node_modules/@openai/codex-*/vendor/*/codex/codex.exe")
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def resolve_executable(argv: list[str]) -> list[str]:
    if not argv:
        return argv

    executable = argv[0]
    explicit_path = Path(executable)
    if explicit_path.is_file():
        return [str(explicit_path), *argv[1:]]

    resolved = shutil.which(executable)
    if not resolved:
        return argv

    resolved_path = Path(resolved)
    if os.name == "nt" and resolved_path.suffix.lower() in {".cmd", ".ps1"}:
        native_binary = native_binary_from_shim(resolved_path)
        if native_binary is not None:
            return [str(native_binary), *argv[1:]]
    return [str(resolved_path), *argv[1:]]
