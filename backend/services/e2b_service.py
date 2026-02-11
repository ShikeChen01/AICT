"""
E2B sandbox lifecycle service.

This module currently provides a local metadata-backed sandbox abstraction.
It can be swapped to real E2B SDK calls later without changing callers.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import Agent
from backend.core.exceptions import SandboxNotFoundError


@dataclass(slots=True)
class SandboxMetadata:
    sandbox_id: str
    agent_id: str
    persistent: bool
    status: str


class E2BService:
    """Manage sandbox metadata and agent sandbox references."""

    async def create_sandbox(
        self,
        session: AsyncSession,
        agent: Agent,
        persistent: bool,
    ) -> SandboxMetadata:
        sandbox_id = f"sbox-{uuid.uuid4()}"
        agent.sandbox_id = sandbox_id
        agent.sandbox_persist = persistent
        await session.flush()
        return SandboxMetadata(
            sandbox_id=sandbox_id,
            agent_id=str(agent.id),
            persistent=persistent,
            status="running",
        )

    async def get_sandbox(self, session: AsyncSession, agent: Agent) -> SandboxMetadata:
        if not agent.sandbox_id:
            raise SandboxNotFoundError(str(agent.id))
        return SandboxMetadata(
            sandbox_id=agent.sandbox_id,
            agent_id=str(agent.id),
            persistent=bool(agent.sandbox_persist),
            status="running",
        )

    async def close_sandbox(self, session: AsyncSession, agent: Agent) -> None:
        if not agent.sandbox_id:
            raise SandboxNotFoundError(str(agent.id))
        agent.sandbox_id = None
        await session.flush()

