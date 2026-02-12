"""
Internal Ticket API endpoints for agent tool calls.

These endpoints are called by agents to interact with the ticket system.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.auth import verify_agent_request
from backend.db.session import get_db
from backend.schemas.ticket import (
    TicketCreate,
    TicketMessageCreate,
    TicketMessageResponse,
    TicketResponse,
)
from backend.services.ticket_service import get_ticket_service

router = APIRouter(prefix="/tickets", tags=["internal-tickets"])


@router.get("", response_model=list[TicketResponse])
async def list_tickets(
    project_id: UUID = Query(..., description="Project ID"),
    direction: str = Query("to", description="'to' for received, 'from' for sent"),
    agent_id: str = Depends(verify_agent_request),
    db: AsyncSession = Depends(get_db),
):
    """List tickets for the requesting agent."""
    service = get_ticket_service(db)
    return await service.list_for_agent(UUID(agent_id), direction)


@router.get("/open", response_model=list[TicketResponse])
async def list_open_tickets(
    agent_id: str = Depends(verify_agent_request),
    db: AsyncSession = Depends(get_db),
):
    """List open tickets where the requesting agent is the recipient."""
    service = get_ticket_service(db)
    return await service.list_open_for_agent(UUID(agent_id))


@router.get("/{ticket_id}", response_model=TicketResponse)
async def get_ticket(
    ticket_id: UUID,
    agent_id: str = Depends(verify_agent_request),
    db: AsyncSession = Depends(get_db),
):
    """Get a ticket by ID."""
    service = get_ticket_service(db)
    return await service.get(ticket_id)


@router.post("", response_model=TicketResponse, status_code=201)
async def create_ticket(
    data: TicketCreate,
    project_id: UUID = Query(..., description="Project ID"),
    agent_id: str = Depends(verify_agent_request),
    db: AsyncSession = Depends(get_db),
):
    """Create a new ticket from the requesting agent."""
    service = get_ticket_service(db)
    return await service.create(project_id, UUID(agent_id), data)


@router.post("/{ticket_id}/reply", response_model=TicketMessageResponse, status_code=201)
async def reply_to_ticket(
    ticket_id: UUID,
    data: TicketMessageCreate,
    agent_id: str = Depends(verify_agent_request),
    db: AsyncSession = Depends(get_db),
):
    """Reply to a ticket."""
    service = get_ticket_service(db)
    return await service.reply(ticket_id, UUID(agent_id), data)


@router.post("/{ticket_id}/close", response_model=TicketResponse)
async def close_ticket(
    ticket_id: UUID,
    agent_id: str = Depends(verify_agent_request),
    db: AsyncSession = Depends(get_db),
):
    """Close a ticket. Only the higher-priority agent can close."""
    service = get_ticket_service(db)
    return await service.close(ticket_id, UUID(agent_id))
