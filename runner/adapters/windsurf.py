"""Windsurf host adapter stub."""

from .base import AdapterError, BaseAdapter


class WindsurfAdapter(BaseAdapter):
    """Stub adapter for Windsurf integration."""

    adapter_id = "windsurf"

    def invoke(self, command: str, prompt: str) -> str:
        raise AdapterError(
            "Windsurf adapter is not implemented yet. "
            "Keep host.primary_adapter=codex-cli or host.primary_adapter=codex-vscode-agent, or implement runner/adapters/windsurf.py."
        )
