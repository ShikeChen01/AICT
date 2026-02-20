"""Docker SDK wrapper for sandbox container lifecycle."""

from __future__ import annotations

import secrets
from typing import Optional

import docker
from docker.errors import APIError, NotFound

from config import (
    CGROUP_PARENT,
    CONTAINER_CPU,
    CONTAINER_INTERNAL_PORT,
    CONTAINER_MEMORY,
    DOCKER_IMAGE,
)


class DockerManager:
    """Thin wrapper around the Docker SDK for sandbox container operations."""

    def __init__(self) -> None:
        self._client = docker.from_env()

    # ── Container lifecycle ───────────────────────────────────────────────────

    def create_container(
        self,
        sandbox_id: str,
        host_port: int,
        auth_token: str,
        volume_name: str,
    ) -> str:
        """
        Create and start a new sandbox container.
        Returns the container ID.
        """
        container = self._client.containers.run(
            image=DOCKER_IMAGE,
            name=f"sandbox-{sandbox_id}",
            detach=True,
            cgroup_parent=CGROUP_PARENT,
            nano_cpus=int(CONTAINER_CPU * 1e9),
            mem_limit=CONTAINER_MEMORY,
            ports={f"{CONTAINER_INTERNAL_PORT}/tcp": host_port},
            volumes={volume_name: {"bind": "/workspace", "mode": "rw"}},
            environment={"AUTH_TOKEN": auth_token},
            restart_policy={"Name": "no"},
        )
        return container.id

    def destroy_container(self, sandbox_id: str) -> None:
        """Stop and remove a container. Idempotent."""
        try:
            c = self._client.containers.get(f"sandbox-{sandbox_id}")
            c.stop(timeout=5)
            c.remove(force=True)
        except NotFound:
            pass
        except APIError as exc:
            raise RuntimeError(f"Docker error destroying sandbox-{sandbox_id}: {exc}") from exc

    def reset_container(
        self,
        sandbox_id: str,
        host_port: int,
        auth_token: str,
        volume_name: str,
    ) -> str:
        """Destroy and recreate a container with the same volume. Returns new container ID."""
        self.destroy_container(sandbox_id)
        return self.create_container(sandbox_id, host_port, auth_token, volume_name)

    def is_running(self, sandbox_id: str) -> bool:
        """Check whether the container process is running."""
        try:
            c = self._client.containers.get(f"sandbox-{sandbox_id}")
            c.reload()
            return c.status == "running"
        except NotFound:
            return False

    def list_sandbox_containers(self) -> list[dict]:
        """List all sandbox-* containers (running or stopped)."""
        containers = self._client.containers.list(
            all=True,
            filters={"name": "sandbox-"},
        )
        result = []
        for c in containers:
            result.append({
                "name": c.name,
                "id": c.id,
                "status": c.status,
                "ports": c.ports,
            })
        return result

    # ── Volume lifecycle ──────────────────────────────────────────────────────

    def ensure_volume(self, volume_name: str) -> None:
        """Create a named volume if it doesn't already exist."""
        try:
            self._client.volumes.get(volume_name)
        except NotFound:
            self._client.volumes.create(name=volume_name)

    def remove_volume(self, volume_name: str) -> None:
        """Remove a named volume. Idempotent."""
        try:
            vol = self._client.volumes.get(volume_name)
            vol.remove(force=True)
        except NotFound:
            pass
