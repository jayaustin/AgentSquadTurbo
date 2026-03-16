"""Cline host adapter stub."""

from .base import AdapterError, BaseAdapter


class ClineAdapter(BaseAdapter):
    """Stub adapter for Cline integration."""

    adapter_id = "cline"

    def invoke(self, command: str, prompt: str) -> str:
        raise AdapterError(
            "Cline adapter is not implemented yet. "
            "Keep host.primary_adapter=codex-cli or host.primary_adapter=codex-vscode-agent, or implement runner/adapters/cline.py."
        )
