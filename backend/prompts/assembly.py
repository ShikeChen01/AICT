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

Context window layout (model-specific, scales with context window W):
    Static overhead (measured at init):
      System prompt blocks  ~1,900 tokens (excluding memory content)
      Tool schemas          ~1,700-2,200 tokens (role-dependent)
      Incoming messages     8,000 tokens cap
      Conditional reserve   500 tokens (loopback, summarization blocks)
    Dynamic pool = W - static overhead, split by ratio:
      Memory                10% of dynamic pool
      Past session history  12% of dynamic pool
      Current session       78% of dynamic pool (primary growth area)

Summarization triggers (independent per section, 70% threshold):
    Memory section: triggers when memory content fills 70% of memory_budget
    Current session: triggers when session messages fill 70% of current_session_budget
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from uuid import UUID

from backend.db.models import Agent, PromptBlockConfig, Repository
from backend.llm.model_catalog import get_context_window, get_image_budget, get_image_tokens_per_image
from backend.tools.loop_registry import get_tool_defs_for_role
from backend.logging.my_logger import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Static constants
# ---------------------------------------------------------------------------

_CHARS_PER_TOKEN = 4

# Static overhead components (tokens)
_INCOMING_MSG_BUDGET_TOKENS = 8_000
_CONDITIONAL_RESERVE_TOKENS = 1_500  # increased: covers loopback + summarization injections
_TOOL_SCHEMA_RESERVE_TOKENS = 4_000  # minimum reservation for tool schemas
_INCOMING_MSG_PER_MSG_WORDS = 6_000
_INCOMING_MSG_BUDGET_CHARS = _INCOMING_MSG_BUDGET_TOKENS * _CHARS_PER_TOKEN
_INCOMING_MSG_PER_MSG_CHARS = _INCOMING_MSG_PER_MSG_WORDS * 5

# Dynamic pool allocation ratios (must sum to 1.0)
_MEMORY_RATIO = 0.10
_PAST_SESSION_RATIO = 0.12
_CURRENT_SESSION_RATIO = 0.78  # remainder after memory + past session

# Summarization fires when a dynamic section reaches this fraction of its budget
SUMMARIZATION_THRESHOLD = 0.70

_LEGACY_TOOL_NAME_ALIASES: dict[str, str] = {
    "execute_command E2B": "execute_command",
}

# Stage-specific block keys — only one may be included at a time
_STAGE_BLOCK_KEYS = frozenset({"thinking_stage", "execution_stage"})

# Conditional blocks are injected at runtime as messages, never in the system prompt
_CONDITIONAL_BLOCK_KEYS = frozenset({
    "loopback", "end_solo_warning",
    "summarization", "summarization_memory", "summarization_history",
})


@dataclass
class BlockMeta:
    name: str
    kind: str
    max_chars: int | None
    truncation: str


BLOCK_REGISTRY: dict[str, BlockMeta] = {
    "rules":                BlockMeta("rules", "system", None, "never"),
    "history_rules":        BlockMeta("history_rules", "system", None, "never"),
    "incoming_message_rules":   BlockMeta("incoming_message_rules", "system", None, "never"),
    "tool_result_rules":    BlockMeta("tool_result_rules", "system", None, "never"),
    "tool_io":              BlockMeta("tool_io", "system", None, "never"),
    "memory":               BlockMeta("memory", "system", None, "dynamic"),
    "identity":             BlockMeta("identity", "system", None, "never"),
    "secrets":              BlockMeta("secrets", "system", None, "never"),
    "thinking_stage":       BlockMeta("thinking_stage", "system", None, "never"),
    "execution_stage":      BlockMeta("execution_stage", "system", None, "never"),
    "loopback":             BlockMeta("loopback", "conditional", 400, "never"),
    "end_solo_warning":     BlockMeta("end_solo_warning", "conditional", 400, "never"),
    "summarization":        BlockMeta("summarization", "conditional", 2_000, "never"),
    "summarization_memory": BlockMeta("summarization_memory", "conditional", 2_000, "never"),
    "summarization_history": BlockMeta("summarization_history", "conditional", 2_000, "never"),
}


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // _CHARS_PER_TOKEN)


# Placeholder values that are dynamically resolved per session
_PLACEHOLDER_KEYS = frozenset({"{project_name}", "{agent_name}", "{memory_content}", "{project_secrets}"})


