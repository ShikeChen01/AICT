# Backend Architecture & API Specification

## Overview

The AICT backend is a FastAPI application that orchestrates a multi-agent AI software development team. It provides two API surfaces (public REST and internal agent API), a WebSocket layer for real-time streaming, and a worker system that runs agents as long-lived async tasks.

### Tech Stack

| Layer | Technology |
|-------|-----------|
| Framework | FastAPI (async, ASGI) |
| Runtime | Python 3.12+, uvicorn |
| Database | PostgreSQL 15+ via SQLAlchemy async ORM |
| Migrations | Alembic |
| Auth | Firebase Admin SDK (user auth) + Bearer token (API auth) |
| Sandbox | E2B (remote sandboxes per agent) |
| LLM | Anthropic Claude, Google Gemini (via LangChain adapters) |
| Visualization | LangGraph (topology metadata only, no execution) |
| Real-time | WebSocket (FastAPI native) |
| Testing | pytest + pytest-asyncio, aiosqlite (unit), testcontainers (integration) |

### Design Principles

1. **DB is the single source of truth** -- no LangGraph checkpointer, no in-memory state persistence. All agent state, memory, messages, and sessions live in PostgreSQL.
2. **One universal execution model** -- all agents (GM, CTO, Engineers) run on the same async loop. Agent-specific behavior is driven by prompt blocks and tool registries.
3. **Messaging as the communication primitive** -- no separate chat system, no ticket system. All communication (agent-to-agent, agent-to-user, user-to-agent) flows through `channel_messages`.
4. **Inspection and interference** -- the user observes agent output via WebSocket streaming and interferes by sending messages to any agent.

---

## Directory Structure

```
backend/
├── main.py                     # FastAPI app, lifespan, middleware
├── config.py                   # Pydantic settings (env-based)
├── __init__.py
│
├── api/                        # Public REST API (user-facing)
│   └── v1/
│       ├── router.py           # Aggregated v1 router
│       ├── auth.py             # Firebase auth + user profile
│       ├── repositories.py     # Project/repo CRUD
│       ├── agents.py           # Agent listing, inspector, spawn
│       ├── tasks.py            # Kanban board CRUD
│       ├── messages.py         # User-to-agent messaging (NEW)
│       ├── sessions.py         # Agent session history (NEW)
│       └── settings.py         # Project settings (NEW)
│
├── api_internal/               # Internal API (agent tools → services)
│   ├── router.py               # Aggregated internal router
│   ├── lifecycle.py            # Agent wake/sleep/interrupt
│   ├── messaging.py            # send_message, broadcast (NEW)
│   ├── tasks.py                # Task CRUD (agent-scoped)
│   ├── git.py                  # Git operations (in sandbox)
│   └── sandbox.py              # execute_command (NEW)
│
├── core/                       # Cross-cutting concerns
│   ├── auth.py                 # Token verification, Firebase init
│   ├── access_control.py       # Role-based permission checks
│   ├── exceptions.py           # Custom exception hierarchy
│   ├── error_handlers.py       # FastAPI exception handlers
│   └── constants.py            # USER_AGENT_ID, role enums (NEW)
│
├── db/                         # Database layer
│   ├── session.py              # Async engine + session factory
│   ├── models.py               # SQLAlchemy ORM models
│   ├── migration_runner.py     # Alembic programmatic runner
│   └── repositories/           # Data access layer (NEW)
│       ├── base.py             # Generic async CRUD base
│       ├── agents.py           # Agent queries (NEW)
│       ├── tasks.py            # Task queries (NEW)
│       ├── messages.py         # Channel + agent message queries (NEW)
│       └── sessions.py         # Session queries (NEW)
│
├── services/                   # Business logic layer
│   ├── agent_service.py        # Agent lifecycle, spawn, state
│   ├── task_service.py         # Task CRUD with business rules
│   ├── message_service.py      # Channel message send/read (NEW)
│   ├── session_service.py      # Agent session tracking (NEW)
│   ├── e2b_service.py          # Sandbox create/connect/close
│   ├── sandbox_pool.py         # Persistent slot allocator (NEW)
│   ├── git_service.py          # Git operations via sandbox
│   ├── prompt_service.py       # Prompt block assembly (NEW)
│   ├── llm_service.py          # LLM client abstraction
│   └── repo_provisioning.py    # Clone repos on project create
│
├── workers/                    # Agent execution runtime (NEW)
│   ├── agent_worker.py         # Per-agent async loop
│   ├── message_router.py       # Singleton message dispatcher
│   ├── worker_manager.py       # Lifecycle manager (startup/shutdown)
│   └── loop.py                 # The universal async loop
│
├── tools/                      # Agent tool definitions
│   ├── registry.py             # Role → tool set mapping
│   ├── core.py                 # end, sleep, send_message, etc. (NEW)
│   ├── management.py           # interrupt, spawn, list_agents (NEW)
│   ├── tasks.py                # create/list/assign/update tasks
│   ├── git.py                  # create_branch, create_pr, etc.
│   ├── sandbox.py              # execute_command (NEW)
│   └── context.py              # ToolContext dataclass (NEW)
│
├── websocket/                  # Real-time streaming
│   ├── endpoint.py             # /ws WebSocket handler
│   ├── manager.py              # Connection + channel manager
│   └── events.py               # Event types + factory functions
│
├── migrations/                 # Alembic migration scripts
│   ├── env.py
│   └── versions/
│
├── schemas/                    # Pydantic request/response models
│
├── scripts/                    # CLI utilities
│   └── seed.py                 # Dev data seeder
│
└── tests/                      # Test suite
```

