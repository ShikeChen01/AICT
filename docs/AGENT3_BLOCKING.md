# Agent 3 — Frontend & Real-time: Blocking Report

**Status: IMPLEMENTED** (Agent 1 messages API landed; Agent 2 sessions/settings/stream events pending — frontend is ready and degrades gracefully.)

Per the **3-Agent Work Split** plan, Agent 3 depends on:

- **Agent 1**: Data & messaging foundation (DB, message_service, MessageRouter, REST messages API)
- **Agent 2**: Agent runtime (WorkerManager, AgentWorker, loop, agents/sessions/settings APIs, WebSocket stream events)

---

## Dependency checklist (must be true before Agent 3 implements)

### From Agent 1

- [ ] **DB**: Tables `channel_messages`, `agent_messages`, `agent_sessions`, `project_settings` exist (per [docs/db.md](db.md)); migrations run cleanly.
- [ ] **REST Messages API** (per [docs/backend/backend&API.md](backend/backend&API.md)):
  - [ ] `POST /api/v1/messages/send` — Body: `{ project_id, target_agent_id, content }`, Response: ChannelMessage, 202 Accepted
  - [ ] `GET /api/v1/messages?project_id=&agent_id=&limit=&offset=` — Returns ChannelMessage[] (user↔agent conversation)
  - [ ] `GET /api/v1/messages/all?project_id=&limit=&offset=` — Returns ChannelMessage[] (all user messages in project)
- [ ] **MessageRouter** and **message_service** exist; send → DB + queue; replay on startup works.

### From Agent 2

- [ ] **Agents API** (aligned with spec):
  - [ ] `GET /api/v1/agents?project_id=`, `GET /api/v1/agents/{id}`, `GET /api/v1/agents/status?project_id=`
  - [ ] `GET /api/v1/agents/{id}/context`, `GET /api/v1/agents/{id}/memory`
- [ ] **Sessions API**:
  - [ ] `GET /api/v1/sessions?project_id=&agent_id=&limit=&offset=` — AgentSession[]
  - [ ] `GET /api/v1/sessions/{id}`, `GET /api/v1/sessions/{id}/messages?limit=&offset=`
- [ ] **Project settings API**:
  - [ ] `GET /api/v1/repositories/{id}/settings`, `PATCH /api/v1/repositories/{id}/settings` (ProjectSettings)
- [ ] **WebSocket stream events** (emitted from agent loop):
  - [ ] `agent_text` — incremental LLM text
  - [ ] `agent_tool_call` — tool call initiated
  - [ ] `agent_tool_result` — tool result
  - [ ] `agent_message` — when agent sends to USER_AGENT_ID (message to user)

---

## Current state (as of this report)

- **Backend**: Still has `api/v1/chat.py`, `api/v1/tickets.py`, `api/v1/engineers.py`, `api/v1/jobs.py`; no `api/v1/messages.py` or `api/v1/sessions.py`. No `message_service.py`, no `MessageRouter`, no `workers/agent_worker.py` or `workers/worker_manager.py`. WebSocket `events.py` uses old event types (`chat_message`, `gm_status`, `AGENT_LOG`, etc.), not `agent_text` / `agent_tool_call` / `agent_tool_result` / `agent_message`.
- **Frontend**: Has `api/client.ts` (chat, tickets, agents, tasks, repos), `contexts/AuthContext.tsx` only. No `ProjectContext.tsx`, `AgentStreamContext.tsx`, `Workspace.tsx`, `AgentChat/`, `useMessages`, `useAgentStream`, `useSessions`. Chat and TicketChat components still present.

---

## What Agent 3 will do when unblocked

1. **Context and routing**: Add `ProjectContext.tsx`, `AgentStreamContext.tsx`; routing per [docs/frontend.md](frontend.md) (`/repository/:projectId/workspace`, kanban, workflow, artifacts, settings).
2. **API client and hooks**: Extend `api/client.ts` with messages, sessions, settings, WebSocket URL/params; add `useMessages`, `useAgentStream`, `useSessions`; align `useAgents`, `useTasks` with new APIs.
3. **Workspace and AgentChat**: `Workspace.tsx` (three-column), `Workspace/` (WorkspaceLayout, Sidebar, ConnectionStatus), `AgentChat/` (AgentChatView, MessageList, MessageInput, AgentStream, AgentSelector).
4. **Agents and inspector**: Update `Agents/` (AgentsPanel, AgentCard, AgentInspector) to new agents/sessions APIs.
5. **Kanban, Workflow, Artifacts**: Update to new task and agent APIs.
6. **Settings**: Project settings (GET/PATCH repositories/:id/settings), user settings (existing auth/me).
7. **Cleanup**: Remove deprecated `Chat/`, `TicketChat/`, `useChat`, `useTicketChat`, ticket-related types.
8. **Verification**: Write unit tests for new components and hooks; fix all issues; production-grade solution.

---

*When the checklist above is satisfied, run Agent 3 again to implement the frontend and real-time layer and verify with tests.*
