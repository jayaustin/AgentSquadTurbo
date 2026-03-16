"""Codex CLI host adapter."""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import tempfile
from pathlib import Path

from .base import AdapterError, BaseAdapter, InvocationResult


class CodexCliAdapter(BaseAdapter):
    """Adapter for the standalone Codex CLI binary."""

    adapter_id = "codex-cli"

    @staticmethod
    def _sanitize_exec_args(args: list[str]) -> list[str]:
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

    @classmethod
    def _split_command(cls, command: str) -> tuple[list[str], list[str]]:
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
        return base_args, cls._sanitize_exec_args(exec_args)

    @staticmethod
    def _parse_thread_id(stdout: str) -> str | None:
        for line in stdout.splitlines():
            text = line.strip()
            if not text or not text.startswith("{"):
                continue
            try:
                event = json.loads(text)
            except json.JSONDecodeError:
                continue
            if event.get("type") == "thread.started":
                thread_id = str(event.get("thread_id", "")).strip()
                if thread_id:
                    return thread_id
        return None

    @staticmethod
    def _native_binary_from_shim(shim_path: Path) -> Path | None:
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

    @classmethod
    def _resolve_executable(cls, argv: list[str]) -> list[str]:
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
            native_binary = cls._native_binary_from_shim(resolved_path)
            if native_binary is not None:
                return [str(native_binary), *argv[1:]]
        return [str(resolved_path), *argv[1:]]

    def invoke_with_session(
        self,
        command: str,
        prompt: str,
        session_id: str | None = None,
    ) -> InvocationResult:
        base_args, default_exec_args = self._split_command(command)
        cli_base = self._resolve_executable(base_args)

        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".txt",
            delete=False,
            encoding="utf-8",
        ) as handle:
            output_path = Path(handle.name)

        try:
            if session_id:
                cli_args = cli_base + [
                    "exec",
                    *default_exec_args,
                    "resume",
                    "--json",
                    "--output-last-message",
                    str(output_path),
                    session_id,
                    "-",
                ]
            else:
                cli_args = cli_base + [
                    "exec",
                    *default_exec_args,
                    "--json",
                    "--output-last-message",
                    str(output_path),
                    "-",
                ]

            env = os.environ.copy()
            env["AGENTSQUAD_PROMPT"] = prompt
            completed = subprocess.run(
                cli_args,
                input=prompt,
                capture_output=True,
                text=True,
                shell=False,
                check=False,
                env=env,
            )
            if completed.returncode != 0:
                stderr = (completed.stderr or "").strip()
                raise AdapterError(
                    f"{self.adapter_id} invocation failed with exit code "
                    f"{completed.returncode}: {stderr}"
                )

            message_text = output_path.read_text(encoding="utf-8").strip() if output_path.exists() else ""
            if not message_text:
                raise AdapterError(f"{self.adapter_id} invocation returned empty output.")

            resolved_session_id = self._parse_thread_id(completed.stdout or "") or session_id
            return InvocationResult(output=message_text, session_id=resolved_session_id)
        finally:
            try:
                output_path.unlink(missing_ok=True)
            except OSError:
                pass
