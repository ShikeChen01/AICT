"""PostgreSQL LISTEN/NOTIFY listener for agent config changes.

When a user updates agent config (model, prompt blocks, tool configs) via the
frontend API, the DB commit fires a pg_notify on the 'agent_config_changed'
channel. This listener receives the notification and sets a dirty flag on the
running Agent instance so the config is reloaded within the next few iterations.

Architecture:
    WorkerManager.start() creates a ConfigListener and starts it as a background task.
    ConfigListener holds one dedicated raw asyncpg connection (NOT from SQLAlchemy pool)
    so it can block on LISTEN without tying up a pool connection.

Reliability note:
    LISTEN/NOTIFY is not durable — notifications sent while the listener connection
    is down are lost. This is acceptable because:
    1. The reconciler runs every 30s and heals stuck state.
    2. Agents always bootstrap fresh from DB at session start, so a missed
       notification means the change takes effect on next wake cycle (seconds away).
"""

from __future__ import annotations

import asyncio
import json
import re
from uuid import UUID

from backend.logging.my_logger import get_logger

logger = get_logger(__name__)

_LISTEN_CHANNEL = "agent_config_changed"
_RECONNECT_DELAY_S = 5


def _asyncpg_dsn(sqlalchemy_url: str) -> str:
    """Convert a SQLAlchemy async URL to a plain asyncpg DSN.

    SQLAlchemy uses 'postgresql+asyncpg://...' — asyncpg.connect() expects
    'postgresql://...' or 'postgres://...'.
    """
    return re.sub(r"^postgresql\+asyncpg://", "postgresql://", sqlalchemy_url)


class ConfigListener:
    """Listens for PostgreSQL NOTIFY events and marks agent configs dirty.

    Usage:
        listener = ConfigListener(dsn, worker_manager)
        task = asyncio.create_task(listener.run_forever())
        # later:
        await listener.stop()
    """

    def __init__(self, dsn: str, worker_manager) -> None:
        """
        Args:
            dsn: Raw asyncpg-compatible DSN (postgresql://...).
            worker_manager: WorkerManager instance for agent lookup.
        """
        self._dsn = dsn
        self._wm = worker_manager
        self._conn = None
        self._stop_event = asyncio.Event()

    async def run_forever(self) -> None:
        """Connect, LISTEN, and reconnect on failure until stop() is called."""
        while not self._stop_event.is_set():
            try:
                await self._connect_and_listen()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning(
                    "ConfigListener disconnected (%s), reconnecting in %ds",
                    exc,
                    _RECONNECT_DELAY_S,
                )
                await asyncio.sleep(_RECONNECT_DELAY_S)

    async def _connect_and_listen(self) -> None:
        """Open a raw asyncpg connection and block on LISTEN."""
        import asyncpg  # imported here to avoid import-time errors if not installed

        self._conn = await asyncpg.connect(self._dsn)
        try:
            await self._conn.add_listener(_LISTEN_CHANNEL, self._on_notification)
            logger.info("ConfigListener: listening on channel '%s'", _LISTEN_CHANNEL)

            # Block until stop() is called or connection drops
            while not self._stop_event.is_set():
                # Keep connection alive; asyncpg fires the callback on its own thread
                await asyncio.sleep(5)
                # Lightweight keepalive: detect dropped connections quickly
                try:
                    await self._conn.fetchval("SELECT 1")
                except Exception as exc:
                    raise ConnectionError(f"Keepalive failed: {exc}") from exc
        finally:
            try:
                await self._conn.remove_listener(_LISTEN_CHANNEL, self._on_notification)
                await self._conn.close()
            except Exception:
                pass
            self._conn = None

    def _on_notification(self, conn, pid: int, channel: str, payload: str) -> None:
        """Asyncpg callback — fired on asyncpg's internal thread.

        Parses agent_id from payload, looks up the worker, and marks the agent
        config dirty. The Agent will reload on its next mid-loop check.
        """
        try:
            data = json.loads(payload)
            agent_id = UUID(data["agent_id"])
        except Exception as exc:
            logger.warning(
                "ConfigListener: malformed NOTIFY payload on '%s': %r — %s",
                channel, payload, exc,
            )
            return

        worker = self._wm.get_worker(agent_id)
        if worker is None:
            # Agent has no active worker (sleeping or unknown) — no-op
            return

        agent = getattr(worker, "agent", None)
        if agent is None:
            # Worker exists but no Agent instance is currently running — no-op
            return

        agent.mark_config_dirty()
        table = data.get("table", "unknown")
        logger.info(
            "ConfigListener: marked agent %s config dirty (table=%s)",
            agent_id, table,
        )

    async def stop(self) -> None:
        """Signal the listener to shut down."""
        self._stop_event.set()
        if self._conn is not None:
            try:
                await self._conn.close()
            except Exception:
                pass
