"""Host adapters for non-API assistant invocation."""

from .antigravity import AntiGravityAdapter
from .base import AdapterError, BaseAdapter
from .claude_code_cli import ClaudeCodeCliAdapter
from .claude_code_vscode_agent import ClaudeCodeVSCodeAgentAdapter
from .cline import ClineAdapter
from .codex_vscode_agent import CodexVsCodeAgentAdapter
from .codex_cli import CodexCliAdapter
from .continue_dev import ContinueAdapter
from .cursor import CursorAdapter
from .gemini_code_assist import GeminiCodeAssistAdapter
from .github_copilot import GitHubCopilotAdapter
from .kiro import KiroAdapter
from .roo import RooAdapter
from .windsurf import WindsurfAdapter


ADAPTER_TYPES = {
    "antigravity": AntiGravityAdapter,
    "claude-code-cli": ClaudeCodeCliAdapter,
    "claude-code-vscode-agent": ClaudeCodeVSCodeAgentAdapter,
    "claude-code": ClaudeCodeCliAdapter,  # Default alias for CLI
    "cline": ClineAdapter,
    "codex-cli": CodexCliAdapter,
    "codex-vscode-agent": CodexVsCodeAgentAdapter,
    "codex": CodexVsCodeAgentAdapter,
    "continue": ContinueAdapter,
    "cursor": CursorAdapter,
    "gemini-code-assist": GeminiCodeAssistAdapter,
    "github-copilot": GitHubCopilotAdapter,
    "kiro": KiroAdapter,
    "roo": RooAdapter,
    "windsurf": WindsurfAdapter,
}


def build_adapter(name: str) -> BaseAdapter:
    lowered = (name or "").strip().lower()
    adapter_type = ADAPTER_TYPES.get(lowered)
    if adapter_type is None:
        supported = ", ".join(sorted(ADAPTER_TYPES.keys()))
        raise AdapterError(f"Unsupported adapter '{name}'. Supported adapters: {supported}.")
    return adapter_type()