### Files to Drop (Deprecated)

These files correspond to the deprecated ticket system, old chat system, old LangGraph execution, and old worker model. They will be replaced during the refactor:

| File | Replacement |
|------|-------------|
| `api/v1/chat.py` | `api/v1/messages.py` (unified messaging) |
| `api/v1/tickets.py` | Dropped (messaging replaces tickets) |
| `api/v1/engineers.py` | Merged into `api/v1/agents.py` |
| `api/v1/jobs.py` | `api/v1/sessions.py` (universal sessions) |
| `api_internal/tickets.py` | `api_internal/messaging.py` |
| `api_internal/files.py` | `api_internal/sandbox.py` (execute_command) |
| `services/chat_service.py` | `services/message_service.py` |
| `services/ticket_service.py` | Dropped |
| `services/engineer_worker.py` | `workers/agent_worker.py` |
| `services/engineer_graph_service.py` | Dropped (no graph execution) |
| `services/orchestrator.py` | `workers/worker_manager.py` + `services/sandbox_pool.py` |
| `graph/` (entire directory) | Dropped (LangGraph is visualization-only, lives in a thin utility) |
| `tools/tickets.py` | Dropped |
| `tools/e2b.py`, `tools/e2b_tool.py` | `tools/sandbox.py` |
| `tools/files.py` | Dropped (file ops via execute_command) |
| `tools/git_tool.py` | Merged into `tools/git.py` |
| `tools/agents.py` | `tools/management.py` |
| `schemas/chat.py` | `schemas/message.py` |
| `schemas/ticket.py` | Dropped |
| `schemas/job.py` | `schemas/session.py` |

---

## Application Lifecycle

### Startup (`main.py` lifespan)

```
1. Run Alembic migrations (auto-migrate on startup)
2. Initialize WorkerManager
   a. Load all agents from DB
   b. Spawn an AgentWorker (asyncio.Task) for each agent
   c. Start the MessageRouter singleton
   d. Replay undelivered messages (channel_messages with status="sent")
3. Initialize sandbox pool state from DB
```

### Shutdown

```
1. Signal all AgentWorkers to stop (cancel tasks)
2. Stop the MessageRouter
3. Close all non-persistent sandboxes
4. Close DB connection pool
```

### Request Flow

```
User HTTP request
  → FastAPI route handler
    → Auth middleware (Firebase token → user identity)
      → Service layer (business logic + DB queries)
        → Response

Agent tool call
  → Internal API route handler
    → Role-based access control
      → Service layer
        → Response (injected as tool result)
```

---

## Configuration (`config.py`)

All configuration is environment-based via `pydantic-settings`. The `Settings` class reads from `.env` (production) or `.env.development` (local).

| Category | Key Settings |
|----------|-------------|
| **Database** | `DATABASE_URL`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`, `DB_SOCKET_PATH` |
| **Auth** | `FIREBASE_CREDENTIALS_PATH`, `FIREBASE_PROJECT_ID`, `API_TOKEN` |
| **E2B** | `E2B_API_KEY`, `E2B_TEMPLATE_ID`, `E2B_TIMEOUT_SECONDS` |
| **LLM** | `CLAUDE_API_KEY`, `GEMINI_API_KEY`, `CLAUDE_MODEL`, `GEMINI_MODEL`, `LLM_REQUEST_TIMEOUT_SECONDS`, `LLM_MAX_TOKENS`, `LLM_TEMPERATURE` |
| **Git** | `GITHUB_TOKEN`, `CODE_REPO_URL`, `SPEC_REPO_PATH`, `CODE_REPO_PATH` |
| **Server** | `HOST`, `PORT`, `DEBUG`, `AUTO_RUN_MIGRATIONS_ON_STARTUP` |

---

## Authentication & Authorization

### User Authentication

User identity uses Firebase (Google OAuth). There is no `POST /auth/login` endpoint. The frontend sends the Firebase ID token as `Authorization: Bearer <token>` on every request; the backend verifies it with Firebase Admin SDK and resolves the user.

**GitHub token** is separate from login. It is stored per user in `users.github_token`, set via `PATCH /api/v1/auth/me`. The backend uses it for Git/repo operations (repository create, import, clone URLs, E2B sandbox repo access). It is not used for authentication.

### API Authorization

Every public API endpoint requires a valid Bearer token verified by the `verify_token` dependency. Internal API endpoints use a separate API token for agent-to-backend calls.

### WebSocket Authentication

WebSocket connections pass the token as a query parameter: `/ws?token=<TOKEN>&project_id=<UUID>`. The token is verified before the connection is accepted.

---

## Public REST API (`/api/v1`)

All endpoints are prefixed with `/api/v1`. All request/response bodies are JSON. All IDs are UUIDs. Timestamps are ISO 8601 UTC.

### Health

```
GET /api/v1/health
Response: { "status": "ok" }
```

---

### Auth

```
GET /api/v1/auth/me
  Auth: Required
  Response: UserProfile
  Notes: Returns current user profile.

