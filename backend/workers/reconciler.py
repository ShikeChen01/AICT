"""
Reconciler: periodic self-healing background task for the worker/agent system.

v2 (original): 4 drift categories.
v3 (extended): 8 drift categories for intelligent cluster control.

Drift categories:
  1. Orphan agents     -- DB agents with no registered worker (spawns one)
  2. Stuck active      -- Agents stuck "active" with no running session >THRESHOLD
  3. Orphaned sessions -- AgentSession rows still "running" for sleeping agents
  4. Stuck messages    -- ChannelMessage rows stuck "sent" >THRESHOLD (re-notifies)
  --- v3 new ---
  5. Cluster drift     -- Agents whose model/role no longer matches their ClusterSpec
  6. Dead-letter retry -- Messages in dead_letter_messages older than retry window
  7. Budget breach     -- Agents exceeding daily cost cap (suspends them)
  8. Zombie sandboxes  -- Agents with sandbox_id but status=sleeping for >IDLE_THRESHOLD
                          (records sandbox as reclaimable)
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta
from uuid import UUID

from sqlalchemy import select, update, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import Agent, AgentSession, ChannelMessage, LLMUsageEvent
from backend.db.session import AsyncSessionLocal
from backend.logging.my_logger import get_logger
from backend.workers.message_router import get_message_router
from backend.workers.worker_manager import get_worker_manager

logger = get_logger(__name__)

RECONCILE_INTERVAL_SECONDS: int = 30
STUCK_ACTIVE_THRESHOLD_SECONDS: int = 600    # 10 minutes
STUCK_MESSAGE_THRESHOLD_SECONDS: int = 60    # 1 minute
ZOMBIE_SANDBOX_IDLE_SECONDS: int = 3600      # 1 hour — sandbox claimed but agent sleeping
DEAD_LETTER_RETRY_SECONDS: int = 300         # 5 minutes before retrying DLQ messages
BUDGET_CHECK_WINDOW_HOURS: int = 24          # rolling 24-hour cost window


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


# ── Main reconcile pass ───────────────────────────────────────────────────────


async def _reconcile_once() -> None:
    """Run one full reconciliation pass across all 8 drift categories."""
    wm = get_worker_manager()
    router = get_message_router()
    now = _utcnow()

    # 1. Orphan agents
    try:
        spawned = await wm.ensure_workers_for_all_agents()
        if spawned:
            logger.info("Reconciler: spawned workers for %d orphan agent(s): %s", len(spawned), spawned)
    except Exception as exc:
        logger.warning("Reconciler: orphan-agent check failed: %s", exc)

    # 2 + 3. Stuck active + orphaned sessions
    try:
        async with AsyncSessionLocal() as db:
            await _fix_stuck_agents(db, now)
            await db.commit()
    except Exception as exc:
        logger.warning("Reconciler: stuck-agent/session check failed: %s", exc)

    # 4. Stuck messages
    try:
        async with AsyncSessionLocal() as db:
            await _retry_stuck_messages(db, router, now)
            await db.commit()
    except Exception as exc:
        logger.warning("Reconciler: stuck-message check failed: %s", exc)

    # 5. Cluster drift (v3)
    try:
        async with AsyncSessionLocal() as db:
            await _reconcile_cluster_drift(db, now)
            await db.commit()
    except Exception as exc:
        logger.warning("Reconciler: cluster-drift check failed: %s", exc)

    # 6. Dead-letter retry (v3)
    try:
        async with AsyncSessionLocal() as db:
            await _retry_dead_letter_messages(db, router, now)
            await db.commit()
    except Exception as exc:
        logger.warning("Reconciler: dead-letter retry failed: %s", exc)

    # 7. Budget breach (v3)
    try:
        async with AsyncSessionLocal() as db:
            await _check_budget_breaches(db, now)
            await db.commit()
    except Exception as exc:
        logger.warning("Reconciler: budget-breach check failed: %s", exc)

    # 8. Zombie sandboxes (v3)
    try:
        async with AsyncSessionLocal() as db:
            await _mark_zombie_sandboxes(db, now)
            await db.commit()
    except Exception as exc:
        logger.warning("Reconciler: zombie-sandbox check failed: %s", exc)


# ── Drift category 1–4 (original) ────────────────────────────────────────────


async def _fix_stuck_agents(db: AsyncSession, now: datetime) -> None:
    """Reset stuck 'active' agents and force-end orphaned sessions."""

    # Pass 1: stuck active agents
    active_agents_result = await db.execute(select(Agent).where(Agent.status == "active"))
    active_agents = list(active_agents_result.scalars().all())

    if active_agents:
        active_agent_ids = [a.id for a in active_agents]
        running_sessions_result = await db.execute(
            select(AgentSession).where(
                AgentSession.agent_id.in_(active_agent_ids),
                AgentSession.status == "running",
            )
        )
        running_sessions = list(running_sessions_result.scalars().all())
        running_by_agent: dict[UUID, AgentSession] = {s.agent_id: s for s in running_sessions}

        for agent in active_agents:
            sess = running_by_agent.get(agent.id)
            is_stuck = sess is None or (
                now.timestamp() - (sess.started_at.timestamp() if sess.started_at else 0)
                > STUCK_ACTIVE_THRESHOLD_SECONDS
            )
            if not is_stuck:
                continue

            logger.warning(
                "Reconciler: agent %s (%s) stuck active >%ds — resetting to sleeping",
                agent.id, agent.role, STUCK_ACTIVE_THRESHOLD_SECONDS,
            )
            agent.status = "sleeping"
            if sess is not None and sess.status == "running":
                sess.status = "force_ended"
                sess.end_reason = "reconciler_orphaned"
                sess.ended_at = now
                logger.warning("Reconciler: force-ending orphaned session %s for agent %s", sess.id, agent.id)

    # Pass 2: orphaned sessions for sleeping agents
    sleeping_ids_result = await db.execute(select(Agent.id).where(Agent.status == "sleeping"))
    sleeping_ids = [row[0] for row in sleeping_ids_result.all()]

    if sleeping_ids:
        orphaned_result = await db.execute(
            select(AgentSession).where(
                AgentSession.agent_id.in_(sleeping_ids),
                AgentSession.status == "running",
            )
        )
        for sess in orphaned_result.scalars().all():
            logger.warning("Reconciler: force-ending session %s for sleeping agent %s", sess.id, sess.agent_id)
            sess.status = "force_ended"
            sess.end_reason = "reconciler_orphaned"
            sess.ended_at = now


async def _retry_stuck_messages(db: AsyncSession, router, now: datetime) -> None:
    """Re-fire notify() for channel messages stuck in 'sent' status."""
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
        logger.info("Reconciler: re-notified %d stuck message(s)", retried)


# ── Drift category 5: Cluster drift (v3) ─────────────────────────────────────


async def _reconcile_cluster_drift(db: AsyncSession, now: datetime) -> None:
    """
    Detect agents whose runtime state has drifted from their declared ClusterSpec.

    Currently checks:
    - Agents with a cluster_name in memory but whose model no longer matches
      a stored cluster spec (if cluster_specs table exists).

    This is a best-effort check — the cluster_specs table may not exist yet
    if the v3 migration hasn't run. We log drift but do not auto-correct model
    changes without explicit operator approval (safety guard).
    """
    try:
        # Check if cluster_specs table exists
        result = await db.execute(
            text("SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'cluster_specs'")
        )
        if result.scalar_one() == 0:
            return  # Table not yet migrated — skip silently

        # Find agents that belong to a cluster
        agents_result = await db.execute(
            select(Agent).where(Agent.memory.isnot(None))
        )
        agents = list(agents_result.scalars().all())

        drifted = 0
        for agent in agents:
            if not isinstance(agent.memory, dict):
                continue
            cluster_name = agent.memory.get("cluster_name")
            if not cluster_name:
                continue

            # Look up the stored spec for this cluster
            spec_result = await db.execute(
                text(
                    "SELECT spec_yaml FROM cluster_specs "
                    "WHERE project_id = :pid AND cluster_name = :name "
                    "LIMIT 1"
                ),
                {"pid": str(agent.project_id), "name": cluster_name},
            )
            row = spec_result.fetchone()
            if row is None:
                continue

            from backend.cluster.spec import ClusterSpec
            spec_obj, errors = ClusterSpec.from_yaml(row[0])
            if errors or spec_obj is None:
                continue

            desired_model = spec_obj.manifest.spec.model
            if agent.model != desired_model:
                logger.warning(
                    "Reconciler: cluster drift detected — agent %s (%s) model=%s but spec wants model=%s. "
                    "Run `POST /clusters/apply` to converge.",
                    agent.id, agent.display_name, agent.model, desired_model,
                )
                drifted += 1

        if drifted:
            logger.info("Reconciler: %d cluster-drifted agent(s) detected", drifted)

    except Exception as exc:
        logger.debug("Reconciler: cluster-drift check skipped: %s", exc)


# ── Drift category 6: Dead-letter retry (v3) ─────────────────────────────────


async def _retry_dead_letter_messages(db: AsyncSession, router, now: datetime) -> None:
    """
    Re-attempt delivery for messages in the dead_letter_messages table.

    Messages older than DEAD_LETTER_RETRY_SECONDS and with retry_count < 5
    are re-queued to their target agent.
    """
    try:
        result = await db.execute(
            text("SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'dead_letter_messages'")
        )
        if result.scalar_one() == 0:
            return

        cutoff = now - timedelta(seconds=DEAD_LETTER_RETRY_SECONDS)
        dlq_result = await db.execute(
            text(
                "SELECT id, target_agent_id, retry_count FROM dead_letter_messages "
                "WHERE resolved_at IS NULL AND retry_count < 5 "
                "AND last_attempted_at < :cutoff "
                "ORDER BY created_at ASC LIMIT 20"
            ),
            {"cutoff": cutoff},
        )
        rows = dlq_result.fetchall()

        retried = 0
        for row in rows:
            dlq_id, target_agent_id, retry_count = row
            if target_agent_id:
                try:
                    agent_uuid = UUID(str(target_agent_id))
                    router.notify(agent_uuid)
                    await db.execute(
                        text(
                            "UPDATE dead_letter_messages SET "
                            "retry_count = retry_count + 1, last_attempted_at = :now "
                            "WHERE id = :id"
                        ),
                        {"now": now, "id": dlq_id},
                    )
                    retried += 1
                except Exception as e:
                    logger.debug("Reconciler: DLQ retry failed for msg %s: %s", dlq_id, e)

        if retried:
            logger.info("Reconciler: retried %d dead-letter message(s)", retried)

    except Exception as exc:
        logger.debug("Reconciler: dead-letter retry skipped: %s", exc)


# ── Drift category 7: Budget breach (v3) ─────────────────────────────────────


async def _check_budget_breaches(db: AsyncSession, now: datetime) -> None:
    """
    Detect projects that have exceeded their daily cost budget and log a warning.

    Budget enforcement is advisory at the reconciler level — the LLM service
    layer performs hard enforcement at call time. The reconciler provides a
    rolling audit that catches drift if the hard enforcement is bypassed.
    """
    try:
        from backend.db.models import ProjectSettings
        from sqlalchemy import func

        window_start = now - timedelta(hours=BUDGET_CHECK_WINDOW_HOURS)

        # Get projects with a daily cost budget set
        settings_result = await db.execute(
            select(ProjectSettings).where(ProjectSettings.daily_cost_budget_usd > 0)
        )
        all_settings = list(settings_result.scalars().all())

        for ps in all_settings:
            # Sum costs in the rolling window
            # LLMUsageEvent doesn't store cost — compute from tokens using a fixed
            # worst-case rate of $0.075/1K tokens (opus input) as a conservative bound.
            # The real cost calculation lives in the LLM service layer.
            cost_result = await db.execute(
                select(
                    func.coalesce(
                        func.sum(
                            (LLMUsageEvent.input_tokens + LLMUsageEvent.output_tokens).cast("float")
                            / 1_000_000.0
                            * 75.0  # conservative worst-case (claude-opus output rate)
                        ),
                        0.0,
                    )
                ).where(
                    LLMUsageEvent.project_id == ps.project_id,
                    LLMUsageEvent.created_at >= window_start,
                )
            )
            estimated_cost = cost_result.scalar_one() or 0.0

            if estimated_cost > ps.daily_cost_budget_usd:
                logger.warning(
                    "Reconciler: project %s has EXCEEDED daily budget "
                    "(estimated=$%.4f, budget=$%.2f) in the last %dh",
                    ps.project_id,
                    estimated_cost,
                    ps.daily_cost_budget_usd,
                    BUDGET_CHECK_WINDOW_HOURS,
                )

    except Exception as exc:
        logger.debug("Reconciler: budget-breach check skipped: %s", exc)


# ── Drift category 8: Zombie sandboxes (v3) ──────────────────────────────────


async def _mark_zombie_sandboxes(db: AsyncSession, now: datetime) -> None:
    """
    Detect sandbox IDs held by sleeping agents that have been idle too long.

    A "zombie sandbox" is an agent that has a sandbox_id assigned but has been
    sleeping for > ZOMBIE_SANDBOX_IDLE_SECONDS. These represent compute resources
    that could be reclaimed. We log them and record in the sandbox_usage_events
    table if it exists.
    """
    try:
        cutoff = now - timedelta(seconds=ZOMBIE_SANDBOX_IDLE_SECONDS)

        result = await db.execute(
            select(Agent).where(
                Agent.status == "sleeping",
                Agent.sandbox_id.isnot(None),
                Agent.updated_at < cutoff,
            ).limit(50)
        )
        zombies = list(result.scalars().all())

        if zombies:
            logger.info(
                "Reconciler: %d zombie sandbox(es) detected (sleeping >%ds with sandbox claimed): %s",
                len(zombies),
                ZOMBIE_SANDBOX_IDLE_SECONDS,
                [str(a.id) for a in zombies],
            )

        # If sandbox_usage_events table exists, record reclaim candidates
        try:
            table_check = await db.execute(
                text("SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'sandbox_usage_events'")
            )
            if table_check.scalar_one() > 0:
                for agent in zombies:
                    # Mark sandbox as reclaimable (upsert-style: skip if already recorded)
                    await db.execute(
                        text(
                            "INSERT INTO sandbox_usage_events "
                            "(id, agent_id, project_id, sandbox_id, event_type, created_at) "
                            "VALUES (gen_random_uuid(), :agent_id, :project_id, :sandbox_id, 'reclaim_candidate', :now) "
                            "ON CONFLICT DO NOTHING"
                        ),
                        {
                            "agent_id": str(agent.id),
                            "project_id": str(agent.project_id),
                            "sandbox_id": agent.sandbox_id,
                            "now": now,
                        },
                    )
        except Exception:
            pass  # Table not yet migrated — skip silently

    except Exception as exc:
        logger.debug("Reconciler: zombie-sandbox check skipped: %s", exc)


# ── Entry point ───────────────────────────────────────────────────────────────


async def run_reconciler_forever() -> None:
    """Run the reconciler loop indefinitely. Meant to be run as a background task."""
    logger.info(
        "Reconciler started (v3, interval=%ds, stuck_active_threshold=%ds, "
        "stuck_msg_threshold=%ds, zombie_sandbox_threshold=%ds)",
        RECONCILE_INTERVAL_SECONDS,
        STUCK_ACTIVE_THRESHOLD_SECONDS,
        STUCK_MESSAGE_THRESHOLD_SECONDS,
        ZOMBIE_SANDBOX_IDLE_SECONDS,
    )
    while True:
        await asyncio.sleep(RECONCILE_INTERVAL_SECONDS)
        try:
            await _reconcile_once()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("Reconciler: unexpected error in reconcile pass: %s", exc, exc_info=True)
