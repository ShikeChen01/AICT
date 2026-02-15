# AICT Testing Guide

This document covers testing the AICT system end-to-end, including backend unit tests, integration tests, and Playwright E2E tests.

## Quick Start

```bash
# Backend unit tests (fast, SQLite)
cd backend
python -m pytest tests/ -v --tb=short

# Backend integration tests (PostgreSQL via testcontainers)
INTEGRATION_TEST=1 python -m pytest tests/ -v

# Frontend unit tests
cd frontend
npm test

# Playwright E2E tests (requires servers running)
npm run test:e2e

# Playwright setup verification (no servers needed)
npx playwright test setup.spec.ts
```

---

## Backend Testing

## Prerequisites

1. **Environment Configuration**

   Ensure `.env.development` (or `.env`) has these values set:

   ```bash
   # Required for LLM
   CLAUDE_API_KEY=sk-ant-...  # or GEMINI_API_KEY
   
   # Required for sandbox execution
   E2B_API_KEY=e2b_...
   E2B_TEMPLATE_ID=  # optional, uses default if empty
   
   # Required for git operations
   GITHUB_TOKEN=ghp_...  # PAT with repo push access
   CODE_REPO_URL=https://github.com/your-org/your-repo
   CODE_REPO_PATH=/data/project
   ```

2. **Database Ready**

   ```bash
   # Run migrations
   cd backend
   alembic upgrade head
   ```

3. **Seed Data**

   ```bash
   # Seed with default project
   python -m backend.scripts.seed
   
   # Or seed with a specific repo
   python -m backend.scripts.seed --repo-url https://github.com/your-org/repo
   
   # Force recreate
   python -m backend.scripts.seed --force
   ```

## Test 1: E2B Sandbox Connectivity

Test that E2B sandboxes can be created and commands executed.

```python
# Run from backend directory
import asyncio
from backend.services.e2b_service import E2BService
from backend.db.session import AsyncSessionLocal
from backend.db.models import Agent
from sqlalchemy import select
import uuid

async def test_sandbox():
    async with AsyncSessionLocal() as session:
        # Get an engineer agent
        result = await session.execute(
            select(Agent).where(Agent.role == "engineer").limit(1)
        )
        agent = result.scalar_one_or_none()
        
        if not agent:
            print("No engineer found. Run seed first.")
            return
        
        e2b = E2BService()
        
        # Create sandbox
        meta = await e2b.create_sandbox(session, agent, persistent=False)
        print(f"Created sandbox: {meta.sandbox_id}")
        
        # Test command (via tool)
        from backend.tools.e2b import execute_in_sandbox
        result = await execute_in_sandbox.ainvoke({
            "agent_id": str(agent.id),
            "command": "echo 'Hello from E2B!'"
        })
        print(f"Command result: {result}")
        
        # Cleanup
        await e2b.close_sandbox(session, agent)
        await session.commit()

asyncio.run(test_sandbox())
```

## Test 2: Git Operations

Test git tools work correctly.

```python
import asyncio
from backend.tools.git import create_branch, commit_changes, push_changes
from backend.config import settings

async def test_git():
    # Ensure CODE_REPO_PATH exists and is a git repo
    import os
    if not os.path.exists(settings.code_repo_path):
        print(f"Repo path {settings.code_repo_path} does not exist")
        return
    
    # Test branch creation
    try:
        branch = create_branch.invoke({
            "branch_name": "test/agent-test-branch",
            "agent_role": "engineer"
        })
        print(f"Created branch: {branch}")
    except Exception as e:
        print(f"Branch creation failed: {e}")

asyncio.run(test_git())
```

## Test 3: WebSocket Events

Test that workflow events are broadcast correctly.

```python
import asyncio
import websockets
import json

async def test_websocket():
    project_id = "00000000-0000-0000-0000-000000000001"
    token = "change-me-in-production"  # Your API_TOKEN
    
    uri = f"ws://localhost:8000/ws?token={token}&project_id={project_id}&channels=all"
    
    async with websockets.connect(uri) as ws:
        print("Connected to WebSocket")
        
        # Send ping
        await ws.send(json.dumps({"type": "ping"}))
        response = await ws.recv()
        print(f"Ping response: {response}")
        
        # Listen for events (keep running while testing chat)
        print("Listening for events... (Ctrl+C to stop)")
        while True:
            msg = await ws.recv()
            event = json.loads(msg)
            print(f"Event: {event['type']} - {event.get('data', {})}")

asyncio.run(test_websocket())
```

