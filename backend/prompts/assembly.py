"""
Centralized prompt assembly for the universal agent loop.

PromptAssembly owns the entire LLM-facing context: system prompt, messages list,
and tool definitions.  Every string the LLM reads is defined here or in the .md
block files loaded by loader.py.  The agent loop creates one instance per session
and calls mutation methods during iteration -- it never builds message dicts itself.

Block ordering (system prompt):
    Memory -> Rules -> Thinking -> Identity -> Tool IO
Identity and Tool IO are placed last so they sit closest to the conversation,
reinforcing the agent's role and available actions.
"""

from __future__ import annotations

from uuid import UUID

from backend.db.models import Agent, Repository
from backend.prompts.builder import (
    get_identity_block,
    get_memory_block,
    get_tool_io_block,
)
from backend.prompts.loader import (
    LOOPBACK_BLOCK,
    RULES_BLOCK,
    SUMMARIZATION_BLOCK,
    THINKING_BLOCK,
)
from backend.tools.loop_registry import get_tool_defs_for_role
from backend.logging.my_logger import get_logger

logger = get_logger(__name__)

_LEGACY_TOOL_NAME_ALIASES: dict[str, str] = {
    "execute_command E2B": "execute_command",
}


class PromptAssembly:
    """Stateful prompt assembly -- owns system_prompt, messages, and tools
    for the entire lifetime of one agent loop session."""

    def __init__(
        self,
        agent: Agent,
        project: Repository,
        memory_content: str | None,
    ) -> None:
        self._agent = agent
        self._project = project
        project_name = project.name or "Project"

        identity = get_identity_block(agent, project_name)
        tool_io = get_tool_io_block(agent.role)
        memory = get_memory_block(memory_content)

        self.system_prompt: str = (
            f"{memory}\n\n{RULES_BLOCK}\n\n{THINKING_BLOCK}\n\n{identity}\n\n{tool_io}"
        )
        self.tools: list[dict] = get_tool_defs_for_role(agent.role)
        self.messages: list[dict] = []

    # ── Initial population ──────────────────────────────────────────────

    def load_history(
        self,
        history: list,
        new_messages_text: str,
        *,
        known_tool_names: set[str],
    ) -> None:
        """Build messages from persisted DB history rows and new unread text.

        ``known_tool_names`` is the set of tool names the current role can
        dispatch (used to filter stale historical tool_calls).
        """
        for h in history:
            if h.role == "user":
                self.messages.append({"role": "user", "content": h.content or ""})
            elif h.role == "assistant":
                self._append_history_assistant(h, known_tool_names)
            elif h.role == "tool":
                self._append_history_tool(h)

        if new_messages_text:
            self.messages.append({"role": "user", "content": new_messages_text})

    def _append_history_assistant(self, h: object, known_tool_names: set[str]) -> None:
        saved_tool_calls = (
            (h.tool_input or {}).get("__tool_calls__") if h.tool_input else None
        )
        msg: dict = {"role": "assistant", "content": h.content or ""}
        if saved_tool_calls:
            normalized: list[dict] = []
            for tc in saved_tool_calls:
                if not isinstance(tc, dict):
                    continue
                tool_id = str(tc.get("id", "") or "")
                tool_name = str(tc.get("name", "") or "")
                tool_name = _LEGACY_TOOL_NAME_ALIASES.get(tool_name, tool_name)
                tool_input = tc.get("input")
                if not isinstance(tool_input, dict):
                    tool_input = (
                        tc.get("args") if isinstance(tc.get("args"), dict) else {}
                    )
                if not tool_id or not tool_name:
                    continue
                if tool_name not in known_tool_names and tool_name != "end":
                    logger.info(
                        "Skipping historical tool_call with unknown tool name=%r id=%r",
                        tool_name,
                        tool_id,
                    )
                    continue
                normalized.append(
                    {"id": tool_id, "name": tool_name, "input": tool_input}
                )
            if normalized:
                msg["tool_calls"] = normalized
        self.messages.append(msg)

    def _append_history_tool(self, h: object) -> None:
        saved_id = (
            (h.tool_input or {}).get("__tool_use_id__") if h.tool_input else None
        )
        self.messages.append(
            {"role": "tool", "content": h.content or "", "tool_use_id": saved_id or ""}
        )

    # ── In-flight mutations (called by the loop each iteration) ─────────

    def append_assistant(
        self, content: str, tool_calls: list[dict] | None
    ) -> None:
        """Append the LLM's response to the conversation."""
        msg: dict = {"role": "assistant", "content": content or ""}
        if tool_calls:
            msg["tool_calls"] = tool_calls
        self.messages.append(msg)

    def append_tool_result(
        self, name: str, result: str, tool_use_id: str
    ) -> None:
        """Append a successful tool execution result."""
        self.messages.append(
            {"role": "tool", "content": result, "tool_use_id": tool_use_id}
        )

    def append_tool_error(
        self, name: str, exc: Exception, tool_use_id: str
    ) -> None:
        """Append a tool execution failure."""
        self.messages.append(
            {
                "role": "tool",
                "content": f"Tool '{name}' failed: {exc}",
                "tool_use_id": tool_use_id,
            }
        )

    def append_loopback(self) -> None:
        """Nudge the agent when it responds without calling any tools."""
        self.messages.append({"role": "user", "content": LOOPBACK_BLOCK})

    def append_end_solo_warning(self) -> None:
        """Warn agent that END must be called alone, not alongside other tools."""
        self.messages.append(
            {
                "role": "tool",
                "content": (
                    "END was called with other tools and was ignored for this "
                    "iteration. Call END alone."
                ),
                "tool_use_id": "end-solo-rule",
            }
        )

    # ── Message formatting helpers ──────────────────────────────────────

    @staticmethod
    def format_incoming_messages(
        unread: list,
        agent_by_id: dict[UUID, Agent],
        user_agent_id: UUID,
        assignment_context: str | None = None,
    ) -> str:
        """Format raw unread channel messages into the text block appended
        as a ``user`` message at the start of a session."""

        def _sender_name(aid: UUID | None) -> str:
            if aid is None:
                return "System"
            if aid == user_agent_id:
                return "User"
            a = agent_by_id.get(aid)
            return a.display_name if a else str(aid)

        chunks: list[str] = []
        for m in unread:
            if m.from_agent_id != user_agent_id:
                a = agent_by_id.get(m.from_agent_id)
                role_label = a.role if a else "user"
                chunks.append(
                    f"[Message from {_sender_name(m.from_agent_id)} "
                    f"({role_label}, id={m.from_agent_id})]: {m.content}"
                )
            else:
                chunks.append(
                    f"[Message from User (id={user_agent_id})]: {m.content}"
                )
        if assignment_context:
            chunks.append(f"[Message from System (system)]: {assignment_context}")
        return "\n".join(chunks).strip()

    # ── Accessors for blocks needed outside the main flow ───────────────

    @staticmethod
    def get_summarization_block() -> str:
        """Return the summarization prompt (injected at ~70% context capacity)."""
        return SUMMARIZATION_BLOCK
