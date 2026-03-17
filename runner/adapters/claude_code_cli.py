"""Claude Code CLI host adapter."""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import tempfile
from pathlib import Path

from .base import AdapterError, BaseAdapter, InvocationResult


class ClaudeCodeCliAdapter(BaseAdapter):
    """Adapter for the Claude Code CLI."""

    adapter_id = "claude-code-cli"

    @staticmethod
    def _sanitize_exec_args(args: list[str]) -> list[str]:
        """Remove exec args that are not applicable to Claude Code CLI."""
        cleaned: list[str] = []
        skip_next = False
        for token in args:
            if skip_next:
                skip_next = False
                continue
            # Claude Code doesn't use these Codex-specific flags
            if token in {"--json", "--ephemeral"}:
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

    @staticmethod
    def _resolve_executable(argv: list[str]) -> list[str]:
        """Resolve the executable path if needed."""
        if not argv:
            return argv

        executable = argv[0]
        explicit_path = Path(executable)
        if explicit_path.is_file():
            return [str(explicit_path), *argv[1:]]

        resolved = shutil.which(executable)
        if not resolved:
            return argv

        return [str(resolved), *argv[1:]]

    def invoke_with_session(
        self,
        command: str,
        prompt: str,
        session_id: str | None = None,
    ) -> InvocationResult:
        """Invoke Claude Code CLI with the given prompt.

        Note: Claude Code CLI doesn't currently support session continuity
        in the same way as Codex, so session_id is accepted but not used
        for resuming sessions. Each invocation is stateless.
        """
        cli_args = self._parse_command(command)
        cli_args = self._resolve_executable(cli_args)

        # Create a temporary file to capture the output
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".txt",
            delete=False,
            encoding="utf-8",
        ) as handle:
            output_path = Path(handle.name)

        try:
            # Claude Code CLI accepts prompt via stdin
            # We'll redirect stdout to a file to capture the response
            env = os.environ.copy()
            env["AGENTSQUAD_PROMPT"] = prompt

            # Run claude with the prompt via stdin, capture stdout
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

            # Extract the output from stdout
            output_text = (completed.stdout or "").strip()
            if not output_text:
                raise AdapterError(f"{self.adapter_id} invocation returned empty output.")

            # Claude Code doesn't provide thread/session IDs in the same way as Codex
            # so we return None for session_id to indicate stateless execution
            return InvocationResult(output=output_text, session_id=None)

        finally:
            try:
                output_path.unlink(missing_ok=True)
            except OSError:
                pass