def _resolve_placeholders(
    content: str,
    agent: Agent,
    project: Repository,
    memory_content: str | None,
    project_secrets: dict[str, str] | None = None,
) -> str:
    """Replace {project_name}, {agent_name}, {memory_content}, {project_secrets} in block content."""
    if memory_content is None:
        memory_text = "No memory recorded yet."
    elif isinstance(memory_content, dict):
        memory_text = json.dumps(memory_content, indent=2).strip() or "No memory recorded yet."
    elif isinstance(memory_content, str) and memory_content.strip():
        memory_text = memory_content.strip()
    else:
        memory_text = "No memory recorded yet."

    secrets = project_secrets or {}
    project_secrets_text = (
        "\n".join(f"{k}={v}" for k, v in sorted(secrets.items()))
        if secrets
        else "No project secrets configured."
    )

    try:
        return content.format(
            project_name=project.name or "Project",
            agent_name=agent.display_name or "Agent",
            memory_content=memory_text,
            project_secrets=project_secrets_text,
        )
    except (KeyError, ValueError):
        return (
            content
            .replace("{project_name}", project.name or "Project")
            .replace("{agent_name}", agent.display_name or "Agent")
            .replace("{memory_content}", memory_text)
            .replace("{project_secrets}", project_secrets_text)
        )


