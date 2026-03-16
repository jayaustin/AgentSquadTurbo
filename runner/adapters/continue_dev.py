"""Continue host adapter stub."""

from .base import AdapterError, BaseAdapter


class ContinueAdapter(BaseAdapter):
    """Stub adapter for Continue integration."""

    adapter_id = "continue"

    def invoke(self, command: str, prompt: str) -> str:
        raise AdapterError(
            "Continue adapter is not implemented yet. "
            "Keep host.primary_adapter=codex-cli or host.primary_adapter=codex-vscode-agent, or implement runner/adapters/continue_dev.py."
        )
