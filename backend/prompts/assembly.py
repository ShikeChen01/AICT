"""
Centralized prompt assembly for the universal agent loop.

PromptAssembly owns the entire LLM-facing context: system prompt, messages list,
and tool definitions. Every string the LLM reads comes from DB-backed PromptBlockConfig
rows (seeded at agent creation from .md files, user-editable at any time).

DB is the source of truth for all prompt blocks. No .md file fallback at runtime.

System prompt block ordering is determined by PromptBlockConfig.position values.
Stage-specific blocks (thinking_stage, execution_stage) are filtered by thinking_stage param:
  - thinking_stage=None      → both excluded (thinking OFF, normal loop)
  - thinking_stage="thinking"  → only "thinking_stage" block included
  - thinking_stage="execution" → only "execution_stage" block included

Conversation message ordering:
    History (last 5 sessions) → Incoming messages → Tool results
    → Conditional (loopback / end-solo warning / summarization)

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

from backend.db.models import Agent, PromptBlockConfig, Repository
from backend.tools.loop_registry import get_tool_defs_for_role
from backend.logging.my_logger import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Token budget constants (character-based: 1 token ≈ 4 chars)
# ---------------------------------------------------------------------------

_CHARS_PER_TOKEN = 4
_CONTEXT_WINDOW_TOKENS = 200_000
_CONVERSATION_BUDGET_TOKENS = 190_000

_HISTORY_BUDGET_TOKENS = int(_CONVERSATION_BUDGET_TOKENS * 0.60)
_TOOL_RESULT_BUDGET_TOKENS = int(_CONVERSATION_BUDGET_TOKENS * 0.30)
_INCOMING_MSG_BUDGET_TOKENS = 8_000
_INCOMING_MSG_PER_MSG_WORDS = 6_000

_HISTORY_BUDGET_CHARS = _HISTORY_BUDGET_TOKENS * _CHARS_PER_TOKEN
_TOOL_RESULT_BUDGET_CHARS = _TOOL_RESULT_BUDGET_TOKENS * _CHARS_PER_TOKEN
_INCOMING_MSG_BUDGET_CHARS = _INCOMING_MSG_BUDGET_TOKENS * _CHARS_PER_TOKEN
_INCOMING_MSG_PER_MSG_CHARS = _INCOMING_MSG_PER_MSG_WORDS * 5

_LEGACY_TOOL_NAME_ALIASES: dict[str, str] = {
    "execute_command E2B": "execute_command",
}

# Stage-specific block keys — only one may be included at a time
_STAGE_BLOCK_KEYS = frozenset({"thinking_stage", "execution_stage"})


@dataclass
class BlockMeta:
    name: str
    kind: str
    max_chars: int | None
    truncation: str


BLOCK_REGISTRY: dict[str, BlockMeta] = {
    "rules":                BlockMeta("rules", "system", None, "never"),
    "history_rules":        BlockMeta("history_rules", "system", None, "never"),
    "incoming_msg_rules":   BlockMeta("incoming_msg_rules", "system", None, "never"),
    "tool_result_rules":    BlockMeta("tool_result_rules", "system", None, "never"),
    "tool_io":              BlockMeta("tool_io", "system", None, "never"),
    "memory":               BlockMeta("memory", "system", 10_000, "never"),
    "identity":             BlockMeta("identity", "system", None, "never"),
    "thinking_stage":       BlockMeta("thinking_stage", "system", None, "never"),
    "execution_stage":      BlockMeta("execution_stage", "system", None, "never"),
    "history":              BlockMeta("history", "conversation", _HISTORY_BUDGET_CHARS, "oldest_first"),
    "incoming_messages":    BlockMeta("incoming_messages", "conversation", _INCOMING_MSG_BUDGET_CHARS, "oldest_first"),
    "tool_result":          BlockMeta("tool_result", "conversation", _TOOL_RESULT_BUDGET_CHARS, "per_item"),
    "loopback":             BlockMeta("loopback", "conditional", 400, "never"),
    "end_solo_warning":     BlockMeta("end_solo_warning", "conditional", 400, "never"),
    "summarization":        BlockMeta("summarization", "conditional", 2_000, "never"),
}


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // _CHARS_PER_TOKEN)


# Placeholder values that are dynamically resolved per session
_PLACEHOLDER_KEYS = frozenset({"{project_name}", "{agent_name}", "{memory_content}"})


def _resolve_placeholders(content: str, agent: Agent, project: Repository, memory_content: str | None) -> str:
    """Replace {project_name}, {agent_name}, {memory_content} in block content."""
    project_name = (project.name or "Project").replace("{", "{{").replace("}", "}}")
    agent_name = (agent.display_name or "Agent").replace("{", "{{").replace("}", "}}")

    if memory_content is None:
        memory_text = "No memory recorded yet."
    elif isinstance(memory_content, dict):
        import json
        memory_text = json.dumps(memory_content, indent=2).strip() or "No memory recorded yet."
    elif isinstance(memory_content, str) and memory_content.strip():
        memory_text = memory_content.strip()
    else:
        memory_text = "No memory recorded yet."

    # Use safe substitution to avoid KeyError on other braces
    try:
        return content.format(
            project_name=project.name or "Project",
            agent_name=agent.display_name or "Agent",
            memory_content=memory_text,
        )
    except (KeyError, ValueError):
        # Content may have literal braces; fall back to simple replacement
        return (
            content
            .replace("{project_name}", project.name or "Project")
            .replace("{agent_name}", agent.display_name or "Agent")
            .replace("{memory_content}", memory_text)
        )


class PromptAssembly:
    """Stateful prompt assembly — owns system_prompt, messages, and tools
    for the entire lifetime of one agent loop session.

    block_configs: all PromptBlockConfig rows for the agent (loaded from DB by loop.py).
    thinking_stage: None = thinking OFF; "thinking" = Stage 1; "execution" = Stage 2.
    """

    def __init__(
        self,
        agent: Agent,
        project: Repository,
        memory_content: str | None,
        *,
        block_configs: list[PromptBlockConfig],
        thinking_stage: str | None = None,
    ) -> None:
        self._agent = agent
        self._project = project

        # Load blocks from DB; sort by position
        enabled_blocks = sorted(
            [b for b in block_configs if b.enabled],
            key=lambda b: b.position,
        )

        # Build system prompt parts; filter stage-specific blocks
        parts: list[str] = []
        for block in enabled_blocks:
            if block.block_key in _STAGE_BLOCK_KEYS:
                # Include only the block matching the current stage
                expected_key = f"{thinking_stage}_stage" if thinking_stage else None
                if block.block_key == expected_key:
                    parts.append(_resolve_placeholders(block.content, agent, project, memory_content))
                continue
            parts.append(_resolve_placeholders(block.content, agent, project, memory_content))

        self.system_prompt: str = "\n\n".join(parts)
        self.tools: list[dict] = get_tool_defs_for_role(agent.role)
        self.messages: list[dict] = []
        self._current_iteration_tool_result_chars: int = 0

    # ── Loopback text accessors (used by loop.py) ────────────────────────────

    def _get_block_content(self, block_key: str) -> str:
        """Look up a block's raw content from the system prompt context."""
        # Used for conditional injections (loopback, end_solo_warning, summarization)
        # These are stored in DB and resolved when needed
        return ""  # Caller should use the DB-loaded block content directly

    # ── Initial population ──────────────────────────────────────────────
    def load_history(
        self,
        history: list,
        new_messages_text: str,
        *,
        known_tool_names: set[str],
    ) -> None:
        candidate: list[dict] = []
        for h in history:
            if h.role == "user":
                candidate.append({"role": "user", "content": h.content or ""})
            elif h.role == "assistant":
                candidate.append(self._build_history_assistant(h, known_tool_names))
            elif h.role == "tool":
                candidate.append(self._build_history_tool(h))

        candidate = self._repair_dangling_tool_use(candidate)

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
                if tool_name not in known_tool_names and tool_name not in ("end", "thinking_done"):
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

    # ── In-flight mutations ──────────────────────────────────────────────────

    def append_assistant(self, content: str, tool_calls: list[dict] | None) -> None:
        msg: dict = {"role": "assistant", "content": content or ""}
        if tool_calls:
            msg["tool_calls"] = tool_calls
        self.messages.append(msg)
        self._current_iteration_tool_result_chars = 0

    def append_tool_result(self, name: str, result: str, tool_use_id: str) -> None:
        result = self._enforce_tool_result_budget(result)
        self.messages.append(
            {"role": "tool", "content": result, "tool_use_id": tool_use_id}
        )
        self._current_iteration_tool_result_chars += len(result)

    def append_tool_error(self, name: str, exc: Exception, tool_use_id: str) -> None:
        from backend.tools.result import ToolExecutionError

        if isinstance(exc, ToolExecutionError):
            error_code = exc.error_code
            error_detail = exc.args[0] if exc.args else str(exc)
            hint = exc.hint or f"Call describe_tool('{name}') for full parameter details."
        else:
            error_code = type(exc).__name__
            error_detail = str(exc)
            hint = f"Review the error and retry with corrected parameters. Call describe_tool('{name}') if the schema is unclear."

        content = (
            f"[ERROR: {error_code}] {error_detail}\n"
            f"tool: {name}\n"
            f"hint: {hint}"
        )
        content = self._enforce_tool_result_budget(content)
        self.messages.append(
            {"role": "tool", "content": content, "tool_use_id": tool_use_id}
        )
        self._current_iteration_tool_result_chars += len(content)

    def append_loopback(self, loopback_content: str) -> None:
        self.messages.append({"role": "user", "content": loopback_content})

    def append_end_solo_warning(self, end_solo_content: str, tool_use_id: str = "end-solo-rule") -> None:
        self.messages.append(
            {"role": "tool", "content": end_solo_content, "tool_use_id": tool_use_id}
        )

    def append_summarization(self, summarization_content: str) -> None:
        self.messages.append({"role": "user", "content": summarization_content})

    def rebuild_for_execution_stage(
        self,
        block_configs: list[PromptBlockConfig],
        memory_content: str | None,
    ) -> None:
        """Rebuild system_prompt for Stage 2 (execution) after thinking_done is called.

        Called by loop.py on stage transition. Replaces system_prompt in-place.
        Keeps messages list intact so execution stage can see thinking stage history.
        """
        enabled_blocks = sorted(
            [b for b in block_configs if b.enabled],
            key=lambda b: b.position,
        )
        parts: list[str] = []
        for block in enabled_blocks:
            if block.block_key in _STAGE_BLOCK_KEYS:
                if block.block_key == "execution_stage":
                    parts.append(_resolve_placeholders(block.content, self._agent, self._project, memory_content))
                continue
            parts.append(_resolve_placeholders(block.content, self._agent, self._project, memory_content))
        self.system_prompt = "\n\n".join(parts)

    # ── Budget helpers ───────────────────────────────────────────────────────

    def _enforce_tool_result_budget(self, result: str) -> str:
        remaining = _TOOL_RESULT_BUDGET_CHARS - self._current_iteration_tool_result_chars
        if len(result) <= remaining:
            return result
        if remaining <= 0:
            return "[tool result omitted — iteration tool result budget exhausted]"
        return result[:remaining] + "\n[output truncated — tool result budget reached]"

    def _cap_incoming_messages(self, text: str) -> str:
        lines = text.split("\n")
        capped_lines: list[str] = []
        total_chars = 0
        for line in lines:
            if len(line) > _INCOMING_MSG_PER_MSG_CHARS:
                line = line[:_INCOMING_MSG_PER_MSG_CHARS] + " [message truncated]"
            if total_chars + len(line) > _INCOMING_MSG_BUDGET_CHARS:
                capped_lines.append("[older messages omitted — incoming message budget reached]")
                break
            capped_lines.append(line)
            total_chars += len(line)
        return "\n".join(capped_lines)

    def context_used_chars(self) -> int:
        return sum(len(m.get("content") or "") for m in self.messages)

    def context_pressure_ratio(self) -> float:
        budget_chars = _CONVERSATION_BUDGET_TOKENS * _CHARS_PER_TOKEN
        return self.context_used_chars() / budget_chars

    # ── Message formatting helpers ──────────────────────────────────────────

    @staticmethod
    def format_incoming_messages(
        unread: list,
        agent_by_id: dict[UUID, Agent],
        user_agent_id: UUID,
        assignment_context: str | None = None,
    ) -> str:
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

    @staticmethod
    def get_summarization_block() -> str:
        """Kept for backward compatibility. Callers should use the DB block content."""
        return "Your conversation context is approaching its limit. Summarize important context into update_memory."
