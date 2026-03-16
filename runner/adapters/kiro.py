"""Kiro host adapter stub."""

from .base import AdapterError, BaseAdapter


class KiroAdapter(BaseAdapter):
    """Stub adapter for Kiro integration."""

    adapter_id = "kiro"

    def invoke(self, command: str, prompt: str) -> str:
        raise AdapterError(
            "Kiro adapter is not implemented yet. "
            "Keep host.primary_adapter=codex-cli or host.primary_adapter=codex-vscode-agent, or implement runner/adapters/kiro.py."
        )

