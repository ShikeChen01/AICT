"""
Deep diagnostics endpoint for debugging agent issues.

Checks worker health, agent state, message queue, session history,
and validates LLM message history for Anthropic API compliance.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.auth import get_current_user
from backend.db.models import Agent, AgentMessage, AgentSession, ChannelMessage, Repository, User
from backend.db.session import get_db

router = APIRouter(prefix="/health", tags=["diagnostics"])


async def _get_project(db: AsyncSession, project_id: UUID, user: User | None) -> Repository:
    q = select(Repository).where(Repository.id == project_id)
    if isinstance(user, User):
        q = q.where((Repository.owner_id == user.id) | (Repository.owner_id.is_(None)))
    result = await db.execute(q)
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def _validate_llm_messages(rows: list[AgentMessage]) -> list[dict]:
    """Validate a sequence of agent_messages for Anthropic API compliance.

    Returns a list of issue dicts: {severity, rule, detail, message_id, index}.
    """
    issues: list[dict] = []

    issued_tool_use_ids: set[str] = set()
    pending_tool_use_ids: set[str] = set()
    prev_role: str | None = None

    for idx, row in enumerate(rows):
        msg_id = str(row.id)
        role = row.role

        if role == "assistant":
            tool_calls = (row.tool_input or {}).get("__tool_calls__") if row.tool_input else None
            if tool_calls:
                for tc in tool_calls:
                    if isinstance(tc, dict):
                        tc_id = tc.get("id", "")
                        if tc_id:
                            issued_tool_use_ids.add(tc_id)
                            pending_tool_use_ids.add(tc_id)

        elif role == "tool":
            tool_use_id = (row.tool_input or {}).get("__tool_use_id__") if row.tool_input else None
            if tool_use_id and tool_use_id in pending_tool_use_ids:
                pending_tool_use_ids.discard(tool_use_id)
            elif tool_use_id and tool_use_id not in issued_tool_use_ids:
                issues.append({
                    "severity": "warning",
                    "rule": "orphan_tool_result",
                    "detail": f"tool_result references tool_use_id={tool_use_id!r} "
                              f"which was never issued by an assistant message",
                    "message_id": msg_id,
                    "index": idx,
                })

        if prev_role is not None and role == prev_role and role in ("user", "assistant"):
            issues.append({
                "severity": "error",
                "rule": "consecutive_same_role",
                "detail": f"Consecutive {role!r} messages at index {idx-1} and {idx}",
                "message_id": msg_id,
                "index": idx,
            })

        prev_role = role

    if pending_tool_use_ids:
        for dangling_id in pending_tool_use_ids:
            issues.append({
                "severity": "error",
                "rule": "dangling_tool_use",
                "detail": f"tool_use id={dangling_id!r} was issued but never got a "
                          f"matching tool_result — this WILL cause Anthropic 400",
                "message_id": None,
                "index": None,
            })

    return issues


@router.get("/diagnose/{project_id}")
async def diagnose_project(
    project_id: UUID,
    current_user: User | None = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Deep diagnostic for a project. Checks every agent's:
    - Worker registration status
    - Agent DB state (status, model, current_task)
    - Pending (unread) channel messages
    - Last session outcome
    - LLM message history validation (Anthropic 400 detection)
    """
    project = await _get_project(db, project_id, current_user)

    from backend.workers.worker_manager import get_worker_manager
    wm = get_worker_manager()
    wm_status = wm.get_status()
    registered_ids = set(wm_status.get("agent_ids", []))

    result = await db.execute(
        select(Agent).where(Agent.project_id == project_id).order_by(Agent.role)
    )
    agents = list(result.scalars().all())
    if not agents:
        return {
            "project_id": str(project_id),
            "project_name": project.name,
            "worker_manager": wm_status,
            "agents": [],
            "summary": "No agents found for this project.",
        }

    agent_ids = [a.id for a in agents]

    pending_counts_result = await db.execute(
        select(ChannelMessage.target_agent_id, func.count(ChannelMessage.id))
        .where(ChannelMessage.target_agent_id.in_(agent_ids))
        .where(ChannelMessage.status == "sent")
        .group_by(ChannelMessage.target_agent_id)
    )
    pending_counts: dict[UUID, int] = dict(pending_counts_result.all())

    pending_msgs_result = await db.execute(
        select(ChannelMessage)
        .where(ChannelMessage.target_agent_id.in_(agent_ids))
        .where(ChannelMessage.status == "sent")
        .order_by(ChannelMessage.created_at.desc())
        .limit(20)
    )
    pending_msgs = list(pending_msgs_result.scalars().all())
    pending_msgs_by_agent: dict[UUID, list] = {}
    for m in pending_msgs:
        pending_msgs_by_agent.setdefault(m.target_agent_id, []).append({
            "id": str(m.id),
            "from": str(m.from_agent_id),
            "content_preview": (m.content or "")[:120],
            "created_at": str(m.created_at),
        })

    agent_reports = []
    critical_issues = []

    for agent in agents:
        aid_str = str(agent.id)
        has_worker = aid_str in registered_ids

        last_session_result = await db.execute(
            select(AgentSession)
            .where(AgentSession.agent_id == agent.id)
            .order_by(AgentSession.started_at.desc())
            .limit(1)
        )
        last_session = last_session_result.scalar_one_or_none()

        last_session_info = None
        llm_validation = None
        if last_session:
            last_session_info = {
                "id": str(last_session.id),
                "status": last_session.status,
                "end_reason": last_session.end_reason,
                "iteration_count": last_session.iteration_count,
                "started_at": str(last_session.started_at),
                "ended_at": str(last_session.ended_at) if last_session.ended_at else None,
            }

            history_result = await db.execute(
                select(AgentMessage)
                .where(AgentMessage.agent_id == agent.id)
                .where(AgentMessage.session_id == last_session.id)
                .order_by(AgentMessage.created_at.asc())
                .limit(500)
            )
            history_rows = list(history_result.scalars().all())
            validation_issues = _validate_llm_messages(history_rows)

            role_counts: dict[str, int] = {}
            for h in history_rows:
                role_counts[h.role] = role_counts.get(h.role, 0) + 1

            llm_validation = {
                "message_count": len(history_rows),
                "role_distribution": role_counts,
                "issues": validation_issues,
                "is_valid": all(i["severity"] != "error" for i in validation_issues),
            }

        pending_count = pending_counts.get(agent.id, 0)
        report: dict = {
            "agent_id": aid_str,
            "role": agent.role,
            "display_name": agent.display_name,
            "model": agent.model,
            "status": agent.status,
            "has_worker": has_worker,
            "current_task_id": str(agent.current_task_id) if agent.current_task_id else None,
            "pending_messages": pending_count,
            "pending_message_details": pending_msgs_by_agent.get(agent.id, []),
            "last_session": last_session_info,
            "llm_history_validation": llm_validation,
            "issues": [],
        }

        if not has_worker:
            issue = f"{agent.role} ({agent.display_name}) has NO registered worker — messages will never be processed"
            report["issues"].append(issue)
            critical_issues.append(issue)

        if pending_count > 0 and agent.status == "sleeping" and has_worker:
            issue = f"{agent.role} has {pending_count} pending message(s) but is sleeping — worker may not have received notify signal"
            report["issues"].append(issue)
            critical_issues.append(issue)

        if last_session and last_session.end_reason == "error":
            issue = f"{agent.role} last session ended with error"
            report["issues"].append(issue)
            critical_issues.append(issue)

        if last_session and last_session.status == "running" and agent.status == "sleeping":
            issue = f"{agent.role} has a session stuck in 'running' while agent is 'sleeping' — orphaned session"
            report["issues"].append(issue)
            critical_issues.append(issue)

        if llm_validation and not llm_validation["is_valid"]:
            dangling = [i for i in llm_validation["issues"] if i["rule"] == "dangling_tool_use"]
            if dangling:
                issue = (
                    f"{agent.role} history has {len(dangling)} dangling tool_use(s) — "
                    f"this WILL cause Anthropic 400 on next session load"
                )
                report["issues"].append(issue)
                critical_issues.append(issue)

        agent_reports.append(report)

    all_sessions_result = await db.execute(
        select(
            AgentSession.end_reason,
            func.count(AgentSession.id),
        )
        .where(AgentSession.agent_id.in_(agent_ids))
        .group_by(AgentSession.end_reason)
    )
    session_stats = dict(all_sessions_result.all())

    return {
        "project_id": str(project_id),
        "project_name": project.name,
        "worker_manager": wm_status,
        "session_outcome_stats": session_stats,
        "agents": agent_reports,
        "critical_issues": critical_issues,
        "summary": (
            f"Found {len(critical_issues)} critical issue(s) across {len(agents)} agents."
            if critical_issues
            else f"All {len(agents)} agents look healthy."
        ),
    }


