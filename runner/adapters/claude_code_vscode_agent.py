"""Claude Code VS Code agent host adapter."""

from __future__ import annotations

import os
import shlex
import subprocess
import tempfile
from pathlib import Path

from .base import AdapterError, BaseAdapter, InvocationResult


class ClaudeCodeVSCodeAgentAdapter(BaseAdapter):
    """Adapter for Claude Code VS Code extension integration.

    This adapter assumes Claude Code can be invoked via a command-line interface
    even when running as a VS Code extension, similar to how Codex VS Code Agent works.
    """

    adapter_id = "claude-code-vscode-agent"

    @staticmethod
    def _sanitize_exec_args(args: list[str]) -> list[str]:
        """Remove exec args that are not applicable to Claude Code."""
        cleaned: list[str] = []
        skip_next = False
        for token in args:
            if skip_next:
                skip_next = False
                continue
            # Claude Code doesn't use these Codex-specific flags
            if token in {"resume", "--json", "--ephemeral"}:
                continue
            if token == "--output-last-message":
                skip_next = True
                continue
            cleaned.append(token)
        return cleaned

    @classmethod
    def _parse_command(cls, command: str) -> list[str]:
        """Parse the command string into executable arguments."""
        raw = (command or "").strip()
        if not raw or "REPLACE_WITH_LOCAL_ASSISTANT_COMMAND" in raw:
            return ["claude"]

        tokens = shlex.split(raw, posix=(os.name != "nt"))
        if not tokens:
            return ["claude"]

        # Clean Codex-specific arguments
        cleaned = cls._sanitize_exec_args(tokens)
        if not cleaned:
            return ["claude"]

        return cleaned

    def invoke_with_session(
        self,
        command: str,
        prompt: str,
        session_id: str | None = None,
    ) -> InvocationResult:
        """Invoke Claude Code VS Code extension with the given prompt.

        Note: Claude Code doesn't currently support session continuity
        in the same way as Codex, so session_id is accepted but not used.
        The prompt is passed as a command-line argument rather than via stdin.
        """
        cli_args = self._parse_command(command)

        # Create a temporary file to capture the output if needed
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".txt",
            delete=False,
            encoding="utf-8",
        ) as handle:
            output_path = Path(handle.name)

        try:
            # For VS Code extension mode, pass prompt as argument
            # This is similar to how Codex VS Code Agent works
            env = os.environ.copy()
            env["AGENTSQUAD_PROMPT"] = prompt

            # Append the prompt as the final argument
            full_args = cli_args + [prompt]

            completed = subprocess.run(
                full_args,
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

            # Extract the output from stdout
            output_text = (completed.stdout or "").strip()
            if not output_text:
                raise AdapterError(f"{self.adapter_id} invocation returned empty output.")

            # Claude Code doesn't provide thread/session IDs like Codex
            # Return None for session_id to indicate stateless execution
            return InvocationResult(output=output_text, session_id=None)

        finally:
            try:
                output_path.unlink(missing_ok=True)
            except OSError:
                pass
