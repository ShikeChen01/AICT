"""
Seed the database with initial MVP-0 data.

Creates:
- 1 Project ("firstproject") with a fixed UUID so the frontend default works
- 1 Manager agent
- 1 Engineer agent (ready to receive tasks)

Uses AgentService for agent creation.

Usage: python -m backend.scripts.seed
       python -m backend.scripts.seed --repo-url https://github.com/user/repo
"""

import argparse
import asyncio
import os
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Reuse the session URL resolver so it works in Cloud Run too
os.environ.setdefault("PYTHONPATH", "/app")

from backend.db.models import Base, Project, Agent
from backend.db.session import _resolve_database_url
from backend.services.agent_service import get_agent_service
from backend.config import settings

# Fixed UUID so it matches the frontend default
PROJECT_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


async def seed(
    repo_url: str | None = None,
    repo_path: str | None = None,
    force: bool = False,
):
    """
    Seed the database with initial project and agents.
    
    Args:
        repo_url: GitHub repository URL for agents to work on.
        repo_path: Local path where repo will be cloned.
        force: If True, delete and recreate existing project.
    """
    url = _resolve_database_url()
    print("Connecting to database...")
    engine = create_async_engine(url, echo=False)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # Use settings if not provided
    actual_repo_url = repo_url or settings.code_repo_url or "https://github.com/placeholder/firstproject"
    actual_repo_path = repo_path or settings.code_repo_path or "/data/project"
    
    async with factory() as session:
        # Check if project already exists
        existing = await session.execute(
            select(Project).where(Project.id == PROJECT_ID)
        )
        existing_project = existing.scalar_one_or_none()
        
        if existing_project:
            if force:
                print(f"Force flag set. Deleting existing project {PROJECT_ID}...")
                await session.delete(existing_project)
                await session.flush()
            else:
                print(f"Project {PROJECT_ID} already exists. Use --force to recreate.")
                # Still ensure agents exist
                agent_service = get_agent_service(session)
                await _ensure_agents(session, existing_project, agent_service)
                await session.commit()
                await engine.dispose()
                return

        # Create project
        project = Project(
            id=PROJECT_ID,
            name="firstproject",
            description="MVP-0 default project for AICT multi-agent platform",
            spec_repo_path=settings.spec_repo_path or "/data/specs",
            code_repo_url=actual_repo_url,
            code_repo_path=actual_repo_path,
            git_token=settings.github_token if settings.github_token else None,
        )
        session.add(project)
        await session.flush()
        print(f"Created project: {project.name} ({project.id})")
        print(f"  - Code repo URL: {project.code_repo_url}")
        print(f"  - Code repo path: {project.code_repo_path}")

        # Create agents
        agent_service = get_agent_service(session)
        await _ensure_agents(session, project, agent_service)

        await session.commit()
        print("Seed complete.")

    await engine.dispose()


async def _ensure_agents(session: AsyncSession, project: Project, agent_service):
    """Ensure Manager and at least one Engineer exist."""
    
    # Check for existing Manager
    result = await session.execute(
        select(Agent).where(
            Agent.project_id == project.id,
            Agent.role == "manager",
        )
    )
    manager = result.scalar_one_or_none()
    
    if not manager:
        manager = Agent(
            project_id=project.id,
            role="manager",
            display_name="Manager",
            model=settings.claude_model or "claude-opus-4-5-20251101",
            status="sleeping",
            sandbox_persist=True,
        )
        session.add(manager)
        await session.flush()
        await session.refresh(manager)
        print(f"Created agent: {manager.display_name} (role={manager.role}, id={manager.id})")
    else:
        print(f"Agent already exists: {manager.display_name} (role={manager.role})")
    
    # Check for existing Engineers
    engineers = await agent_service.list_by_role(project.id, "engineer")
    
    if not engineers:
        engineer = await agent_service.spawn_engineer(
            project.id,
            display_name="Engineer-1",
            model=settings.gemini_model or "gemini-3-pro-preview",
        )
        print(f"Created agent: {engineer.display_name} (role={engineer.role}, id={engineer.id})")
    else:
        print(f"Engineers already exist: {len(engineers)} engineer(s)")


def main():
    parser = argparse.ArgumentParser(description="Seed the AICT database")
    parser.add_argument(
        "--repo-url",
        type=str,
        default=None,
        help="GitHub repository URL for the project (default: from CODE_REPO_URL env)",
    )
    parser.add_argument(
        "--repo-path",
        type=str,
        default=None,
        help="Local path for cloned repo (default: from CODE_REPO_PATH env)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force recreate project if it exists",
    )
    args = parser.parse_args()
    
    asyncio.run(seed(
        repo_url=args.repo_url,
        repo_path=args.repo_path,
        force=args.force,
    ))


if __name__ == "__main__":
    main()
