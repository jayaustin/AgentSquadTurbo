"""Context manifest assembly for role invocation."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path


class ContextLoadError(RuntimeError):
    """Raised when context cannot be loaded."""


@dataclass(frozen=True)
class ContextEntry:
    """A single context document in the active load manifest."""

    kind: str
    path: Path
    content: str


def _read_markdown(path: Path) -> str:
    if not path.exists():
        raise ContextLoadError(f"Missing context file: {path}")
    return path.read_text(encoding="utf-8")


def _ensure_recent_activity_file(root: Path, role_id: str) -> Path:
    path = root / "agents" / "roles" / role_id / "recent_activity.md"
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
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
        ),
        encoding="utf-8",
    )
    return path


def build_manifest(root: Path, role_id: str) -> list[ContextEntry]:
    steering_dir = root / "steering"
    steering_files = sorted(steering_dir.glob("*.md"))
    if not steering_files:
        raise ContextLoadError("No steering files found in steering/ directory.")

    role_path = root / "agents" / "roles" / role_id / "agent-role.md"
    project_context_path = root / "project" / "context" / "project-context.md"
    override_path = root / "project" / "context" / "role-overrides" / f"{role_id}.md"
    recent_activity_path = _ensure_recent_activity_file(root, role_id)

    entries: list[ContextEntry] = []
    for path in steering_files:
        entries.append(ContextEntry(kind="steering", path=path, content=_read_markdown(path)))
    entries.append(ContextEntry(kind="role", path=role_path, content=_read_markdown(role_path)))
    entries.append(
        ContextEntry(
            kind="project-context",
            path=project_context_path,
            content=_read_markdown(project_context_path),
        )
    )
    if override_path.exists():
        entries.append(
            ContextEntry(kind="role-override", path=override_path, content=_read_markdown(override_path))
        )
    entries.append(
        ContextEntry(
            kind="recent-activity",
            path=recent_activity_path,
            content=_read_markdown(recent_activity_path),
        )
    )
    return entries


def manifest_paths(manifest: list[ContextEntry]) -> list[str]:
    return [entry.path.as_posix() for entry in manifest]


def compose_context_text(manifest: list[ContextEntry]) -> str:
    sections: list[str] = []
    for entry in manifest:
        sections.append(f"### BEGIN {entry.kind}: {entry.path.as_posix()}")
        sections.append(entry.content.rstrip())
        sections.append(f"### END {entry.kind}: {entry.path.as_posix()}")
    return "\n\n".join(sections) + "\n"


def manifest_hash(manifest: list[ContextEntry]) -> str:
    """Stable hash for loaded context contents and order."""
    hasher = hashlib.sha256()
    for entry in manifest:
        hasher.update(entry.kind.encode("utf-8"))
        hasher.update(b"\n")
        hasher.update(entry.path.as_posix().encode("utf-8"))
        hasher.update(b"\n")
        hasher.update(entry.content.encode("utf-8"))
        hasher.update(b"\n")
    return hasher.hexdigest()
