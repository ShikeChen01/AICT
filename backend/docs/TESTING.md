# AICT Testing Guide

This guide reflects the current architecture:
- Public APIs: `messages`, `sessions`, `tasks`, `agents`, `repositories`
- Workspace route: `/repository/:projectId/workspace`
- WebSocket events: `agent_text`, `agent_tool_call`, `agent_tool_result`, `agent_message`, `system_message`, `task_*`, `agent_status`, `workflow_update`, `agent_log`, `sandbox_log`

## Quick Start

```bash
# Backend tests
cd backend
python -m pytest tests/ -v --tb=short

# Frontend tests
cd frontend
npm test
```

## Backend Smoke Checks

### 1) Health

```bash
curl "http://localhost:8000/api/v1/health"
curl "http://localhost:8000/internal/agent/health"
```

### 2) Send a user message to manager

```bash
curl -X POST "http://localhost:8000/api/v1/messages/send" \
  -H "Authorization: Bearer change-me-in-production" \
  -H "Content-Type: application/json" \
  -d '{
    "project_id":"00000000-0000-0000-0000-000000000001",
    "target_agent_id":"11111111-1111-1111-1111-111111111111",
    "content":"Plan and assign this feature."
  }'
```

### 3) Read conversation and activity messages

```bash
curl "http://localhost:8000/api/v1/messages?project_id=00000000-0000-0000-0000-000000000001&agent_id=11111111-1111-1111-1111-111111111111" \
  -H "Authorization: Bearer change-me-in-production"

curl "http://localhost:8000/api/v1/messages/all?project_id=00000000-0000-0000-0000-000000000001" \
  -H "Authorization: Bearer change-me-in-production"
```

### 4) Sessions API

```bash
curl "http://localhost:8000/api/v1/sessions?project_id=00000000-0000-0000-0000-000000000001" \
  -H "Authorization: Bearer change-me-in-production"
```

### 5) Agent controls (memory / interrupt / wake)

```bash
curl "http://localhost:8000/api/v1/agents/{agent_id}/memory" \
  -H "Authorization: Bearer change-me-in-production"

curl -X POST "http://localhost:8000/api/v1/agents/{agent_id}/interrupt" \
  -H "Authorization: Bearer change-me-in-production" \
  -H "Content-Type: application/json" \
  -d '{"reason":"Manual interruption from test"}'

curl -X POST "http://localhost:8000/api/v1/agents/{agent_id}/wake" \
  -H "Authorization: Bearer change-me-in-production" \
  -H "Content-Type: application/json" \
  -d '{"message":"Resume execution"}'
```

## WebSocket Smoke Check

```python
import asyncio, json, websockets

async def main():
    project_id = "00000000-0000-0000-0000-000000000001"
    token = "change-me-in-production"
    uri = f"ws://localhost:8000/ws?token={token}&project_id={project_id}&channels=all"
    async with websockets.connect(uri) as ws:
        await ws.send(json.dumps({"type": "ping"}))
        print(await ws.recv())
        while True:
            print(await ws.recv())

asyncio.run(main())
```

Expected event families:
- `agent_text`, `agent_tool_call`, `agent_tool_result`
- `agent_message`, `system_message`
- `task_created`, `task_update`, `agent_status`
- `workflow_update`, `agent_log`, `sandbox_log`

## Frontend / E2E

- Workspace is the canonical page (`/repository/:projectId/workspace`).
- Legacy chat route/tests were removed.
- Run Playwright setup and active specs from `frontend/e2e`:

```bash
cd frontend
npx playwright test setup.spec.ts
npm run test:e2e
```

## Troubleshooting

- `401/422` on APIs: ensure `Authorization: Bearer <API_TOKEN>` is present.
- Missing stream updates: verify WebSocket `channels=all` or include required channels.
- No agent execution: confirm workers started in backend startup logs.
