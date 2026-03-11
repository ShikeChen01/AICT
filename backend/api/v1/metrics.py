"""
Prometheus-compatible metrics endpoint (v3).

GET /metrics  — returns plain-text Prometheus exposition format.

Metrics exported:
  aict_active_agents_total          Gauge   Number of currently active agents
  aict_sleeping_agents_total        Gauge   Number of sleeping agents
  aict_worker_count                 Gauge   Number of registered AgentWorker tasks
  aict_llm_tokens_total             Counter Total LLM tokens (input+output) across all time
  aict_llm_cost_usd_total           Counter Total estimated LLM cost in USD
  aict_sandbox_pod_seconds_total    Counter Total sandbox compute seconds metered (v3)
  aict_dead_letter_queue_depth      Gauge   Number of messages in dead-letter queue (v3)
  aict_ws_active_connections        Gauge   Number of active WebSocket connections
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse
from sqlalchemy import func, select, text

from backend.db.models import Agent, LLMUsageEvent
from backend.db.session import AsyncSessionLocal
from backend.workers.worker_manager import get_worker_manager
from backend.websocket.manager import ws_manager
from backend.logging.my_logger import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["metrics"])

_SCRAPE_START = time.time()


def _ts() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _gauge(name: str, value: float | int, help_text: str = "", labels: dict | None = None) -> str:
    label_str = ""
    if labels:
        pairs = ",".join(f'{k}="{v}"' for k, v in labels.items())
        label_str = f"{{{pairs}}}"
    lines = []
    if help_text:
        lines.append(f"# HELP {name} {help_text}")
    lines.append(f"# TYPE {name} gauge")
    lines.append(f"{name}{label_str} {value}")
    return "\n".join(lines)


def _counter(name: str, value: float | int, help_text: str = "", labels: dict | None = None) -> str:
    label_str = ""
    if labels:
        pairs = ",".join(f'{k}="{v}"' for k, v in labels.items())
        label_str = f"{{{pairs}}}"
    lines = []
    if help_text:
        lines.append(f"# HELP {name} {help_text}")
    lines.append(f"# TYPE {name} counter")
    lines.append(f"{name}{label_str} {value}")
    return "\n".join(lines)


@router.get("/metrics", response_class=PlainTextResponse, include_in_schema=True)
async def prometheus_metrics() -> PlainTextResponse:
    """
    Prometheus scrape endpoint.

    No authentication required — metrics contain aggregate counts only,
    no PII. Operators may add a reverse-proxy auth layer if needed.
    """
    blocks: list[str] = []

    # ---- WorkerManager metrics ----
    wm = get_worker_manager()
    wm_status = wm.get_status()
    blocks.append(_gauge("aict_worker_count", wm_status["worker_count"],
                         "Number of registered AgentWorker tasks"))

    # ---- Agent status metrics ----
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Agent.status, func.count(Agent.id).label("cnt"))
                .group_by(Agent.status)
            )
            rows = result.all()
        counts: dict[str, int] = {row[0]: row[1] for row in rows}
        blocks.append(_gauge("aict_active_agents_total", counts.get("active", 0),
                             "Number of currently active agents"))
        blocks.append(_gauge("aict_sleeping_agents_total", counts.get("sleeping", 0),
                             "Number of sleeping agents"))
    except Exception as exc:
        logger.warning("metrics: agent status query failed: %s", exc)
        blocks.append(_gauge("aict_active_agents_total", -1))
        blocks.append(_gauge("aict_sleeping_agents_total", -1))

    # ---- LLM usage metrics ----
    try:
        async with AsyncSessionLocal() as db:
            token_result = await db.execute(
                select(
                    func.coalesce(func.sum(LLMUsageEvent.input_tokens + LLMUsageEvent.output_tokens), 0)
                )
            )
            total_tokens: int = token_result.scalar_one() or 0
        blocks.append(_counter("aict_llm_tokens_total", total_tokens,
                               "Total LLM tokens (input+output) across all time"))
    except Exception as exc:
        logger.warning("metrics: LLM token query failed: %s", exc)
        blocks.append(_counter("aict_llm_tokens_total", -1))

    # ---- Sandbox pod-seconds ----
    try:
        async with AsyncSessionLocal() as db:
            # Try the new metering table (v3); fall back to 0 if not yet migrated
            try:
                ps_result = await db.execute(
                    text("SELECT COALESCE(SUM(pod_seconds), 0) FROM sandbox_usage_events")
                )
                total_pod_seconds: float = ps_result.scalar_one() or 0.0
            except Exception:
                total_pod_seconds = 0.0
        blocks.append(_counter("aict_sandbox_pod_seconds_total", total_pod_seconds,
                               "Total sandbox compute seconds metered"))
    except Exception as exc:
        logger.warning("metrics: sandbox pod-seconds query failed: %s", exc)
        blocks.append(_counter("aict_sandbox_pod_seconds_total", 0))

    # ---- Dead-letter queue depth ----
    try:
        async with AsyncSessionLocal() as db:
            try:
                dlq_result = await db.execute(
                    text("SELECT COUNT(*) FROM dead_letter_messages WHERE resolved_at IS NULL")
                )
                dlq_depth: int = dlq_result.scalar_one() or 0
            except Exception:
                dlq_depth = 0
        blocks.append(_gauge("aict_dead_letter_queue_depth", dlq_depth,
                             "Number of unresolved messages in dead-letter queue"))
    except Exception as exc:
        logger.warning("metrics: dead-letter depth query failed: %s", exc)
        blocks.append(_gauge("aict_dead_letter_queue_depth", 0))

    # ---- WebSocket connections ----
    blocks.append(_gauge("aict_ws_active_connections", ws_manager.active_connections,
                         "Number of active WebSocket connections"))

    # ---- Uptime ----
    uptime = time.time() - _SCRAPE_START
    blocks.append(_gauge("aict_uptime_seconds", uptime, "Process uptime in seconds"))

    output = "\n\n".join(blocks) + "\n"
    return PlainTextResponse(content=output, media_type="text/plain; version=0.0.4; charset=utf-8")
