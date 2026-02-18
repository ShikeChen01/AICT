# Agent 2 — Blocked on Agent 1

**Status:** Agent 2 (Agent runtime: loop, prompts, tools, workers) is **blocked** until Agent 1 (Data & messaging foundation) has landed.

Per the [3-Agent Work Split](../../.cursor/plans/3-agent_work_split_2f569943.plan.md):

- **Agent 1** must land first (DB + messaging are the base).
- **Agent 2** depends on Agent 1 (DB, MessageRouter, message service).

---

## Prerequisites (Agent 1 deliverables)

Before Agent 2 can implement, the following must exist and be verified:

### 1. Database

- [ ] **Alembic migrations** that add/change:
  - `project_settings` table
  - `channel_messages` table
  - `agent_messages` table
  - `agent_sessions` table
  - `agents.memory`, `agents.role` updates, drop `agents.priority`
  - Drop abort fields from `tasks`
  - Migrate then drop: `chat_messages`, `tickets`, `ticket_messages`, `engineer_jobs`
- [ ] **ORM models** in `db/models.py` for: channel messages, agent messages, sessions, project settings; updated agents/tasks models
- [ ] **Repositories** in `db/repositories/`: `messages.py` (channel + agent message queries), `sessions.py`, plus updates to agents/tasks repos

### 2. Core

- [ ] `core/constants.py`: `USER_AGENT_ID` and role enums

### 3. Message service & router

- [ ] `services/message_service.py`: send, list (by target/conversation), mark received; broadcast (write only, no wake)
- [ ] `api_internal/messaging.py`: internal endpoints (send_message, broadcast_message) used by tools
- [ ] `api/v1/messages.py`: `POST /messages/send`, `GET /messages`, `GET /messages/all` per [backend&API.md](backend/backend&API.md)
- [ ] `workers/message_router.py`: singleton that receives send requests, writes to DB (`channel_messages`, status `sent`), pushes wake-up to per-agent `asyncio.Queue`; on startup, replay undelivered (`status = 'sent'`) into queues
- [ ] Schemas: Pydantic for channel messages, project settings (and DTOs for these endpoints)

### 4. Verification

- [ ] Migrations run cleanly
- [ ] Message send/list and internal messaging work
- [ ] MessageRouter can be unit/integration tested (e.g. send → DB + queue; replay on startup)

**How to verify:** Run `python backend/scripts/check_agent1_landed.py` from the project root. When it exits 0, Agent 2 can proceed.

---

## Agent 2 scope (to implement after unblock)

Once Agent 1 has landed, Agent 2 will implement the following with **production-grade code** and **unit tests** for all builds.

### Workers and loop

- `workers/worker_manager.py`: startup (migrations if configured, init MessageRouter, load agents from DB, spawn one AgentWorker per agent, replay undelivered); shutdown (cancel workers, stop router, close sandboxes, DB pool)
- `workers/agent_worker.py`: per-agent task; outer loop: `await notification_queue.get()` then run inner loop; inner loop: check interrupt, read new messages from DB (message_service), context-window/summarization, assemble prompt, call LLM, persist to `agent_messages`, handle tool calls (END solo rule, execute others, result injection), loopback handling, max iterations/loopbacks; session create/end via session_service
- `workers/loop.py`: shared loop logic (or inlined in agent_worker) per [ideas.md](ideas.md) Pillar 2

### Prompts

- `services/prompt_service.py`: block assembly (Identity, Rules, Thinking, Memory, Loopback, Summarization) per [agents.md](backend/agents.md); token budgets and truncation of conversation only
- Identity/Rules/Thinking/Memory/Loopback/Summarization content (or templates) for manager, cto, engineer

### Tools

- `tools/context.py`: ToolContext (agent_id, project_id, sandbox_id, etc.); `tools/registry.py`: role → tool set; build_tools(agent, project) binding context
- `tools/core.py`: end, sleep, send_message, broadcast_message, update_memory, read_history (message_service / agent repo / session repo)
- `tools/management.py`: interrupt_agent, abort_task, spawn_engineer, list_agents (WorkerManager, task_service)
- `tools/tasks.py`: create_task, list_tasks, assign_task, update_task_status, get_task_details (task_service)
- `tools/git.py`, `tools/sandbox.py`: create_branch, create_pull_request, list_branches, view_diff; execute_command (sandbox service). Sandbox pool: `services/sandbox_pool.py` (persistent slot allocator per project_settings)
- Tool result truncation: temp file in sandbox + truncated reply per [tools.md](backend/tools.md)

### Services

- `services/session_service.py`: create/end session, write to `agent_sessions`, link `agent_messages`
- `services/agent_service.py`: lifecycle (spawn worker via WorkerManager), list, get, get context (inspector); ensure GM/CTO created on project create
- `services/llm_service.py`: non-streaming LLM calls (Claude/Gemini via existing adapters)
- `services/e2b_service.py` and sandbox pool integration (existing + pool logic)

### API

- `api_internal/lifecycle.py`, `api_internal/tasks.py`, `api_internal/git.py`, `api_internal/sandbox.py` (used by tools)
- `api/v1/agents.py`: list, get, status, context, memory. `api/v1/sessions.py`: list sessions. `api/v1/settings.py`: GET/PATCH project settings. Drop or merge: chat, tickets, jobs, engineers per backend spec

### WebSocket (backend only)

- Emit events from the loop: `agent_text`, `agent_tool_call`, `agent_tool_result`, `agent_message` (when agent sends to USER_AGENT_ID) for frontend (Agent 3)

### Testing

- Unit tests for: WorkerManager, AgentWorker, loop logic, prompt_service, tool registry and each tool module, session_service, agent_service, sandbox_pool, API routes (agents, sessions, settings), WebSocket event emission
- Fix all issues; solution must be production grade

---

## Next step

When Agent 1 is complete, run:

```bash
python backend/scripts/check_agent1_landed.py
```

If it exits with code 0, resume Agent 2 implementation using this document and the plan as the source of truth.
