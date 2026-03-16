"""Gemini Code Assist host adapter stub."""

from .base import AdapterError, BaseAdapter


class GeminiCodeAssistAdapter(BaseAdapter):
    """Stub adapter for Gemini Code Assist integration."""

    adapter_id = "gemini-code-assist"

    def invoke(self, command: str, prompt: str) -> str:
        raise AdapterError(
            "Gemini Code Assist adapter is not implemented yet. "
            "Keep host.primary_adapter=codex-cli or host.primary_adapter=codex-vscode-agent, or implement runner/adapters/gemini_code_assist.py."
        )