## Test 4: End-to-End Chat → Task → Code Flow (Parallel Engineers)

This is the full integration test with the parallel engineer architecture.

### Architecture Overview

The system now uses **background workers** for engineer execution:
- Manager/OM handle user interaction synchronously
- Engineers execute tasks asynchronously via the EngineerWorker service
- Multiple engineers can work in parallel on different tasks
- Job progress is broadcast via WebSocket events

### Start the Backend

```bash
cd backend
ENV=development uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

The engineer worker starts automatically on app startup.

### Send a Chat Message

```bash
curl -X POST "http://localhost:8000/api/v1/chat/send?project_id=00000000-0000-0000-0000-000000000001" \
  -H "Authorization: Bearer change-me-in-production" \
  -H "Content-Type: application/json" \
  -d '{"content": "Create a simple Python function that adds two numbers in src/math_utils.py"}'
```

### Expected Flow (Parallel Architecture)

1. **Manager receives message** → Emits `workflow_update` (node: manager, status: started)
2. **Manager creates task** → Uses `create_kanban_task` tool
3. **Manager hands off to OM** → "OM should coordinate this work"
4. **OM assigns task** → Uses `list_engineers`, `assign_task` tools
5. **OM dispatches to engineer** → Uses `dispatch_to_engineer` tool
6. **OM returns immediately** → "I've dispatched the task to Engineer-1"
7. **Manager responds to user** → "Work has been assigned. You'll see progress via live updates."

**Meanwhile, in background:**
8. **EngineerWorker picks up job** → Emits `job_started` event
9. **Engineer implements** → Emits `job_progress` events for tool calls
10. **Engineer creates PR** → Emits `job_completed` event with PR URL

### Monitor WebSocket Events

Workflow events (synchronous Manager/OM flow):
```json
{"type": "workflow_update", "data": {"current_node": "manager", "node_status": "started"}}
{"type": "agent_log", "data": {"agent_role": "manager", "log_type": "tool_call", "tool_name": "create_kanban_task"}}
{"type": "workflow_update", "data": {"current_node": "om", "node_status": "started"}}
{"type": "agent_log", "data": {"agent_role": "om", "log_type": "tool_call", "tool_name": "dispatch_to_engineer"}}
{"type": "workflow_update", "data": {"current_node": "om", "node_status": "completed"}}
```

Job events (async engineer execution):
```json
{"type": "job_started", "data": {"job_id": "...", "agent_id": "...", "status": "started"}}
{"type": "job_progress", "data": {"job_id": "...", "tool_name": "create_branch", "message": "..."}}
{"type": "job_progress", "data": {"job_id": "...", "tool_name": "write_file", "message": "..."}}
{"type": "job_completed", "data": {"job_id": "...", "result": "...", "pr_url": "..."}}
```

## Test 5: Parallel Engineer Execution

Verify multiple engineers can work simultaneously.

```bash
# Create two tasks and dispatch to different engineers
curl -X POST "http://localhost:8000/api/v1/chat/send?project_id=00000000-0000-0000-0000-000000000001" \
  -H "Authorization: Bearer change-me-in-production" \
  -H "Content-Type: application/json" \
  -d '{"content": "Create two features: 1) Add a subtract function in math_utils.py 2) Add a multiply function in math_utils.py. Assign each to a different engineer."}'
```

### Monitor Active Jobs

```bash
curl "http://localhost:8000/api/v1/jobs/active?project_id=00000000-0000-0000-0000-000000000001" \
  -H "Authorization: Bearer change-me-in-production"
```

### Expected

Both jobs should run in parallel (status: "running"), each handled by a different engineer.

## Test 6: Job Status API

## Test 7: Task API

Verify tasks can be created and listed.

```bash
# List tasks
curl "http://localhost:8000/api/v1/tasks?project_id=00000000-0000-0000-0000-000000000001" \
  -H "Authorization: Bearer change-me-in-production"

# Get task details
curl "http://localhost:8000/api/v1/tasks/{task_id}" \
  -H "Authorization: Bearer change-me-in-production"
