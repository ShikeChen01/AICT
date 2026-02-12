"""
Seed the database with initial MVP-0 data.

Creates:
- 1 Project ("firstproject") with a fixed UUID so the frontend default works
- 1 GM agent
- 1 OM agent

Usage: python -m backend.scripts.seed
"""

import asyncio
import os
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Reuse the session URL resolver so it works in Cloud Run too
os.environ.setdefault("PYTHONPATH", "/app")

from backend.db.models import Agent, Base, Project
from backend.db.session import _resolve_database_url

# Fixed UUIDs so they match the frontend default
PROJECT_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
GM_ID = uuid.UUID("00000000-0000-0000-0000-000000000010")
OM_ID = uuid.UUID("00000000-0000-0000-0000-000000000020")


async def seed():
    url = _resolve_database_url()
    print(f"Connecting to database...")
    engine = create_async_engine(url, echo=False)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with factory() as session:
        # Check if project already exists
        existing = await session.execute(
            select(Project).where(Project.id == PROJECT_ID)
        )
        if existing.scalar_one_or_none():
            print(f"Project {PROJECT_ID} already exists. Skipping seed.")
            await engine.dispose()
            return

        # Create project
        project = Project(
            id=PROJECT_ID,
            name="firstproject",
            description="MVP-0 default project for AICT multi-agent platform",
            spec_repo_path="/data/specs",
            code_repo_url="https://github.com/placeholder/firstproject",
            code_repo_path="/data/project",
        )
        session.add(project)
        await session.flush()
        print(f"Created project: {project.name} ({project.id})")

        # Create GM agent
        gm = Agent(
            id=GM_ID,
            project_id=PROJECT_ID,
            role="gm",
            display_name="GM",
            model="gemini-2.5-pro",
            status="sleeping",
            sandbox_persist=True,
            priority=0,
        )
        session.add(gm)
        print(f"Created agent: {gm.display_name} (role={gm.role})")

        # Create OM agent
        om = Agent(
            id=OM_ID,
            project_id=PROJECT_ID,
            role="om",
            display_name="OM-1",
            model="claude-4-sonnet",
            status="sleeping",
            sandbox_persist=True,
            priority=1,
        )
        session.add(om)
        print(f"Created agent: {om.display_name} (role={om.role})")

        await session.commit()
        print("Seed complete.")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())