PATCH /api/v1/auth/me
  Auth: Required
  Body: { "display_name"?: string, "github_token"?: string }
  Response: UserProfile
  Notes: Updates user profile. github_token is the per-user GitHub Personal Access Token for repo operations (not used for login); stored in users.github_token.
```

**UserProfile schema:**
```json
{
  "id": "uuid",
  "email": "string",
  "display_name": "string | null",
  "github_token_set": "boolean",
  "created_at": "datetime",
  "updated_at": "datetime"
}
```

---

### Repositories (Projects)

```
GET /api/v1/repositories
  Auth: Required
  Response: Repository[]
  Notes: Lists all repositories owned by the authenticated user.

POST /api/v1/repositories
  Auth: Required
  Body: { "name": string, "description"?: string, "private"?: boolean }
  Response: Repository
  Notes: Creates a new GitHub repo and project. Auto-creates GM and CTO agents.
         Auto-creates project_settings with defaults.

POST /api/v1/repositories/import
  Auth: Required
  Body: { "name": string, "description"?: string, "code_repo_url": string }
  Response: Repository
  Notes: Imports an existing GitHub repo as a project.

GET /api/v1/repositories/{id}
  Auth: Required
  Response: Repository

PATCH /api/v1/repositories/{id}
  Auth: Required
  Body: { "name"?: string, "description"?: string, "code_repo_url"?: string }
  Response: Repository

DELETE /api/v1/repositories/{id}
  Auth: Required
  Response: 204 No Content
  Notes: Cascades to agents, tasks, messages, sessions, settings.
```

**Repository schema:**
```json
{
  "id": "uuid",
  "owner_id": "uuid | null",
  "name": "string",
  "description": "string | null",
  "spec_repo_path": "string",
  "code_repo_url": "string",
  "code_repo_path": "string",
  "created_at": "datetime",
  "updated_at": "datetime"
}
```

---

### Project Settings (NEW)

```
GET /api/v1/repositories/{id}/settings
  Auth: Required
  Response: ProjectSettings

PATCH /api/v1/repositories/{id}/settings
  Auth: Required
  Body: { "max_engineers"?: int, "persistent_sandbox_count"?: int }
  Response: ProjectSettings
  Notes: Updates project-level configurables.
```

**ProjectSettings schema:**
```json
{
  "id": "uuid",
  "project_id": "uuid",
  "max_engineers": "int (default 5)",
  "persistent_sandbox_count": "int (default 1)",
  "created_at": "datetime",
  "updated_at": "datetime"
}
```

---

### Agents

```
GET /api/v1/agents?project_id={uuid}
  Auth: Required
  Response: Agent[]
  Notes: Lists all agents for a project, ordered by role hierarchy.

GET /api/v1/agents/{id}
  Auth: Required
  Response: Agent

GET /api/v1/agents/status?project_id={uuid}
  Auth: Required
  Response: AgentStatusDetailed[]
  Notes: Extended agent info with task queue size and pending message count.

GET /api/v1/agents/{id}/context
  Auth: Required
  Response: AgentContext
  Notes: Inspector data: system prompt blocks, available tools, recent messages,
         sandbox status. Used by the frontend Agent Inspector panel.

GET /api/v1/agents/{id}/memory
  Auth: Required
  Response: { "memory": object | null }
  Notes: Returns the agent's Layer 1 memory (self-define block content).
