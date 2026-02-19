# Test Report

**Date:** 2026-02-18  
**Scope:** Backend/frontend parity migration with legacy removal.

## Architecture Verified

- Legacy chat/ticket/jobs paths removed from frontend runtime and tests.
- Canonical public APIs used by frontend:
  - `/api/v1/messages/*`
  - `/api/v1/sessions/*`
  - `/api/v1/agents/*`
  - `/api/v1/repositories/*`
  - `/api/v1/tasks/*`
- Workspace route is canonical:
  - `/repository/:projectId/workspace`
- WebSocket contract aligned to current events:
  - `agent_text`, `agent_tool_call`, `agent_tool_result`, `agent_message`, `system_message`
  - plus workflow/activity/task/agent status events.

## Legacy Removal Summary

- Removed frontend ticket/chat artifacts (`TicketChat`, `useTicketChat`, ticket API client methods).
- Removed deprecated websocket event usage in frontend (`gm_status`, `job_*`, `ticket_*`).
- Removed backend runtime references to deprecated OM/GM roles in access-control and orchestration logic.
- Removed deprecated ticket-related backend exceptions and corresponding handler mappings.
- Removed legacy test files centered on tickets/jobs/chat routes.

## Remaining Compatibility Notes

- DB migrations still include historical `gm`/`om` conversion logic for existing data.
- Some test helper variable names may still use legacy naming, but runtime behavior now enforces manager/cto/engineer.

## Recommended Validation Commands

```bash
# Backend
cd backend
python -m pytest tests/ -v --tb=short

# Frontend
cd frontend
npm test

# Optional E2E
npm run test:e2e
```
