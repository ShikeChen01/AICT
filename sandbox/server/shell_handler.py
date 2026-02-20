"""PTY-based shell handler with ring buffer output and WebSocket streaming."""

from __future__ import annotations

import asyncio
import fcntl
import os
import pty
import signal
import struct
import termios
from collections import deque

from fastapi import WebSocket, WebSocketDisconnect

from config import RING_BUFFER_BYTES

TRUNCATION_NOTICE = b"\n[... output truncated - ring buffer full ...]\n"


class RingBuffer:
    """Byte ring buffer that drops oldest data when full."""

    def __init__(self, max_bytes: int) -> None:
        self._max = max_bytes
        self._buf: deque[bytes] = deque()
        self._size = 0

    def write(self, data: bytes) -> None:
        self._buf.append(data)
        self._size += len(data)
        while self._size > self._max:
            dropped = self._buf.popleft()
            self._size -= len(dropped)
            # Prepend truncation notice once per overflow event
            self._buf.appendleft(TRUNCATION_NOTICE)
            self._size += len(TRUNCATION_NOTICE)

    def read_all(self) -> bytes:
        return b"".join(self._buf)

    def clear(self) -> None:
        self._buf.clear()
        self._size = 0


class ShellSession:
    """One persistent PTY shell (bash) bound to a WebSocket connection."""

    def __init__(self, ws: WebSocket) -> None:
        self.ws = ws
        self._pid: int | None = None
        self._master_fd: int | None = None
        self._ring = RingBuffer(RING_BUFFER_BYTES)
        self._reader_task: asyncio.Task | None = None

    async def start(self) -> None:
        """Fork a PTY + bash process and start the read loop."""
        pid, master_fd = pty.fork()
        if pid == 0:
            # Child — exec bash
            os.execvp("/bin/bash", ["/bin/bash"])
        else:
            self._pid = pid
            self._master_fd = master_fd
            # Keep the fd blocking — _read_fd runs in an executor thread so it
            # is fine to block there. O_NONBLOCK would cause os.read to raise
            # EAGAIN immediately when no data is ready, breaking the read loop
            # before any output arrives.
            self._reader_task = asyncio.get_event_loop().create_task(self._read_loop())

    async def _read_loop(self) -> None:
        """Read PTY output and stream it to the WebSocket."""
        loop = asyncio.get_event_loop()
        fd = self._master_fd
        try:
            while True:
                try:
                    data = await loop.run_in_executor(None, self._read_fd, fd)
                    if not data:
                        break
                    self._ring.write(data)
                    await self.ws.send_bytes(data)
                except OSError:
                    break
        except WebSocketDisconnect:
            pass
        finally:
            await self.close()

    def _read_fd(self, fd: int) -> bytes:
        """Blocking read from PTY fd (runs in executor)."""
        try:
            return os.read(fd, 4096)
        except OSError:
            return b""

    async def send_input(self, data: bytes) -> None:
        """Write data (keystrokes / commands) to the PTY."""
        if self._master_fd is None:
            return
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, os.write, self._master_fd, data)

    async def resize(self, rows: int, cols: int) -> None:
        """Handle terminal resize (TIOCSWINSZ)."""
        if self._master_fd is None:
            return
        size = struct.pack("HHHH", rows, cols, 0, 0)
        fcntl.ioctl(self._master_fd, termios.TIOCSWINSZ, size)

    async def close(self) -> None:
        """Kill the shell process and close the fd."""
        if self._reader_task and not self._reader_task.done():
            self._reader_task.cancel()
        if self._pid is not None:
            try:
                os.kill(self._pid, signal.SIGKILL)
                os.waitpid(self._pid, 0)
            except (ProcessLookupError, ChildProcessError):
                pass
            self._pid = None
        if self._master_fd is not None:
            try:
                os.close(self._master_fd)
            except OSError:
                pass
            self._master_fd = None


async def handle_shell_ws(ws: WebSocket, token: str) -> None:
    """
    WebSocket handler for /ws/shell.
    Protocol:
      - Client → server: raw bytes (keystrokes / commands)
      - Server → client: raw bytes (PTY output)
      - Client can send JSON {"type":"resize","rows":N,"cols":N} for resize
    """
    import json

    await ws.accept()
    session = ShellSession(ws)
    await session.start()
    try:
        while True:
            data = await ws.receive_bytes()
            # Check if it's a resize control message
            try:
                msg = json.loads(data)
                if isinstance(msg, dict) and msg.get("type") == "resize":
                    await session.resize(int(msg["rows"]), int(msg["cols"]))
                    continue
            except (ValueError, KeyError):
                pass
            await session.send_input(data)
    except WebSocketDisconnect:
        pass
    finally:
        await session.close()
