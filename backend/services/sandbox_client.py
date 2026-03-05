"""
Sandbox Client — connection multiplexer to individual sandbox containers.

Maintains one persistent WebSocket per sandbox for shell streaming, and
issues HTTP requests for stateless operations (screenshot, mouse, keyboard).

Agents and tool executors never deal with container IPs, ports, or tokens
directly — they call this client by sandbox_id only.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

import httpx

from backend.logging.my_logger import get_logger

logger = get_logger(__name__)

# Maximum bytes to buffer per shell command response before truncating
_MAX_SHELL_OUTPUT_BYTES = 1 * 1024 * 1024  # 1 MB

# Sentinel that sandbox server echoes back after we write a known marker
_CMD_END_MARKER = "__AICT_CMD_DONE_{marker}__"


@dataclass
class ShellResult:
    stdout: str
    exit_code: int | None = None
    truncated: bool = False

    def __str__(self) -> str:
        parts = []
        if self.truncated:
            parts.append("[output truncated]")
        parts.append(self.stdout)
        if self.exit_code is not None:
            parts.append(f"Exit Code: {self.exit_code}")
        return "\n".join(parts)


@dataclass
class SandboxConnection:
    """State for a single sandbox's connection to the backend."""

    sandbox_id: str
    rest_base_url: str   # http://{vm_host}:{port}
    auth_token: str
    status: str = "idle"  # "idle" | "connected" | "dead"

    # Per-connection HTTP client (persistent, auth pre-configured)
    _http: httpx.AsyncClient | None = field(default=None, repr=False)

    def http(self) -> httpx.AsyncClient:
        if self._http is None or self._http.is_closed:
            self._http = httpx.AsyncClient(
                base_url=self.rest_base_url,
                headers={"Authorization": f"Bearer {self.auth_token}"},
                timeout=30.0,
            )
        return self._http

    async def close(self) -> None:
        if self._http and not self._http.is_closed:
            await self._http.aclose()
        self._http = None