```

**Agent schema:**
```json
{
  "id": "uuid",
  "project_id": "uuid",
  "role": "manager | cto | engineer",
  "display_name": "string",
  "model": "string",
  "status": "sleeping | active | busy",
  "current_task_id": "uuid | null",
  "sandbox_id": "string | null",
  "sandbox_persist": "boolean",
  "memory": "object | null",
  "created_at": "datetime",
  "updated_at": "datetime"
}
```

**AgentStatusDetailed schema** (extends Agent):
```json
{
  "...Agent fields",
  "queue_size": "int",
  "pending_message_count": "int",
  "task_queue": "TaskSummary[]"
}
```

---

### Messages (NEW -- replaces Chat + Tickets)

User-to-agent messaging. All messages flow through `channel_messages`. The user is represented by `USER_AGENT_ID` (`00000000-0000-0000-0000-000000000000`).

```
POST /api/v1/messages/send
  Auth: Required
  Body: { "project_id": uuid, "target_agent_id": uuid, "content": string }
  Response: ChannelMessage
  Status: 202 Accepted
  Notes: Persists the message and pushes a notification to the target agent.
         Returns immediately (async). The agent's response arrives via WebSocket.
         The target agent wakes up if sleeping.

GET /api/v1/messages?project_id={uuid}&agent_id={uuid}&limit={int}&offset={int}
  Auth: Required
  Response: ChannelMessage[]
  Notes: Returns messages between the user and a specific agent (conversation view).
         Ordered by created_at descending. Both directions (user→agent and agent→user).

GET /api/v1/messages/all?project_id={uuid}&limit={int}&offset={int}
  Auth: Required
  Response: ChannelMessage[]
  Notes: Returns all messages to/from the user across all agents in a project.
         Used for a unified activity view.
```

**ChannelMessage schema:**
```json
{
  "id": "uuid",
  "project_id": "uuid",
  "from_agent_id": "uuid | null",
  "target_agent_id": "uuid | null",
  "content": "string",
  "message_type": "normal | system",
  "status": "sent | received",
  "broadcast": "boolean",
  "created_at": "datetime"
}
```

**Key design decisions:**

- `POST /messages/send` is **fire-and-forget** (202 Accepted). There is no synchronous response. The old `POST /chat/send` was synchronous (waited for GM to respond); the new system is fully async.
- The user sees agent responses via WebSocket events (`agent_message` event type) delivered in real-time as the agent loop processes the message.
- This endpoint replaces `POST /api/v1/chat/send`. The old endpoint waited for the GM response synchronously, which blocked the HTTP connection for 30-60s. The new flow is non-blocking.

---

### Agent Sessions (NEW -- replaces Jobs)

```
GET /api/v1/sessions?project_id={uuid}&agent_id={uuid}&limit={int}&offset={int}
  Auth: Required
  Response: AgentSession[]
  Notes: Lists sessions for an agent, most recent first.

GET /api/v1/sessions/{id}
  Auth: Required
  Response: AgentSession
  Notes: Full session details including iteration count and end reason.

GET /api/v1/sessions/{id}/messages?limit={int}&offset={int}
  Auth: Required
  Response: AgentMessage[]
  Notes: Returns the persistent message log for a session.
         Used by the frontend inspector for debugging.
```

**AgentSession schema:**
```json
{
  "id": "uuid",
  "agent_id": "uuid",
  "project_id": "uuid",
  "task_id": "uuid | null",
  "trigger_message_id": "uuid | null",
  "status": "running | completed | force_ended | error",
  "end_reason": "normal_end | max_iterations | max_loopbacks | interrupted | aborted | error | null",
  "iteration_count": "int",
  "started_at": "datetime",
  "ended_at": "datetime | null"
}
```

**AgentMessage schema:**
```json
{
  "id": "uuid",
  "agent_id": "uuid",
  "session_id": "uuid | null",
  "project_id": "uuid",
  "role": "system | user | assistant | tool",
  "content": "string",
  "tool_name": "string | null",
  "tool_input": "object | null",
  "tool_output": "string | null",
  "loop_iteration": "int",
  "created_at": "datetime"
}
```

---

### Tasks (Kanban)

```
GET /api/v1/tasks?project_id={uuid}&status={string}
  Auth: Required
  Response: Task[]
  Notes: Lists tasks with optional status filter.

POST /api/v1/tasks?project_id={uuid}
  Auth: Required
  Body: TaskCreate
  Response: Task
  Status: 201

GET /api/v1/tasks/{id}
  Auth: Required
  Response: Task

PATCH /api/v1/tasks/{id}
  Auth: Required
  Body: TaskUpdate
  Response: Task

PATCH /api/v1/tasks/{id}/status?status={string}
  Auth: Required
  Response: Task

POST /api/v1/tasks/{id}/assign?agent_id={uuid}
  Auth: Required
  Response: Task

DELETE /api/v1/tasks/{id}
  Auth: Required
  Response: 204
