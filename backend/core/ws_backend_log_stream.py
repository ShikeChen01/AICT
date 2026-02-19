"""
In-memory backend log stream for websocket clients.

Captures Python logging records into a ring buffer (last N lines) and exposes
an async broadcaster loop to emit incremental log events over websocket.

Threading model:
  - ``append()`` is called from any thread (via the logging handler).
  - ``run_broadcaster()`` runs on the main asyncio event loop.
  - We use ``loop.call_soon_threadsafe`` to bridge the two, feeding an
    ``asyncio.Queue`` that the broadcaster awaits without polling.
"""

from __future__ import annotations

import asyncio
import logging
import sys
import threading
from collections import deque
from datetime import UTC, datetime
from typing import TypedDict

_MAX_MESSAGE_LEN = 10_000
_BROADCAST_ERROR_LOG_INTERVAL = 50


class BackendLogItem(TypedDict):
    seq: int
    ts: str
    level: str
    logger: str
    message: str


class WebSocketBackendLogStream:
    """Thread-safe backend log buffer plus async drain queue."""

    def __init__(self, max_items: int = 1000):
        self._max_items = max_items
        self._buffer: deque[BackendLogItem] = deque(maxlen=max_items)
        self._async_queue: asyncio.Queue[BackendLogItem] | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._lock = threading.Lock()
        self._next_seq = 1
        self._broadcast_errors = 0

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Bind to the running event loop so append() can enqueue safely."""
        self._loop = loop
        self._async_queue = asyncio.Queue()

    def append(self, *, level: str, logger_name: str, message: str, ts: str | None = None) -> BackendLogItem:
        """Append one log item to ring buffer and enqueue for streaming."""
        if ts is None:
            ts = datetime.now(UTC).isoformat()

        if len(message) > _MAX_MESSAGE_LEN:
            message = message[:_MAX_MESSAGE_LEN] + f"\n… [truncated, total {len(message)} chars]"

        with self._lock:
            seq = self._next_seq
            self._next_seq += 1
            item: BackendLogItem = {
                "seq": seq,
                "ts": ts,
                "level": level,
                "logger": logger_name,
                "message": message,
            }
            self._buffer.append(item)

        if self._loop is not None and self._async_queue is not None:
            try:
                self._loop.call_soon_threadsafe(self._async_queue.put_nowait, item)
            except RuntimeError:
                pass
        return item

    def snapshot(self) -> tuple[list[BackendLogItem], int]:
        """Get a copy of buffered items and latest sequence number."""
        with self._lock:
            items = list(self._buffer)
            latest_seq = self._next_seq - 1
        return items, latest_seq

    async def run_broadcaster(self) -> None:
        """
        Drain queued log items and broadcast to activity channel.

        Awaits the asyncio.Queue (no polling). Per-item errors are logged to
        stderr at a throttled rate so they don't cascade into the websocket
        handler itself.
        """
        from backend.websocket.events import create_backend_log_event
        from backend.websocket.manager import Channel, ws_manager

        if self._async_queue is None:
            self.bind_loop(asyncio.get_running_loop())

        queue = self._async_queue
        assert queue is not None

        while True:
            item = await queue.get()
            try:
                event = create_backend_log_event(
                    seq=item["seq"],
                    ts=item["ts"],
                    level=item["level"],
                    logger=item["logger"],
                    message=item["message"],
                )
                await ws_manager.broadcast(event, Channel.BACKEND_LOGS)
                self._broadcast_errors = 0
            except Exception as exc:
                self._broadcast_errors += 1
                if self._broadcast_errors % _BROADCAST_ERROR_LOG_INTERVAL == 1:
                    print(
                        f"[ws_backend_log_stream] broadcast error "
                        f"(#{self._broadcast_errors}): {exc!r}",
                        file=sys.stderr,
                    )


class WebSocketBackendLogHandler(logging.Handler):
    """Logging handler that forwards root logs into the websocket stream."""

    _DEFAULT_EXCLUDED_LOGGER_PREFIXES = (
        "backend.core.ws_backend_log_stream",
        "backend.websocket.manager",
        "uvicorn.access",
    )

    def __init__(self, stream: WebSocketBackendLogStream):
        super().__init__()
        self._stream = stream
        # Use a plain formatter so message contains the full log text
        # including any exception traceback (via Formatter's built-in exc_info
        # handling) without duplicating the timestamp/level already shown by
        # the frontend UI.
        self.setFormatter(logging.Formatter("%(message)s"))

    def emit(self, record: logging.LogRecord) -> None:
        try:
            if record.name.startswith(self._DEFAULT_EXCLUDED_LOGGER_PREFIXES):
                return

            # self.format() already appends the exception traceback when
            # record.exc_info is set (standard Formatter behaviour), so we do
            # not need a separate exc_info block here.
            message = self.format(record)

            timestamp = datetime.fromtimestamp(record.created, UTC).isoformat()
            self._stream.append(
                level=record.levelname,
                logger_name=record.name,
                message=message,
                ts=timestamp,
            )
        except Exception:
            self.handleError(record)


ws_backend_log_stream = WebSocketBackendLogStream(max_items=1000)
ws_backend_log_handler = WebSocketBackendLogHandler(ws_backend_log_stream)
