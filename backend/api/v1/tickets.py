"""
Ticket REST API endpoints.

Agent-to-agent ticket system for communication and escalation.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.auth import verify_token
from backend.db.models import Agent, TicketMessage, _utcnow
from backend.db.session import get_db
from backend.schemas.ticket import (
    TicketCreate,
    TicketMessageCreate,
    TicketMessageResponse,
    TicketResponse,
)
from backend.services.ticket_service import get_ticket_service

router = APIRouter(prefix="/tickets", tags=["tickets"])


@router.get("", response_model=list[TicketResponse])
async def list_tickets(
    project_id: UUID = Query(..., description="Project ID"),
    status: str | None = Query(None, description="Filter by status (open/closed)"),
    _auth: bool = Depends(verify_token),
    db: AsyncSession = Depends(get_db),
):
    """List tickets for a project."""
    service = get_ticket_service(db)
    return await service.list_by_project(project_id, status)


@router.get("/{ticket_id}", response_model=TicketResponse)
async def get_ticket(
    ticket_id: UUID,
    _auth: bool = Depends(verify_token),
    db: AsyncSession = Depends(get_db),
):
    """Get a single ticket by ID with all messages."""
    service = get_ticket_service(db)
    return await service.get(ticket_id)


@router.post("", response_model=TicketResponse, status_code=201)
async def create_ticket(
    data: TicketCreate,
    project_id: UUID = Query(..., description="Project ID"),
    from_agent_id: UUID = Query(..., description="Sending agent ID"),
    _auth: bool = Depends(verify_token),
    db: AsyncSession = Depends(get_db),
):
    """Create a new ticket."""
    service = get_ticket_service(db)
    return await service.create(project_id, from_agent_id, data)


@router.post("/{ticket_id}/reply", response_model=TicketMessageResponse, status_code=201)
async def reply_to_ticket(
    ticket_id: UUID,
    data: TicketMessageCreate,
    from_agent_id: UUID = Query(..., description="Replying agent ID"),
    _auth: bool = Depends(verify_token),
    db: AsyncSession = Depends(get_db),
):
    """Reply to a ticket."""
    service = get_ticket_service(db)
    return await service.reply(ticket_id, from_agent_id, data)


@router.post("/{ticket_id}/close", response_model=TicketResponse)
async def close_ticket(
    ticket_id: UUID,
    closing_agent_id: UUID = Query(..., description="Agent closing the ticket"),
    _auth: bool = Depends(verify_token),
    db: AsyncSession = Depends(get_db),
):
    """Close a ticket. Only the higher-priority agent can close."""
    service = get_ticket_service(db)
    return await service.close(ticket_id, closing_agent_id)


@router.post("/{ticket_id}/user-reply", response_model=TicketMessageResponse, status_code=201)
async def user_reply_to_ticket(
    ticket_id: UUID,
    data: TicketMessageCreate,
    _auth: bool = Depends(verify_token),
    db: AsyncSession = Depends(get_db),
):
    """
    Reply to a ticket as the authenticated user.
    If the ticket was created by an interrupted engineer (type=question), this also resumes the engineer graph.
    """
    service = get_ticket_service(db)
    ticket = await service.get(ticket_id)

    message = TicketMessage(
        ticket_id=ticket_id,
        from_user_id=None,  # TODO: get from auth context when user model is wired
        from_agent_id=None,
        content=data.content,
    )
    db.add(message)
    await db.flush()
    await db.refresh(message)

    from backend.websocket.manager import ws_manager
    await ws_manager.broadcast_ticket_reply(
        ticket_id=ticket_id,
        project_id=ticket.project_id,
        to_agent_id=ticket.to_agent_id,
        header=ticket.header,
        ticket_type=ticket.ticket_type,
        message=data.content,
        from_agent_id=None,
        from_user_id=None,
    )

    if ticket.ticket_type == "question" and ticket.status == "open":
        from backend.services.engineer_graph_service import get_engineer_graph_service
        svc = get_engineer_graph_service()
        agent_result = await db.execute(
            select(Agent).where(Agent.id == ticket.from_agent_id)
        )
        agent = agent_result.scalar_one_or_none()
        if agent and agent.current_task_id:
            await svc.resume_engineer(
                agent_id=ticket.from_agent_id,
                task_id=agent.current_task_id,
                user_message=data.content,
            )

    ticket.status = "closed"
    ticket.closed_at = _utcnow()
    ticket.closed_by_id = None
    await db.commit()
    await db.refresh(ticket)

    await ws_manager.broadcast_ticket_closed(
        ticket_id=ticket_id,
        project_id=ticket.project_id,
        from_agent_id=ticket.from_agent_id,
        to_agent_id=ticket.to_agent_id,
        header=ticket.header,
        ticket_type=ticket.ticket_type,
    )

    return message
