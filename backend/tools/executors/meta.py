"""Tool executors — meta: sleep, get_project_metadata."""

from __future__ import annotations

import asyncio
import json

from sqlalchemy import select

from backend.tools.base import RunContext


async def run_sleep(ctx: RunContext, tool_input: dict) -> str:
    duration = max(0, min(int(tool_input.get("duration_seconds", 0)), 3600))
    await asyncio.sleep(duration)
    return f"Slept for {duration} seconds."


async def run_get_project_metadata(ctx: RunContext, _input: dict) -> str:
    from sqlalchemy import func

    from backend.db.models import Agent, ProjectSettings, Task, User

    settings_row = await ctx.db.execute(
        select(ProjectSettings).where(ProjectSettings.project_id == ctx.project.id)
    )
    project_settings = settings_row.scalar_one_or_none()

    owner_row = await ctx.db.execute(
        select(User).where(User.id == ctx.project.owner_id)
    )
    owner = owner_row.scalar_one_or_none()

    agent_rows = await ctx.db.execute(
        select(Agent.role, Agent.status, func.count(Agent.id))
        .where(Agent.project_id == ctx.project.id)
        .group_by(Agent.role, Agent.status)
    )
    agent_counts = {f"{role}:{status}": count for role, status, count in agent_rows}

    task_rows = await ctx.db.execute(
        select(Task.status, func.count(Task.id))
        .where(Task.project_id == ctx.project.id)
        .group_by(Task.status)
    )
    task_counts = {status: count for status, count in task_rows}

    metadata = {
        "project": {
            "id": str(ctx.project.id),
            "name": ctx.project.name,
            "description": ctx.project.description,
            "code_repo_url": ctx.project.code_repo_url,
            "code_repo_path": ctx.project.code_repo_path,
            "spec_repo_path": ctx.project.spec_repo_path,
            "settings": {
                "max_engineers": project_settings.max_engineers if project_settings else None,
            },
            "agents": agent_counts,
            "tasks": task_counts,
        },
        "owner": {
            "display_name": owner.display_name if owner else None,
            "email": owner.email if owner else None,
            "github_token": owner.github_token if owner else None,
        } if owner else None,
    }
    return json.dumps(metadata, indent=2)
