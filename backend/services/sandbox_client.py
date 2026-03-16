"""
Sandbox Client — stateless connection to individual sandbox containers.

Issues HTTP and WebSocket requests for sandbox operations (shell, screenshot, mouse, keyboard).
All connection parameters come from the database row, no in-memory cache.

This is a completely stateless client — each operation creates fresh connections.
"""

from __future__ import annotations

from dataclasses import dataclass
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


class SandboxClient:
    """
    Stateless sandbox client. All connection info comes from parameters.

    Each method creates a fresh httpx.AsyncClient or WebSocket connection
    and closes it when done. No in-memory connection cache or singleton state.
    """

    # ── Shell execution ───────────────────────────────────────────────────────

    async def execute_shell(
        self,
        host: str,
        port: int,
        auth_token: str,
        command: str,
        timeout: int = 120,
    ) -> ShellResult:
        """Execute a shell command via the sandbox server REST endpoint."""
        rest_base_url = f"http://{host}:{port}"
        async with httpx.AsyncClient(
            base_url=rest_base_url,
            headers={"Authorization": f"Bearer {auth_token}"},
            timeout=timeout + 10.0,
        ) as client:
            try:
                resp = await client.post(
                    "/shell/execute",
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

    # ── REST operations ───────────────────────────────────────────────────────

    async def health_check(self, host: str, port: int, auth_token: str) -> dict[str, Any]:
        rest_base_url = f"http://{host}:{port}"
        async with httpx.AsyncClient(
            base_url=rest_base_url,
            headers={"Authorization": f"Bearer {auth_token}"},
            timeout=30.0,
        ) as client:
            resp = await client.get("/health")
            resp.raise_for_status()
            return resp.json()

    async def get_screenshot(self, host: str, port: int, auth_token: str) -> bytes:
        rest_base_url = f"http://{host}:{port}"
        async with httpx.AsyncClient(
            base_url=rest_base_url,
            headers={"Authorization": f"Bearer {auth_token}"},
            timeout=30.0,
        ) as client:
            resp = await client.get("/screenshot", timeout=20.0)
            resp.raise_for_status()
            return resp.content

    async def mouse_move(self, host: str, port: int, auth_token: str, x: int, y: int) -> dict[str, Any]:
        rest_base_url = f"http://{host}:{port}"
        async with httpx.AsyncClient(
            base_url=rest_base_url,
            headers={"Authorization": f"Bearer {auth_token}"},
            timeout=30.0,
        ) as client:
            resp = await client.post("/mouse/move", json={"x": x, "y": y})
            resp.raise_for_status()
            return resp.json()

    async def mouse_click(
        self,
        host: str,
        port: int,
        auth_token: str,
        x: int | None = None,
        y: int | None = None,
        button: int = 1,
        click_type: str = "single",
    ) -> dict[str, Any]:
        rest_base_url = f"http://{host}:{port}"
        payload: dict[str, Any] = {"button": button, "click_type": click_type}
        if x is not None:
            payload["x"] = x
        if y is not None:
            payload["y"] = y
        async with httpx.AsyncClient(
            base_url=rest_base_url,
            headers={"Authorization": f"Bearer {auth_token}"},
            timeout=30.0,
        ) as client:
            resp = await client.post("/mouse/click", json=payload)
            resp.raise_for_status()
            return resp.json()

    async def mouse_scroll(
        self,
        host: str,
        port: int,
        auth_token: str,
        x: int | None = None,
        y: int | None = None,
        direction: str = "down",
        clicks: int = 3,
    ) -> dict[str, Any]:
        rest_base_url = f"http://{host}:{port}"
        payload: dict[str, Any] = {"direction": direction, "clicks": clicks}
        if x is not None:
            payload["x"] = x
        if y is not None:
            payload["y"] = y
        async with httpx.AsyncClient(
            base_url=rest_base_url,
            headers={"Authorization": f"Bearer {auth_token}"},
            timeout=30.0,
        ) as client:
            resp = await client.post("/mouse/scroll", json=payload)
            resp.raise_for_status()
            return resp.json()

    async def mouse_location(self, host: str, port: int, auth_token: str) -> dict[str, Any]:
        rest_base_url = f"http://{host}:{port}"
        async with httpx.AsyncClient(
            base_url=rest_base_url,
            headers={"Authorization": f"Bearer {auth_token}"},
            timeout=30.0,
        ) as client:
            resp = await client.get("/mouse/location")
            resp.raise_for_status()
            return resp.json()

    async def keyboard_press(
        self,
        host: str,
        port: int,
        auth_token: str,
        keys: str | None = None,
        text: str | None = None,
    ) -> dict[str, Any]:
        rest_base_url = f"http://{host}:{port}"
        payload: dict[str, str] = {}
        if keys:
            payload["keys"] = keys
        if text:
            payload["text"] = text
        async with httpx.AsyncClient(
            base_url=rest_base_url,
            headers={"Authorization": f"Bearer {auth_token}"},
            timeout=30.0,
        ) as client:
            resp = await client.post("/keyboard", json=payload)
            resp.raise_for_status()
            return resp.json()

    async def start_recording(self, host: str, port: int, auth_token: str) -> dict[str, Any]:
        rest_base_url = f"http://{host}:{port}"
        async with httpx.AsyncClient(
            base_url=rest_base_url,
            headers={"Authorization": f"Bearer {auth_token}"},
            timeout=30.0,
        ) as client:
            resp = await client.post("/record/start", timeout=10.0)
            resp.raise_for_status()
            return resp.json()

    async def stop_recording(self, host: str, port: int, auth_token: str) -> bytes:
        rest_base_url = f"http://{host}:{port}"
        async with httpx.AsyncClient(
            base_url=rest_base_url,
            headers={"Authorization": f"Bearer {auth_token}"},
            timeout=30.0,
        ) as client:
            resp = await client.post("/record/stop", timeout=60.0)
            resp.raise_for_status()
            return resp.content


# Process-level singleton for backward compatibility
_client = SandboxClient()


def get_sandbox_client() -> SandboxClient:
    """Return the module-level stateless client instance."""
    return _client
