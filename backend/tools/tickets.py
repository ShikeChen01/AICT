"""
Ticket and abort tools for engineer agents.

Enables human-in-the-loop (request_human_input with interrupt) and
reporting/abort (report_to_manager, abort_mission).
"""

import uuid
import logging
from langchain_core.tools import tool
from sqlalchemy import select

from backend.db.models import Agent, Task, Ticket, TicketMessage
from backend.db.session import AsyncSessionLocal
from backend.schemas.ticket import TicketCreate
from backend.services.ticket_service import get_ticket_service

logger = logging.getLogger(__name__)

try:
    from langgraph.types import interrupt
except ImportError:
    interrupt = None
    logger.warning("langgraph.types.interrupt not available; request_human_input will not pause.")


async def _get_manager_agent(project_id: uuid.UUID) -> Agent | None:
    """Return the manager agent for the project, or None."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Agent).where(
                Agent.project_id == project_id,
                Agent.role == "manager",
            )
        )
        return result.scalar_one_or_none()


@tool
async def request_human_input(
    agent_id: str,
    project_id: str,
    question: str,
) -> str:
    """
    Ask the user a question and pause until they respond.
    Use when you are blocked and need clarification.

    Args:
        agent_id: Your agent UUID.
        project_id: The project UUID.
        question: The question to ask the user.
    """
    agent_uuid = uuid.UUID(agent_id)
    project_uuid = uuid.UUID(project_id)

    async with AsyncSessionLocal() as session:
        manager = await _get_manager_agent(project_uuid)
        to_agent_id = manager.id if manager else agent_uuid

        service = get_ticket_service(session)
        ticket = await service.create(
            project_id=project_uuid,
            from_agent_id=agent_uuid,
            data=TicketCreate(
                to_agent_id=to_agent_id,
                header=question[:100] if len(question) > 100 else question,
                ticket_type="question",
                initial_message=question,
            ),
        )
        await session.commit()
        ticket_id_str = str(ticket.id)

    try:
        from backend.websocket.manager import ws_manager
        await ws_manager.broadcast_ticket_created(
            ticket_id=ticket.id,
            project_id=project_uuid,
            from_agent_id=agent_uuid,
            to_agent_id=to_agent_id,
            header=ticket.header,
            ticket_type="question",
            message=question,
        )
    except Exception as e:
        logger.warning("Failed to broadcast ticket_created: %s", e)

    if interrupt is None:
        return "Interrupt not available; user was not prompted. Proceed without user input."

    user_response = interrupt({"ticket_id": ticket_id_str, "question": question})
    if isinstance(user_response, dict):
        user_response = user_response.get("message") or user_response.get("content") or str(user_response)
    return f"User responded: {user_response}"


@tool
async def report_to_manager(
    agent_id: str,
    project_id: str,
    header: str,
    message: str,
    ticket_type: str = "help",
) -> str:
    """
    Send a report or issue to the Manager without pausing.
    Use for status updates, warnings, or non-blocking issues.

    Args:
        agent_id: Your agent UUID.
        project_id: The project UUID.
        header: Short subject for the ticket.
        message: The report content.
        ticket_type: One of task_assignment, question, help, issue (default: help).
    """
    agent_uuid = uuid.UUID(agent_id)
    project_uuid = uuid.UUID(project_id)

    async with AsyncSessionLocal() as session:
        manager = await _get_manager_agent(project_uuid)
        if not manager:
            return "No manager found for this project; report not sent."
        to_agent_id = manager.id

        service = get_ticket_service(session)
        ticket = await service.create(
            project_id=project_uuid,
            from_agent_id=agent_uuid,
            data=TicketCreate(
                to_agent_id=to_agent_id,
                header=header[:100] if len(header) > 100 else header,
                ticket_type=ticket_type,
                initial_message=message,
            ),
        )
        await session.commit()

    try:
        from backend.websocket.manager import ws_manager
        await ws_manager.broadcast_ticket_created(
            ticket_id=ticket.id,
            project_id=project_uuid,
            from_agent_id=agent_uuid,
            to_agent_id=to_agent_id,
            header=ticket.header,
            ticket_type=ticket_type,
            message=message,
        )
    except Exception as e:
        logger.warning("Failed to broadcast ticket_created: %s", e)

    return f"Report sent: {header}"


@tool
async def abort_mission(
    agent_id: str,
    task_id: str,
    reason: str,
    documentation: str,
) -> str:
    """
    Abort the current task. You MUST provide a detailed reason and documentation.

    Args:
        agent_id: Your agent UUID.
        task_id: The task UUID.
        reason: Short reason for aborting (1-2 sentences).
        documentation: Detailed docs of what you tried and why it failed.
    """
    agent_uuid = uuid.UUID(agent_id)
    task_uuid = uuid.UUID(task_id)

    async with AsyncSessionLocal() as session:
        task_result = await session.execute(select(Task).where(Task.id == task_uuid))
        task = task_result.scalar_one_or_none()
        if not task:
            return f"Task {task_id} not found."

        task.status = "aborted"
        task.abort_reason = reason
        task.abort_documentation = documentation
        task.aborted_by_id = agent_uuid

        agent_result = await session.execute(select(Agent).where(Agent.id == agent_uuid))
        agent = agent_result.scalar_one_or_none()
        if agent:
            agent.status = "active"
            agent.current_task_id = None

        await session.commit()
        project_id = task.project_id

    try:
        from backend.websocket.manager import ws_manager
        manager = await _get_manager_agent(project_id)
        to_agent_id = manager.id if manager else agent_uuid
        await ws_manager.broadcast_mission_aborted(
            ticket_id=uuid.uuid4(),  # No ticket record for simple abort broadcast
            project_id=project_id,
            from_agent_id=agent_uuid,
            to_agent_id=to_agent_id,
            header=f"Abort: {task.title}",
            message=reason,
        )
    except Exception as e:
        logger.warning("Failed to broadcast mission_aborted: %s", e)

    return f"ABORTED: Task returned to backlog. Reason: {reason}"
