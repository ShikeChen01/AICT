"""First-class Agent abstraction.

An Agent encapsulates identity, prompt assembly, tool registry, LLM interaction,
and the wake-to-END loop. All agents are instances of the same class; behavior
differs by role via prompt blocks and tool configuration (DB-driven).

Relationship:
    AgentWorker (lifecycle orchestrator — wake/sleep/queue)
        → Agent (behavioral abstraction — owns metadata + loop)
            → PromptAssembly, tool dispatch, LLM calls
"""

from __future__ import annotations

import json as _json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agents.helpers import (
    MAX_ITERATIONS,
    MID_LOOP_MSG_CHECK_INTERVAL,
    assignment_message_for_agent,
    attach_images_to_prompt,
    default_model_for_agent,
    model_supports_vision,
    persist_tool_message,
    rate_limit_soft_pause,
    send_fallback_message,
)
from backend.core.constants import USER_AGENT_ID
from backend.db.models import Agent as AgentRecord, PromptBlockConfig, Repository
from backend.db.repositories.agent_templates import PromptBlockConfigRepository
from backend.db.repositories.attachments import AttachmentRepository
from backend.db.repositories.llm_usage import LLMUsageRepository
from backend.db.repositories.messages import AgentMessageRepository
from backend.db.repositories.project_secrets import ProjectSecretsRepository
from backend.db.repositories.project_settings import ProjectSettingsRepository
from backend.llm.contracts import ImagePart
from backend.llm.model_resolver import resolve_provider
from backend.llm.pricing import estimate_cost_usd
from backend.prompts.assembly import PromptAssembly
from backend.services.agent_service import AgentService
from backend.services.llm_service import LLMService
from backend.services.message_service import MessageService
from backend.services.session_service import SessionService
from backend.services.task_service import TaskService
from backend.tools.base import RunContext, ToolExecutor
from backend.tools.executors.sandbox import ScreenshotResult
from backend.tools.base import truncate_for_history
from backend.tools.loop_registry import (
    get_handlers_for_role,
    get_thinking_phase_handlers,
    get_thinking_phase_tool_defs,
    get_tool_defs_for_agent,
    truncate_tool_output,
    validate_tool_input,
)
from backend.websocket.manager import ws_manager
from backend.logging.my_logger import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Supporting dataclasses
# ---------------------------------------------------------------------------


@dataclass
class BudgetPolicy:
    """Project-scoped budget and rate-limit configuration. Mutable mid-session."""

    daily_token_budget: int = 0
    daily_cost_budget_usd: float = 0.0
    calls_per_hour_limit: int = 0
    tokens_per_hour_limit: int = 0


@dataclass
class SessionState:
    """Per-run mutable state. Created fresh for each agent.run() invocation."""

    session_id: UUID = None  # type: ignore[assignment]
    iteration: int = 0
    loopbacks: int = 0
    summarization_state: dict = field(
        default_factory=lambda: {"memory_injected": False, "history_injected": False}
    )
    thinking_stage: str | None = None  # None | "thinking" | "execution"


@dataclass
class EmitCallbacks:
    """WebSocket emission callbacks provided by the worker layer."""

    emit_text: Callable[[str], None] | None = None
    emit_tool_call: Callable[[str, dict], None] | None = None
    emit_tool_result: Callable[[str, str], None] | None = None
    emit_agent_message: Callable[[object], None] | None = None


@dataclass
class AgentServices:
    """Infrastructure services needed by the agent during a session."""

    message_service: MessageService
    session_service: SessionService
    task_service: TaskService
    agent_service: AgentService
    agent_msg_repo: AgentMessageRepository
    usage_repo: LLMUsageRepository
    ps_repo: ProjectSettingsRepository
    llm: LLMService


# ---------------------------------------------------------------------------
# Agent: first-class abstraction
# ---------------------------------------------------------------------------


