"""
Background worker for executing engineer jobs in parallel.

This service polls the engineer_jobs table for pending work and executes
each job in a separate async task, allowing multiple engineers to work
concurrently.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import Agent, EngineerJob, Task
from backend.db.session import AsyncSessionLocal
from backend.graph.model_factory import get_model
from backend.services.e2b_service import E2BService
from backend.services.orchestrator import sandbox_should_persist

logger = logging.getLogger(__name__)


class EngineerWorker:
    """
    Background worker that processes engineer jobs from the queue.
    
    Supports parallel execution - multiple engineers can work on different
    tasks simultaneously.
    """

    def __init__(
        self,
        e2b_service: E2BService | None = None,
        poll_interval: float = 2.0,
        max_concurrent_jobs: int = 5,
    ):
        self.e2b_service = e2b_service or E2BService()
        self.poll_interval = poll_interval
        self.max_concurrent_jobs = max_concurrent_jobs
        self._running = False
        self._active_jobs: set[UUID] = set()
        self._shutdown_event = asyncio.Event()

    async def start(self) -> None:
        """Start the worker loop."""
        if self._running:
            logger.warning("EngineerWorker already running")
            return
        
        self._running = True
        self._shutdown_event.clear()
        logger.info(
            "EngineerWorker started (poll_interval=%.1fs, max_concurrent=%d)",
            self.poll_interval,
            self.max_concurrent_jobs,
        )
        
        try:
            await self._worker_loop()
        finally:
            self._running = False
            logger.info("EngineerWorker stopped")

    async def stop(self) -> None:
        """Signal the worker to stop gracefully."""
        if not self._running:
            return
        logger.info("Stopping EngineerWorker...")
        self._shutdown_event.set()

    async def _worker_loop(self) -> None:
        """Main polling loop."""
        while not self._shutdown_event.is_set():
            try:
                # Check capacity
                available_slots = self.max_concurrent_jobs - len(self._active_jobs)
                if available_slots > 0:
                    jobs = await self._fetch_pending_jobs(limit=available_slots)
                    for job in jobs:
                        if job.id not in self._active_jobs:
                            self._active_jobs.add(job.id)
                            asyncio.create_task(self._execute_job(job.id))
                
                # Sleep with shutdown check
                try:
                    await asyncio.wait_for(
                        self._shutdown_event.wait(),
                        timeout=self.poll_interval,
                    )
                except asyncio.TimeoutError:
                    pass
                    
            except Exception as exc:
                logger.exception("Error in worker loop: %s", exc)
                await asyncio.sleep(self.poll_interval)

    async def _fetch_pending_jobs(self, limit: int) -> list[EngineerJob]:
        """Fetch pending jobs from the queue."""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(EngineerJob)
                .where(EngineerJob.status == "pending")
                .order_by(EngineerJob.created_at)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
            jobs = list(result.scalars().all())
            
            # Mark as running immediately to prevent double-pickup
            for job in jobs:
                job.status = "running"
                job.started_at = datetime.now(timezone.utc)
            
            await session.commit()
            return jobs

    async def _execute_job(self, job_id: UUID) -> None:
        """Execute a single engineer job."""
        try:
            async with AsyncSessionLocal() as session:
                # Load job with relationships
                result = await session.execute(
                    select(EngineerJob)
                    .where(EngineerJob.id == job_id)
                )
                job = result.scalar_one_or_none()
                
                if not job:
                    logger.error("Job %s not found", job_id)
                    return
                
                # Load related entities
                agent_result = await session.execute(
                    select(Agent).where(Agent.id == job.agent_id)
                )
                agent = agent_result.scalar_one_or_none()
                
                task_result = await session.execute(
                    select(Task).where(Task.id == job.task_id)
                )
                task = task_result.scalar_one_or_none()
                
                if not agent or not task:
                    await self._fail_job(session, job, "Agent or task not found")
                    return
                
                # Broadcast job started event
                await self._broadcast_job_started(job, f"Starting: {task.title}")
                
                # Wake agent and create sandbox
                logger.info(
                    "Starting job %s: task=%s, engineer=%s",
                    job_id, task.title, agent.display_name,
                )
                
                try:
                    await self._wake_agent(session, agent)
                except Exception as exc:
                    await self._fail_job(session, job, f"Failed to wake agent: {exc}")
                    return
                
                # Run the engineer workflow
                try:
                    result_text = await self._run_engineer_workflow(
                        session, agent, task, job
                    )
                    await self._complete_job(session, job, result_text)
                except Exception as exc:
                    logger.exception("Engineer workflow failed: %s", exc)
                    await self._fail_job(session, job, str(exc))
                finally:
                    # Close ephemeral sandbox
                    if not sandbox_should_persist(agent.role) and agent.sandbox_id:
                        try:
                            await self.e2b_service.close_sandbox(session, agent)
                        except Exception as close_exc:
                            logger.warning(
                                "Failed to close sandbox for %s: %s",
                                agent.id, close_exc,
                            )
                            
        except Exception as exc:
            logger.exception("Job execution failed: %s", exc)
        finally:
            self._active_jobs.discard(job_id)

    async def _wake_agent(self, session: AsyncSession, agent: Agent) -> None:
        """Wake agent and ensure sandbox is ready."""
        if agent.status == "sleeping":
            agent.status = "active"
        
        if not agent.sandbox_id:
            await self.e2b_service.create_sandbox(
                session=session,
                agent=agent,
                persistent=sandbox_should_persist(agent.role),
            )
        
        await session.commit()

    async def _run_engineer_workflow(
        self,
        session: AsyncSession,
        agent: Agent,
        task: Task,
        job: EngineerJob,
    ) -> str:
        """
        Execute the engineer LLM workflow for a task.
        
        This runs a simple chain: prompt -> LLM -> tools -> response.
        The engineer has access to sandbox, git, and file tools.
        """
        # Import tools inside function to avoid circular imports
        from backend.tools.registry import get_engineer_tools
        
        model = get_model()
        tools = get_engineer_tools()
        model_with_tools = model.bind_tools(tools)
        
        # Build system prompt with task context
        system_prompt = self._build_engineer_system_prompt(agent, task)
        
        # Initial prompt
        task_prompt = (
            f"You have been assigned task: {task.title}\n\n"
            f"Description: {task.description or 'No description provided'}\n\n"
            f"Your agent_id is: {agent.id}\n"
            f"Project ID: {agent.project_id}\n"
            f"Task ID: {task.id}\n\n"
            "Please implement this task. Start by creating a branch, "
            "make your changes, test them, then commit and create a PR."
        )
        
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=task_prompt),
        ]
        
        # Broadcast initial thought
        await self._broadcast_job_progress(job, f"Starting implementation: {task.title}")
        
        # Run agent loop (simplified - single turn for now)
        # TODO: Implement multi-turn tool calling loop
        max_iterations = 10
        iteration = 0
        final_response = ""
        
        while iteration < max_iterations:
            iteration += 1
            
            response = await model_with_tools.ainvoke(messages)
            messages.append(response)
            
            # Check for tool calls
            if hasattr(response, "tool_calls") and response.tool_calls:
                tool_results = await self._execute_tools(
                    response.tool_calls, agent, task, job
                )
                messages.extend(tool_results)
            else:
                # No tool calls - we're done
                content = response.content if hasattr(response, "content") else str(response)
                # Handle LangChain multi-part content (list of text/dict)
                if isinstance(content, list):
                    text_parts = []
                    for part in content:
                        if isinstance(part, str):
                            text_parts.append(part)
                        elif isinstance(part, dict) and "text" in part:
                            text_parts.append(part["text"])
                    content = "\n".join(text_parts) if text_parts else ""
                final_response = content
                break
        
        # Update task status if PR was created
        if task.pr_url:
            task.status = "in_review"
            await session.commit()
        
        return final_response or "Task processed"

    def _build_engineer_system_prompt(self, agent: Agent, task: Task) -> str:
        """Build the system prompt for the engineer."""
        return f"""You are an expert Software Engineer Agent.
