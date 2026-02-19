"""
E2B Sandbox tools for LangGraph agents.
"""

import uuid
import os
from langchain_core.tools import tool
from sqlalchemy import select

from backend.db.session import AsyncSessionLocal
from backend.db.models import Agent
from backend.config import settings
from backend.logging.my_logger import get_logger
from backend.services.e2b_service import E2BService, LOCAL_FALLBACK_SANDBOX_ERROR

logger = get_logger(__name__)

try:
    from e2b import AsyncSandbox
except ImportError:
    AsyncSandbox = None
    logger.warning("E2B SDK not found.")

@tool
async def execute_in_sandbox(agent_id: str, command: str) -> str:
    """
    Execute a shell command in the agent's assigned sandbox.
    
    Args:
        agent_id: UUID of the agent.
        command: Shell command to run (e.g., 'ls -la', 'pytest').
    """
    if AsyncSandbox is None:
        return "Error: E2B SDK not installed."

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Agent).where(Agent.id == uuid.UUID(agent_id)))
        agent = result.scalar_one_or_none()
        
        if not agent:
            return "Error: Agent not found."
        
        svc = E2BService()
        metadata = await svc.ensure_running_sandbox(
            session,
            agent,
            persistent=bool(agent.sandbox_persist),
        )
        await session.flush()

        if E2BService._is_local_fallback_sandbox(metadata.sandbox_id):
            return LOCAL_FALLBACK_SANDBOX_ERROR

        try:
            os.environ["E2B_API_KEY"] = settings.e2b_api_key

            # Connect to the running sandbox
            sandbox = await AsyncSandbox.connect(
                metadata.sandbox_id,
                timeout=settings.e2b_timeout_seconds,
            )

            # Run the command
            proc = await sandbox.process.start(command)
            await proc.wait()

            prefix = ""
            if metadata.restarted:
                prefix = metadata.message or f"Sandbox restarted: {metadata.sandbox_id}"
            elif metadata.created:
                prefix = metadata.message or f"Sandbox created: {metadata.sandbox_id}"
            else:
                prefix = f"Sandbox ready: {metadata.sandbox_id}"

            output = f"{prefix}\nCommand: {command}\nExit Code: {proc.exit_code}\n"
            if proc.stdout:
                output += f"Stdout:\n{proc.stdout}\n"
            if proc.stderr:
                output += f"Stderr:\n{proc.stderr}\n"
                
            return output
            
        except Exception as e:
            return f"Sandbox execution failed: {str(e)}"


@tool
async def start_sandbox(agent_id: str) -> str:
    """
    Start or refresh the agent sandbox and return status details.

    Args:
        agent_id: UUID of the agent.
    """
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Agent).where(Agent.id == uuid.UUID(agent_id)))
        agent = result.scalar_one_or_none()

        if not agent:
            return "Error: Agent not found."

        svc = E2BService()
        metadata = await svc.ensure_running_sandbox(
            session,
            agent,
            persistent=bool(agent.sandbox_persist),
        )
        await session.flush()

        if E2BService._is_local_fallback_sandbox(metadata.sandbox_id):
            return (
                f"Sandbox ready (local fallback): {metadata.sandbox_id}. "
                "Remote E2B execution is unavailable in this environment."
            )
        if metadata.restarted:
            return metadata.message or f"Sandbox restarted: {metadata.sandbox_id}"
        if metadata.created:
            return metadata.message or f"Sandbox created: {metadata.sandbox_id}"
        return metadata.message or f"Sandbox already running: {metadata.sandbox_id}"