@router.get("/diagnose/{project_id}/agent/{agent_id}/history")
async def diagnose_agent_history(
    project_id: UUID,
    agent_id: UUID,
    session_count: int = Query(default=3, ge=1, le=10),
    current_user: User | None = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Dump the raw LLM message history for an agent across recent sessions.

    Shows the exact messages that would be loaded by PromptAssembly.load_history(),
    with Anthropic compliance validation on each session.
    """
    await _get_project(db, project_id, current_user)

    result = await db.execute(select(Agent).where(Agent.id == agent_id, Agent.project_id == project_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found in this project")

    sessions_result = await db.execute(
        select(AgentSession)
        .where(AgentSession.agent_id == agent_id)
        .order_by(AgentSession.started_at.desc())
        .limit(session_count)
    )
    sessions = list(sessions_result.scalars().all())

    session_reports = []
    for sess in reversed(sessions):
        msg_result = await db.execute(
            select(AgentMessage)
            .where(AgentMessage.session_id == sess.id)
            .order_by(AgentMessage.created_at.asc())
            .limit(500)
        )
        messages = list(msg_result.scalars().all())
        validation = _validate_llm_messages(messages)

        msg_dump = []
        for m in messages:
            entry: dict = {
                "id": str(m.id),
                "role": m.role,
                "content_preview": (m.content or "")[:200],
                "iteration": m.loop_iteration,
                "tool_name": m.tool_name,
                "created_at": str(m.created_at),
            }
            if m.role == "assistant" and m.tool_input:
                tcs = m.tool_input.get("__tool_calls__", [])
                entry["tool_calls"] = [
                    {"id": tc.get("id"), "name": tc.get("name")}
                    for tc in tcs if isinstance(tc, dict)
                ]
            if m.role == "tool" and m.tool_input:
                entry["tool_use_id"] = m.tool_input.get("__tool_use_id__")
            msg_dump.append(entry)

        session_reports.append({
            "session_id": str(sess.id),
            "status": sess.status,
            "end_reason": sess.end_reason,
            "iteration_count": sess.iteration_count,
            "started_at": str(sess.started_at),
            "ended_at": str(sess.ended_at) if sess.ended_at else None,
            "message_count": len(messages),
            "messages": msg_dump,
            "validation": {
                "issues": validation,
                "is_valid": all(i["severity"] != "error" for i in validation),
            },
        })

    cross_session_result = await db.execute(
        select(AgentMessage)
        .where(AgentMessage.agent_id == agent_id)
        .where(AgentMessage.session_id.in_([s.id for s in sessions]))
        .order_by(AgentMessage.created_at.asc())
        .limit(2000)
    )
    all_msgs = list(cross_session_result.scalars().all())
    cross_validation = _validate_llm_messages(all_msgs)

    return {
        "agent_id": str(agent_id),
        "role": agent.role,
        "display_name": agent.display_name,
        "status": agent.status,
        "model": agent.model,
        "sessions": session_reports,
        "cross_session_validation": {
            "total_messages": len(all_msgs),
            "issues": cross_validation,
            "is_valid": all(i["severity"] != "error" for i in cross_validation),
        },
    }