```

**Task schema:**
```json
{
  "id": "uuid",
  "project_id": "uuid",
  "title": "string",
  "description": "string | null",
  "status": "backlog | specifying | assigned | in_progress | review | done | aborted",
  "critical": "int (0-10, 0=most critical)",
  "urgent": "int (0-10, 0=most urgent)",
  "assigned_agent_id": "uuid | null",
  "module_path": "string | null",
  "git_branch": "string | null",
  "pr_url": "string | null",
  "parent_task_id": "uuid | null",
  "created_by_id": "uuid | null",
  "created_at": "datetime",
  "updated_at": "datetime"
}
```

---

### User Actions on Agents (NEW)

These endpoints let the user directly interfere with agent operations.

```
POST /api/v1/agents/{id}/interrupt
  Auth: Required
  Body: { "reason": string }
  Response: { "message": "Agent interrupted." }
  Notes: Force-ends the agent's current session. Same as interrupt_agent tool
         but invoked by the user via the API. The agent's current iteration
         completes before the session ends.

POST /api/v1/agents/{id}/wake
  Auth: Required
  Body: { "message"?: string }
  Response: { "message": "Agent woken." }
  Notes: Sends a wake-up notification to a sleeping agent. Optionally includes
         a message that the agent will see at its next iteration.
```

---

## Internal API (`/internal/agent`)

Agent tools call the internal API to perform operations. These endpoints are authenticated via a shared API token (not Firebase). The internal API provides a clean boundary between tool functions and service logic.

All internal endpoints receive `agent_id` and `project_id` as headers or query parameters for context and access control.

### Lifecycle

```
POST /internal/agent/end
  Body: { "agent_id": uuid }
  Notes: Handled by the loop directly; included for completeness.

POST /internal/agent/sleep
  Body: { "agent_id": uuid, "duration_seconds": int }

POST /internal/agent/interrupt
  Body: { "agent_id": uuid, "target_agent_id": uuid, "reason": string }
  Access: GM, CTO only
```

### Messaging

```
POST /internal/agent/send-message
  Body: { "agent_id": uuid, "target_agent_id": uuid, "content": string }
  Notes: Writes to channel_messages, pushes notification to target.

POST /internal/agent/broadcast
  Body: { "agent_id": uuid, "content": string }
  Notes: Writes broadcast message. Does NOT wake any agents.

GET /internal/agent/read-messages
  Query: agent_id, status=sent
  Notes: Returns unread messages for the agent. Called by the loop.

POST /internal/agent/mark-received
  Body: { "message_ids": uuid[] }
  Notes: Marks messages as received after the agent reads them.
```

### Memory

```
POST /internal/agent/update-memory
  Body: { "agent_id": uuid, "content": string }
  Notes: Overwrites agent.memory. Enforces 2500 token hard cap.

GET /internal/agent/read-history
  Query: agent_id, limit, offset, session_id
  Notes: Queries agent_messages table.
```

### Tasks

```
POST /internal/agent/tasks
  Body: { "agent_id": uuid, "project_id": uuid, "title": string, ... }
  Access: GM only

GET /internal/agent/tasks
  Query: project_id, status, assigned_to
  Access: All agents

POST /internal/agent/tasks/{id}/assign
  Body: { "agent_id": uuid, "target_agent_id": uuid }
  Access: GM only

PATCH /internal/agent/tasks/{id}/status
  Body: { "agent_id": uuid, "status": string }
  Access: GM (any task), Engineers (own tasks)

GET /internal/agent/tasks/{id}
  Access: All agents

POST /internal/agent/abort-task
  Body: { "agent_id": uuid, "reason": string }
  Access: Engineers only
  Notes: Atomically: update task → notify assigner → end session.
```

### Management

```
POST /internal/agent/spawn-engineer
  Body: { "agent_id": uuid, "display_name": string, "model"?: string }
  Access: GM only
  Notes: Checks project_settings.max_engineers before spawning.

GET /internal/agent/list-agents
  Query: project_id
  Access: GM, CTO
```

### Git

```
POST /internal/agent/git/create-branch
  Body: { "agent_id": uuid, "branch_name": string }
  Access: CTO, Engineers

POST /internal/agent/git/create-pr
  Body: { "agent_id": uuid, "title": string, "description"?: string }
  Access: CTO, Engineers

GET /internal/agent/git/branches
  Query: agent_id
  Access: All agents

GET /internal/agent/git/diff
  Query: agent_id, base, head
  Access: All agents
```

### Sandbox

```
POST /internal/agent/execute
  Body: { "agent_id": uuid, "command": string, "timeout"?: int }
  Access: All agents
  Notes: Runs command in the agent's E2B sandbox. On first call in a session,
         acquires a sandbox from the pool (see sandbox_pool.py).
         Result is subject to MAX_TOOL_RESULT_TOKENS truncation.
