"""Structured error type for tool executors.

Executors should raise ToolExecutionError rather than returning "Error: ..." strings.
The loop catches this (and all exceptions) and formats them for the LLM via
PromptAssembly.append_tool_error().
"""

from __future__ import annotations


class ToolExecutionError(Exception):
    """Raised by tool executors to signal a structured, actionable failure.

    Carries:
    - error_code: machine-readable category the LLM can pattern-match on
    - hint: one-sentence next action for the LLM to self-correct
    """

    INVALID_INPUT = "INVALID_INPUT"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    SANDBOX_TIMEOUT = "SANDBOX_TIMEOUT"
    SANDBOX_UNAVAILABLE = "SANDBOX_UNAVAILABLE"
    TOOL_DISABLED = "TOOL_DISABLED"
    NOT_FOUND = "NOT_FOUND"
    PROVIDER_ERROR = "PROVIDER_ERROR"

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "TOOL_ERROR",
        hint: str | None = None,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.hint = hint

    def __str__(self) -> str:
        base = f"[{self.error_code}] {super().__str__()}"
        if self.hint:
            return f"{base} Hint: {self.hint}"
        return base
