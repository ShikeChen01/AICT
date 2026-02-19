"""Tests for WebSocketBackendLogStream and WebSocketBackendLogHandler."""

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.core.ws_backend_log_stream import (
    WebSocketBackendLogHandler,
    WebSocketBackendLogStream,
)


class TestWebSocketBackendLogStream:
    """Unit tests for the ring-buffer + async-queue stream."""

    def test_append_assigns_sequential_ids(self):
        stream = WebSocketBackendLogStream(max_items=10)
        a = stream.append(level="INFO", logger_name="test", message="one")
        b = stream.append(level="INFO", logger_name="test", message="two")
        assert a["seq"] == 1
        assert b["seq"] == 2

    def test_append_truncates_long_messages(self):
        stream = WebSocketBackendLogStream(max_items=10)
        item = stream.append(level="INFO", logger_name="test", message="x" * 20_000)
        assert len(item["message"]) < 20_000
        assert "truncated" in item["message"]

    def test_snapshot_returns_buffer_copy(self):
        stream = WebSocketBackendLogStream(max_items=5)
        for i in range(3):
            stream.append(level="INFO", logger_name="test", message=f"msg-{i}")
        items, seq = stream.snapshot()
        assert len(items) == 3
        assert seq == 3

    def test_ring_buffer_evicts_oldest(self):
        stream = WebSocketBackendLogStream(max_items=2)
        stream.append(level="INFO", logger_name="test", message="a")
        stream.append(level="INFO", logger_name="test", message="b")
        stream.append(level="INFO", logger_name="test", message="c")
        items, _ = stream.snapshot()
        assert len(items) == 2
        assert items[0]["message"] == "b"
        assert items[1]["message"] == "c"

    @pytest.mark.asyncio
    async def test_bind_loop_enables_async_enqueue(self):
        stream = WebSocketBackendLogStream(max_items=10)
        stream.bind_loop(asyncio.get_running_loop())
        stream.append(level="INFO", logger_name="test", message="hello")
        assert stream._async_queue is not None
        item = await asyncio.wait_for(stream._async_queue.get(), timeout=1.0)
        assert item["message"] == "hello"

    @pytest.mark.asyncio
    async def test_append_before_bind_loop_does_not_raise(self):
        stream = WebSocketBackendLogStream(max_items=10)
        item = stream.append(level="INFO", logger_name="test", message="no loop yet")
        assert item["seq"] == 1

    @pytest.mark.asyncio
    async def test_broadcaster_sends_events(self):
        stream = WebSocketBackendLogStream(max_items=10)
        stream.bind_loop(asyncio.get_running_loop())

        mock_broadcast = AsyncMock(return_value=1)
        mock_ws_manager = MagicMock()
        mock_ws_manager.broadcast = mock_broadcast

        with patch("backend.websocket.manager.ws_manager", mock_ws_manager):
            stream.append(level="INFO", logger_name="test.mod", message="hello world")
            task = asyncio.create_task(stream.run_broadcaster())
            await asyncio.sleep(0.05)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        mock_broadcast.assert_called()
        event = mock_broadcast.call_args[0][0]
        assert event.data["message"] == "hello world"

    @pytest.mark.asyncio
    async def test_broadcaster_logs_errors_instead_of_swallowing(self, capsys):
        stream = WebSocketBackendLogStream(max_items=10)
        stream.bind_loop(asyncio.get_running_loop())

        mock_ws_manager = MagicMock()
        mock_ws_manager.broadcast = AsyncMock(side_effect=RuntimeError("broadcast fail"))

        with patch("backend.websocket.manager.ws_manager", mock_ws_manager):
            stream.append(level="ERROR", logger_name="test", message="boom")
            task = asyncio.create_task(stream.run_broadcaster())
            await asyncio.sleep(0.05)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        captured = capsys.readouterr()
        assert "broadcast error" in captured.err
        assert "broadcast fail" in captured.err


class TestWebSocketBackendLogHandler:
    """Tests for the logging.Handler that feeds the stream."""

    def test_excluded_loggers_are_filtered(self):
        stream = WebSocketBackendLogStream(max_items=10)
        handler = WebSocketBackendLogHandler(stream)

        record = logging.LogRecord(
            name="backend.core.ws_backend_log_stream",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="should be filtered",
            args=(),
            exc_info=None,
        )
        handler.emit(record)

        items, _ = stream.snapshot()
        assert len(items) == 0

    def test_normal_logs_are_captured(self):
        stream = WebSocketBackendLogStream(max_items=10)
        handler = WebSocketBackendLogHandler(stream)

        record = logging.LogRecord(
            name="backend.services.agent_service",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="agent spawned",
            args=(),
            exc_info=None,
        )
        handler.emit(record)

        items, _ = stream.snapshot()
        assert len(items) == 1
        assert items[0]["message"] == "agent spawned"
        assert items[0]["level"] == "INFO"

    def test_uvicorn_access_is_excluded(self):
        stream = WebSocketBackendLogStream(max_items=10)
        handler = WebSocketBackendLogHandler(stream)

        record = logging.LogRecord(
            name="uvicorn.access",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="GET /health 200",
            args=(),
            exc_info=None,
        )
        handler.emit(record)

        items, _ = stream.snapshot()
        assert len(items) == 0
