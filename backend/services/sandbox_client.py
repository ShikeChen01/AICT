"""
Sandbox Client — stateless connection to individual sandbox containers.

Issues HTTP and WebSocket requests for sandbox operations (shell, screenshot, mouse, keyboard).
All connection parameters come from the database row, no in-memory cache.

This is a completely stateless client — each operation creates fresh connections.
"""

from __future__ import annotations

import asyncio
import secrets
from dataclasses import dataclass
from typing import Any

import httpx
import websockets

from backend.logging.my_logger import get_logger

logger = get_logger(__name__)

# Maximum bytes to buffer per shell command response before truncating
_MAX_SHELL_OUTPUT_BYTES = 1 * 1024 * 1024  # 1 MB

# Sentinel that sandbox server echoes back after we write a known marker
_CMD_END_MARKER = "__AICT_CMD_DONE_{marker}__"
_DRAIN_MARKER = "__AICT_DRAIN_{marker}__"


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


class SandboxClient:
    """
    Stateless sandbox client. All connection info comes from parameters.

    Each method creates a fresh httpx.AsyncClient or WebSocket connection
    and closes it when done. No in-memory connection cache or singleton state.

    The ``path_prefix`` parameter is used for desktop VMs whose traffic is
    proxied through the pool manager (e.g. ``/api/sandbox/{id}/proxy``).
    When set, REST endpoints become ``{prefix}/shell/execute`` instead of
    ``/shell/execute``.
    """

    @staticmethod
    def _base_url(host: str, port: int) -> str:
        return f"http://{host}:{port}"

    # ── Shell execution ───────────────────────────────────────────────────────

    async def execute_shell(
        self,
        host: str,
        port: int,
        auth_token: str,
        command: str,
        timeout: int = 120,
        *,
        path_prefix: str = "",
    ) -> ShellResult:
        """Execute a shell command via REST, with WS fallback for older sandboxes."""
        try:
            return await self._execute_shell_rest(host, port, auth_token, command, timeout, path_prefix=path_prefix)
        except RuntimeError as exc:
            if path_prefix:
                # WS fallback doesn't work through the proxy — re-raise
                raise
            logger.warning(
                "Shell REST path unavailable for %s:%s, falling back to WS shell: %s",
                host,
                port,
                exc,
            )
            return await self._execute_shell_ws(host, port, auth_token, command, timeout)

    async def _execute_shell_rest(
        self,
        host: str,
        port: int,
        auth_token: str,
        command: str,
        timeout: int = 120,
        *,
        path_prefix: str = "",
    ) -> ShellResult:
        """Execute a shell command via the sandbox server REST endpoint."""
        rest_base_url = self._base_url(host, port)
        async with httpx.AsyncClient(
            base_url=rest_base_url,
            headers={"Authorization": f"Bearer {auth_token}"},
            timeout=timeout + 10.0,
        ) as client:
            try:
                resp = await client.post(
                    f"{path_prefix}/shell/execute",
                    json={"command": command, "timeout": timeout},
                )
            except Exception as exc:
                logger.error("Shell REST error: %s", exc)
                raise RuntimeError(f"Shell execution failed: {exc}") from exc

        if resp.status_code == 408:
            logger.warning("Shell timeout after %ds", timeout)
            data = resp.json()
            return ShellResult(
                stdout=str(data.get("stdout", "Command timed out")),
                exit_code=None,
                truncated=False,
            )

        try:
            resp.raise_for_status()
        except Exception as exc:
            logger.error("Shell REST request failed: status=%s body=%s", resp.status_code, resp.text)
            raise RuntimeError(f"Shell execution failed: {exc}") from exc

        data = resp.json()
        stdout = str(data.get("stdout", ""))
        stdout_bytes = stdout.encode("utf-8", errors="replace")
        truncated = len(stdout_bytes) > _MAX_SHELL_OUTPUT_BYTES
        if truncated:
            stdout = stdout_bytes[-_MAX_SHELL_OUTPUT_BYTES :].decode("utf-8", errors="replace")
        exit_code = data.get("exit_code")
        try:
            exit_code = int(exit_code) if exit_code is not None else None
        except (TypeError, ValueError):
            exit_code = None
        return ShellResult(stdout=stdout, exit_code=exit_code, truncated=truncated)

    async def _execute_shell_ws(
        self,
        host: str,
        port: int,
        auth_token: str,
        command: str,
        timeout: int = 120,
    ) -> ShellResult:
        marker = secrets.token_hex(8)
        drain_sentinel = _DRAIN_MARKER.format(marker=marker)
        end_sentinel = _CMD_END_MARKER.format(marker=marker)
        ws_url = f"ws://{host}:{port}/ws/shell?token={auth_token}"

        async with websockets.connect(ws_url, max_size=2**22) as ws:
            await ws.send(self._encode_drain_command(drain_sentinel))
            await self._drain_shell_prompt(ws, drain_sentinel, timeout)
            await ws.send(self._encode_shell_command(command, end_sentinel))
            return await self._collect_shell_output(ws, end_sentinel, timeout)

    @staticmethod
    def _encode_drain_command(drain_sentinel: str) -> bytes:
        return f"printf '{drain_sentinel}\\n{drain_sentinel}\\n'\n".encode("utf-8")

    @staticmethod
    def _encode_shell_command(command: str, end_sentinel: str) -> bytes:
        wrapped = (
            f"{command}\n"
            "status=$?\n"
            f"printf '{end_sentinel}:%s\\n' \"$status\"\n"
        )
        return wrapped.encode("utf-8")

    @staticmethod
    def _decode_ws_chunk(payload: Any) -> bytes:
        if isinstance(payload, bytes):
            return payload
        if isinstance(payload, str):
            return payload.encode("utf-8", errors="replace")
        return b""

    async def _drain_shell_prompt(self, ws: Any, drain_sentinel: str, timeout: int | float) -> None:
        seen = 0
        deadline = asyncio.get_running_loop().time() + float(timeout)
        while seen < 2:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise RuntimeError("Shell prompt drain timed out")
            chunk = self._decode_ws_chunk(await asyncio.wait_for(ws.recv(), timeout=remaining))
            if not chunk:
                continue
            seen += chunk.decode("utf-8", errors="replace").count(drain_sentinel)

    async def _collect_shell_output(
        self,
        ws: Any,
        end_sentinel: str,
        timeout: int | float,
    ) -> ShellResult:
        deadline = asyncio.get_running_loop().time() + float(timeout)
        chunks: list[bytes] = []
        exit_code: int | None = None
        sentinel_bytes = end_sentinel.encode("utf-8")
        truncated = False

        while True:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                break
            try:
                chunk = self._decode_ws_chunk(await asyncio.wait_for(ws.recv(), timeout=remaining))
            except asyncio.TimeoutError:
                break
            if not chunk:
                break
            chunks.append(chunk)
            combined = b"".join(chunks)
            marker_index = combined.find(sentinel_bytes)
            if marker_index == -1:
                continue

            line_end = combined.find(b"\n", marker_index)
            if line_end == -1:
                continue

            sentinel_line = combined[marker_index:line_end].decode("utf-8", errors="replace")
            _, _, exit_text = sentinel_line.partition(":")
            try:
                exit_code = int(exit_text.strip())
            except ValueError:
                exit_code = None

            stdout_bytes = combined[:marker_index]
            truncated = line_end + 1 > _MAX_SHELL_OUTPUT_BYTES
            if len(stdout_bytes) > _MAX_SHELL_OUTPUT_BYTES:
                stdout_bytes = stdout_bytes[-_MAX_SHELL_OUTPUT_BYTES :]
            elif truncated:
                stdout_bytes = stdout_bytes[-_MAX_SHELL_OUTPUT_BYTES :]
            return ShellResult(
                stdout=stdout_bytes.decode("utf-8", errors="replace"),
                exit_code=exit_code,
                truncated=truncated,
            )

        stdout_bytes = b"".join(chunks)
        if len(stdout_bytes) > _MAX_SHELL_OUTPUT_BYTES:
            stdout_bytes = stdout_bytes[-_MAX_SHELL_OUTPUT_BYTES :]
            truncated = True
        return ShellResult(
            stdout=stdout_bytes.decode("utf-8", errors="replace"),
            exit_code=None,
            truncated=truncated,
        )

    # ── REST operations ───────────────────────────────────────────────────────

    async def health_check(self, host: str, port: int, auth_token: str, *, path_prefix: str = "") -> dict[str, Any]:
        async with httpx.AsyncClient(
            base_url=self._base_url(host, port),
            headers={"Authorization": f"Bearer {auth_token}"},
            timeout=30.0,
        ) as client:
            resp = await client.get(f"{path_prefix}/health")
            resp.raise_for_status()
            return resp.json()

    async def get_screenshot(self, host: str, port: int, auth_token: str, *, path_prefix: str = "") -> bytes:
        async with httpx.AsyncClient(
            base_url=self._base_url(host, port),
            headers={"Authorization": f"Bearer {auth_token}"},
            timeout=30.0,
        ) as client:
            resp = await client.get(f"{path_prefix}/screenshot", timeout=20.0)
            resp.raise_for_status()
            return resp.content

    async def mouse_move(self, host: str, port: int, auth_token: str, x: int, y: int, *, path_prefix: str = "") -> dict[str, Any]:
        async with httpx.AsyncClient(
            base_url=self._base_url(host, port),
            headers={"Authorization": f"Bearer {auth_token}"},
            timeout=30.0,
        ) as client:
            resp = await client.post(f"{path_prefix}/mouse/move", json={"x": x, "y": y})
            resp.raise_for_status()
            return resp.json()

    async def mouse_click(
        self, host: str, port: int, auth_token: str,
        x: int | None = None, y: int | None = None,
        button: int = 1, click_type: str = "single",
        *, path_prefix: str = "",
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"button": button, "click_type": click_type}
        if x is not None:
            payload["x"] = x
        if y is not None:
            payload["y"] = y
        async with httpx.AsyncClient(
            base_url=self._base_url(host, port),
            headers={"Authorization": f"Bearer {auth_token}"},
            timeout=30.0,
        ) as client:
            resp = await client.post(f"{path_prefix}/mouse/click", json=payload)
            resp.raise_for_status()
            return resp.json()

    async def mouse_scroll(
        self, host: str, port: int, auth_token: str,
        x: int | None = None, y: int | None = None,
        direction: str = "down", clicks: int = 3,
        *, path_prefix: str = "",
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"direction": direction, "clicks": clicks}
        if x is not None:
            payload["x"] = x
        if y is not None:
            payload["y"] = y
        async with httpx.AsyncClient(
            base_url=self._base_url(host, port),
            headers={"Authorization": f"Bearer {auth_token}"},
            timeout=30.0,
        ) as client:
            resp = await client.post(f"{path_prefix}/mouse/scroll", json=payload)
            resp.raise_for_status()
            return resp.json()

    async def mouse_location(self, host: str, port: int, auth_token: str, *, path_prefix: str = "") -> dict[str, Any]:
        async with httpx.AsyncClient(
            base_url=self._base_url(host, port),
            headers={"Authorization": f"Bearer {auth_token}"},
            timeout=30.0,
        ) as client:
            resp = await client.get(f"{path_prefix}/mouse/location")
            resp.raise_for_status()
            return resp.json()

    async def keyboard_press(
        self, host: str, port: int, auth_token: str,
        keys: str | None = None, text: str | None = None,
        *, path_prefix: str = "",
    ) -> dict[str, Any]:
        payload: dict[str, str] = {}
        if keys:
            payload["keys"] = keys
        if text:
            payload["text"] = text
        async with httpx.AsyncClient(
            base_url=self._base_url(host, port),
            headers={"Authorization": f"Bearer {auth_token}"},
            timeout=30.0,
        ) as client:
            resp = await client.post(f"{path_prefix}/keyboard", json=payload)
            resp.raise_for_status()
            return resp.json()

    async def start_recording(self, host: str, port: int, auth_token: str, *, path_prefix: str = "") -> dict[str, Any]:
        async with httpx.AsyncClient(
            base_url=self._base_url(host, port),
            headers={"Authorization": f"Bearer {auth_token}"},
            timeout=30.0,
        ) as client:
            resp = await client.post(f"{path_prefix}/record/start", timeout=10.0)
            resp.raise_for_status()
            return resp.json()

    async def stop_recording(self, host: str, port: int, auth_token: str, *, path_prefix: str = "") -> bytes:
        async with httpx.AsyncClient(
            base_url=self._base_url(host, port),
            headers={"Authorization": f"Bearer {auth_token}"},
            timeout=30.0,
        ) as client:
            resp = await client.post(f"{path_prefix}/record/stop", timeout=60.0)
            resp.raise_for_status()
            return resp.content


# Process-level singleton for backward compatibility
_client = SandboxClient()


def get_sandbox_client() -> SandboxClient:
    """Return the module-level stateless client instance."""
    return _client