```

---

## WebSocket Protocol (`/ws`)

### Connection

```
ws://{host}/ws?token={TOKEN}&project_id={UUID}&channels={CHANNELS}
```

- `token`: Bearer token for authentication
- `project_id`: Scopes events to a specific project
- `channels`: Comma-separated list of channels to subscribe to

### Channels

| Channel | Events | Purpose |
|---------|--------|---------|
| `agent_stream` | `agent_text`, `agent_tool_call`, `agent_tool_result` | Real-time agent loop output (NEW) |
| `messages` | `agent_message`, `system_message` | Messages to/from user (NEW) |
| `kanban` | `task_created`, `task_update` | Kanban board changes |
| `agents` | `agent_status` | Agent state changes (sleeping/active/busy) |
| `activity` | `agent_log`, `sandbox_log` | Debug-level activity feed |
| `all` | All of the above | Subscribe to everything |

### Client → Server Messages

```json
{ "type": "ping" }
→ { "type": "pong" }

{ "type": "subscribe", "channel": "agent_stream" }
{ "type": "unsubscribe", "channel": "activity" }

{ "type": "inspect_agent", "agent_id": "uuid" }
// Switches which agent's stream is being forwarded to this connection.
// The backend always streams all agent output; this tells the server
// which agent's buffer to prioritize for this client.
```

### Server → Client Events

**Agent Stream Events (NEW):**

These replace the old synchronous chat response. The agent's loop output is streamed token-by-token to the frontend.

```json
{
  "type": "agent_text",
  "data": {
    "agent_id": "uuid",
    "agent_role": "manager",
    "content": "string (incremental text chunk)",
    "session_id": "uuid",
    "iteration": 3
  }
}

{
  "type": "agent_tool_call",
  "data": {
    "agent_id": "uuid",
    "agent_role": "engineer",
    "tool_name": "execute_command",
    "tool_input": { "command": "npm test" },
    "session_id": "uuid",
    "iteration": 5
  }
}

{
  "type": "agent_tool_result",
  "data": {
    "agent_id": "uuid",
    "tool_name": "execute_command",
    "output": "string (truncated if large)",
    "success": true,
    "session_id": "uuid",
    "iteration": 5
  }
}
```

**Message Events (NEW):**

```json
{
  "type": "agent_message",
  "data": {
    "id": "uuid",
    "from_agent_id": "uuid",
    "target_agent_id": "00000000-0000-0000-0000-000000000000",
    "content": "string",
    "message_type": "normal",
    "created_at": "datetime"
  }
}
```

Messages where `target_agent_id = USER_AGENT_ID` are pushed to the user's WebSocket connection. This is how agents "talk" to the user.

**Task Events:**

```json
{
  "type": "task_created",
  "data": { "...Task fields" }
}

{
  "type": "task_update",
  "data": { "...Task fields" }
}
```

**Agent Status Events:**

```json
{
  "type": "agent_status",
  "data": {
    "id": "uuid",
    "role": "engineer",
    "display_name": "Engineer-1",
    "status": "active",
    "current_task_id": "uuid | null"
  }
}
```

---

## Worker System

The worker system is the runtime that executes agents. It consists of three components.

### WorkerManager (singleton, startup)

Initialized during FastAPI lifespan. Manages everything:

```python
class WorkerManager:
    async def start(self):
        """Called at startup."""
        self.message_router = MessageRouter()
        await self.message_router.start()

        agents = await load_all_agents_from_db()
        for agent in agents:
            worker = AgentWorker(agent.id, self.message_router)
            self.workers[agent.id] = worker
            asyncio.create_task(worker.run())

        await self.replay_undelivered_messages()

    async def spawn_worker(self, agent_id: UUID):
        """Called when a new engineer is spawned at runtime."""
        worker = AgentWorker(agent_id, self.message_router)
        self.workers[agent_id] = worker
        asyncio.create_task(worker.run())

    async def shutdown(self):
        """Called at app shutdown."""
        for worker in self.workers.values():
            worker.cancel()
        await self.message_router.stop()
```

### MessageRouter (singleton)

Routes messages between agents:

```python
class MessageRouter:
    async def send(self, from_id, target_id, content, project_id, msg_type="normal"):
        """Persist message to DB, notify target worker."""
        msg = await self.message_service.create(from_id, target_id, content, project_id, msg_type)

        if target_id == USER_AGENT_ID:
            await ws_manager.push_to_user(project_id, msg)
        else:
            worker = self.worker_manager.get_worker(target_id)
            if worker:
                await worker.notify()

        return msg

    async def broadcast(self, from_id, content, project_id):
        """Persist broadcast message. No notifications (passive)."""
        await self.message_service.create_broadcast(from_id, content, project_id)

    async def replay_undelivered(self):
        """On startup: re-notify workers for any sent-but-unreceived messages."""
        pending = await self.message_service.get_undelivered()
        for msg in pending:
            worker = self.worker_manager.get_worker(msg.target_agent_id)
            if worker:
                await worker.notify()