Your name is: {agent.display_name}
Your agent ID is: {agent.id}

Current Task:
- Title: {task.title}
- Description: {task.description or 'No description'}
- Task ID: {task.id}
- Project ID: {agent.project_id}

Your workflow:
1. Create a git branch (e.g., feat/{task.title.lower().replace(' ', '-')[:30]})
2. Implement the solution by writing files in the sandbox
3. Test your changes if applicable
4. Commit your changes with a descriptive message
5. Push the branch to remote
6. Create a Pull Request

Available Tools:
- create_branch: Create a new git branch
- commit_changes: Commit files with a message
- push_changes: Push to remote
- create_pull_request: Open a PR
- execute_in_sandbox: Run commands in your sandbox
- read_file / write_file: File operations
- update_task_status: Update the task status

IMPORTANT: Always pass your agent_id ({agent.id}) when using sandbox/file tools.

When finished, respond with "DONE: <summary of what was completed>"."""

    async def _execute_tools(
        self,
        tool_calls: list,
        agent: Agent,
        task: Task,
        job: EngineerJob,
    ) -> list:
        """Execute tool calls and return results."""
        from langchain_core.messages import ToolMessage
        from backend.tools.registry import get_engineer_tools
        
        tools = get_engineer_tools()
        tools_by_name = {tool.name: tool for tool in tools}
        
        results = []
        for tool_call in tool_calls:
            tool_name = tool_call.get("name") or tool_call.get("function", {}).get("name")
            tool_args = tool_call.get("args") or tool_call.get("function", {}).get("arguments", {})
            tool_id = tool_call.get("id", "unknown")
            
            # Broadcast tool call
            await self._broadcast_job_progress(
                job,
                message=f"Using tool: {tool_name}",
                tool_name=tool_name,
                tool_args=tool_args,
            )
            
            try:
                tool_fn = tools_by_name.get(tool_name)
                if tool_fn:
                    # Inject agent_id if not provided
                    if "agent_id" in tool_fn.args_schema.__fields__ if hasattr(tool_fn, "args_schema") else False:
                        if "agent_id" not in tool_args:
                            tool_args["agent_id"] = str(agent.id)
                    
                    result = await tool_fn.ainvoke(tool_args)
                    results.append(ToolMessage(content=str(result), tool_call_id=tool_id))
                else:
                    results.append(ToolMessage(
                        content=f"Tool '{tool_name}' not found",
                        tool_call_id=tool_id,
                    ))
            except Exception as exc:
                logger.warning("Tool %s failed: %s", tool_name, exc)
                results.append(ToolMessage(
                    content=f"Tool error: {exc}",
                    tool_call_id=tool_id,
                ))
        
        return results

    async def _complete_job(
        self,
        session: AsyncSession,
        job: EngineerJob,
        result: str,
    ) -> None:
        """Mark job as completed."""
        job.status = "completed"
        job.result = result[:10000] if result else None  # Truncate long results
        job.completed_at = datetime.now(timezone.utc)
        await session.commit()
        
        logger.info("Job %s completed: %s", job.id, result[:100] if result else "No result")
        
        await self._broadcast_job_completed(
            job,
            result=result[:500] if result else None,
            pr_url=job.pr_url,
        )

    async def _fail_job(
        self,
        session: AsyncSession,
        job: EngineerJob,
        error: str,
    ) -> None:
        """Mark job as failed."""
        job.status = "failed"
        job.error = error[:5000]  # Truncate long errors
        job.completed_at = datetime.now(timezone.utc)
        await session.commit()
        
        logger.error("Job %s failed: %s", job.id, error)
        
        await self._broadcast_job_failed(job, error)

    async def _broadcast_job_started(self, job: EngineerJob, message: str | None = None) -> None:
        """Broadcast job started event via WebSocket."""
        try:
            from backend.websocket.manager import ws_manager
            await ws_manager.broadcast_job_started(
                job_id=job.id,
                project_id=job.project_id,
                task_id=job.task_id,
                agent_id=job.agent_id,
                message=message,
            )
        except Exception as exc:
            logger.warning("Failed to broadcast job_started: %s", exc)

    async def _broadcast_job_progress(
        self,
        job: EngineerJob,
        message: str | None = None,
        tool_name: str | None = None,
        tool_args: dict | None = None,
    ) -> None:
        """Broadcast job progress event via WebSocket."""
        try:
            from backend.websocket.manager import ws_manager
            await ws_manager.broadcast_job_progress(
                job_id=job.id,
                project_id=job.project_id,
                task_id=job.task_id,
                agent_id=job.agent_id,
                message=message,
                tool_name=tool_name,
                tool_args=tool_args,
            )
        except Exception as exc:
            logger.warning("Failed to broadcast job_progress: %s", exc)

    async def _broadcast_job_completed(
        self,
        job: EngineerJob,
        result: str | None = None,
        pr_url: str | None = None,
    ) -> None:
        """Broadcast job completed event via WebSocket."""
        try:
            from backend.websocket.manager import ws_manager
            await ws_manager.broadcast_job_completed(
                job_id=job.id,
                project_id=job.project_id,
                task_id=job.task_id,
                agent_id=job.agent_id,
                result=result,
                pr_url=pr_url,
            )
        except Exception as exc:
            logger.warning("Failed to broadcast job_completed: %s", exc)

    async def _broadcast_job_failed(self, job: EngineerJob, error: str) -> None:
        """Broadcast job failed event via WebSocket."""
        try:
            from backend.websocket.manager import ws_manager
            await ws_manager.broadcast_job_failed(
                job_id=job.id,
                project_id=job.project_id,
                task_id=job.task_id,
                agent_id=job.agent_id,
                error=error,
            )
        except Exception as exc:
            logger.warning("Failed to broadcast job_failed: %s", exc)


# Global worker instance
_worker: EngineerWorker | None = None


def get_engineer_worker() -> EngineerWorker:
    """Get or create the global engineer worker."""
    global _worker
    if _worker is None:
        _worker = EngineerWorker()
    return _worker


async def start_engineer_worker() -> None:
    """Start the global engineer worker."""
    worker = get_engineer_worker()
    await worker.start()


async def stop_engineer_worker() -> None:
    """Stop the global engineer worker."""
    if _worker:
        await _worker.stop()
