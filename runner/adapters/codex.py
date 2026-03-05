"""Codex host adapter."""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import tempfile
from pathlib import Path

from .base import AdapterError, BaseAdapter, InvocationResult


class CodexAdapter(BaseAdapter):
    """Adapter for Codex-style local host execution with session continuity."""

    adapter_id = "codex"

    @staticmethod
    def _split_command(command: str) -> list[str]:
        raw = (command or "").strip()
        if not raw or "REPLACE_WITH_LOCAL_ASSISTANT_COMMAND" in raw:
            return ["codex"]
        return shlex.split(raw, posix=(os.name != "nt"))

    @staticmethod
    def _parse_thread_id(stdout: str) -> str | None:
        for line in stdout.splitlines():
            text = line.strip()
            if not text:
                continue
            if not text.startswith("{"):
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

    def invoke_with_session(
        self,
        command: str,
        prompt: str,
        session_id: str | None = None,
    ) -> InvocationResult:
        args = self._split_command(command)
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".txt",
            delete=False,
            encoding="utf-8",
        ) as handle:
            output_path = Path(handle.name)

        try:
            if session_id:
                cli_args = args + [
                    "exec",
                    "resume",
                    "--json",
                    "--output-last-message",
                    str(output_path),
                    session_id,
                    prompt,
                ]
            else:
                cli_args = args + [
                    "exec",
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

            resolved_session_id = self._parse_thread_id(completed.stdout or "") or session_id
            return InvocationResult(output=message_text, session_id=resolved_session_id)
        finally:
            try:
                output_path.unlink(missing_ok=True)
            except OSError:
                pass