```

### AgentWorker (one per agent)

The per-agent async task. See `agents.md` and `ideas.md` for the full loop specification.

```python
class AgentWorker:
    def __init__(self, agent_id, message_router):
        self.agent_id = agent_id
        self.notification_queue = asyncio.Queue()
        self.interrupt_flag = asyncio.Event()
        self.message_router = message_router

    async def run(self):
        """Outer loop: agent lifetime."""
        while True:
            await self.notification_queue.get()      # SLEEP until notified

            session = await self.start_session()      # Create agent_sessions row
            try:
                await self.run_session(session)       # Inner loop
            finally:
                await self.end_session(session)       # Update session row

    async def run_session(self, session):
        """Inner loop: one wake-to-END cycle."""
        iteration = 0
        loopback_count = 0

        while True:
            iteration += 1
            if iteration > MAX_ITERATIONS:
                session.end_reason = "max_iterations"
                break

            if self.interrupt_flag.is_set():
                self.interrupt_flag.clear()
                session.end_reason = "interrupted"
                break

            new_messages = await self.read_unread_messages()
            conversation = self.assemble_conversation(new_messages)

            if self.token_count(conversation) > CONTEXT_THRESHOLD:
                await self.trigger_summarization(conversation)

            response = await self.call_llm(conversation)
            await self.persist_response(session, iteration, response)
            await self.emit_stream_events(response)

            if response.has_tool_calls:
                loopback_count = 0
                if response.has_end_call:
                    if response.has_other_calls:
                        # END mixed with other tools: strip END, execute others, continue
                        results = await self.execute_tools(response.other_calls)
                        self.inject_end_stripped_note(conversation)
                    else:
                        # Solo END: break
                        session.end_reason = "normal_end"
                        break
                else:
                    results = await self.execute_tools(response.tool_calls)
                    self.inject_tool_results(conversation, results)
            else:
                loopback_count += 1
                if loopback_count >= MAX_LOOPBACKS:
                    session.end_reason = "max_loopbacks"
                    break
                self.inject_loopback_prompt(conversation)

    async def notify(self):
        """Wake this agent (called by MessageRouter)."""
        await self.notification_queue.put(True)
```

---

## Service Layer

Services contain business logic. They are injected into API routes and worker loops. They do not import FastAPI types (no Request, Response, Depends).

### MessageService

```python
class MessageService:
    async def send(self, from_id, target_id, content, project_id, msg_type) -> ChannelMessage
    async def broadcast(self, from_id, content, project_id) -> ChannelMessage
    async def get_unread(self, agent_id) -> list[ChannelMessage]
    async def mark_received(self, message_ids: list[UUID])
    async def get_conversation(self, agent_id_a, agent_id_b, project_id, limit, offset) -> list[ChannelMessage]
    async def get_undelivered(self) -> list[ChannelMessage]  # status=sent, for recovery
```

### SessionService

```python
class SessionService:
    async def start(self, agent_id, project_id, trigger_message_id, task_id) -> AgentSession
    async def end(self, session_id, end_reason, iteration_count)
    async def persist_message(self, session_id, agent_id, project_id, role, content, iteration, ...)
    async def get_session_messages(self, session_id, limit, offset) -> list[AgentMessage]
```

### AgentService (refactored)

```python
class AgentService:
    async def spawn_engineer(self, project_id, display_name, model) -> Agent
    async def ensure_project_agents(self, project) -> tuple[Agent, Agent]  # GM, CTO
    async def get_by_id(self, agent_id) -> Agent
    async def update_status(self, agent_id, status)
    async def update_memory(self, agent_id, content)  # enforce 2500 token cap
    async def get_memory(self, agent_id) -> dict | None
```

### SandboxPoolService (NEW)

```python
class SandboxPoolService:
    async def acquire(self, agent_id, project_id) -> SandboxMetadata
        """
        Acquire a sandbox for an agent.
        1. Check for free persistent slot → assign if available
        2. No free slot → create non-persistent sandbox
        """

    async def release(self, agent_id, project_id)
        """
        Release an agent's sandbox after session ends.
        If agent held a persistent slot → free the slot
        If another agent has a non-persistent sandbox → promote it
        """

    async def get_persistent_count(self, project_id) -> int
    async def get_active_sandboxes(self, project_id) -> list[SandboxMetadata]
```

### PromptService (NEW)

```python
class PromptService:
    def build_identity_block(self, role, project_name, agent_name) -> str
    def build_rules_block(self) -> str
    def build_thinking_block(self) -> str
    def build_memory_block(self, memory_content) -> str
    def assemble_system_prompt(self, agent, project) -> str
    def format_channel_messages(self, messages) -> list[dict]
    def build_loopback_block(self) -> str
    def build_summarization_block(self) -> str
