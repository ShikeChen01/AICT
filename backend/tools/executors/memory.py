"""Tool executors — memory: update_memory, read_history, list_sessions."""

from __future__ import annotations

from sqlalchemy import select

from backend.db.models import AgentMessage
from backend.tools.base import RunContext, parse_tool_uuid
from backend.tools.result import ToolExecutionError


async def run_compact_history(ctx: RunContext, tool_input: dict) -> str:
    """Signal that the agent wants to compact its context window.

    The actual truncation is performed by loop.py after this executor returns.
    This executor just validates input and returns an acknowledgment.
    """
    keep_recent = tool_input.get("keep_recent", 20)
    try:
        keep_recent = int(keep_recent)
    except (ValueError, TypeError):
        keep_recent = 20
    return f"Context compacted. Keeping {keep_recent} most recent messages in context."


async def run_update_memory(ctx: RunContext, tool_input: dict) -> str:
    content = tool_input.get("content")
    if not content:
        raise ToolExecutionError(
            "'content' is required (string).",
            error_code=ToolExecutionError.INVALID_INPUT,
            hint="Provide the memory text you want to persist in the 'content' field.",
        )
    ctx.agent.memory = {"content": str(content)}
    await ctx.db.flush()
    return "Memory updated."


async def run_read_history(ctx: RunContext, tool_input: dict) -> str:
    limit = int(tool_input.get("limit", 20))
    offset = int(tool_input.get("offset", 0))
    session_filter = parse_tool_uuid(tool_input, "session_id", required=False)

    if session_filter is not None:
        q = (
            select(AgentMessage)
            .where(AgentMessage.agent_id == ctx.agent.id)
            .where(AgentMessage.session_id == session_filter)
            .order_by(AgentMessage.created_at.asc())
            .limit(limit)
            .offset(offset)
        )
    else:
        q = (
            select(AgentMessage)
            .where(AgentMessage.agent_id == ctx.agent.id)
            .where(AgentMessage.session_id == ctx.session_id)
            .order_by(AgentMessage.created_at.desc())
            .limit(limit)
            .offset(offset)
        )

    res = await ctx.db.execute(q)
    rows = list(res.scalars().all())
    if not rows:
        return "No history."

    lines: list[str] = []
    current_session: object = None
    for m in rows:
        if m.session_id != current_session:
            current_session = m.session_id
            ts = m.created_at.strftime("%Y-%m-%d") if m.created_at else "unknown"
            lines.append(f"--- Session {m.session_id} (started {ts}) ---")
        ts_full = m.created_at.strftime("%Y-%m-%d %H:%M:%S") if m.created_at else ""
        lines.append(f"[session:{str(m.session_id)[:8]}] [{ts_full}] [{m.role}] {m.content}")

    return "\n".join(lines)


async def run_list_sessions(ctx: RunContext, tool_input: dict) -> str:
    from sqlalchemy import func

    from backend.db.models import AgentSession

    limit = int(tool_input.get("limit", 20))

    count_q = (
        select(AgentMessage.session_id, func.count(AgentMessage.id).label("msg_count"))
        .where(AgentMessage.agent_id == ctx.agent.id)
        .group_by(AgentMessage.session_id)
    )
    count_res = await ctx.db.execute(count_q)
    msg_counts: dict = {row[0]: row[1] for row in count_res.all()}

    sessions_q = (
        select(AgentSession)
        .where(AgentSession.agent_id == ctx.agent.id)
        .order_by(AgentSession.started_at.desc())
        .limit(limit)
    )
    sess_res = await ctx.db.execute(sessions_q)
    sessions = list(sess_res.scalars().all())

    if not sessions:
        return "No sessions."

    lines: list[str] = []
    for s in sessions:
        started = s.started_at.strftime("%Y-%m-%d %H:%M:%S") if s.started_at else "?"
        ended = s.ended_at.strftime("%Y-%m-%d %H:%M:%S") if s.ended_at else "running"
        count = msg_counts.get(s.id, 0)
        lines.append(f"{s.id} | {started} | {ended} | {s.status} | {count} messages")

    return "\n".join(lines)