```

## Test 8: Job Status API

Check engineer job status.

```bash
# List all jobs for a project
curl "http://localhost:8000/api/v1/jobs?project_id=00000000-0000-0000-0000-000000000001" \
  -H "Authorization: Bearer change-me-in-production"

# List active jobs only
curl "http://localhost:8000/api/v1/jobs/active?project_id=00000000-0000-0000-0000-000000000001" \
  -H "Authorization: Bearer change-me-in-production"

# Get specific job details
curl "http://localhost:8000/api/v1/jobs/{job_id}" \
  -H "Authorization: Bearer change-me-in-production"

# Cancel a pending job
curl -X POST "http://localhost:8000/api/v1/jobs/{job_id}/cancel" \
  -H "Authorization: Bearer change-me-in-production"
```

## Troubleshooting

### "No LLM provider configured"

- Check that `CLAUDE_API_KEY` or `GEMINI_API_KEY` is set in your env file.
- Ensure `ENV=development` is set to load `.env.development`.

### "E2B SDK not installed"

```bash
pip install e2b
```

### "Agent has no active sandbox"

- Sandboxes are created on-demand when the orchestrator wakes an agent.
- Ensure E2B_API_KEY is valid.

### "GitHub PR creation failed"

- Check `GITHUB_TOKEN` has write access to the repo.
- Ensure the branch was pushed before creating PR.

### Events not appearing in WebSocket

- Verify you're subscribed to the correct channels (`workflow`, `activity`, or `all`).
- Check backend logs for "Failed to emit" warnings.

---

## Playwright E2E Testing

Playwright tests provide browser-based end-to-end testing of the full application.

### Setup

```bash
cd frontend

# Install dependencies
npm install

# Install Playwright browsers
npx playwright install chromium
```

### Configuration

Copy `.env.test` to `.env.test.local` and configure:

```bash
# Required for GitHub integration tests
GITHUB_TOKEN=ghp_...        # For app operations
GITHUB_TOKEN_TEST=ghp_...   # For cleanup ONLY
GITHUB_TEST_OWNER=your-username
TEST_PROJECT_ID=...         # UUID of test project in database
```

### Running Tests

```bash
# Setup verification (no servers needed)
npx playwright test setup.spec.ts

# All E2E tests (with servers)
START_SERVERS=1 npm run test:e2e

# Specific test file
npx playwright test chat.spec.ts

# With UI mode
npm run test:e2e:ui

# GitHub integration tests (creates real repos!)
npx playwright test github-integration.spec.ts
```

### Test Structure

```
frontend/e2e/
├── fixtures/
│   ├── auth.ts          # Authentication helpers
│   └── test-data.ts     # Test data and config
├── pages/
│   ├── chat.page.ts     # Chat page object
│   ├── projects.page.ts # Projects page object
│   └── kanban.page.ts   # Kanban page object
├── utils/
│   └── github-cleanup.ts # GitHub cleanup (GITHUB_TOKEN_TEST)
├── setup.spec.ts        # Setup verification
├── projects.spec.ts     # Projects dashboard tests
├── chat.spec.ts         # Chat with GM tests
├── kanban.spec.ts       # Kanban board tests
└── github-integration.spec.ts # Full GitHub workflow test
```

### GitHub Integration Test

This test validates the complete agent workflow:

1. Sends chat message: "Create repo and push README.md"
2. Manager processes → OM dispatches to Engineer
3. Engineer creates repo and pushes (using `GITHUB_TOKEN`)
4. Test verifies repo exists on GitHub
5. Test cleanup deletes repo (using `GITHUB_TOKEN_TEST`)

**Important**: `GITHUB_TOKEN_TEST` is used ONLY for test cleanup (deleting repos).
The application always uses `GITHUB_TOKEN` for operations.

### CI/CD

The GitHub Actions workflow in `.github/workflows/test.yml` runs:

1. **Backend Unit Tests** - SQLite, fast
2. **Backend Integration Tests** - PostgreSQL service
3. **Frontend Unit Tests** - Vitest
4. **E2E Tests** - Playwright (projects, chat, kanban)
5. **GitHub Integration Tests** - Full workflow (main branch only)

Required GitHub Secrets:
- `API_TOKEN` - Backend auth token
- `GITHUB_TOKEN` - For app operations
- `GITHUB_TOKEN_TEST` - For test cleanup
- `GITHUB_TEST_OWNER` - GitHub username
- `TEST_PROJECT_ID` - Test project UUID
