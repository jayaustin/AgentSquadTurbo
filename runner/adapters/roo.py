"""Roo host adapter stub."""

from .base import AdapterError, BaseAdapter


class RooAdapter(BaseAdapter):
    """Stub adapter for Roo integration."""

    adapter_id = "roo"

    def invoke(self, command: str, prompt: str) -> str:
        raise AdapterError(
            "Roo adapter is not implemented yet. "
            "Keep host.primary_adapter=codex-cli or host.primary_adapter=codex-vscode-agent, or implement runner/adapters/roo.py."
        )

