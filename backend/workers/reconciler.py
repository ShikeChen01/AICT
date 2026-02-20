"""
Reconciler: periodic self-healing background task for the worker/agent system.

Runs every RECONCILE_INTERVAL_SECONDS and fixes four categories of drift:

1. Orphan agents   -- agents in DB with no registered worker (spawns one).
2. Stuck active    -- agents stuck in "active" with no running session for
                      longer than STUCK_ACTIVE_THRESHOLD_SECONDS (resets to
                      "sleeping" and force-ends the stale session).
3. Orphaned sessions -- AgentSession rows still "running" while their agent
                        is "sleeping" (force-ends them).
4. Stuck messages  -- ChannelMessage rows still "sent" for longer than
                      STUCK_MESSAGE_THRESHOLD_SECONDS (re-fires notify()).

These checks make the system self-correcting: even if a worker fails to spawn
at creation time or a notification is dropped, the reconciler catches it within
one interval.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import Agent, AgentSession, ChannelMessage
from backend.db.session import AsyncSessionLocal
from backend.logging.my_logger import get_logger
from backend.workers.message_router import get_message_router
from backend.workers.worker_manager import get_worker_manager

logger = get_logger(__name__)

RECONCILE_INTERVAL_SECONDS: int = 30
STUCK_ACTIVE_THRESHOLD_SECONDS: int = 600   # 10 minutes
STUCK_MESSAGE_THRESHOLD_SECONDS: int = 60   # 1 minute


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


async def _reconcile_once() -> None:
    """Run one reconciliation pass."""
    wm = get_worker_manager()
    router = get_message_router()
    now = _utcnow()

    # ------------------------------------------------------------------
    # 1. Orphan agents: DB agent with no registered worker
    # ------------------------------------------------------------------
    try:
        spawned = await wm.ensure_workers_for_all_agents()
        if spawned:
            logger.info("Reconciler: spawned workers for %d orphan agent(s): %s", len(spawned), spawned)
    except Exception as exc:
        logger.warning("Reconciler: orphan-agent check failed: %s", exc)

    # ------------------------------------------------------------------
    # 2. Stuck active agents + 3. Orphaned sessions
    # ------------------------------------------------------------------
    try:
        async with AsyncSessionLocal() as db:
            await _fix_stuck_agents(db, now)
            await db.commit()
    except Exception as exc:
        logger.warning("Reconciler: stuck-agent/session check failed: %s", exc)

    # ------------------------------------------------------------------
    # 4. Stuck messages: re-notify for "sent" messages older than threshold
    # ------------------------------------------------------------------
    try:
        async with AsyncSessionLocal() as db:
            await _retry_stuck_messages(db, router, now)
            await db.commit()
    except Exception as exc:
        logger.warning("Reconciler: stuck-message check failed: %s", exc)


async def _fix_stuck_agents(db: AsyncSession, now: datetime) -> None:
    """Reset agents stuck "active" and force-end orphaned sessions.

    Two independent passes:
    1. Active agents — reset any that have been "active" too long with no
       running session (or whose running session is stale).
    2. Sleeping agents — force-end any AgentSession still marked "running"
       whose agent is sleeping (crash/restart left it orphaned).
    """
    # ------------------------------------------------------------------
    # Pass 1: stuck "active" agents
    # ------------------------------------------------------------------
    active_agents_result = await db.execute(
        select(Agent).where(Agent.status == "active")
    )
    active_agents = list(active_agents_result.scalars().all())

    if active_agents:
        active_agent_ids = [a.id for a in active_agents]
        running_sessions_result = await db.execute(
            select(AgentSession)
            .where(
                AgentSession.agent_id.in_(active_agent_ids),
                AgentSession.status == "running",
            )
        )
        running_sessions = list(running_sessions_result.scalars().all())
        running_by_agent: dict[UUID, AgentSession] = {s.agent_id: s for s in running_sessions}

        for agent in active_agents:
            sess = running_by_agent.get(agent.id)

            is_stuck = False
            if sess is None:
                is_stuck = True
            else:
                started_ts = sess.started_at.timestamp() if sess.started_at else 0
                if now.timestamp() - started_ts > STUCK_ACTIVE_THRESHOLD_SECONDS:
                    is_stuck = True

            if not is_stuck:
                continue

            logger.warning(
                "Reconciler: agent %s (%s) stuck active for >%ds — resetting to sleeping",
                agent.id,
                agent.role,
                STUCK_ACTIVE_THRESHOLD_SECONDS,
            )
            agent.status = "sleeping"

            if sess is not None and sess.status == "running":
                sess.status = "force_ended"
                sess.end_reason = "reconciler_orphaned"
                sess.ended_at = now
                logger.warning(
                    "Reconciler: force-ending orphaned session %s for agent %s",
                    sess.id,
                    agent.id,
                )

    # ------------------------------------------------------------------
    # Pass 2: orphaned sessions for sleeping agents
    # ------------------------------------------------------------------
    sleeping_agents_result = await db.execute(
        select(Agent.id).where(Agent.status == "sleeping")
    )
    sleeping_ids = [row[0] for row in sleeping_agents_result.all()]

    if sleeping_ids:
        orphaned_sessions_result = await db.execute(
            select(AgentSession).where(
                AgentSession.agent_id.in_(sleeping_ids),
                AgentSession.status == "running",
            )
        )
        for sess in orphaned_sessions_result.scalars().all():
            logger.warning(
                "Reconciler: force-ending session %s for sleeping agent %s",
                sess.id,
                sess.agent_id,
            )
            sess.status = "force_ended"
            sess.end_reason = "reconciler_orphaned"
            sess.ended_at = now


async def _retry_stuck_messages(db: AsyncSession, router, now: datetime) -> None:
    """Re-fire notify() for channel messages stuck in 'sent' status."""
    cutoff = now.timestamp() - STUCK_MESSAGE_THRESHOLD_SECONDS

    result = await db.execute(
        select(ChannelMessage)
        .where(
            ChannelMessage.status == "sent",
            ChannelMessage.target_agent_id.isnot(None),
        )
        .order_by(ChannelMessage.created_at.asc())
        .limit(50)
    )
    stuck = list(result.scalars().all())

    retried = 0
    for msg in stuck:
        created_ts = msg.created_at.timestamp() if msg.created_at else 0
        if now.timestamp() - created_ts < STUCK_MESSAGE_THRESHOLD_SECONDS:
            continue
        router.notify(msg.target_agent_id)
        retried += 1

    if retried:
        logger.info(
            "Reconciler: re-notified %d stuck message(s)",
            retried,
        )


async def run_reconciler_forever() -> None:
    """Run the reconciler loop indefinitely. Meant to be run as a background task."""
    logger.info(
        "Reconciler started (interval=%ds, stuck_active_threshold=%ds, stuck_msg_threshold=%ds)",
        RECONCILE_INTERVAL_SECONDS,
        STUCK_ACTIVE_THRESHOLD_SECONDS,
        STUCK_MESSAGE_THRESHOLD_SECONDS,
    )
    while True:
        await asyncio.sleep(RECONCILE_INTERVAL_SECONDS)
        try:
            await _reconcile_once()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("Reconciler: unexpected error in reconcile pass: %s", exc, exc_info=True)
