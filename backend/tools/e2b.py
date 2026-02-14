"""
E2B Sandbox tools for LangGraph agents.
"""

import uuid
import os
import logging
from langchain_core.tools import tool
from sqlalchemy import select

from backend.db.session import AsyncSessionLocal
from backend.db.models import Agent
from backend.config import settings

logger = logging.getLogger(__name__)

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
        
        if not agent.sandbox_id:
            return "Error: Agent has no active sandbox."
            
        try:
            os.environ["E2B_API_KEY"] = settings.e2b_api_key
            
            # Connect to the running sandbox
            sandbox = await AsyncSandbox.connect(agent.sandbox_id, timeout=settings.e2b_timeout_seconds)
            
            # Run the command
            proc = await sandbox.process.start(command)
            await proc.wait()
            
            output = f"Command: {command}\nExit Code: {proc.exit_code}\n"
            if proc.stdout:
                output += f"Stdout:\n{proc.stdout}\n"
            if proc.stderr:
                output += f"Stderr:\n{proc.stderr}\n"
                
            return output
            
        except Exception as e:
            return f"Sandbox execution failed: {str(e)}"
