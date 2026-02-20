"""
Centralized prompt assembly for the universal agent loop.

PromptAssembly owns the entire LLM-facing context: system prompt, messages list,
and tool definitions.  Every string the LLM reads is defined here or in the .md
block files loaded by loader.py.  The agent loop creates one instance per session
and calls mutation methods during iteration -- it never builds message dicts itself.

System prompt block ordering (new):
    Rules -> History Rules -> Incoming Message Rules -> Tool Result Rules
    -> Tool IO -> Thinking -> Memory -> Identity

Tool Schema is sent as the separate `tools` parameter, not concatenated into the
system prompt string.

Conversation message ordering:
    History (last 5 sessions) -> Incoming messages -> Tool results
    -> Conditional (loopback / end-solo warning / summarization)

Token budget (character-based estimate, 1 token ≈ 4 chars):
    System prompt (static):  ~7k tokens
    Tool schemas:             ~3k tokens  (fixed, provider-generated)
    Conversation budget:      ~190k tokens remaining of a 200k window
      - History:              up to 60% of conversation budget (~114k tokens)
      - Tool results:         up to 30% of conversation budget (~57k tokens)
      - Incoming messages:    8000 tokens aggregate, 6000-word per-message cap
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from backend.db.models import Agent, Repository
from backend.prompts.builder import (
    get_identity_block,
    get_memory_block,
    get_tool_io_block,
)
from backend.prompts.loader import (
    END_SOLO_WARNING_BLOCK,
    HISTORY_RULES_BLOCK,
    INCOMING_MESSAGE_RULES_BLOCK,
    LOOPBACK_BLOCK,
    RULES_BLOCK,
    SUMMARIZATION_BLOCK,
    THINKING_BLOCK,
    TOOL_RESULT_RULES_BLOCK,
)
from backend.tools.loop_registry import get_tool_defs_for_role
from backend.logging.my_logger import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Token budget constants (character-based: 1 token ≈ 4 chars)
# ---------------------------------------------------------------------------

_CHARS_PER_TOKEN = 4
_CONTEXT_WINDOW_TOKENS = 200_000
_CONVERSATION_BUDGET_TOKENS = 190_000  # after system prompt + tool schemas

_HISTORY_BUDGET_TOKENS = int(_CONVERSATION_BUDGET_TOKENS * 0.60)   # 114k
_TOOL_RESULT_BUDGET_TOKENS = int(_CONVERSATION_BUDGET_TOKENS * 0.30)  # 57k
_INCOMING_MSG_BUDGET_TOKENS = 8_000
_INCOMING_MSG_PER_MSG_WORDS = 6_000

_HISTORY_BUDGET_CHARS = _HISTORY_BUDGET_TOKENS * _CHARS_PER_TOKEN
_TOOL_RESULT_BUDGET_CHARS = _TOOL_RESULT_BUDGET_TOKENS * _CHARS_PER_TOKEN
_INCOMING_MSG_BUDGET_CHARS = _INCOMING_MSG_BUDGET_TOKENS * _CHARS_PER_TOKEN
_INCOMING_MSG_PER_MSG_CHARS = _INCOMING_MSG_PER_MSG_WORDS * 5  # ~5 chars/word

_LEGACY_TOOL_NAME_ALIASES: dict[str, str] = {
    "execute_command E2B": "execute_command",
}


# ---------------------------------------------------------------------------
# BlockMeta — lightweight descriptor for every named block
# ---------------------------------------------------------------------------

@dataclass
class BlockMeta:
    name: str
    kind: str          # "system" | "conversation" | "conditional"
    max_chars: int | None   # None = no per-block cap (governed by budget)
    truncation: str    # "never" | "oldest_first" | "per_item"


BLOCK_REGISTRY: dict[str, BlockMeta] = {
    "rules":                BlockMeta("rules", "system", None, "never"),
    "history_rules":        BlockMeta("history_rules", "system", None, "never"),
    "incoming_msg_rules":   BlockMeta("incoming_msg_rules", "system", None, "never"),
    "tool_result_rules":    BlockMeta("tool_result_rules", "system", None, "never"),
    "tool_io":              BlockMeta("tool_io", "system", None, "never"),
    "thinking":             BlockMeta("thinking", "system", None, "never"),
    "memory":               BlockMeta("memory", "system", 10_000, "never"),
    "identity":             BlockMeta("identity", "system", None, "never"),
    "history":              BlockMeta("history", "conversation", _HISTORY_BUDGET_CHARS, "oldest_first"),
    "incoming_messages":    BlockMeta("incoming_messages", "conversation", _INCOMING_MSG_BUDGET_CHARS, "oldest_first"),
    "tool_result":          BlockMeta("tool_result", "conversation", _TOOL_RESULT_BUDGET_CHARS, "per_item"),
    "loopback":             BlockMeta("loopback", "conditional", 400, "never"),
    "end_solo_warning":     BlockMeta("end_solo_warning", "conditional", 400, "never"),
    "summarization":        BlockMeta("summarization", "conditional", 2_000, "never"),
}


def estimate_tokens(text: str) -> int:
    """Rough token estimate: 1 token per 4 characters."""
    return max(1, len(text) // _CHARS_PER_TOKEN)


# ---------------------------------------------------------------------------
# PromptAssembly
# ---------------------------------------------------------------------------

class PromptAssembly:
    """Stateful prompt assembly — owns system_prompt, messages, and tools
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

        # New system prompt order:
        # Rules -> History Rules -> Incoming Msg Rules -> Tool Result Rules
        # -> Tool IO -> Thinking -> Memory -> Identity
        self.system_prompt: str = "\n\n".join([
            RULES_BLOCK,
            HISTORY_RULES_BLOCK,
            INCOMING_MESSAGE_RULES_BLOCK,
            TOOL_RESULT_RULES_BLOCK,
            tool_io,
            THINKING_BLOCK,
            memory,
            identity,
        ])
        self.tools: list[dict] = get_tool_defs_for_role(agent.role)
        self.messages: list[dict] = []
        self._current_iteration_tool_result_chars: int = 0

    # ── Initial population ──────────────────────────────────────────────

    def load_history(
        self,
        history: list,
        new_messages_text: str,
        *,
        known_tool_names: set[str],
    ) -> None:
        """Build messages from persisted DB history rows and new unread text.

        ``history`` should already be ordered oldest-first and span at most the
        last 5 sessions (the caller — loop.py — is responsible for fetching
        the right rows).  We apply character-budget truncation here: if the
        total history exceeds _HISTORY_BUDGET_CHARS we drop the oldest messages.

        ``known_tool_names`` is used to filter stale historical tool_calls.
        """
        # Build candidate message list from history rows
        candidate: list[dict] = []
        for h in history:
            if h.role == "user":
                candidate.append({"role": "user", "content": h.content or ""})
            elif h.role == "assistant":
                candidate.append(self._build_history_assistant(h, known_tool_names))
            elif h.role == "tool":
                candidate.append(self._build_history_tool(h))

        candidate = self._repair_dangling_tool_use(candidate)

        # Enforce history budget: drop oldest messages first
        total_chars = sum(len(m.get("content") or "") for m in candidate)
        while total_chars > _HISTORY_BUDGET_CHARS and candidate:
            dropped = candidate.pop(0)
            total_chars -= len(dropped.get("content") or "")

        self.messages.extend(candidate)

        if new_messages_text:
            capped = self._cap_incoming_messages(new_messages_text)
            self.messages.append({"role": "user", "content": capped})

    def _build_history_assistant(self, h: object, known_tool_names: set[str]) -> dict:
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
        return msg

    def _build_history_tool(self, h: object) -> dict:
        saved_id = (
            (h.tool_input or {}).get("__tool_use_id__") if h.tool_input else None
        )
        return {
            "role": "tool",
            "content": h.content or "",
            "tool_use_id": saved_id or "",
        }

    @staticmethod
    def _repair_dangling_tool_use(messages: list[dict]) -> list[dict]:
        """Inject synthetic error tool_results for any tool_use IDs that lack
        a matching tool_result in the history.

        Without this, Anthropic returns 400: "tool_use ids were found without
        tool_result blocks immediately after".  This happens when a session was
        interrupted after persisting an assistant message but before all tool
        results were saved (e.g. end_solo_warning with wrong ID, crash, etc.).
        """
        issued: dict[str, int] = {}
        resolved: set[str] = set()

        for idx, m in enumerate(messages):
            if m.get("role") == "assistant":
                for tc in m.get("tool_calls", []):
                    tc_id = tc.get("id", "")
                    if tc_id:
                        issued[tc_id] = idx
            elif m.get("role") == "tool":
                uid = m.get("tool_use_id", "")
                if uid:
                    resolved.add(uid)

        dangling = set(issued.keys()) - resolved
        if not dangling:
            return messages

        logger.warning(
            "Repairing %d dangling tool_use id(s) in history: %s",
            len(dangling),
            dangling,
        )

        patched: list[dict] = []
        for idx, m in enumerate(messages):
            patched.append(m)
            if m.get("role") == "assistant":
                for tc in m.get("tool_calls", []):
                    tc_id = tc.get("id", "")
                    if tc_id in dangling:
                        patched.append({
                            "role": "tool",
                            "content": (
                                f"[Session interrupted — tool '{tc.get('name', '?')}' "
                                f"was never executed. Ignore this result.]"
                            ),
                            "tool_use_id": tc_id,
                        })
        return patched

    # ── In-flight mutations (called by the loop each iteration) ─────────

    def append_assistant(
        self, content: str, tool_calls: list[dict] | None
    ) -> None:
        """Append the LLM's response to the conversation."""
        msg: dict = {"role": "assistant", "content": content or ""}
        if tool_calls:
            msg["tool_calls"] = tool_calls
        self.messages.append(msg)
        # Reset per-iteration tool result budget counter
        self._current_iteration_tool_result_chars = 0

    def append_tool_result(
        self, name: str, result: str, tool_use_id: str
    ) -> None:
        """Append a successful tool execution result (with budget enforcement)."""
        result = self._enforce_tool_result_budget(result)
        self.messages.append(
            {"role": "tool", "content": result, "tool_use_id": tool_use_id}
        )
        self._current_iteration_tool_result_chars += len(result)

    def append_tool_error(
        self, name: str, exc: Exception, tool_use_id: str
    ) -> None:
        """Append a tool execution failure."""
        content = f"Tool '{name}' failed: {exc}"
        self.messages.append(
            {
                "role": "tool",
                "content": content,
                "tool_use_id": tool_use_id,
            }
        )

    def append_loopback(self) -> None:
        """Nudge the agent when it responds without calling any tools."""
        self.messages.append({"role": "user", "content": LOOPBACK_BLOCK})

    def append_end_solo_warning(self, tool_use_id: str = "end-solo-rule") -> None:
        """Warn agent that END must be called alone, not alongside other tools.

        ``tool_use_id`` MUST be the real id from the end tool_call so the
        Anthropic API sees a matching tool_result for every tool_use block.
        """
        self.messages.append(
            {
                "role": "tool",
                "content": END_SOLO_WARNING_BLOCK,
                "tool_use_id": tool_use_id,
            }
        )

    def append_summarization(self) -> None:
        """Inject the summarization prompt when context budget hits threshold."""
        self.messages.append({"role": "user", "content": SUMMARIZATION_BLOCK})

    # ── Budget helpers ──────────────────────────────────────────────────

    def _enforce_tool_result_budget(self, result: str) -> str:
        """Cap result if adding it would exceed the per-iteration tool result budget."""
        remaining = _TOOL_RESULT_BUDGET_CHARS - self._current_iteration_tool_result_chars
        if len(result) <= remaining:
            return result
        if remaining <= 0:
            return "[tool result omitted — iteration tool result budget exhausted]"
        return result[:remaining] + "\n[output truncated — tool result budget reached]"

    def _cap_incoming_messages(self, text: str) -> str:
        """Enforce aggregate and per-message caps on incoming message text."""
        lines = text.split("\n")
        capped_lines: list[str] = []
        total_chars = 0
        for line in lines:
            # Per-message word cap
            if len(line) > _INCOMING_MSG_PER_MSG_CHARS:
                line = line[:_INCOMING_MSG_PER_MSG_CHARS] + " [message truncated]"
            # Aggregate budget
            if total_chars + len(line) > _INCOMING_MSG_BUDGET_CHARS:
                capped_lines.append("[older messages omitted — incoming message budget reached]")
                break
            capped_lines.append(line)
            total_chars += len(line)
        return "\n".join(capped_lines)

    def context_used_chars(self) -> int:
        """Rough total character count across all messages (for budget monitoring)."""
        return sum(len(m.get("content") or "") for m in self.messages)

    def context_pressure_ratio(self) -> float:
        """Fraction of conversation budget consumed (0.0–1.0+)."""
        budget_chars = _CONVERSATION_BUDGET_TOKENS * _CHARS_PER_TOKEN
        return self.context_used_chars() / budget_chars

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

    # ── Accessors ───────────────────────────────────────────────────────

    @staticmethod
    def get_summarization_block() -> str:
        """Return the summarization prompt (injected at ~70% context capacity)."""
        return SUMMARIZATION_BLOCK
