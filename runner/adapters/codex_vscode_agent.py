"""Codex VS Code agent host adapter."""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

from .base import AdapterError, BaseAdapter, InvocationResult
from .codex_common import parse_jsonl_events, parse_thread_id, resolve_executable, split_command


class CodexVsCodeAgentAdapter(BaseAdapter):
    """Adapter for the original Codex VS Code Agent flow with session continuity."""

    adapter_id = "codex-vscode-agent"
    supports_native_subagents = True

    def invoke_with_session(
        self,
        command: str,
        prompt: str,
        session_id: str | None = None,
    ) -> InvocationResult:
        base_args, default_exec_args = split_command(command)
        cli_base = resolve_executable(base_args)
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
                    prompt,
                ]
            else:
                cli_args = cli_base + [
                    "exec",
                    *default_exec_args,
                    "--json",
                    "--output-last-message",
                    str(output_path),
                    prompt,
                ]

            env = os.environ.copy()
            env["AGENTSQUAD_PROMPT"] = prompt
            completed = subprocess.run(
                cli_args,
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

            host_events = parse_jsonl_events(completed.stdout or "")
            resolved_session_id = parse_thread_id(host_events) or session_id
            return InvocationResult(
                output=message_text,
                session_id=resolved_session_id,
                host_events=host_events,
            )
        finally:
            try:
                output_path.unlink(missing_ok=True)
            except OSError:
                pass


CodexAdapter = CodexVsCodeAgentAdapter
