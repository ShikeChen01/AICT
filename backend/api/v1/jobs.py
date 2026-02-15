"""
Engineer Job REST API endpoints.

Provides status and results for background engineer jobs.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.auth import verify_token
from backend.db.models import EngineerJob
from backend.db.session import get_db
from backend.schemas.job import JobResponse, JobSummary

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("", response_model=list[JobSummary])
async def list_jobs(
    project_id: UUID = Query(..., description="Project ID to list jobs for"),
    status: str | None = Query(None, description="Filter by status"),
    task_id: UUID | None = Query(None, description="Filter by task"),
    agent_id: UUID | None = Query(None, description="Filter by agent"),
    limit: int = Query(50, ge=1, le=200, description="Max results"),
    _auth: bool = Depends(verify_token),
    db: AsyncSession = Depends(get_db),
):
    """
    List engineer jobs for a project.
    
    Jobs represent background work being done by engineers.
    Status can be: pending, running, completed, failed, cancelled
    """
    query = (
        select(EngineerJob)
        .where(EngineerJob.project_id == project_id)
        .order_by(EngineerJob.created_at.desc())
        .limit(limit)
    )
    
    if status:
        query = query.where(EngineerJob.status == status)
    if task_id:
        query = query.where(EngineerJob.task_id == task_id)
    if agent_id:
        query = query.where(EngineerJob.agent_id == agent_id)
    
    result = await db.execute(query)
    jobs = result.scalars().all()
    
    return jobs


@router.get("/active", response_model=list[JobSummary])
async def list_active_jobs(
    project_id: UUID = Query(..., description="Project ID to list jobs for"),
    _auth: bool = Depends(verify_token),
    db: AsyncSession = Depends(get_db),
):
    """List currently active (pending or running) jobs for a project."""
    result = await db.execute(
        select(EngineerJob)
        .where(
            EngineerJob.project_id == project_id,
            EngineerJob.status.in_(["pending", "running"]),
        )
        .order_by(EngineerJob.created_at)
    )
    return result.scalars().all()


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: UUID,
    _auth: bool = Depends(verify_token),
    db: AsyncSession = Depends(get_db),
):
    """Get details of a specific engineer job."""
    result = await db.execute(
        select(EngineerJob).where(EngineerJob.id == job_id)
    )
    job = result.scalar_one_or_none()
    
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    return job


@router.post("/{job_id}/cancel", response_model=JobResponse)
async def cancel_job(
    job_id: UUID,
    _auth: bool = Depends(verify_token),
    db: AsyncSession = Depends(get_db),
):
    """
    Cancel a pending job.
    
    Only pending jobs can be cancelled. Running jobs must complete.
    """
    result = await db.execute(
        select(EngineerJob).where(EngineerJob.id == job_id)
    )
    job = result.scalar_one_or_none()
    
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if job.status != "pending":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel job with status '{job.status}'. Only pending jobs can be cancelled."
        )
    
    job.status = "cancelled"
    await db.commit()
    await db.refresh(job)
    
    return job
