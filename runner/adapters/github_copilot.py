"""GitHub Copilot host adapter stub."""

from .base import AdapterError, BaseAdapter


class GitHubCopilotAdapter(BaseAdapter):
    """Stub adapter for GitHub Copilot integration."""

    adapter_id = "github-copilot"

    def invoke(self, command: str, prompt: str) -> str:
        raise AdapterError(
            "GitHub Copilot adapter is not implemented yet. "
            "Keep host.primary_adapter=codex-cli or host.primary_adapter=codex-vscode-agent, or implement runner/adapters/github_copilot.py."
        )