class SandboxClient:
    """
    Multiplexer: one instance shared across the backend process.
    Thread-safe via asyncio.

    Connections are lazily created on first use and cached.
    """

    def __init__(self) -> None:
        self._connections: dict[str, SandboxConnection] = {}
        self._lock = asyncio.Lock()

    # ── Connection management ─────────────────────────────────────────────────

    def register(
        self,
        sandbox_id: str,
        vm_host: str,
        host_port: int,
        auth_token: str,
    ) -> None:
        """Register a sandbox connection (called after pool manager assigns one)."""
        conn = SandboxConnection(
            sandbox_id=sandbox_id,
            rest_base_url=f"http://{vm_host}:{host_port}",
            auth_token=auth_token,
        )
        self._connections[sandbox_id] = conn

    def unregister(self, sandbox_id: str) -> None:
        """Remove a sandbox connection (called when sandbox is released)."""
        conn = self._connections.pop(sandbox_id, None)
        if conn:
            asyncio.create_task(conn.close())

    def has_connection(self, sandbox_id: str) -> bool:
        """Check if a connection is registered for the given sandbox_id."""
        return sandbox_id in self._connections

    def _get_conn(self, sandbox_id: str) -> SandboxConnection:
        conn = self._connections.get(sandbox_id)
        if not conn:
            raise RuntimeError(f"No connection registered for sandbox {sandbox_id!r}")
        return conn

    # ── Shell execution ───────────────────────────────────────────────────────

    async def execute_shell(
        self,
        sandbox_id: str,
        command: str,
        timeout: int = 120,
    ) -> ShellResult:
        """
        Execute a shell command via WebSocket PTY streaming.

        Strategy:
          1. Open WS to /ws/shell
          2. Drain the initial bash prompt / startup noise
          3. Disable PTY echo and prompt so only real command output is returned
          4. Send command + a unique end-marker echo
          5. Collect output until end-marker appears or timeout
          6. Parse exit code from shell (via $? captured after command)
          7. Close WS
        """
        import secrets
        import websockets

        conn = self._get_conn(sandbox_id)
        ws_url = conn.rest_base_url.replace("http://", "ws://") + f"/ws/shell?token={conn.auth_token}"

        marker = secrets.token_hex(8)
        end_sentinel = _CMD_END_MARKER.format(marker=marker)

        # Preamble: disable PTY echo and silence the bash prompt so that the
        # only bytes coming back over the WebSocket are real command stdout/stderr.
        # Without this the PTY echoes each byte we send back to us, which means
        # the sentinel string appears in the stream BEFORE the command executes,
        # causing the reader to break immediately with an empty (or echoed) result.
        setup_preamble = "stty -echo 2>/dev/null; PS1=''; PS2=''; export TERM=dumb\n"

        # After the real command, capture $? and echo the end-marker with exit code.
        full_cmd = f"{command}\n__exit__=$?\necho '{end_sentinel}:'$__exit__\n"

        output_chunks: list[bytes] = []
        total_bytes = 0
        truncated = False
        exit_code: int | None = None

        try:
            async with websockets.connect(ws_url, open_timeout=10) as ws:
                # Step 1: send setup preamble and drain its output. PTY echo is still on
                # when we send, so the sentinel appears twice: once echoed, once from the
                # real echo command. Wait for the second occurrence so the shell is ready.
                drain_sentinel = f"__AICT_DRAIN_{marker}__"
                sentinel_bytes = drain_sentinel.encode()
                await ws.send(f"{setup_preamble}echo '{drain_sentinel}'\n".encode())

                drain_buf = b""
                seen_count = 0

                async def _drain() -> None:
                    nonlocal drain_buf, seen_count
                    while True:
                        raw = await ws.recv()
                        if isinstance(raw, str):
                            raw = raw.encode()
                        drain_buf += raw
                        seen_count = drain_buf.count(sentinel_bytes)
                        if seen_count >= 2:
                            break

                await asyncio.wait_for(_drain(), timeout=10)

                # Brief delay so any remaining preamble output flushes before we send the command.
                await asyncio.sleep(0.05)

                # Step 2: send the real command and collect output until end sentinel.
                await ws.send(full_cmd.encode())

                async def _read() -> None:
                    nonlocal total_bytes, truncated, exit_code
                    while True:
                        raw = await ws.recv()
                        if isinstance(raw, str):
                            raw = raw.encode()
                        output_chunks.append(raw)
                        total_bytes += len(raw)
                        if total_bytes > _MAX_SHELL_OUTPUT_BYTES:
                            truncated = True
                            while total_bytes > _MAX_SHELL_OUTPUT_BYTES // 2 and len(output_chunks) > 1:
                                dropped = output_chunks.pop(0)
                                total_bytes -= len(dropped)

                        combined = b"".join(output_chunks).decode("utf-8", errors="replace")
                        if end_sentinel in combined:
                            idx = combined.find(end_sentinel)
                            marker_line = combined[idx:]
                            colon_idx = marker_line.find(":")
                            if colon_idx != -1:
                                try:
                                    exit_code = int(marker_line[colon_idx + 1:].split()[0])
                                except (ValueError, IndexError):
                                    exit_code = None
                            break

                await asyncio.wait_for(_read(), timeout=timeout)

        except asyncio.TimeoutError:
            logger.warning("Shell timeout on sandbox %s after %ds", sandbox_id, timeout)
            exit_code = None
        except Exception as exc:
            logger.error("Shell WS error on sandbox %s: %s", sandbox_id, exc)
            raise RuntimeError(f"Shell execution failed: {exc}") from exc

        combined = b"".join(output_chunks).decode("utf-8", errors="replace")
        # Strip the sentinel line (and anything after it) from the output
        if end_sentinel in combined:
            combined = combined[: combined.find(end_sentinel)].rstrip()

        return ShellResult(stdout=combined, exit_code=exit_code, truncated=truncated)

    # ── REST operations ───────────────────────────────────────────────────────

    async def health_check(self, sandbox_id: str) -> dict[str, Any]:
        conn = self._get_conn(sandbox_id)
        resp = await conn.http().get("/health")
        resp.raise_for_status()
        return resp.json()

    async def get_screenshot(self, sandbox_id: str) -> bytes:
        conn = self._get_conn(sandbox_id)
        resp = await conn.http().get("/screenshot", timeout=20.0)
        resp.raise_for_status()
        return resp.content

    async def mouse_move(self, sandbox_id: str, x: int, y: int) -> dict[str, Any]:
        conn = self._get_conn(sandbox_id)
        resp = await conn.http().post("/mouse/move", json={"x": x, "y": y})
        resp.raise_for_status()
        return resp.json()

    async def mouse_click(
        self,
        sandbox_id: str,
        x: int | None = None,
        y: int | None = None,
        button: int = 1,
        click_type: str = "single",
    ) -> dict[str, Any]:
        conn = self._get_conn(sandbox_id)
        payload: dict[str, Any] = {"button": button, "click_type": click_type}
        if x is not None:
            payload["x"] = x
        if y is not None:
            payload["y"] = y
        resp = await conn.http().post("/mouse/click", json=payload)
        resp.raise_for_status()
        return resp.json()

    async def mouse_scroll(
        self,
        sandbox_id: str,
        x: int | None = None,
        y: int | None = None,
        direction: str = "down",
        clicks: int = 3,
    ) -> dict[str, Any]:
        conn = self._get_conn(sandbox_id)
        payload: dict[str, Any] = {"direction": direction, "clicks": clicks}
        if x is not None:
            payload["x"] = x
        if y is not None:
            payload["y"] = y
        resp = await conn.http().post("/mouse/scroll", json=payload)
        resp.raise_for_status()
        return resp.json()

    async def mouse_location(self, sandbox_id: str) -> dict[str, Any]:
        conn = self._get_conn(sandbox_id)
        resp = await conn.http().get("/mouse/location")
        resp.raise_for_status()
        return resp.json()

    async def keyboard_press(
        self,
        sandbox_id: str,
        keys: str | None = None,
        text: str | None = None,
    ) -> dict[str, Any]:
        conn = self._get_conn(sandbox_id)
        payload: dict[str, str] = {}
        if keys:
            payload["keys"] = keys
        if text:
            payload["text"] = text
        resp = await conn.http().post("/keyboard", json=payload)
        resp.raise_for_status()
        return resp.json()

    async def start_recording(self, sandbox_id: str) -> dict[str, Any]:
        conn = self._get_conn(sandbox_id)
        resp = await conn.http().post("/record/start", timeout=10.0)
        resp.raise_for_status()
        return resp.json()

    async def stop_recording(self, sandbox_id: str) -> bytes:
        conn = self._get_conn(sandbox_id)
        resp = await conn.http().post("/record/stop", timeout=60.0)
        resp.raise_for_status()
        return resp.content

    async def close_all(self) -> None:
        for conn in list(self._connections.values()):
            await conn.close()
        self._connections.clear()


# Process-level singleton — instantiated once at backend startup
_sandbox_client: SandboxClient | None = None


def get_sandbox_client() -> SandboxClient:
    global _sandbox_client
    if _sandbox_client is None:
        _sandbox_client = SandboxClient()
    return _sandbox_client