class PromptAssembly:
    """Stateful prompt assembly — owns system_prompt, messages, and tools
    for the entire lifetime of one agent loop session.

    block_configs: all PromptBlockConfig rows for the agent (loaded from DB by loop.py).
    model: the resolved model name used to look up context window size.
    thinking_stage: None = thinking OFF; "thinking" = Stage 1; "execution" = Stage 2.
    """

    def __init__(
        self,
        agent: Agent,
        project: Repository,
        memory_content: str | None,
        *,
        block_configs: list[PromptBlockConfig],
        model: str = "",
        thinking_stage: str | None = None,
        project_secrets: dict[str, str] | None = None,
    ) -> None:
        self._agent = agent
        self._project = project
        self._block_configs = block_configs
        self._model = model or (agent.model or "")
        self._project_secrets = project_secrets or {}

        # ── Step 1: Load tool defs ────────────────────────────────────────────
        self.tools: list[dict] = get_tool_defs_for_role(agent.role)

        # ── Step 2: Measure tool schema tokens ────────────────────────────────
        measured_tool_tokens: int = sum(
            len(json.dumps({
                "name": t.get("name", ""),
                "description": t.get("description", ""),
                "input_schema": t.get("input_schema", {}),
            }))
            for t in self.tools
        ) // _CHARS_PER_TOKEN
        # Use the higher of measured or the minimum reserve floor to avoid
        # underestimating tool overhead when schemas change at runtime
        self.tool_schema_tokens: int = max(measured_tool_tokens, _TOOL_SCHEMA_RESERVE_TOKENS)

        # ── Step 3: Build system prompt (without memory content) ─────────────
        enabled_blocks = sorted(
            [b for b in block_configs if b.enabled],
            key=lambda b: b.position,
        )
        parts: list[str] = []
        for block in enabled_blocks:
            if block.block_key in _CONDITIONAL_BLOCK_KEYS:
                # Conditional blocks are injected at runtime as messages, never here
                continue
            if block.block_key in _STAGE_BLOCK_KEYS:
                expected_key = f"{thinking_stage}_stage" if thinking_stage else None
                if block.block_key == expected_key:
                    parts.append(_resolve_placeholders(block.content, agent, project, memory_content, project_secrets or {}))
                continue
            parts.append(_resolve_placeholders(block.content, agent, project, memory_content, project_secrets or {}))

        self.system_prompt: str = "\n\n".join(parts)

        # Measure system prompt tokens (excluding the current memory content size;
        # memory_content has already been substituted above for the placeholder)
        system_prompt_tokens = estimate_tokens(self.system_prompt)

        # ── Step 4: Compute model-specific budgets ────────────────────────────
        context_window = get_context_window(self._model)

        # Per-agent overrides from token_allocations (falls back to module constants)
        alloc = getattr(agent, "token_allocations", None) or {}
        effective_incoming = int(alloc.get("incoming_msg_tokens", _INCOMING_MSG_BUDGET_TOKENS))
        effective_memory_ratio = float(alloc.get("memory_pct", _MEMORY_RATIO * 100)) / 100.0
        effective_past_ratio = float(alloc.get("past_session_pct", _PAST_SESSION_RATIO * 100)) / 100.0

        # Image reserve: per-agent cap for Claude; default 10 images for all vision models.
        # Kept outside the text context window — dynamic pool is computed from context_window only.
        max_images = int(alloc.get("max_images_per_turn", 10))
        image_reserve_tokens = get_image_budget(self._model, max_images)

        static_overhead = (
            system_prompt_tokens
            + self.tool_schema_tokens
            + effective_incoming
            + _CONDITIONAL_RESERVE_TOKENS
        )
        dynamic_pool = max(0, context_window - static_overhead)

        self._context_window_tokens: int = context_window
        self._static_overhead_tokens: int = static_overhead
        self._dynamic_pool_tokens: int = dynamic_pool
        self._system_prompt_tokens: int = system_prompt_tokens
        self._image_reserve_tokens: int = image_reserve_tokens
        self._image_tokens_per_image: int = get_image_tokens_per_image(self._model)
        self._max_images_per_turn: int = max_images

        self._memory_budget_tokens: int = int(dynamic_pool * effective_memory_ratio)
        self._memory_budget_chars: int = self._memory_budget_tokens * _CHARS_PER_TOKEN

        self._past_session_budget_tokens: int = int(dynamic_pool * effective_past_ratio)

        self._current_session_budget_tokens: int = (
            dynamic_pool - self._memory_budget_tokens - self._past_session_budget_tokens
        )
        self._current_session_budget_chars: int = self._current_session_budget_tokens * _CHARS_PER_TOKEN

        # ── Step 5: Message list and session tracking ─────────────────────────
        self.messages: list[dict] = []
        self._current_iteration_tool_result_chars: int = 0

        # Track which messages belong to the current session for compact_messages
        self._current_session_start_index: int = 0

        # Current memory content for pressure tracking
        self._current_memory_content: str = (
            memory_content if isinstance(memory_content, str) else ""
        )

        logger.debug(
            "PromptAssembly init: model=%s window=%d static=%d pool=%d "
            "mem=%d past=%d session=%d tools_tokens=%d image_reserve=%d max_images=%d",
            self._model,
            context_window,
            static_overhead,
            dynamic_pool,
            self._memory_budget_tokens,
            self._past_session_budget_tokens,
            self._current_session_budget_tokens,
            self.tool_schema_tokens,
            image_reserve_tokens,
            max_images,
        )

    # ── Initial population ──────────────────────────────────────────────
    def load_history(
        self,
        past_session_msgs: list,
        current_session_msgs: list,
        new_messages_text: str,
        *,
        known_tool_names: set[str],
    ) -> None:
        """Load history in two phases.

        Phase 1: Past sessions (conversation only, pre-budget-fitted by DB query).
        Phase 2: Current session (all message types, chronological).
        Phase 3: Incoming new user message.
        """
        # Phase 1: Past sessions
        # Tool messages are filtered out by the DB query for past sessions,
        # so we must also strip tool_calls from assistant messages to avoid
        # OpenAI's "assistant message with tool_calls must be followed by
        # tool messages" validation error.
        past_candidate: list[dict] = []
        current_past_session_id = None
        for h in past_session_msgs:
            if h.session_id != current_past_session_id:
                current_past_session_id = h.session_id
                past_candidate.append({
                    "role": "user",
                    "content": f"--- Session {str(h.session_id)[:8]} ---",
                })
            if h.role == "user":
                past_candidate.append({"role": "user", "content": h.content or ""})
            elif h.role == "assistant":
                msg = self._build_history_assistant(h, known_tool_names)
                # Strip tool_calls since their tool results are not loaded
                # for past sessions. Summarize which tools were called into
                # the content so the agent retains awareness.
                tool_calls = msg.pop("tool_calls", None)
                if tool_calls:
                    tool_names = [tc.get("name", "?") for tc in tool_calls]
                    summary = ", ".join(tool_names)
                    existing = msg.get("content", "")
                    msg["content"] = (
                        f"{existing}\n[Called tools: {summary} — results truncated from history]"
                        if existing
                        else f"[Called tools: {summary} — results truncated from history]"
                    )
                past_candidate.append(msg)
            # tool messages already filtered out by DB query

        if past_candidate:
            past_candidate.append({
                "role": "user",
                "content": (
                    "[Past session tool results are fully truncated. "
                    "Use read_history(session_id=...) to view them if needed.]"
                ),
            })
        self.messages.extend(past_candidate)

        # Phase 2: Current session (all message types)
        # Tool results in DB are truncated (ephemeral design).  The agent
        # sees tool_calls paired with truncated results on session reload;
        # full results only existed in-memory for one iteration.
        current_candidate: list[dict] = []
        for h in current_session_msgs:
            if h.role == "user":
                current_candidate.append({"role": "user", "content": h.content or ""})
            elif h.role == "assistant":
                current_candidate.append(self._build_history_assistant(h, known_tool_names))
            elif h.role == "tool":
                current_candidate.append(self._build_history_tool(h))

        current_candidate = self._repair_dangling_tool_use(current_candidate)

        # Mark the start index for current session messages
        self._current_session_start_index = len(self.messages)
        self.messages.extend(current_candidate)

        # Phase 3: Incoming messages
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
        for m in messages:
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
        """Rebuild system_prompt for Stage 2 (execution) after thinking_done is called."""
        enabled_blocks = sorted(
            [b for b in block_configs if b.enabled],
            key=lambda b: b.position,
        )
        parts: list[str] = []
        for block in enabled_blocks:
            if block.block_key in _CONDITIONAL_BLOCK_KEYS:
                continue
            if block.block_key in _STAGE_BLOCK_KEYS:
                if block.block_key == "execution_stage":
                    parts.append(_resolve_placeholders(block.content, self._agent, self._project, memory_content, self._project_secrets))
                continue
            parts.append(_resolve_placeholders(block.content, self._agent, self._project, memory_content, self._project_secrets))
        self.system_prompt = "\n\n".join(parts)

    # ── Memory refresh and compaction ────────────────────────────────────────

    def _refresh_memory_in_system_prompt(
        self,
        memory_content: str | None,
        block_configs: list[PromptBlockConfig] | None = None,
        thinking_stage: str | None = None,
    ) -> None:
        """Rebuild system prompt with updated memory content.

        Called after update_memory so the next LLM call sees fresh memory.
        """
        configs = block_configs or self._block_configs
        enabled_blocks = sorted(
            [b for b in configs if b.enabled],
            key=lambda b: b.position,
        )
        parts: list[str] = []
        for block in enabled_blocks:
            if block.block_key in _CONDITIONAL_BLOCK_KEYS:
                continue
            if block.block_key in _STAGE_BLOCK_KEYS:
                expected_key = f"{thinking_stage}_stage" if thinking_stage else None
                if block.block_key == expected_key:
                    parts.append(_resolve_placeholders(block.content, self._agent, self._project, memory_content, self._project_secrets))
                continue
            parts.append(_resolve_placeholders(block.content, self._agent, self._project, memory_content, self._project_secrets))
        self.system_prompt = "\n\n".join(parts)

        # Update tracked memory content for pressure calculation
        if isinstance(memory_content, str):
            self._current_memory_content = memory_content
        elif isinstance(memory_content, dict):
            self._current_memory_content = json.dumps(memory_content)
        else:
            self._current_memory_content = ""

    def compact_messages(self, keep_recent: int = 20) -> None:
        """Remove past session messages and trim older current session messages.

        Called by loop.py after the agent calls compact_history. Removes all messages
        before _current_session_start_index, then keeps only the most recent
        keep_recent messages from the current session.
        """
        # Keep only current session messages
        current_msgs = self.messages[self._current_session_start_index:]

        # Trim to most recent keep_recent messages
        if len(current_msgs) > keep_recent:
            current_msgs = current_msgs[-keep_recent:]

        # Repair any dangling tool_calls created by the trim
        current_msgs = self._repair_dangling_tool_use(current_msgs)

        self.messages = current_msgs
        self._current_session_start_index = 0
        logger.info(
            "compact_messages: kept %d current session messages",
            len(self.messages),
        )

    # ── Summarization pressure checks ───────────────────────────────────────

    def check_summarization_triggers(self) -> list[str]:
        """Check each dynamic section independently.

        Returns list of section keys that have exceeded SUMMARIZATION_THRESHOLD.
        Possible values: 'memory', 'current_session'.
        Both can trigger simultaneously.
        """
        triggered = []

        # Memory pressure: compare current memory content tokens to memory budget
        if self._memory_budget_tokens > 0:
            memory_used_tokens = estimate_tokens(self._current_memory_content)
            if memory_used_tokens >= self._memory_budget_tokens * SUMMARIZATION_THRESHOLD:
                triggered.append("memory")

        # Current session pressure: messages added since current session start
        current_msgs = self.messages[self._current_session_start_index:]
        session_used_chars = sum(len(m.get("content") or "") for m in current_msgs)
        if self._current_session_budget_chars > 0:
            if session_used_chars >= self._current_session_budget_chars * SUMMARIZATION_THRESHOLD:
                triggered.append("current_session")

        return triggered

    # ── Budget helpers ───────────────────────────────────────────────────────

    def _enforce_tool_result_budget(self, result: str) -> str:
        # Use current_session budget for per-iteration tool result cap
        max_per_iter = self._current_session_budget_chars // 4  # 25% of session budget per iteration
        remaining = max_per_iter - self._current_iteration_tool_result_chars
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

    def current_session_used_tokens(self) -> int:
        """Tokens used by current session messages."""
        current_msgs = self.messages[self._current_session_start_index:]
        return sum(len(m.get("content") or "") for m in current_msgs) // _CHARS_PER_TOKEN

    def context_used_chars(self) -> int:
        return sum(len(m.get("content") or "") for m in self.messages)

    def context_pressure_ratio(self) -> float:
        """Legacy: overall context pressure as fraction of current_session budget."""
        if self._current_session_budget_chars <= 0:
            return 0.0
        current_msgs = self.messages[self._current_session_start_index:]
        used = sum(len(m.get("content") or "") for m in current_msgs)
        return used / self._current_session_budget_chars

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
            is_user_message = (
                getattr(m, "from_user_id", None) is not None
                or m.from_agent_id == user_agent_id
            )
            if not is_user_message:
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