```

---

## Tool System Integration

Tools are stateless functions. Runtime context (agent_id, project_id, sandbox_id) is bound at assembly time using a `ToolContext` dataclass.

### ToolContext

```python
@dataclass
class ToolContext:
    agent_id: UUID
    project_id: UUID
    agent_role: str
    sandbox_id: str | None
    repo_url: str
    message_router: MessageRouter
    session: AsyncSession
```

### Tool Assembly

```python
def build_tools(agent: Agent, project: Repository, ctx: ToolContext) -> list[Tool]:
    tools = [
        end_tool(ctx),
        sleep_tool(ctx),
        send_message_tool(ctx),
        broadcast_message_tool(ctx),
        update_memory_tool(ctx),
        read_history_tool(ctx),
    ]

    if agent.role == "manager":
        tools += [
            interrupt_agent_tool(ctx),
            spawn_engineer_tool(ctx),
            list_agents_tool(ctx),
            create_task_tool(ctx),
            list_tasks_tool(ctx),
            assign_task_tool(ctx),
            update_task_status_tool(ctx),
            get_task_details_tool(ctx),
        ]
    elif agent.role == "cto":
        tools += [
            interrupt_agent_tool(ctx),
            list_agents_tool(ctx),
            list_tasks_tool(ctx, read_only=True),
            get_task_details_tool(ctx),
        ]
    elif agent.role == "engineer":
        tools += [
            abort_task_tool(ctx),
            update_task_status_tool(ctx, own_only=True),
            get_task_details_tool(ctx),
            list_tasks_tool(ctx, read_only=True),
        ]

    # All roles get git and sandbox tools (scoped by role)
    tools += build_git_tools(agent.role, ctx)
    tools.append(execute_command_tool(ctx))

    return tools
```

---

## Error Handling

### Exception Hierarchy

```
AICTException (base)
├── TaskNotFoundError
├── AgentNotFoundError
├── ProjectNotFoundError
├── SandboxNotFoundError
├── MaxEngineersReached
├── InvalidAgentRole
├── InvalidTaskStatus
├── GitOperationFailed
├── GitOperationBlocked
├── ScopeViolationError           # Agent accessing outside its scope
├── MemoryExceededError (NEW)     # update_memory exceeds 2500 tokens
├── SessionNotFoundError (NEW)
└── MessageNotFoundError (NEW)
```

### Error Response Format

All errors return a consistent JSON structure:

```json
{
  "detail": "Human-readable error summary",
  "message": "Technical error message",
  "path": "/api/v1/..."
}
```

HTTP status codes:
- `400` -- Bad request (validation, business rule violation)
- `401` -- Unauthorized (missing/invalid token)
- `403` -- Forbidden (insufficient permissions)
- `404` -- Not found
- `409` -- Conflict (e.g., max engineers reached)
- `422` -- Validation error (Pydantic)
- `500` -- Internal server error
- `504` -- Gateway timeout (LLM timeout)

---

## Database Integration

### Session Management

SQLAlchemy async sessions are managed via a factory pattern:

- API routes: `Depends(get_db)` provides a session per request with auto-commit/rollback
- Worker loops: `AsyncSessionLocal()` context manager per operation batch
- Services: receive session as a parameter (never create their own)

### Repository Pattern

Data access is encapsulated in repository classes under `db/repositories/`. Each repository provides typed query methods:

```python
class AgentRepository(BaseRepository[Agent]):
    async def get_by_project(self, project_id) -> list[Agent]
    async def get_by_role(self, project_id, role) -> list[Agent]
    async def count_by_role(self, project_id, role) -> int
    async def update_status(self, agent_id, status)
    async def update_memory(self, agent_id, memory)
```

### Migration Strategy

Alembic migrations run automatically at startup (configurable via `AUTO_RUN_MIGRATIONS_ON_STARTUP`). See `db.md` for the full migration plan from the current schema to the new schema.

---

## Observability

### Logging

Python `logging` module throughout. Key log points:
- Agent session start/end with duration and iteration count
- LLM calls with model, token count, latency
- Tool executions with name, duration, success/failure
- Sandbox operations (create, connect, close)
- Message routing (send, broadcast, wake-up)
- WebSocket connections/disconnections

### WebSocket Activity Feed

The `activity` channel streams debug-level events to the frontend:
- `agent_log`: agent thoughts, tool calls, tool results
- `sandbox_log`: sandbox stdout/stderr

### Session Audit Trail

Every agent session is recorded in `agent_sessions` with:
- Start/end timestamps
- Iteration count
- End reason (normal, max_iterations, interrupted, error, etc.)
- Triggering message
- Associated task

Every message in a session is recorded in `agent_messages` with:
- Role (system/user/assistant/tool)
- Content
- Tool name, input, output (for tool calls)
- Loop iteration number
