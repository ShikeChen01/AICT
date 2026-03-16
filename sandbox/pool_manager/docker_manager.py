"""Docker SDK wrapper for sandbox container lifecycle."""

from __future__ import annotations

import secrets
from typing import Optional

import docker
from docker.errors import APIError, NotFound

from config import (
    CGROUP_PARENT,
    CONTAINER_CPU_SHARES,
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
            # cpu_shares is a relative weight (not a hard quota).  Containers
            # can freely burst to use idle cores; the kernel only enforces the
            # weight when CPUs are genuinely contested, enabling
            # oversubscription across up to 35 sandboxes on a 4-core host.
            cpu_shares=CONTAINER_CPU_SHARES,
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

    # ── Snapshot operations ────────────────────────────────────────────────────

    def commit_container(self, sandbox_id: str, snapshot_name: str) -> str:
        """Commit the current container state to a new image. Returns image tag."""
        try:
            c = self._client.containers.get(f"sandbox-{sandbox_id}")
            c.commit(repository=snapshot_name, tag="latest")
            return f"{snapshot_name}:latest"
        except NotFound:
            raise RuntimeError(f"Container sandbox-{sandbox_id} not found for snapshot")

    def restore_from_snapshot(
        self,
        sandbox_id: str,
        snapshot_name: str,
        host_port: int,
        auth_token: str,
        volume_name: str,
    ) -> str:
        """Restore a container from a previously committed snapshot image."""
        self.destroy_container(sandbox_id)
        # Create from the snapshot image instead of the default base
        container = self._client.containers.run(
            image=f"{snapshot_name}:latest" if ":" not in snapshot_name else snapshot_name,
            name=f"sandbox-{sandbox_id}",
            detach=True,
            cgroup_parent=CGROUP_PARENT,
            cpu_shares=CONTAINER_CPU_SHARES,
            mem_limit=CONTAINER_MEMORY,
            ports={f"{CONTAINER_INTERNAL_PORT}/tcp": host_port},
            volumes={volume_name: {"bind": "/workspace", "mode": "rw"}} if volume_name else {},
            environment={"AUTH_TOKEN": auth_token},
            restart_policy={"Name": "no"},
        )
        return container.id

    def list_snapshots(self, sandbox_id: str) -> list[dict]:
        """List snapshot images for a given sandbox."""
        prefix = f"sandbox-snap-{sandbox_id}"
        images = self._client.images.list(name=prefix)
        return [
            {"name": img.tags[0] if img.tags else img.short_id, "id": img.short_id}
            for img in images
        ]

    # ── Stats ─────────────────────────────────────────────────────────────────

    def get_container_memory_mb(self, sandbox_id: str) -> float | None:
        """Return RSS memory usage in MB for a running container, or None if unavailable."""
        try:
            c = self._client.containers.get(f"sandbox-{sandbox_id}")
            raw = c.stats(stream=False)
            mem_usage = raw["memory_stats"].get("usage", 0)
            cache = raw["memory_stats"].get("stats", {}).get("cache", 0)
            return round((mem_usage - cache) / (1024 * 1024), 2)
        except (NotFound, KeyError):
            return None
