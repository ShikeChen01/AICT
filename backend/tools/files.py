"""
File tools for LangGraph agents.

Allows engineers to read, write, and list files in their E2B sandbox.
"""

import os
import uuid
import logging
from langchain_core.tools import tool
from sqlalchemy import select

from backend.db.session import AsyncSessionLocal
from backend.db.models import Agent
from backend.config import settings
from backend.services.e2b_service import E2BService, LOCAL_FALLBACK_SANDBOX_ERROR

logger = logging.getLogger(__name__)

try:
    from e2b import AsyncSandbox
except ImportError:
    AsyncSandbox = None
    logger.warning("E2B SDK not found.")


@tool
async def read_file(agent_id: str, file_path: str) -> str:
    """
    Read the contents of a file in the agent's sandbox.
    
    Args:
        agent_id: UUID of the agent.
        file_path: Path to the file (relative to /home/user or absolute).
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
        if E2BService._is_local_fallback_sandbox(agent.sandbox_id):
            return LOCAL_FALLBACK_SANDBOX_ERROR
            
        try:
            os.environ["E2B_API_KEY"] = settings.e2b_api_key
            
            sandbox = await AsyncSandbox.connect(agent.sandbox_id, timeout=settings.e2b_timeout_seconds)
            
            # Read file content
            content = await sandbox.filesystem.read(file_path)
            
            return f"File: {file_path}\n---\n{content}"
            
        except Exception as e:
            return f"Failed to read file: {str(e)}"


@tool
async def write_file(agent_id: str, file_path: str, content: str) -> str:
    """
    Write content to a file in the agent's sandbox.
    Creates parent directories if needed.
    
    Args:
        agent_id: UUID of the agent.
        file_path: Path to the file (relative to /home/user or absolute).
        content: The content to write to the file.
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
        if E2BService._is_local_fallback_sandbox(agent.sandbox_id):
            return LOCAL_FALLBACK_SANDBOX_ERROR
            
        try:
            os.environ["E2B_API_KEY"] = settings.e2b_api_key
            
            sandbox = await AsyncSandbox.connect(agent.sandbox_id, timeout=settings.e2b_timeout_seconds)
            
            # Ensure parent directory exists
            dir_path = os.path.dirname(file_path)
            if dir_path:
                await sandbox.filesystem.make_dir(dir_path)
            
            # Write file content
            await sandbox.filesystem.write(file_path, content)
            
            return f"Successfully wrote {len(content)} characters to {file_path}"
            
        except Exception as e:
            return f"Failed to write file: {str(e)}"


@tool
async def list_directory(agent_id: str, dir_path: str = "/home/user") -> str:
    """
    List files and directories in the agent's sandbox.
    
    Args:
        agent_id: UUID of the agent.
        dir_path: Path to the directory (default: /home/user).
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
        if E2BService._is_local_fallback_sandbox(agent.sandbox_id):
            return LOCAL_FALLBACK_SANDBOX_ERROR
            
        try:
            os.environ["E2B_API_KEY"] = settings.e2b_api_key
            
            sandbox = await AsyncSandbox.connect(agent.sandbox_id, timeout=settings.e2b_timeout_seconds)
            
            # List directory contents
            entries = await sandbox.filesystem.list(dir_path)
            
            if not entries:
                return f"Directory {dir_path} is empty."
            
            lines = [f"Contents of {dir_path}:"]
            for entry in entries:
                entry_type = "DIR " if entry.is_dir else "FILE"
                lines.append(f"  [{entry_type}] {entry.name}")
            
            return "\n".join(lines)
            
        except Exception as e:
            return f"Failed to list directory: {str(e)}"


@tool
async def delete_file(agent_id: str, file_path: str) -> str:
    """
    Delete a file in the agent's sandbox.
    
    Args:
        agent_id: UUID of the agent.
        file_path: Path to the file to delete.
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
        if E2BService._is_local_fallback_sandbox(agent.sandbox_id):
            return LOCAL_FALLBACK_SANDBOX_ERROR
            
        try:
            os.environ["E2B_API_KEY"] = settings.e2b_api_key
            
            sandbox = await AsyncSandbox.connect(agent.sandbox_id, timeout=settings.e2b_timeout_seconds)
            
            # Remove file
            await sandbox.filesystem.remove(file_path)
            
            return f"Successfully deleted {file_path}"
            
        except Exception as e:
            return f"Failed to delete file: {str(e)}"
