"""
Dev-mode tunnel for sandbox connections via kubectl port-forward.

When the backend runs locally (ENV=development), sandbox ClusterIP addresses
inside GKE are unreachable. This module manages kubectl port-forward
processes to create local tunnels, translating (ClusterIP, port) into
(localhost, local_port).

Production (Cloud Run) doesn't need this — Cloud Run reaches ClusterIPs
through the VPC connector.
"""

from __future__ import annotations

import asyncio
import os
import socket
import subprocess
import sys
from contextlib import closing

from backend.logging.my_logger import get_logger

logger = get_logger(__name__)

_SANDBOX_NAMESPACE = "sandboxes"


def _is_dev_mode() -> bool:
    """True when running locally (not on Cloud Run) with ENV=development."""
    if os.getenv("K_SERVICE"):
        return False
    return os.getenv("ENV", "").lower() == "development"


def _find_free_port() -> int:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _Tunnel:
    __slots__ = ("sandbox_id", "local_port", "process")

    def __init__(self, sandbox_id: str, local_port: int, process: subprocess.Popen):
        self.sandbox_id = sandbox_id
        self.local_port = local_port
        self.process = process


class SandboxTunnelManager:
    """Manages kubectl port-forward tunnels for local dev access to sandbox pods."""

    def __init__(self) -> None:
        self._tunnels: dict[str, _Tunnel] = {}
        self._lock = asyncio.Lock()

    async def get_host_port(self, sandbox_id: str, remote_port: int = 8080) -> tuple[str, int]:
        """Return (host, port) to reach a sandbox.

        In dev mode, starts a kubectl port-forward and returns localhost:local_port.
        """
        if not _is_dev_mode():
            raise RuntimeError("SandboxTunnelManager should only be used in dev mode")

        async with self._lock:
            tunnel = self._tunnels.get(sandbox_id)
            if tunnel and tunnel.process.poll() is None:
                return ("127.0.0.1", tunnel.local_port)

            if tunnel:
                del self._tunnels[sandbox_id]

        local_port = _find_free_port()
        svc_name = f"svc/sandbox-{sandbox_id}"

        logger.info(
            "Starting kubectl port-forward for sandbox %s: svc=%s local=%d remote=%d",
            sandbox_id, svc_name, local_port, remote_port,
        )

        creationflags = 0
        if sys.platform == "win32":
            creationflags = subprocess.CREATE_NO_WINDOW

        proc = subprocess.Popen(
            ["kubectl", "port-forward", "-n", _SANDBOX_NAMESPACE, svc_name, f"{local_port}:{remote_port}"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=creationflags,
        )

        tunnel = _Tunnel(sandbox_id, local_port, proc)
        async with self._lock:
            self._tunnels[sandbox_id] = tunnel

        for _ in range(30):
            await asyncio.sleep(0.3)
            if proc.poll() is not None:
                stderr = proc.stderr.read() if proc.stderr else b""
                logger.error(
                    "kubectl port-forward failed for sandbox %s (exit=%s): %s",
                    sandbox_id, proc.returncode, stderr.decode(errors="replace"),
                )
                async with self._lock:
                    self._tunnels.pop(sandbox_id, None)
                raise ConnectionError(f"kubectl port-forward failed: {stderr.decode(errors='replace')}")
            try:
                conn = socket.create_connection(("127.0.0.1", local_port), timeout=0.5)
                conn.close()
                logger.info(
                    "Tunnel ready for sandbox %s -> localhost:%d",
                    sandbox_id, local_port,
                )
                return ("127.0.0.1", local_port)
            except (ConnectionRefusedError, OSError):
                continue

        proc.kill()
        async with self._lock:
            self._tunnels.pop(sandbox_id, None)
        raise ConnectionError(f"kubectl port-forward timed out for sandbox {sandbox_id}")

    async def close_tunnel(self, sandbox_id: str) -> None:
        async with self._lock:
            tunnel = self._tunnels.pop(sandbox_id, None)
        if tunnel and tunnel.process.poll() is None:
            tunnel.process.terminate()
            try:
                tunnel.process.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                tunnel.process.kill()

    async def shutdown(self) -> None:
        async with self._lock:
            ids = list(self._tunnels.keys())
        for sid in ids:
            await self.close_tunnel(sid)


_tunnel_manager: SandboxTunnelManager | None = None


def get_tunnel_manager() -> SandboxTunnelManager:
    global _tunnel_manager
    if _tunnel_manager is None:
        _tunnel_manager = SandboxTunnelManager()
    return _tunnel_manager
