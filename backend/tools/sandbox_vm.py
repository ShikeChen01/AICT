"""
LangGraph-compatible tool wrappers for the VM sandbox system.

These wrap SandboxService operations as @tool functions for use
in the LangGraph engineer graph (registry.py).

The inner loop (loop_registry.py) uses its own executor functions directly;
these are only for the LangGraph codepath.
"""

from __future__ import annotations

import uuid

from langchain_core.tools import tool
from sqlalchemy import select

from backend.db.session import AsyncSessionLocal
from backend.db.models import Agent
from backend.logging.my_logger import get_logger

logger = get_logger(__name__)


async def _get_agent(agent_id: str, session) -> Agent | None:
    result = await session.execute(select(Agent).where(Agent.id == uuid.UUID(agent_id)))
    return result.scalar_one_or_none()


@tool
async def sandbox_start_session(agent_id: str) -> str:
    """
    Ensure a sandbox container is running for the agent.

    Args:
        agent_id: UUID of the agent.
    """
    from backend.services.sandbox_service import SandboxService

    async with AsyncSessionLocal() as session:
        agent = await _get_agent(agent_id, session)
        if not agent:
            return "Error: Agent not found."
        svc = SandboxService()
        meta = await svc.ensure_running_sandbox(session, agent)
        await session.flush()
        return meta.message or f"Sandbox ready: {meta.sandbox_id}"


@tool
async def sandbox_end_session(agent_id: str) -> str:
    """
    Release the agent's sandbox back to the pool.

    Args:
        agent_id: UUID of the agent.
    """
    from backend.services.sandbox_service import SandboxService

    async with AsyncSessionLocal() as session:
        agent = await _get_agent(agent_id, session)
        if not agent:
            return "Error: Agent not found."
        if not agent.sandbox_id:
            return "No active sandbox."
        svc = SandboxService()
        await svc.close_sandbox(session, agent)
        await session.flush()
        return "Sandbox session ended."


@tool
async def sandbox_health(agent_id: str) -> str:
    """
    Check sandbox health.

    Args:
        agent_id: UUID of the agent.
    """
    from backend.services.sandbox_service import SandboxService

    async with AsyncSessionLocal() as session:
        agent = await _get_agent(agent_id, session)
        if not agent or not agent.sandbox_id:
            return "Error: No sandbox for agent."
        svc = SandboxService()
        data = await svc.sandbox_health(agent)
        return f"status={data.get('status')} uptime={data.get('uptime_seconds')}s"


@tool
async def sandbox_execute_command(agent_id: str, command: str, timeout: int = 120) -> str:
    """
    Execute a shell command in the agent's sandbox.

    Args:
        agent_id: UUID of the agent.
        command: Shell command to run.
        timeout: Timeout in seconds (default 120).
    """
    from backend.services.sandbox_service import SandboxService

    async with AsyncSessionLocal() as session:
        agent = await _get_agent(agent_id, session)
        if not agent:
            return "Error: Agent not found."
        svc = SandboxService()
        result = await svc.execute_command(session, agent, command, timeout=timeout)
        await session.flush()
        parts = [f"Sandbox: {agent.sandbox_id}"]
        if result.truncated:
            parts.append("[output truncated]")
        parts.append(result.stdout)
        if result.exit_code is not None:
            parts.append(f"Exit Code: {result.exit_code}")
        return "\n".join(parts)


@tool
async def sandbox_screenshot(agent_id: str) -> str:
    """
    Take a screenshot of the sandbox display.

    Args:
        agent_id: UUID of the agent.
    """
    import base64
    from backend.services.sandbox_service import SandboxService

    async with AsyncSessionLocal() as session:
        agent = await _get_agent(agent_id, session)
        if not agent or not agent.sandbox_id:
            return "Error: No sandbox for agent."
        svc = SandboxService()
        img_bytes = await svc.take_screenshot(agent)
        b64 = base64.b64encode(img_bytes).decode()
        return f"Screenshot ({len(img_bytes)} bytes base64 JPEG):\n{b64}"


@tool
async def sandbox_mouse_move(agent_id: str, x: int, y: int) -> str:
    """
    Move mouse to (x, y) in the sandbox display.

    Args:
        agent_id: UUID of the agent.
        x: X coordinate.
        y: Y coordinate.
    """
    from backend.services.sandbox_service import SandboxService

    async with AsyncSessionLocal() as session:
        agent = await _get_agent(agent_id, session)
        if not agent or not agent.sandbox_id:
            return "Error: No sandbox for agent."
        svc = SandboxService()
        await svc.mouse_move(agent, x, y)
        return f"Mouse moved to ({x}, {y})"


@tool
async def sandbox_mouse_location(agent_id: str) -> str:
    """
    Get current mouse cursor position in sandbox.

    Args:
        agent_id: UUID of the agent.
    """
    from backend.services.sandbox_service import SandboxService

    async with AsyncSessionLocal() as session:
        agent = await _get_agent(agent_id, session)
        if not agent or not agent.sandbox_id:
            return "Error: No sandbox for agent."
        svc = SandboxService()
        loc = await svc.mouse_location(agent)
        return f"Mouse at x={loc.get('x')}, y={loc.get('y')}"


@tool
async def sandbox_keyboard_press(
    agent_id: str,
    keys: str | None = None,
    text: str | None = None,
) -> str:
    """
    Send keyboard input to the sandbox.

    Args:
        agent_id: UUID of the agent.
        keys: xdotool key combo (e.g. 'ctrl+c', 'Return').
        text: Raw text to type.
    """
    from backend.services.sandbox_service import SandboxService

    if not keys and not text:
        return "Error: provide 'keys' or 'text'."
    async with AsyncSessionLocal() as session:
        agent = await _get_agent(agent_id, session)
        if not agent or not agent.sandbox_id:
            return "Error: No sandbox for agent."
        svc = SandboxService()
        await svc.keyboard_press(agent, keys=keys, text=text)
        return f"Input sent: keys={keys!r} text={text!r}"


@tool
async def sandbox_record_screen(agent_id: str) -> str:
    """
    Start recording the sandbox screen.

    Args:
        agent_id: UUID of the agent.
    """
    from backend.services.sandbox_service import SandboxService

    async with AsyncSessionLocal() as session:
        agent = await _get_agent(agent_id, session)
        if not agent or not agent.sandbox_id:
            return "Error: No sandbox for agent."
        svc = SandboxService()
        data = await svc.start_recording(agent)
        return f"Recording started: {data.get('status')}"


@tool
async def sandbox_end_record_screen(agent_id: str) -> str:
    """
    Stop recording and return video as base64.

    Args:
        agent_id: UUID of the agent.
    """
    import base64
    from backend.services.sandbox_service import SandboxService

    async with AsyncSessionLocal() as session:
        agent = await _get_agent(agent_id, session)
        if not agent or not agent.sandbox_id:
            return "Error: No sandbox for agent."
        svc = SandboxService()
        video_bytes = await svc.stop_recording(agent)
        b64 = base64.b64encode(video_bytes).decode()
        return f"Recording stopped ({len(video_bytes)} bytes base64 MP4):\n{b64}"
