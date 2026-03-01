# AICT — System Architecture

## Table of Contents

1. [Overview](#overview)
2. [System Topology](#system-topology)
3. [Tech Stack](#tech-stack)
4. [Backend Architecture](#backend-architecture)
   - [Application Lifecycle](#application-lifecycle)
   - [Public REST API](#public-rest-api)
   - [Internal Agent API](#internal-agent-api)
   - [WebSocket Layer](#websocket-layer)
   - [Worker System](#worker-system)
   - [Agent Execution Loop](#agent-execution-loop)
   - [LangGraph Orchestration Layer](#langgraph-orchestration-layer)
5. [Agent System](#agent-system)
   - [Agent Roles](#agent-roles)
   - [Agent State Machine](#agent-state-machine)
   - [Messaging Protocol](#messaging-protocol)
6. [LLM Layer](#llm-layer)
7. [Prompt System](#prompt-system)
8. [Tool System](#tool-system)
9. [Sandbox System](#sandbox-system)
10. [Database Layer](#database-layer)
11. [Frontend Architecture](#frontend-architecture)
12. [Authentication & Authorization](#authentication--authorization)
13. [Observability](#observability)
14. [Design Principles](#design-principles)

---

## Overview

AICT (AI Code Team) is a multi-agent AI software development platform. Users interact with a team of AI agents — a **Manager**, a **CTO**, and dynamically-spawned **Engineers** — through a real-time web interface. Agents autonomously plan, implement, and ship code in isolated sandbox environments, communicating through a shared messaging channel.

The system is built around an **inspection and interference** model: users observe any agent's live output in real-time and can send messages to any agent at any time to redirect, clarify, or instruct.

---

## System Topology

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           USER BROWSER                                  │
│                                                                         │
│   React SPA (Vite + TypeScript)                                        │
│   ├── REST requests → /api/v1/*    (Firebase Bearer token)             │
│   └── WebSocket → /ws              (real-time event stream)            │
└──────────────────────────┬──────────────────────────────────────────────┘
                           │
                    HTTPS / WSS
                           │
┌──────────────────────────▼──────────────────────────────────────────────┐
│                       BACKEND (Cloud Run)                               │
│                                                                         │
│   FastAPI + uvicorn                                                     │
│   ├── /api/v1/*         Public REST API (user-facing)                  │
│   ├── /internal/agent/* Internal API (agent tool calls)                │
│   ├── /ws               WebSocket endpoint                              │
│   │                                                                     │
│   ├── WorkerManager     Startup orchestrator                           │
│   │   └── AgentWorker × N   One per agent, outer loop                 │
│   │       └── run_inner_loop()   Universal LLM + tool loop            │
│   │                                                                     │
│   ├── MessageRouter     In-process async notification bus              │
│   ├── Reconciler        Background self-healing task                   │
│   └── ws_backend_log_stream  Backend log WebSocket broadcaster        │
└────────────┬─────────────────────────┬───────────────────────────────┘
             │                         │
    ┌────────▼──────────┐   ┌──────────▼──────────┐
    │   PostgreSQL       │   │   LLM Providers      │
    │   (Self-hosted VM) │   │   ├── Anthropic       │
    │                   │   │   ├── Google Gemini   │
    │  Single source    │   │   └── OpenAI          │
    │  of truth for     │   └─────────────────────────┘
    │  all state        │
    └───────────────────┘          ┌──────────────────────┐
                                   │   Sandbox VM          │
                                   │   (self-hosted pool   │
                                   │    manager port 9090) │
                                   └──────────────────────┘
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Backend Framework** | FastAPI (async ASGI) |
| **Runtime** | Python 3.11+, uvicorn |
| **Database** | PostgreSQL 15+ via SQLAlchemy async ORM |
| **Migrations** | Alembic (auto-run at startup) |
| **Auth** | Firebase Admin SDK (user) + Bearer token (internal API) |
| **LLM Providers** | Anthropic Claude, Google Gemini, OpenAI GPT |
| **Agent Orchestration** | LangGraph (Manager/CTO graph) + custom inner loop |
| **Sandbox Execution** | Self-hosted VM pool manager (httpx REST client) |
| **Real-time** | WebSocket (FastAPI native) |
| **Frontend Framework** | React 19 + TypeScript |
| **Build** | Vite 7 |
| **Styling** | Tailwind CSS 4 |
| **State** | React hooks + context (no external library) |
| **Containerization** | Docker (python:3.11-slim) |
| **Deployment** | Google Cloud Run |
| **Testing** | pytest + pytest-asyncio (backend), Vitest + Playwright (frontend) |

---

## Backend Architecture

### Application Lifecycle

`backend/main.py` defines the FastAPI app and its startup/shutdown sequence via an async lifespan context manager.

**Startup sequence** (in order):

1. **Database migrations** (soft-fail) — Alembic runs all pending migrations via `run_startup_migrations()`. If this times out or fails, startup continues (configurable via `AUTO_RUN_MIGRATIONS_ON_STARTUP`).
2. **Repository provisioning** (soft-fail) — `RepoProvisioningService.provision_all_projects()` ensures cloned repos exist on disk for all projects. Non-critical; skipped on timeout/error.
3. **WorkerManager startup** (hard-fail, retried 3×) — loads all agents from DB, spawns one `AgentWorker` asyncio task per agent, waits for all queues to register, then replays any undelivered messages. If all 3 attempts fail, the container crashes and Cloud Run restarts it. This is intentionally hard-fail because a backend with no workers silently drops all user messages.
4. **Backend log broadcaster** — binds the log stream to the event loop and starts broadcasting backend log lines to WebSocket subscribers.
5. **Reconciler** — starts the background self-healing loop that runs every 30 seconds.

**Shutdown sequence:**

1. Cancel all `AgentWorker` asyncio tasks
2. Cancel reconciler and log broadcaster tasks
3. Reset the `MessageRouter` singleton

**Background tasks running continuously:**

| Task | Purpose | Restart on crash? |
|------|---------|-------------------|
| `AgentWorker × N` | Per-agent outer loop | Yes (WorkerManager respawns) |
| `_run_broadcaster_forever` | Backend log WebSocket broadcast | Yes (wrapping loop) |
| `_run_reconciler_forever` | System self-healing | Yes (wrapping loop) |

---

### Public REST API

All user-facing endpoints are at `/api/v1/*`. Firebase Bearer token authentication is required on every endpoint.

| Resource | Prefix | Description |
|----------|--------|-------------|
| Health | `GET /api/v1/health` | Basic liveness check |
| Worker health | `GET /api/v1/health/workers` | WorkerManager diagnostic status |
| Auth | `/api/v1/auth/*` | User profile, GitHub token |
| Repositories | `/api/v1/repositories/*` | Project CRUD, settings, usage |
| Agents | `/api/v1/agents/*` | Agent roster, status, inspector, memory |
| Messages | `/api/v1/messages/*` | User↔agent messaging |
| Sessions | `/api/v1/sessions/*` | Agent session history and message log |
| Tasks | `/api/v1/tasks/*` | Kanban board CRUD |
| Attachments | `/api/v1/attachments/*` | Image upload/download (stored as bytea in Postgres) |
| Documents | `/api/v1/documents/*` | Per-project architecture documents (read-only for users) |
| Diagnostics | `/api/v1/diagnostics/*` | Debug endpoints |

See `docs/backend/backend&API.md` for the full endpoint specification.

**Repository creation flow** — when `POST /api/v1/repositories` is called:
1. Creates GitHub repo via `GitService` using the user's stored GitHub token
2. Clones the repo into a local `code_path` directory
3. Creates a `Repository` DB row with local paths
4. Auto-creates **Manager** and **CTO** agents for the project
5. Adds the creating user as an `owner` membership row in `repository_memberships`
6. Spawns `AgentWorker` tasks for both agents via `WorkerManager.spawn_worker()`

---

### Internal Agent API

All agent tool calls go through the internal API at `/internal/agent/*`. This API uses a shared Bearer token (not Firebase) for authentication.

| Category | Routes | Description |
|----------|--------|-------------|
| Lifecycle | `/lifecycle/*` | Agent sleep/interrupt |
| Messaging | `/messaging/*` | send_message, broadcast, read messages |
| Memory | `/memory/*` | update_memory, read_history |
| Management | `/management/*` | spawn_engineer, list_agents |
| Git | `/git/*` | create_branch, create_pull_request, list_branches, view_diff |
| Files | `/files/*` | File access helpers |
| Tasks | `/tasks/*` | Task CRUD, status updates, assignment |

Access control is role-based: route handlers check the calling agent's role before executing operations.

---

### WebSocket Layer

WebSocket connections are project-scoped: `ws://{host}/ws?token={TOKEN}&project_id={UUID}`.

**Event categories streamed to the client:**

| Channel | Event Types | Payload |
|---------|-------------|---------|
| `agent_stream` | `agent_text`, `agent_tool_call`, `agent_tool_result` | Live agent loop output |
| `messages` | `agent_message`, `system_message` | Channel messages to/from user |
| `kanban` | `task_created`, `task_update` | Board changes |
| `agents` | `agent_status` | Agent state changes |
| `activity` | `agent_log`, `sandbox_log` | Debug feed |
| `backend_logs` | `backend_log` | Server-side log lines |
| `workflow` | `workflow_update` | LangGraph workflow state changes |
| `usage` | `usage_update` | LLM token/cost usage events |
| `documents` | `document_update` | Project document create/update events |
| `all` | all of the above | Subscribe to every channel |

The backend WebSocket manager (`backend/websocket/manager.py`) broadcasts events to all connected clients subscribed to a project. Events are emitted from:
- The inner loop (`loop.py`) for agent stream events
- Service layer for task/kanban events
- Internal messaging for agent_message events

---

### Worker System

The worker system is the core runtime that keeps agents alive and processes messages. See `docs/backend/workers.md` for the full deep-dive.

**Three components:**

#### WorkerManager (`backend/workers/worker_manager.py`)

Singleton initialized at startup. Responsibilities:
- Spawns one `AgentWorker` asyncio task per agent at startup
- Tracks worker tasks and metadata in memory
- Auto-respawns workers that crash (via `task.add_done_callback`)
- Exposes `spawn_worker()` for runtime agent creation (e.g., new engineers)
- Exposes `remove_worker()` for permanent agent removal
- Exposes `interrupt_agent()` to signal a worker to break its inner loop
- Provides `get_status()` diagnostic for the health endpoint

#### MessageRouter (`backend/workers/message_router.py`)

In-process singleton. Holds a `dict[UUID, asyncio.Queue]` mapping agent IDs to their wake-up queues.

- `register(agent_id, queue)` — called by each `AgentWorker` when it starts
- `notify(agent_id)` — pushes a sentinel (`None`) to the agent's queue to wake it
- `replay(messages)` — on startup, re-notifies workers for any messages stuck in `"sent"` status
- Does **not** write to the database; that is the `MessageService`'s job

#### Reconciler (`backend/workers/reconciler.py`)

Background task that runs every 30 seconds. Fixes four categories of drift:

| Category | Condition | Fix |
|----------|-----------|-----|
| Orphan agents | Agent in DB with no registered worker | Spawn worker |
| Stuck active | Agent `status="active"` > 10 min with no running session | Reset to `sleeping`, force-end session |
| Orphaned sessions | `AgentSession.status="running"` but agent is `sleeping` | Force-end session |
| Stuck messages | `ChannelMessage.status="sent"` > 60 seconds | Re-fire `router.notify()` |

---

### Agent Execution Loop

The universal inner loop (`backend/workers/loop.py`) is the heart of agent execution. All agents — Manager, CTO, and Engineers — run the exact same loop. Agent-specific behavior is driven by prompt blocks and tool registries, not different loop implementations.

**Outer loop** (`AgentWorker.run()`):
```
Register queue with MessageRouter
Loop forever:
  await queue.get()          # Sleep until woken by a message
  Load agent + project from DB
  Mark agent status = "active"
  Create AgentSession row
  → run_inner_loop()
  Mark agent status = "sleeping"
  Commit
```

**Inner loop** (`run_inner_loop()`):
```
Load unread channel messages for this agent
If no unread messages AND no current task assignment → end session (normal_end)
Mark messages as received

Load last 5 sessions of agent_messages (history)
Load project_settings (model_overrides, prompt_overrides, all budget/rate limits)
Assemble PromptAssembly (system prompt + message history + incoming messages)
  → injects role-specific project prompt_override block (max 2000 chars) if set
Resolve model: agent.model_override > project_model_overrides > global defaults

While iteration < MAX_ITERATIONS (1000):
  If interrupt_flag → end session (interrupted)

  Every MID_LOOP_MSG_CHECK_INTERVAL (5) iterations:
    Re-check unread messages from DB
    If new messages found: mark received, inject into messages list

  If context_pressure >= 70% AND not already injected:
    Inject summarization block into messages
    Set summarization_injected = True

  ── Pre-call gates (checked every iteration, in order) ──────────────
  Gate 1 — daily_token_budget > 0:
    If tokens_today >= budget → end session (budget_exhausted) [hard stop]
  Gate 2 — daily_cost_budget_usd > 0:
    If cost_today_usd >= budget → end session (cost_budget_exhausted) [hard stop]
  Gate 3 — calls_per_hour_limit or tokens_per_hour_limit > 0:
    If hourly window exceeded → SOFT PAUSE:
      Sleep 5s, re-read project_settings from DB, re-check limits
      Repeat until limits clear OR user raises the limit OR 10-min timeout
      On timeout → end session (rate_limited_timeout)
      On interrupt during pause → end session (interrupted)
  ─────────────────────────────────────────────────────────────────────

  Call LLM (model, system_prompt, messages, tools)
  Record LLMUsageEvent (provider, model, input_tokens, output_tokens) [soft-fail]
  Save assistant message to agent_messages
  Emit agent_text WebSocket event

  If no tool_calls:
    loopbacks++
    If loopbacks >= MAX_LOOPBACKS (3) → end session (max_loopbacks)
    Inject loopback prompt
    Continue

  If tool_calls contains "end" AND other tools:
    Strip "end", inject end_solo_warning tool result (using real end tool_use_id)
    Continue (do NOT break)

  For each non-end tool call:
    Look up handler by tool name
    Validate tool input schema
    Execute handler (with RunContext)
    Truncate result to tool result budget
    If update_memory succeeds AND summarization was injected:
      Reset summarization_injected = False (allows re-trigger)
    Save tool result to agent_messages
    Emit agent_tool_call + agent_tool_result WebSocket events

  If only "end" tool call → end session (normal_end)

End session (max_iterations)
```

**Session end reasons:**

| Reason | Trigger |
|--------|---------|
| `normal_end` | Agent called `end` tool alone |
| `max_iterations` | Hit 1,000-iteration safeguard |
| `max_loopbacks` | 3 consecutive responses without tool calls |
| `interrupted` | Interrupt flag set by WorkerManager |
| `error` | Unrecoverable exception |
| `budget_exhausted` | Daily token budget reached (hard stop) |
| `cost_budget_exhausted` | Daily cost budget (USD) reached (hard stop) |
| `rate_limited_timeout` | Hourly rate limit not cleared within 10-minute soft-pause window |

**Rate limit soft-pause behaviour**: when the hourly call or token limit is hit, the loop does **not** end the session. Instead it sleeps in 5-second cycles, re-reading `project_settings` from DB on each cycle. If the user raises or clears the limit from the Settings page the agent resumes within one poll cycle (≤5 s) without losing session state. After 10 minutes of waiting the session ends with `rate_limited_timeout`.

---

### LangGraph Orchestration Layer

> **Technical debt** — the inner loop (`loop.py`) is the primary and preferred execution path for **all agents**. The LangGraph graph below is legacy infrastructure; it is inconsistent with the "DB is single source of truth" principle (ADR-001) and is a candidate for removal.

The Manager and CTO agents additionally use a LangGraph `StateGraph` compiled with a checkpointer (`backend/graph/workflow.py`). This graph handles the **Manager↔CTO consultation flow**:

```
Manager node
  → manager_tools (ToolNode)   if LLM called tools
  → cto node                   if response mentions "consult cto", "architecture", etc.
  → END                        otherwise

CTO node
  → cto_tools (ToolNode)       if LLM called tools
  → Manager node               otherwise (returns response to manager)
```

The `OrchestratorService.run_manager_graph()` method invokes this graph and extracts the final AI response. The graph uses either `AsyncPostgresSaver` (production, `GRAPH_PERSIST_POSTGRES=true`) or `MemorySaver` (fallback/default) as a checkpointer, keyed by `project_id` as the thread ID.

The LangGraph graph is used specifically by the `OrchestratorService` for Manager-level interactions triggered by the v1 messages API. The universal `run_inner_loop()` does not use LangGraph.

---

## Agent System

### Agent Roles

| Role | Count | Created by | Default model (env-configurable) | Sandbox |
|------|-------|------------|----------------------------------|---------|
| `manager` | 1 per project | System (on repo create) | `MANAGER_MODEL_DEFAULT` (e.g. `claude-sonnet-4-6`) | Persistent |
| `cto` | 1 per project | System (on repo create) | `CTO_MODEL_DEFAULT` (e.g. `claude-opus-4-6`) | Persistent |
| `engineer` | 0–N per project | Manager (via `spawn_engineer` tool) | `junior` → `ENGINEER_JUNIOR_MODEL`, `intermediate` → `ENGINEER_INTERMEDIATE_MODEL`, `senior` → `ENGINEER_SENIOR_MODEL` | Ephemeral |

**Manager (GM)** is the user-facing orchestrator. It receives all user messages, plans work, creates tasks on the Kanban board, spawns engineers, assigns tasks, and relays results. It can consult the CTO for architectural decisions.

**CTO** is the architecture expert. It is consulted by the Manager or engineers for system design decisions, technology choices, and complex debugging. It has no management authority — it does not spawn or assign engineers.

**Engineers** are implementation workers. They receive assigned tasks, create git branches, write and test code, commit, push, and open pull requests. They report back to whoever assigned their task. The Manager can spawn up to `project_settings.max_engineers` engineers per project (falls back to global `MAX_ENGINEERS` env var if no project setting is set). The `model_override` field on an agent always takes priority over the role/seniority default.

---

### Agent State Machine

```
sleeping ──(message received)──► active ──(END called)──► sleeping
                                    │
                          (task assigned)
                                    │
                                  busy ──(task complete, END)──► sleeping
```

- **sleeping** — blocked on `await queue.get()`, zero CPU cost
- **active** — running the inner loop, processing an LLM turn
- **busy** — active with a `current_task_id` set (working on a specific task)

All state transitions persist to the `agents.status` column immediately.

---

### Messaging Protocol

All communication flows through the `channel_messages` table. There is no separate chat system or ticket system.

**Participants:** Every agent has a UUID. The user is represented by the reserved `USER_AGENT_ID = UUID("00000000-0000-0000-0000-000000000000")`, which never exists in the `agents` table. User messages carry a `from_user_id` FK to the `users` table for attribution.

**Message delivery flow:**
1. Sender calls `send_message` tool (or user calls `POST /api/v1/messages/send`)
2. `MessageService.send()` creates a `ChannelMessage` row with `status="sent"`
3. `MessageRouter.notify(target_agent_id)` pushes a sentinel to the target's queue
4. Target's `AgentWorker` wakes from `await queue.get()`
5. Inner loop reads unread messages from DB via `MessageService.get_unread_for_agent()`
6. Messages are marked `status="received"` after being consumed
7. For messages targeting `USER_AGENT_ID`: a WebSocket `agent_message` event is emitted instead of queue notification

**Broadcast messages** — `broadcast_message` tool — write to `channel_messages` with `broadcast=True` and `target_agent_id=NULL`. They are **not** wake-up signals. Agents read missed broadcasts when they naturally wake for other reasons.

**Message types:**
- `normal` — standard agent-to-agent communication, wakes the target
- `system` — lifecycle events (task assignment notifications, interrupt records); does not wake the target

---

## LLM Layer

The LLM layer is a provider-agnostic abstraction in `backend/llm/`. See `docs/backend/llm.md` for full details.

**Contracts** (`backend/llm/contracts.py`): `LLMTool`, `LLMToolCall`, `LLMMessage`, `LLMRequest`, `LLMResponse` — provider-independent dataclasses. `LLMResponse` includes `input_tokens` and `output_tokens` populated by every provider.

**Provider Router** (`backend/llm/router.py`): resolves the correct provider from the model name string (keyword matching: `claude` → Anthropic, `gemini` → Google, `gpt`/`o1`/`o3` → OpenAI). Falls back to whichever API key is configured.

**Providers** (`backend/llm/providers/`):
- `AnthropicSDKProvider` — Anthropic Python SDK; captures `usage.input_tokens` / `usage.output_tokens` from the response.
- `GeminiProviderAdapter` — Google Gemini SDK; captures `usage_metadata` token counts.
- `OpenAISDKProvider` — OpenAI Python SDK; captures `usage.prompt_tokens` / `usage.completion_tokens`.

**Model resolver** (`backend/llm/model_resolver.py`): maps agent role + seniority → model string with a three-tier priority: (1) agent's own `model_override`, (2) project-level `model_overrides` dict (keyed by role), (3) global defaults from `settings`. Engineer seniority levels: `junior`, `intermediate`, `senior`.

**Pricing** (`backend/llm/pricing.py`): `estimate_cost_usd(model, input_tokens, output_tokens)` — looks up `LLM_MODEL_PRICING` in `backend/config.py` (exact match then longest-prefix match) and returns an estimated USD cost. Used by `LLMUsageRepository` when recording and summarising usage events.

**LLM Service** (`backend/services/llm_service.py`): thin service used by the inner loop. Calls `ProviderRouter.get_provider(model)` then `provider.complete(request)`. Returns a 3-tuple `(text, tool_calls, llm_response)` so the caller can record token counts.

---

## Prompt System

See `docs/backend/prompt_system.md` for the complete specification.

**`PromptAssembly`** (`backend/prompts/assembly.py`) owns the entire LLM-facing context for a session. It is instantiated once per session by the inner loop and mutated as iterations progress. Accepts a `prompt_overrides` dict; if a role-specific entry is present, it appends a `## Project-specific instructions` block (capped at 2,000 characters) at the end of the system prompt.

**System prompt block order** (concatenated, sent as the `system` parameter):
```
Rules → History Rules → Incoming Message Rules → Tool Result Rules
→ Tool IO → Thinking → Memory → Identity
[→ Project-specific instructions (if prompt_override set for this role)]
```

**Conversation message order** (sent as `messages` array):
```
History (last 5 sessions, oldest-first, budget-capped)
→ Incoming messages (new unread channel messages)
→ Tool results (appended each iteration)
→ Conditional: Loopback | End-Solo Warning | Summarization
```

**Token budgets** (character-based, 1 token ≈ 4 chars, 200k token context window):
- System prompt + tool schemas: ~10k tokens (fixed)
- Conversation budget: 190k tokens
  - History: 60% of conversation budget (~114k tokens)
  - Tool results: 30% of conversation budget (~57k tokens)
  - Incoming messages: 8,000 tokens aggregate (6,000-word per-message cap)

**Summarization trigger**: when `context_pressure_ratio() >= 0.70` (total message chars / conversation budget chars), the loop injects the summarization block (once per trigger). After the agent responds with a successful `update_memory` tool call, `summarization_injected` resets to `False`, allowing the trigger to fire again if context pressure remains high.

**History repair**: `_repair_dangling_tool_use()` detects tool_use IDs in history that have no matching tool_result (can happen after mid-session crash) and injects synthetic "session interrupted" tool_results. This prevents Anthropic 400 errors on resumption.

---

## Tool System

Tools are stateless async functions registered in `backend/tools/loop_registry.py`. The inner loop resolves handlers by name and executes them with a `RunContext` that carries the DB session, agent, project, and service instances.

**Tool categories:**

| Category | Tools | Available to |
|----------|-------|-------------|
| **Core** | `end`, `sleep`, `send_message`, `broadcast_message`, `update_memory`, `read_history` | All agents |
| **Management** | `interrupt_agent`, `spawn_engineer`, `list_agents` | Manager, CTO |
| **Management** | `abort_task` | Engineer only |
| **Task** | `create_task`, `assign_task`, `update_task_status` | Manager (scoped) |
| **Task** | `list_tasks`, `get_task_details` | All agents |
| **Git** | `create_branch`, `create_pull_request`, `list_branches`, `view_diff` | CTO, Engineer |
| **Sandbox** | `execute_command` | All agents |
| **Introspection** | `describe_tool` | All agents |

**`end` tool enforcement**: If `end` is called alongside other tools in the same response, the loop strips `end`, executes all other tools, and injects an `end_solo_warning` tool result. The loop does not break. The agent must call `end` alone in a subsequent response.

**Structured tool errors**: when a tool handler raises an exception, `PromptAssembly.append_tool_error()` formats a structured error result:
```
[Tool Error]
tool: <name>
error: <ExceptionType>: <message>
next_action: Review the error above and retry with corrected parameters.
             If the schema is unclear, call describe_tool('<name>') for full parameter details.
```

**Tool result budget**: each tool result is checked against a per-iteration budget (30% of conversation budget). Results exceeding the budget are truncated with a suffix indicating truncation.

See `docs/backend/tools.md` for the complete tool specification.

---

## Sandbox System

Agents execute code in isolated sandbox environments managed by a self-hosted VM pool manager.

**`SandboxService`** (`backend/services/sandbox_service.py`) wraps a `PoolManagerClient` that calls the VM pool manager REST API (`http://{SANDBOX_VM_HOST}:{SANDBOX_VM_POOL_PORT}/api`).

**Pool manager operations:**
- `POST /api/sandbox/session/start` — acquire/create a sandbox for an agent
- `POST /api/sandbox/session/end` — release a sandbox after session ends
- `GET /api/health` — health check
- `GET /api/sandbox/list` — list active sandboxes
- `DELETE /api/sandbox/{id}` — destroy a sandbox

**Sandbox lifecycle by role:**
- **Manager** — gets a persistent sandbox from the pool when using `execute_command` or git tools
- **CTO** — on-demand: sandbox created on first `execute_command` or git tool call
- **Engineer** — ephemeral: sandbox created at session start, destroyed at session end

When `SANDBOX_VM_HOST` is not configured (local dev without a VM), `SandboxService` returns an "offline" placeholder so callers don't crash.

Each agent that holds a sandbox ID has it stored on `agents.sandbox_id`. The `SandboxClient` (`backend/services/sandbox_client.py`) is a multiplexer that routes shell commands and GUI operations to the correct sandbox by ID.

---

## Database Layer

PostgreSQL is the single source of truth for all state. No in-memory state persistence, no LangGraph checkpointer for the inner loop. See `docs/db.md` for the complete schema specification.

**Tables:**

| Table | Purpose |
|-------|---------|
| `users` | Firebase-authenticated users with GitHub credentials |
| `repositories` | Projects (git repos + local paths) |
| `repository_memberships` | User access to projects (roles: `owner`, `member`, `viewer`) |
| `project_settings` | Per-project configurables: max engineers, model/prompt overrides, token/cost/rate budgets |
| `agents` | Agent definitions (role, model, status, memory, sandbox) |
| `tasks` | Kanban board items with 2D priority (critical + urgent) |
| `channel_messages` | Inter-agent and user communication channel; includes `from_user_id` for attribution |
| `agent_sessions` | Session tracking (one row per agent wake→END cycle) |
| `agent_messages` | Persistent log of every LLM message in every session |
| `llm_usage_events` | One row per LLM API call: provider, model, token counts, estimated cost, agent, session, user |
| `attachments` | Binary image blobs (bytea, ≤10 MB, image/* only) |
| `message_attachments` | Junction table linking channel messages to attachments |
| `project_documents` | Manager-writable architecture documents (`doc_type` keyed, e.g. `arc42_lite`, `adr/<slug>`) |

**`project_settings` key columns:**

| Column | Type | Purpose |
|--------|------|---------|
| `max_engineers` | int | Max simultaneous engineer agents |
| `model_overrides` | JSONB | Per-role model override map (e.g. `{"manager": "claude-opus-4-6"}`) |
| `prompt_overrides` | JSONB | Per-role extra system prompt text (max 2,000 chars per role) |
| `daily_token_budget` | int | Max tokens/day (UTC); `0` = unlimited. Hard stop. |
| `daily_cost_budget_usd` | float | Max estimated USD/day (UTC); `0.0` = unlimited. Hard stop. |
| `calls_per_hour_limit` | int | Max LLM calls in rolling 60-min window; `0` = unlimited. Soft pause. |
| `tokens_per_hour_limit` | int | Max tokens in rolling 60-min window; `0` = unlimited. Soft pause. |

**Access control:** every API endpoint that touches a project calls `require_project_access(db, project_id, user_id)` from `backend/core/project_access.py`. This checks `repository_memberships` for a matching row and falls back to the legacy `owner_id IS NULL` pattern for backwards compatibility. Owner-only operations pass `owner_only=True`.

**Session management:**
- API routes: `Depends(get_db)` — one session per request with auto-commit/rollback
- Worker loops: `AsyncSessionLocal()` context manager — one session per agent wake cycle
- Services: receive session as a parameter, never create their own

**Migrations:** Alembic, auto-run at startup via `run_startup_migrations()` (configurable via `AUTO_RUN_MIGRATIONS_ON_STARTUP`). Migration files live in `backend/migrations/versions/`. Currently at migration `014` (project documents). Startup migration is a soft-fail — the backend continues to serve if migration times out or fails.

---

## Frontend Architecture

The frontend is a React 19 + TypeScript SPA built with Vite. See `docs/frontend.md` for the complete specification.

**Key design choices:**
- **No external state library** — React hooks + context only
- **Streaming-first** — all agent output arrives via WebSocket, never from polling
- **Buffer, don't store** — agent stream output is held in an ephemeral per-agent buffer, not React state. Historical data loads from the API on demand.
- **Progressive disclosure** — default view shows text + messages; tool calls and debug info are opt-in visibility levels

**Context hierarchy:**
```
<AuthProvider>              # Firebase auth state (token, user)
  <ProjectProvider>         # Active project + project list
    <AgentStreamProvider>   # WebSocket connection + per-agent stream buffers
      <App />
    </AgentStreamProvider>
  </ProjectProvider>
</AuthProvider>
```

**Routing:**
- `/repositories` — project list, create, import
- `/repository/:projectId/workspace` — main workspace (agent chat)
- `/repository/:projectId/kanban` — Kanban board
- `/repository/:projectId/workflow` — agent topology graph
- `/repository/:projectId/artifacts` — file browser
- `/repository/:projectId/settings` — project settings
- `/settings` — user settings (display name, GitHub token)

**Real-time data flow (user sends a message):**
1. `POST /api/v1/messages/send` → `202 Accepted` (instant)
2. Backend persists message, wakes agent via MessageRouter
3. Agent loop runs: `agent_text` / `agent_tool_call` / `agent_tool_result` WebSocket events stream to the browser
4. Agent calls `send_message(USER_AGENT_ID, ...)` → `agent_message` WebSocket event
5. Frontend appends message to the conversation history

---

## Authentication & Authorization

### User Authentication (Firebase)

Users authenticate via Firebase Google OAuth. The frontend gets a Firebase ID token, sends it as `Authorization: Bearer <token>` on every API request. The backend verifies it with Firebase Admin SDK and resolves/creates the user record.

No separate login endpoint exists. Token verification happens in the `get_current_user` FastAPI dependency.

### Project Access Control (Membership)

Project-level access is enforced by `backend/core/project_access.py`:
- `require_project_access(db, project_id, user_id, owner_only=False)` — raises `403` if the user has no `repository_memberships` row for the project (falls back to `owner_id IS NULL` for legacy/public projects).
- `add_owner_membership(db, project_id, user_id)` — called automatically on `POST /repositories` and import to give the creator `owner` role.
- Membership roles: `owner` (full control including settings), `member` (read/write), `viewer` (read-only). Role enforcement is per-endpoint.

### GitHub Token (per-user)

A GitHub Personal Access Token is stored per user in `users.github_token` and configured via `PATCH /api/v1/auth/me`. It is used for:
- Creating GitHub repositories
- Cloning repos (embedded in clone URLs)
- Git operations within sandboxes

It is **not** used for authentication with AICT — it is a separate credential for GitHub API access.

### Internal API Authorization

The internal agent API (`/internal/agent/*`) uses a shared Bearer token (`API_TOKEN` env var), separate from Firebase. Agent tool implementations authenticate with this token when calling back to the backend.

Role-based access control within the internal API is enforced by checking the calling agent's role in the `agents` table (looked up by the `agent_id` parameter passed in the request).

### WebSocket Authentication

WebSocket connections pass the Firebase token as a query parameter: `/ws?token=<TOKEN>&project_id=<UUID>`. The backend verifies the token before accepting the connection.

---

## Observability

### Logging

Python's standard `logging` module throughout. Structured logs at `INFO` level for:
- Agent session start/end (with duration, iteration count, end reason)
- LLM calls (model, timeout, errors)
- Tool executions (name, success/failure)
- Sandbox operations (create, connect, close, error)
- Message routing (notify, replay, stuck messages)
- WebSocket connections/disconnections
- Reconciler actions (orphan fixes, stuck resets)
- WorkerManager lifecycle (start, stop, respawn)

Logs are broadcast to WebSocket subscribers via the backend log stream (channel: `backend_logs`, event type: `backend_log`).

### WebSocket Activity Feed

The `activity` channel delivers `agent_log` events containing structured agent activity:
- Agent text output
- Tool call details (name, input summary)
- Tool results (success/failure, truncated output)
- Error messages

### Session Audit Trail

Every agent session is recorded in `agent_sessions` with start/end timestamps, iteration count, end reason, and triggering message. Every message in a session is recorded in `agent_messages` — a complete, queryable log of every prompt, response, tool call, and tool result.

The frontend **Agent Inspector** reads from this data via:
- `GET /api/v1/agents/{id}/memory` — working memory content
- `GET /api/v1/sessions?agent_id={id}` — session history
- `GET /api/v1/sessions/{id}/messages` — full message log for a session

### LLM Usage & Cost Monitoring

Every LLM call records an `llm_usage_events` row via `LLMUsageRepository.record()` (soft-fail — write errors do not abort the agent loop). The `GET /api/v1/repositories/{id}/usage` endpoint returns:
- **Today's rollup** — total calls, total input/output tokens, estimated cost USD, per-model breakdown.
- **Last-hour rollup** — calls and tokens in the rolling 60-minute window (used for rate-limit progress bars in the UI).
- **Recent 50 calls** — individual call records with model, tokens, and estimated cost.

Cost estimation uses `backend/llm/pricing.py`, which looks up `LLM_MODEL_PRICING` (defined in `backend/config.py`) by exact model name then longest-prefix match. Prices are in USD per 1,000,000 tokens for input and output separately. Users can edit `LLM_MODEL_PRICING` directly in `config.py` to keep pricing current.

---

## Design Principles

1. **DB is the single source of truth** — no LangGraph checkpointer for the inner loop, no in-memory state persistence. All agent state, memory, messages, and sessions live in PostgreSQL.

2. **One universal execution model** — all agents (Manager, CTO, Engineers) run on the same `run_inner_loop()`. Agent-specific behavior is driven by prompt blocks and tool registries, not different loop implementations.

3. **Messaging as the communication primitive** — no separate chat system, no ticket system. All communication (agent-to-agent, agent-to-user, user-to-agent) flows through `channel_messages`.

4. **Inspection and interference** — users observe any agent's loop output via WebSocket streaming and interfere by sending messages to any agent at any time.

5. **Self-healing system** — the Reconciler runs every 30 seconds and corrects drift: orphaned workers, stuck agents, orphaned sessions, stuck messages. The system is designed to recover from crashes without manual intervention.

6. **Fail loudly for critical components, silently for non-critical** — the WorkerManager startup is a hard-fail (no agents = no value). Migrations and repo provisioning are soft-fail (backend can serve without them).

7. **Provider agnosticism** — the LLM layer abstracts over Anthropic, Google, and OpenAI. The `ProviderRouter` selects the provider by model name; model strings are the only coupling point.

---

## Current State & Roadmap

See `docs/todo.md` for the full phased roadmap. Summary of completion status as of 2026-02-25:

### Phase 0 — Baseline correctness (COMPLETE)

| Fix | File | Status |
|-----|------|--------|
| OpenAI/GPT SDK wiring via provider router | `backend/services/llm_service.py`, `backend/llm/` | Done |
| Engineer `model_override` takes priority | `backend/llm/model_resolver.py` | Done |
| Project-level `max_engineers` enforcement | `backend/services/agent_service.py` | Done |
| Mid-session human messages visible to agent | `backend/workers/loop.py` (mid-loop check every 5 iter) | Done |
| Structured tool error messages with `next_action` | `backend/prompts/assembly.py` | Done |
| Prompt system hardening (block budgets, summarization hooks) | `backend/prompts/assembly.py` | Done |

### Phase 2 — Multi-user access + attribution (COMPLETE)

| Item | Files |
|------|-------|
| `repository_memberships` table + `channel_messages.from_user_id` | migration 009 |
| Centralised access check | `backend/core/project_access.py` |
| Membership data access | `backend/db/repositories/membership.py` |
| All API endpoints use `require_project_access()` | repositories, messages, agents, sessions, tasks |
| Auto-owner membership on create/import | `backend/api/v1/repositories.py` |
| User attribution on sent messages | `MessageService`, schema, frontend types |

### Phase 3 — Project-level model selection + prompt overrides (COMPLETE)

| Item | Files |
|------|-------|
| `model_overrides` + `prompt_overrides` columns | migration 010, `db/models.py` |
| Three-tier model resolution | `backend/llm/model_resolver.py` |
| Prompt override injection into system prompt | `backend/prompts/assembly.py` |
| Settings UI: per-role model inputs + prompt textareas | `frontend/src/pages/Settings.tsx` |
| API + types updated | `backend/schemas/project_settings.py`, `frontend/src/types/index.ts` |

### Phase 4 — API limit monitor + token usage safeguards (COMPLETE)

| Item | Files |
|------|-------|
| `llm_usage_events` table + `daily_token_budget` | migration 011 |
| Token usage captured in all 3 providers | `backend/llm/providers/` |
| Usage repository (record, rollup, summary) | `backend/db/repositories/llm_usage.py` |
| Loop records usage after each LLM call | `backend/workers/loop.py` |
| Daily token hard-stop gate in loop | `backend/workers/loop.py` |
| `GET /repositories/{id}/usage` endpoint | `backend/api/v1/repositories.py` |
| Settings UI: budget + usage table + recent calls | `frontend/src/pages/Settings.tsx` |
| Hourly rate limits (calls + tokens) — soft-pause | migration 012, `loop.py` |
| Daily cost budget (USD) — hard-stop | migration 012, `loop.py` |
| Cost estimation (pricing lookup) | `backend/llm/pricing.py`, `backend/config.py` |
| Settings UI: rate limit inputs + progress bars + cost column | `frontend/src/pages/Settings.tsx` |

### Phase 1 — Self-host PostgreSQL (COMPLETE)

Self-hosted PostgreSQL 16 on a GCE VM via `infra/postgres/docker-compose.yml`. Custom `postgresql.conf` and `pg_hba.conf` mounted read-only; SSL certs from `/opt/postgres/ssl`. Backup/restore scripts in `infra/postgres/scripts/`. Backend connects via VPC (private IP, not Cloud SQL socket).

### Phase 6 — Image/attachment end-to-end (COMPLETE)

| Item | Files |
|------|-------|
| `attachments` + `message_attachments` tables | migration 013, `db/models.py` |
| Upload endpoint (multipart, ≤10 MB, image/* only) | `backend/api/v1/attachments.py` |
| SHA-256 integrity stored per attachment | `db/models.py` (`Attachment.sha256`) |
| Attachment IDs surfaced on `ChannelMessage` | `db/models.py` (selectin relationship) |

### Phase 10 — Per-project typed document store (COMPLETE)

| Item | Files |
|------|-------|
| `project_documents` table | migration 014, `db/models.py` |
| REST read endpoints for users | `backend/api/v1/documents.py` |
| Agent write tool | `backend/tools/executors/docs.py` |
| WebSocket `document_update` events | `backend/websocket/` |
| Architecture page in frontend | `frontend/src/components/Architecture/ArchitecturePage.tsx` |

### Phases 5, 7–9 — Not yet started

| Phase | Goal |
|-------|------|
| 5 | Kimi/Moonshot provider integration (cheap provider) |
| 7 | Streaming + messaging upgrades (structured WS events, chat semantics) |
| 8 | Subagent pattern + async tooling safety model |
| 9 | Sandbox image upgrades + pressure tests |

### Known Technical Debt

| Item | Impact |
|------|--------|
| LangGraph checkpointer for Manager-CTO graph | Inconsistent with ADR-001; candidate for removal |
| `Project = Repository` alias in models | Naming confusion |
| `graph_persist_postgres` defaults to `False` | MemorySaver loses checkpoints on restart |
| `LLM_MODEL_PRICING` in `config.py` is manually maintained | Prices go stale; no automated price-feed |
| Sandbox containers lose file state on backend restart | Mitigated by `PROVISION_REPOS_ON_STARTUP` re-clone |