class Agent:
    """First-class agent abstraction. Contains all metadata + owns the loop.

    Constructed per-session from DB records + injected infrastructure.
    The loop is a method of the Agent, not a standalone function.
    """

    def __init__(
        self,
        *,
        record: AgentRecord,
        project: Repository,
        db: AsyncSession,
        callbacks: EmitCallbacks,
        interrupt_flag: Callable[[], bool],
    ) -> None:
        # Live SQLAlchemy object (for mutations like memory updates)
        self._record = record
        self._project = project
        self._db = db
        self._callbacks = callbacks
        self._interrupt_flag = interrupt_flag

        # Initialized in _bootstrap(), not __init__
        self._prompt: PromptAssembly | None = None
        self._run_context: RunContext | None = None
        self._handlers: dict[str, ToolExecutor] = {}
        self._thinking_handlers: dict[str, ToolExecutor] | None = None
        self._block_configs: list[PromptBlockConfig] = []
        self._tool_defs: list[dict] = []
        self._resolved_model: str = ""
        self._resolved_provider: str = ""
        self._budget = BudgetPolicy()
        self._services: AgentServices | None = None
        self._agent_roster: dict[UUID, AgentRecord] = {}

        # Config sync flag (set by ConfigListener via LISTEN/NOTIFY)
        self._config_dirty: bool = False

    # ── Identity properties (from DB record) ──

    @property
    def id(self) -> UUID:
        return self._record.id

    @property
    def project_id(self) -> UUID:
        return self._record.project_id

    @property
    def role(self) -> str:
        return self._record.role

    @property
    def display_name(self) -> str:
        return self._record.display_name

    @property
    def model(self) -> str:
        return self._resolved_model

    @property
    def provider(self) -> str:
        return self._resolved_provider

    @property
    def thinking_enabled(self) -> bool:
        return getattr(self._record, "thinking_enabled", False)

    @property
    def memory(self) -> Any:
        return self._record.memory

    @property
    def token_allocations(self) -> dict | None:
        return getattr(self._record, "token_allocations", None)

    # ── MCP tool loading ──

    async def _load_mcp_handlers(self, db: AsyncSession, agent_id: UUID) -> None:
        """Register bridge executors for any enabled MCP tools on this agent.

        For every ToolConfig row with source='mcp' and enabled=True, we add a
        closure-wrapped version of run_mcp_tool to self._handlers keyed by the
        prefixed tool name (e.g. mcp__github__list_issues).

        The closure captures the tool name so the bridge executor can look up
        the correct McpServerConfig at call time.
        """
        from backend.tools.executors.mcp_bridge import run_mcp_tool
        from backend.db.models import ToolConfig

        result = await db.execute(
            select(ToolConfig).where(
                ToolConfig.agent_id == agent_id,
                ToolConfig.source == "mcp",
                ToolConfig.enabled.is_(True),
            )
        )
        mcp_tools = list(result.scalars().all())

        def _make_handler(captured_name: str) -> ToolExecutor:
            """Factory that captures tool_name to avoid loop-variable closure pitfall."""
            async def handler(ctx: RunContext, tool_input: dict) -> str:
                ctx._current_mcp_tool_name = captured_name  # type: ignore[attr-defined]
                try:
                    return await run_mcp_tool(ctx, tool_input)
                finally:
                    if hasattr(ctx, "_current_mcp_tool_name"):
                        del ctx._current_mcp_tool_name
            return handler

        for tc in mcp_tools:
            self._handlers[tc.tool_name] = _make_handler(tc.tool_name)

        if mcp_tools:
            logger.info(
                "Agent %s: loaded %d MCP tool handlers",
                agent_id, len(mcp_tools),
            )

    # ── Config sync (LISTEN/NOTIFY) ──

    def mark_config_dirty(self) -> None:
        """Set by ConfigListener when PostgreSQL NOTIFY fires for this agent."""
        self._config_dirty = True

    async def _maybe_reload_config(self) -> None:
        """Check dirty flag and reload from DB if needed."""
        if not self._config_dirty:
            return
        self._config_dirty = False
        await self._reload_config()

    async def _reload_config(self) -> None:
        """Re-read agent config from DB and rebuild prompt/tools.

        Called when LISTEN/NOTIFY signals a config change mid-session.
        """
        db = self._db

        # Refresh the agent record from DB
        await db.refresh(self._record)

        # Re-resolve model and provider
        self._resolved_model = self._record.model or default_model_for_agent(self._record)
        self._resolved_provider = resolve_provider(self._record.provider, self._resolved_model)

        # Reload prompt block configs
        block_repo = PromptBlockConfigRepository(db)
        self._block_configs = await block_repo.list_for_agent(self._record.id)

        # Reload tool definitions from DB (includes both native and MCP tools)
        self._tool_defs = await get_tool_defs_for_agent(self._record.id, self._record.role, db)
        self._handlers = get_handlers_for_role(self._record.role)
        await self._load_mcp_handlers(db, self._record.id)

        # Reload budget/rate-limit settings
        ps = await self._services.ps_repo.get_by_project(self._project.id)
        self._budget = BudgetPolicy(
            daily_token_budget=(ps.daily_token_budget or 0) if ps else 0,
            daily_cost_budget_usd=(ps.daily_cost_budget_usd or 0.0) if ps else 0.0,
            calls_per_hour_limit=(ps.calls_per_hour_limit or 0) if ps else 0,
            tokens_per_hour_limit=(ps.tokens_per_hour_limit or 0) if ps else 0,
        )

        # Rebuild system prompt with updated blocks + memory
        memory_content = self._record.memory
        if isinstance(memory_content, dict):
            memory_content = _json.dumps(memory_content) if memory_content else None
        if self._prompt is not None:
            self._prompt._refresh_memory_in_system_prompt(
                memory_content, self._block_configs, None
            )
            # Update tool defs on the prompt assembly
            self._prompt.tools = self._tool_defs

        logger.info(
            "Agent %s: config reloaded from DB (model=%s, %d blocks, %d tools)",
            self._record.id, self._resolved_model,
            len(self._block_configs), len(self._tool_defs),
        )

    # ── Lifecycle: the main run loop ──

    async def run(
        self,
        session_id: UUID,
        trigger_message_id: UUID | None = None,
    ) -> str:
        """Execute the wake-to-END loop for one agent session.

        Returns an end reason string: "normal_end", "interrupted",
        "max_iterations", "max_loopbacks", "budget_exhausted",
        "cost_budget_exhausted", "rate_limited_timeout", or "error".
        """
        early_exit = await self._bootstrap(session_id, trigger_message_id)
        if early_exit:
            return early_exit

        session = SessionState(
            session_id=session_id,
            thinking_stage="thinking" if self.thinking_enabled else None,
        )

        # Check summarization at session start (loaded history may already be near budget)
        self._check_and_inject_summarization(session)

        # Main loop: each iteration = one LLM call, then optional tool execution
        while session.iteration < MAX_ITERATIONS:
            end_reason = await self._run_iteration(session)
            if end_reason is not None:
                return end_reason

        # Fell through: hit MAX_ITERATIONS (safeguard)
        logger.warning(
            "Agent %s hit max_iterations (%d) in session %s",
            self._record.id, MAX_ITERATIONS, session_id,
        )
        await self._services.session_service.end_session_force(session_id, "max_iterations")
        await send_fallback_message(
            self._services.message_service,
            self._record,
            self._project.id,
            "My session exceeded the maximum number of iterations and was ended automatically. "
            "Please send a new message to continue.",
            self._callbacks.emit_agent_message,
        )
        return "max_iterations"

    # ── Bootstrap ──

    async def _bootstrap(
        self,
        session_id: UUID,
        trigger_message_id: UUID | None,
    ) -> str | None:
        """One-time session setup. Returns early_exit reason or None."""
        db = self._db
        record = self._record
        project = self._project

        # Initialize services
        message_service = MessageService(db)
        session_service = SessionService(db)
        task_service = TaskService(db)
        agent_service = AgentService(db)
        agent_msg_repo = AgentMessageRepository(db)
        block_repo = PromptBlockConfigRepository(db)
        llm = LLMService()

        self._services = AgentServices(
            message_service=message_service,
            session_service=session_service,
            task_service=task_service,
            agent_service=agent_service,
            agent_msg_repo=agent_msg_repo,
            usage_repo=LLMUsageRepository(db),
            ps_repo=ProjectSettingsRepository(db),
            llm=llm,
        )

        self._handlers = get_handlers_for_role(record.role)

        # Load MCP bridge handlers for any enabled MCP tools on this agent.
        await self._load_mcp_handlers(db, record.id)

        # Require either unread messages or an assigned task
        unread = await message_service.get_unread_for_agent(record.id)
        assignment_context = None
        if not unread:
            assignment_context = await assignment_message_for_agent(db, record)
            if not assignment_context:
                await session_service.end_session(
                    session_id, end_reason="normal_end", status="completed"
                )
                return "normal_end"
        else:
            await message_service.mark_received([m.id for m in unread])

        # Build agent roster for message formatting
        result = await db.execute(
            select(AgentRecord).where(AgentRecord.project_id == project.id)
        )
        project_agents = list(result.scalars().all())
        self._agent_roster = {a.id: a for a in project_agents}

        # Format incoming messages
        new_messages_text = PromptAssembly.format_incoming_messages(
            unread, self._agent_roster, USER_AGENT_ID, assignment_context,
        )

        # Load image attachments
        attachment_repo = AttachmentRepository(db)
        unread_ids = [m.id for m in unread if m.id is not None]
        attachments_by_msg = await attachment_repo.get_for_messages(unread_ids)

        # Resolve memory
        memory_content = record.memory
        if isinstance(memory_content, dict):
            memory_content = _json.dumps(memory_content) if memory_content else None

        # Load project settings (budget/rate limits)
        project_settings = await self._services.ps_repo.get_by_project(project.id)
        self._budget = BudgetPolicy(
            daily_token_budget=(project_settings.daily_token_budget or 0) if project_settings else 0,
            daily_cost_budget_usd=(project_settings.daily_cost_budget_usd or 0.0) if project_settings else 0.0,
            calls_per_hour_limit=(project_settings.calls_per_hour_limit or 0) if project_settings else 0,
            tokens_per_hour_limit=(project_settings.tokens_per_hour_limit or 0) if project_settings else 0,
        )

        # Load project secrets
        from backend.config import settings as app_settings
        secrets_repo = ProjectSecretsRepository(db, encryption_key=app_settings.secret_encryption_key)
        project_secrets = await secrets_repo.get_plaintext_values(project.id)

        # Resolve model and provider
        self._resolved_model = record.model or default_model_for_agent(record)
        self._resolved_provider = resolve_provider(record.provider, self._resolved_model)

        # Determine thinking stage
        thinking_stage: str | None = "thinking" if self.thinking_enabled else None

        # Load prompt block configs from DB
        self._block_configs = await block_repo.list_for_agent(record.id)

        # Load DB-customized tool defs
        self._tool_defs = await get_tool_defs_for_agent(record.id, record.role, db)

        # Build prompt assembly
        if self.thinking_enabled:
            pa = PromptAssembly(
                record, project, memory_content,
                block_configs=self._block_configs,
                model=self._resolved_model,
                thinking_stage="thinking",
                project_secrets=project_secrets,
            )
            pa.tools = get_thinking_phase_tool_defs(record.role)
            self._thinking_handlers = get_thinking_phase_handlers()
            logger.info("Agent %s: thinking_enabled=True — starting Stage 1 (thinking)", record.id)
        else:
            pa = PromptAssembly(
                record, project, memory_content,
                block_configs=self._block_configs,
                model=self._resolved_model,
                thinking_stage=None,
                project_secrets=project_secrets,
            )
            pa.tools = self._tool_defs
            self._thinking_handlers = None

        self._prompt = pa

        # Load history (past sessions + current session)
        past_session_msgs = await agent_msg_repo.list_past_session_history(
            record.id, session_id,
            budget_tokens=pa._past_session_budget_tokens,
        )
        current_session_msgs = await agent_msg_repo.list_current_session(
            record.id, session_id,
        )
        pa.load_history(
            past_session_msgs,
            current_session_msgs,
            new_messages_text,
            known_tool_names=set(self._handlers.keys()) | {"thinking_done", "compact_history"},
        )

        # Attach images from message attachments
        if attachments_by_msg and new_messages_text:
            attach_images_to_prompt(pa, unread, attachments_by_msg, self._resolved_model, record)

        # Persist the initial user turn
        if new_messages_text:
            await agent_msg_repo.create_message(
                agent_id=record.id,
                project_id=project.id,
                role="user",
                content=new_messages_text,
                loop_iteration=0,
                session_id=session_id,
            )

        # Build RunContext for tool executors
        self._run_context = RunContext(
            db=db,
            agent=record,
            project=project,
            session_id=session_id,
            message_service=message_service,
            session_service=session_service,
            task_service=task_service,
            agent_service=agent_service,
            agent_msg_repo=agent_msg_repo,
            emit_agent_message=self._callbacks.emit_agent_message,
        )

        logger.info(
            "Agent %s (%s) session %s started: unread=%d",
            record.id, record.role, session_id, len(unread),
        )

        return None

    # ── Single iteration ──

    async def _run_iteration(self, session: SessionState) -> str | None:
        """Execute one loop iteration: LLM call + tool dispatch.

        Returns end_reason if session should stop, None to continue.
        """
        svc = self._services
        pa = self._prompt

        if self._interrupt_flag():
            await svc.session_service.end_session_force(session.session_id, "interrupted")
            return "interrupted"

        # Mid-loop: periodically pull new channel messages and check config reload
        if session.iteration > 0 and session.iteration % MID_LOOP_MSG_CHECK_INTERVAL == 0:
            await self._inject_mid_loop_messages(session)
            await self._maybe_reload_config()

        # Summarization pressure check
        self._check_and_inject_summarization(session)

        # Budget/rate-limit gates
        gate_result = await self._check_budget_gates(session)
        if gate_result is not None:
            return gate_result

        # Expire tool results from previous iterations so the LLM only ever
        # sees the *most recent* batch of tool results in full.  Older ones
        # are replaced with a short truncated summary.
        self._expire_previous_tool_results()

        # Call LLM
        content, tool_calls, llm_response = await self._call_llm()
        if content is None and tool_calls is None:
            return "error"  # _call_llm handles error logging

        # Record token usage and broadcast
        await self._record_usage(llm_response, session)

        session.iteration += 1
        await svc.session_service.increment_iteration(session.session_id)

        # Persist assistant turn
        assistant_tool_input = {"__tool_calls__": tool_calls} if tool_calls else None
        await svc.agent_msg_repo.create_message(
            agent_id=self._record.id,
            project_id=self._project.id,
            role="assistant",
            content=content or "",
            loop_iteration=session.iteration,
            session_id=session.session_id,
            tool_input=assistant_tool_input,
        )
        if content and self._callbacks.emit_text:
            self._callbacks.emit_text(content)
        pa.append_assistant(content or "", tool_calls)

        # No tool calls: treat a text response as a valid completion.
        if not tool_calls:
            return await self._handle_loopback(session)

        session.loopbacks = 0
        return await self._dispatch_tool_calls(tool_calls, session)

    # ── LLM call ──

    async def _call_llm(self) -> tuple[str | None, list[dict] | None, Any]:
        """Call the LLM with current prompt context.

        Returns (content, tool_calls, llm_response) or (None, None, None) on error.
        """
        from backend.config import settings as app_settings

        try:
            content, tool_calls, llm_response = await self._services.llm.chat_completion_with_tools(
                model=self._resolved_model,
                system_prompt=self._prompt.system_prompt,
                messages=self._prompt.messages,
                tools=self._prompt.tools,
                max_tokens=app_settings.llm_max_tokens_agent_loop,
            )
            return content, tool_calls, llm_response
        except Exception as exc:
            logger.exception("LLM call failed for agent %s: %s", self._record.id, exc)
            await self._services.session_service.end_session_error(
                self._run_context.session_id
            )
            await send_fallback_message(
                self._services.message_service,
                self._record,
                self._project.id,
                f"I encountered an error processing your request and could not respond. "
                f"Error: {type(exc).__name__}: {str(exc)[:200]}",
                self._callbacks.emit_agent_message,
            )
            return None, None, None

    # ── Usage recording ──

    async def _record_usage(self, llm_response, session: SessionState) -> None:
        """Record token usage and broadcast usage event via WebSocket."""
        effective_model = llm_response.model or self._resolved_model
        effective_provider = llm_response.provider or "unknown"

        try:
            await self._services.usage_repo.record(
                project_id=self._project.id,
                agent_id=self._record.id,
                session_id=session.session_id,
                provider=effective_provider,
                model=effective_model,
                input_tokens=llm_response.input_tokens,
                output_tokens=llm_response.output_tokens,
                request_id=llm_response.request_id,
            )
        except Exception as exc:
            logger.warning("Failed to record LLM usage event: %s", exc)

        try:
            call_cost = estimate_cost_usd(
                effective_model,
                llm_response.input_tokens,
                llm_response.output_tokens,
            )
            await ws_manager.broadcast_usage_update(
                project_id=self._project.id,
                agent_id=self._record.id,
                model=effective_model,
                provider=effective_provider,
                input_tokens=llm_response.input_tokens,
                output_tokens=llm_response.output_tokens,
                estimated_cost_usd=round(call_cost, 6),
                created_at=datetime.now(timezone.utc).isoformat(),
            )
        except Exception as exc:
            logger.warning("Failed to broadcast usage_update event: %s", exc)

    # ── Loopback handling ──

    async def _handle_loopback(self, session: SessionState) -> str | None:
        """Handle assistant responses without tool calls as normal completion."""
        session.loopbacks = 0
        await self._services.session_service.end_session(
            session.session_id,
            end_reason="normal_end",
            status="completed",
        )
        return "normal_end"

    # ── Ephemeral tool result expiry ──

    def _expire_previous_tool_results(self) -> None:
        """Replace full tool results from earlier iterations with truncated summaries.

        Tool results are ephemeral: the agent sees the full output for exactly
        one LLM call (the iteration immediately after tool execution).  On the
        *next* iteration the results are truncated to MAX_TOOL_RESULT_HISTORY_CHARS
        so they no longer consume context budget.

        The mechanism is simple: every tool-role message that was already present
        *before* the most recent assistant message is considered "seen" and gets
        truncated.  Tool-role messages that come *after* the last assistant
        message are the freshly appended results from the previous iteration's
        tool execution — those stay intact for the upcoming LLM call.
        """
        # Find the index of the last assistant message
        last_assistant_idx = -1
        for i in range(len(self._prompt.messages) - 1, -1, -1):
            if self._prompt.messages[i].get("role") == "assistant":
                last_assistant_idx = i
                break

        if last_assistant_idx < 0:
            return  # no assistant message yet — nothing to expire

        expired_count = 0
        for i in range(last_assistant_idx):  # everything *before* last assistant
            msg = self._prompt.messages[i]
            if msg.get("role") != "tool":
                continue
            content = msg.get("content", "")
            truncated = truncate_for_history(content)
            if truncated != content:
                self._prompt.messages[i] = {**msg, "content": truncated}
                expired_count += 1

        if expired_count:
            logger.debug(
                "Agent %s: expired %d tool result(s) from earlier iterations",
                self._record.id,
                expired_count,
            )

    # ── Tool dispatch ──

    async def _dispatch_tool_calls(
        self,
        tool_calls: list[dict],
        session: SessionState,
    ) -> str | None:
        """Route tool calls: thinking_done, end, or regular tools."""
        pa = self._prompt

        # thinking_done handling: stage transition (Stage 1 → Stage 2)
        thinking_done_calls = [tc for tc in tool_calls if tc.get("name") == "thinking_done"]
        if thinking_done_calls and self.thinking_enabled and session.thinking_stage == "thinking":
            tool_calls = await self._handle_thinking_transition(
                thinking_done_calls[0], tool_calls, session,
            )
            if not tool_calls:
                return None  # continue to next iteration

        # Rule: END must be called alone
        end_calls = [tc for tc in tool_calls if tc.get("name") == "end"]
        non_end_calls = [tc for tc in tool_calls if tc.get("name") not in ("end", "thinking_done")]

        if end_calls and non_end_calls:
            await self._handle_end_solo_warning(end_calls, session)

        # Execute each non-END tool
        if non_end_calls:
            pending_screenshot_parts = await self._execute_tool_batch(non_end_calls, session)

            # Inject pending screenshot images
            if pending_screenshot_parts:
                for _i in range(len(pa.messages) - 1, -1, -1):
                    if pa.messages[_i].get("role") == "tool":
                        pa.messages[_i]["image_parts"] = pending_screenshot_parts
                        break
                logger.info(
                    "Agent %s: injected %d screenshot image_part(s) into conversation",
                    self._record.id, len(pending_screenshot_parts),
                )

        # Agent called only END: end session normally
        if end_calls and not non_end_calls:
            end_text = "Session ended."
            if self._callbacks.emit_tool_result:
                self._callbacks.emit_tool_result("end", end_text)
            await persist_tool_message(
                self._services.agent_msg_repo, self._record.id, self._project.id,
                session.session_id, session.iteration, "end", "", {}, end_text,
            )
            await self._services.session_service.end_session(
                session.session_id, end_reason="normal_end", status="completed"
            )
            return "normal_end"

        return None  # continue to next iteration

    # ── Tool execution ──

    async def _execute_tool_batch(
        self,
        non_end_calls: list[dict],
        session: SessionState,
    ) -> list[ImagePart]:
        """Execute all non-END tool calls, persist results, return pending screenshot parts."""
        active_handlers = (
            self._thinking_handlers
            if (self.thinking_enabled and session.thinking_stage == "thinking")
            else self._handlers
        )
        pending_screenshot_parts: list[ImagePart] = []

        for tc in non_end_calls:
            name = tc.get("name", "")
            tool_input = tc.get("input") or {}
            if self._callbacks.emit_tool_call:
                self._callbacks.emit_tool_call(name, tool_input)

            tool_use_id = tc.get("id", "")
            try:
                handler = active_handlers.get(name)
                if handler is None:
                    raise RuntimeError(f"Unknown tool '{name}'")
                validate_tool_input(name, tool_input)
                raw_result = await handler(self._run_context, tool_input)
            except Exception as exc:
                result_text = truncate_tool_output(f"Tool '{name}' failed: {exc}")
                self._prompt.append_tool_error(name, exc, tool_use_id)
                if self._callbacks.emit_tool_result:
                    self._callbacks.emit_tool_result(name, result_text)
                await persist_tool_message(
                    self._services.agent_msg_repo, self._record.id, self._project.id,
                    session.session_id, session.iteration, name, tool_use_id, tool_input, result_text,
                )
                continue

            # Handle ScreenshotResult
            if isinstance(raw_result, ScreenshotResult):
                result_text = f"Screenshot captured ({len(raw_result.image_bytes)} bytes). The image is attached below for your inspection."
                if model_supports_vision(self._resolved_model):
                    pending_screenshot_parts.append(
                        ImagePart(data=raw_result.image_bytes, media_type=raw_result.media_type)
                    )
                else:
                    result_text += (
                        f"\n[Warning: model '{self._resolved_model}' does not support vision. "
                        "You cannot view the screenshot. Consider using a vision-capable model.]"
                    )
            else:
                result_text = truncate_tool_output(raw_result)

            if self._callbacks.emit_tool_result:
                self._callbacks.emit_tool_result(name, result_text)
            self._prompt.append_tool_result(name, result_text, tool_use_id)

            # Post-tool hooks
            if name == "update_memory":
                self._enforce_memory_budget(session)

            if name == "compact_history":
                keep_recent = tool_input.get("keep_recent", 20)
                self._prompt.compact_messages(keep_recent=keep_recent)
                session.summarization_state["history_injected"] = False

            await persist_tool_message(
                self._services.agent_msg_repo, self._record.id, self._project.id,
                session.session_id, session.iteration, name, tool_use_id, tool_input, result_text,
            )

        return pending_screenshot_parts

    # ── Budget gates ──

    async def _check_budget_gates(self, session: SessionState) -> str | None:
        """Check all budget/rate-limit gates before an LLM call.

        Returns an end-reason string if the session must stop, or None if all clear.
        """
        svc = self._services
        budget = self._budget

        # Gate 1: daily token budget — hard stop
        if budget.daily_token_budget > 0:
            tokens_today = await svc.usage_repo.daily_tokens_for_project(self._project.id)
            if tokens_today >= budget.daily_token_budget:
                logger.warning(
                    "Agent %s: daily token budget (%d) exhausted (%d used) — ending session",
                    self._record.id, budget.daily_token_budget, tokens_today,
                )
                await svc.session_service.end_session_force(session.session_id, "budget_exhausted")
                await send_fallback_message(
                    svc.message_service, self._record, self._project.id,
                    f"This project's daily token budget ({budget.daily_token_budget:,} tokens) has been "
                    "reached. Agents will resume after midnight UTC.",
                    self._callbacks.emit_agent_message,
                )
                return "budget_exhausted"

        # Gate 2: daily cost budget — hard stop
        if budget.daily_cost_budget_usd > 0:
            cost_today = await svc.usage_repo.daily_cost_usd_for_project(self._project.id)
            if cost_today >= budget.daily_cost_budget_usd:
                logger.warning(
                    "Agent %s: daily cost budget ($%.4f) exhausted ($%.4f used) — ending session",
                    self._record.id, budget.daily_cost_budget_usd, cost_today,
                )
                await svc.session_service.end_session_force(session.session_id, "cost_budget_exhausted")
                await send_fallback_message(
                    svc.message_service, self._record, self._project.id,
                    f"This project's daily cost budget (${budget.daily_cost_budget_usd:.2f}) has been "
                    f"reached (${cost_today:.4f} spent today). Agents will resume after midnight UTC.",
                    self._callbacks.emit_agent_message,
                )
                return "cost_budget_exhausted"

        # Gate 3: hourly rate limits — soft pause
        if budget.calls_per_hour_limit > 0 or budget.tokens_per_hour_limit > 0:
            hourly = await svc.usage_repo.hourly_stats(self._project.id)
            calls_over = budget.calls_per_hour_limit > 0 and hourly["calls"] >= budget.calls_per_hour_limit
            tokens_over = budget.tokens_per_hour_limit > 0 and hourly["tokens"] >= budget.tokens_per_hour_limit
            if calls_over or tokens_over:
                end_reason, fresh_limits = await rate_limit_soft_pause(
                    usage_repo=svc.usage_repo,
                    ps_repo=svc.ps_repo,
                    project_id=self._project.id,
                    agent_id=self._record.id,
                    interrupt_flag=self._interrupt_flag,
                )
                if end_reason == "interrupted":
                    await svc.session_service.end_session_force(session.session_id, "interrupted")
                    return "interrupted"
                if end_reason == "rate_limited_timeout":
                    await svc.session_service.end_session_force(session.session_id, "rate_limited_timeout")
                    await send_fallback_message(
                        svc.message_service, self._record, self._project.id,
                        "The project's hourly rate limit was not cleared within 10 minutes. "
                        "Please raise the limit in Project Settings and send a new message.",
                        self._callbacks.emit_agent_message,
                    )
                    return "rate_limited_timeout"
                # Limits cleared or user relaxed them — refresh local limit vars
                if fresh_limits:
                    self._budget.calls_per_hour_limit = fresh_limits.get("calls_per_hour_limit", budget.calls_per_hour_limit)
                    self._budget.tokens_per_hour_limit = fresh_limits.get("tokens_per_hour_limit", budget.tokens_per_hour_limit)
                    self._budget.daily_token_budget = fresh_limits.get("daily_token_budget", budget.daily_token_budget)
                    self._budget.daily_cost_budget_usd = fresh_limits.get("daily_cost_budget_usd", budget.daily_cost_budget_usd)

        return None

    # ── Summarization ──

    def _check_and_inject_summarization(self, session: SessionState) -> None:
        """Check each dynamic section independently and inject appropriate prompts."""
        pa = self._prompt
        triggered = pa.check_summarization_triggers()

        if "memory" in triggered and not session.summarization_state["memory_injected"]:
            logger.info(
                "Agent %s: memory pressure — injecting memory summarization",
                self._record.id,
            )
            mem_content = next(
                (b.content for b in self._block_configs if b.block_key == "summarization_memory" and b.enabled),
                (
                    "Your working memory is approaching its budget limit. Compress your memory "
                    "using update_memory: merge related items, remove redundant entries, "
                    "keep only actively relevant context. Call update_memory then continue your work."
                ),
            )
            pa.append_summarization(mem_content)
            session.summarization_state["memory_injected"] = True

        if "current_session" in triggered and not session.summarization_state["history_injected"]:
            logger.info(
                "Agent %s: session pressure %.0f%% — injecting history summarization",
                self._record.id,
                pa.context_pressure_ratio() * 100,
            )
            hist_content = next(
                (b.content for b in self._block_configs if b.block_key == "summarization_history" and b.enabled),
                next(
                    (b.content for b in self._block_configs if b.block_key == "summarization" and b.enabled),
                    PromptAssembly.get_summarization_block(),
                ),
            )
            pa.append_summarization(hist_content)
            session.summarization_state["history_injected"] = True

    # ── Mid-loop messages ──

    async def _inject_mid_loop_messages(self, session: SessionState) -> None:
        """Check for new channel messages mid-loop and inject them into the prompt."""
        svc = self._services
        mid_loop_unread = await svc.message_service.get_unread_for_agent(self._record.id)
        if not mid_loop_unread:
            return
        await svc.message_service.mark_received([m.id for m in mid_loop_unread])
        mid_loop_text = PromptAssembly.format_incoming_messages(
            mid_loop_unread, self._agent_roster, USER_AGENT_ID
        )
        capped = self._prompt._cap_incoming_messages(mid_loop_text)
        self._prompt.messages.append({"role": "user", "content": capped})
        await svc.agent_msg_repo.create_message(
            agent_id=self._record.id,
            project_id=self._project.id,
            role="user",
            content=capped,
            loop_iteration=session.iteration,
            session_id=session.session_id,
        )
        logger.info(
            "Agent %s mid-loop: injected %d new message(s) at iteration %d",
            self._record.id, len(mid_loop_unread), session.iteration,
        )

    # ── Thinking phase transition ──

    async def _handle_thinking_transition(
        self,
        thinking_done_call: dict,
        tool_calls: list[dict],
        session: SessionState,
    ) -> list[dict]:
        """Process thinking_done tool call: persist result, rebuild prompt for Stage 2.

        Returns the tool_calls list with thinking_done calls removed.
        """
        td_id = thinking_done_call.get("id", "thinking-done-transition")
        td_summary = (thinking_done_call.get("input") or {}).get("summary", "Plan saved to memory.")
        result_text = f"Thinking phase complete. Transitioning to execution phase.\nPlan summary: {td_summary}"

        self._prompt.append_tool_result("thinking_done", result_text, td_id)
        await persist_tool_message(
            self._services.agent_msg_repo, self._record.id, self._project.id,
            session.session_id, session.iteration, "thinking_done", td_id,
            thinking_done_call.get("input") or {}, result_text,
        )
        if self._callbacks.emit_tool_result:
            self._callbacks.emit_tool_result("thinking_done", result_text)

        # Rebuild for Stage 2
        session.thinking_stage = "execution"
        memory_content = self._record.memory
        if isinstance(memory_content, dict):
            memory_content = _json.dumps(memory_content) if memory_content else None
        self._prompt.rebuild_for_execution_stage(self._block_configs, memory_content)
        self._prompt.tools = self._tool_defs
        logger.info("Agent %s: thinking_done called — entering Stage 2 (execution)", self._record.id)

        return [tc for tc in tool_calls if tc.get("name") != "thinking_done"]

    # ── END solo warning ──

    async def _handle_end_solo_warning(
        self,
        end_calls: list[dict],
        session: SessionState,
    ) -> None:
        """Inject warning when END was called alongside other tools."""
        for ec in end_calls:
            end_use_id = ec.get("id") or "end-solo-rule"
            end_solo_content = (
                "END was called alongside other tools in the same response and was ignored "
                "for this iteration. END must always be called alone. If you have remaining "
                "work, complete it first. Then call END by itself in a separate response."
            )
            self._prompt.append_end_solo_warning(end_solo_content, end_use_id)
            await persist_tool_message(
                self._services.agent_msg_repo, self._record.id, self._project.id,
                session.session_id, session.iteration, "end", end_use_id, {}, end_solo_content,
            )

    # ── Memory budget enforcement ──

    def _enforce_memory_budget(self, session: SessionState) -> None:
        """Enforce memory budget after an update_memory call and refresh the system prompt."""
        raw_memory = self._record.memory
        if isinstance(raw_memory, dict):
            mem_str = raw_memory.get("content", "") if raw_memory else ""
        elif isinstance(raw_memory, str):
            mem_str = raw_memory
        else:
            mem_str = ""

        mem_budget_chars = self._prompt._memory_budget_chars
        if len(mem_str) > mem_budget_chars:
            mem_str = mem_str[:mem_budget_chars] + "\n[Memory truncated to budget limit]"
            self._record.memory = {"content": mem_str}
            logger.warning(
                "Agent %s: memory exceeded budget (%d chars) — truncated to %d chars",
                self._record.id, len(mem_str), mem_budget_chars,
            )

        mem_now = self._record.memory
        if isinstance(mem_now, dict):
            mem_now = _json.dumps(mem_now) if mem_now else None
        self._prompt._refresh_memory_in_system_prompt(
            mem_now, self._block_configs, session.thinking_stage
        )
        session.summarization_state["memory_injected"] = False
