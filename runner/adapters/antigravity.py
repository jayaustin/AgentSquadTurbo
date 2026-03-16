"""AntiGravity host adapter stub."""

from .base import AdapterError, BaseAdapter


class AntiGravityAdapter(BaseAdapter):
    """Stub adapter for AntiGravity integration."""

    adapter_id = "antigravity"

    def invoke(self, command: str, prompt: str) -> str:
        raise AdapterError(
            "AntiGravity adapter is not implemented yet. "
            "Keep host.primary_adapter=codex-cli or host.primary_adapter=codex-vscode-agent, or implement runner/adapters/antigravity.py."
        )
