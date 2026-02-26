# AICT — arc42-lite Architecture Document

## 1. Introduction & Goals

### What is AICT?

AICT (AI Code Team) is a multi-agent AI software development platform. Users interact with a team of AI agents through a real-time web interface. Agents autonomously plan, implement, and ship code in isolated sandbox environments.

### Core Design Philosophy

**"We are designing a platform, not a workflow."**

AICT provides the infrastructure and primitives for multi-agent orchestration. It does not prescribe a fixed workflow. Users select which agents to interact with, agents communicate via a unified messaging protocol, and the system self-heals when components drift.

### Quality Goals

| Priority | Quality Goal | Motivation |
|----------|-------------|------------|
| 1 | **Reliability** | Agents must not silently drop messages or get stuck. The system self-heals via the Reconciler. Workers respawn on crash. All state is in PostgreSQL. |
| 2 | **Real-time observability** | Users must see agent activity as it happens. Inspection and interference model: observe any agent, message any agent, at any time. |
| 3 | **Provider agnosticism** | LLM providers change rapidly. The platform must swap providers without code changes. Model strings are the only coupling point. |
| 4 | **Simplicity** | Single purpose: managing multi-agent coding. Avoid redundant features. Keep maintenance low. |
| 5 | **Cost efficiency** | Different agent roles can use different model tiers. Engineers use cheaper models for simple tasks, expensive models for complex ones. |

### Stakeholders

| Role | Expectations |
|------|-------------|
| **User (Developer)** | Reliable agent orchestration. Real-time visibility into agent work. Ability to intervene and redirect agents. Low API cost. |
| **Platform Operator** | Easy deployment (single container + database). Minimal ops burden. Self-healing without manual intervention. |
| **AI Agents** | Stable execution environment. Clear communication protocol. Reliable sandbox access. Persistent memory across sessions. |

---

## 2. Constraints

### Technical Constraints

| Constraint | Rationale |
|-----------|-----------|
| Python 3.11+ backend | Async ecosystem maturity (asyncio, FastAPI, SQLAlchemy async). LLM SDK availability. |
| Single-process async model | Avoids inter-process communication complexity. All workers run as asyncio tasks in one event loop. |
| PostgreSQL as sole state store | No Redis, no message queues, no in-memory state persistence. Simplifies operations and recovery. |
| Docker-based sandboxes | Isolation between agent execution environments. Each sandbox is a disposable container. |

### Organizational Constraints

| Constraint | Rationale |
|-----------|-----------|
| Small team developer project | Architecture must be maintainable by a small team of developers. Avoid over-engineering. |
| GCP deployment target | Cloud Run for compute, Cloud SQL for database. Infrastructure-as-code not yet required. |
| Firebase for auth | Existing dependency. No plans to replace. |

### Convention Constraints

| Constraint | Details |
|-----------|---------|
| All communication via `channel_messages` | No separate chat, ticket, or notification systems. One unified protocol. |
| All agents run the same loop | `run_inner_loop()` is universal. Agent-specific behavior comes from prompts and tool registries. |
| Database migrations auto-run at startup | Alembic migrations execute before workers start. |

---

## 3. Context & Scope

### Business Context

```
User ←──── HTTPS/WSS ────→ AICT Platform ←──── HTTPS ────→ GitHub
                                  │                              (repo ops)
                                  │
                                  ├──── HTTPS ────→ LLM Providers
                                  │                  (Claude, Gemini, GPT)
                                  │
                                  ├──── HTTPS ────→ Firebase Auth
                                  │                  (token verification)
                                  │
                                  └──── SQL ──────→ PostgreSQL
                                                     (all state)
```

| External System | Interface | Purpose |
|----------------|-----------|---------|
| **User Browser** | HTTPS REST + WSS | Project management, agent messaging, real-time observation |
| **GitHub** | HTTPS API | Repository CRUD, clone, push, pull request creation |
| **LLM Providers** | HTTPS API | Agent reasoning via completions (Anthropic, Google, OpenAI) |
| **Firebase** | HTTPS SDK | User identity verification (Google OAuth) |
| **PostgreSQL** | asyncpg (TCP/Unix) | All persistent state |
| **Sandbox VMs** | HTTP REST | Agent code execution in isolated containers |

### Technical Context

See [C4 Diagrams](c4-diagrams.md) for L1 (Context), L2 (Container), and L3 (Component) views.

---

## 4. Solution Strategy

### Key Strategic Decisions

| Decision | Approach | See ADR |
|----------|---------|---------|
| State management | PostgreSQL is the single source of truth. No in-memory persistence, no LangGraph checkpointer for the inner loop. | [ADR-001](adr/001-postgresql-single-source-of-truth.md) |
| Agent execution | One universal loop (`run_inner_loop`) for all agent roles. Behavior is driven by prompts and tools, not code. | [ADR-002](adr/002-universal-agent-execution-loop.md) |
| Communication | All messages flow through `channel_messages`. No separate chat, ticket, or notification systems. | [ADR-003](adr/003-channel-messages-unified-communication.md) |
| Worker architecture | In-process asyncio tasks, not separate processes or containers. Workers share the FastAPI event loop. | [ADR-004](adr/004-in-process-async-workers.md) |
| LLM integration | Provider-agnostic abstraction. `ProviderRouter` selects provider by model name string. | [ADR-005](adr/005-provider-agnostic-llm-layer.md) |
| Platform philosophy | Platform, not workflow. Users select agents, agents are peers, no hardcoded orchestration graph. | [ADR-006](adr/006-platform-not-workflow.md) |
| Resilience | Self-healing Reconciler runs every 30s. Fixes orphan agents, stuck sessions, stuck messages. | [ADR-007](adr/007-self-healing-reconciler.md) |
| Auth separation | Firebase for user identity, separate GitHub PAT for git operations. | [ADR-008](adr/008-firebase-auth-separate-github-credentials.md) |
| Sandbox isolation | Ephemeral sandboxes for engineers (per-session), persistent for Manager/CTO. | [ADR-009](adr/009-ephemeral-vs-persistent-sandboxes.md) |
| Frontend state | React hooks + context only. No Redux, Zustand, or other external state library. | [ADR-010](adr/010-frontend-react-context-only.md) |

### Technology Choices

| Concern | Choice | Rationale |
|---------|--------|-----------|
| Backend framework | FastAPI | Async-native, WebSocket support, dependency injection, OpenAPI docs. |
| Database | PostgreSQL + SQLAlchemy async | ACID guarantees, JSON columns for agent memory, mature async driver (asyncpg). |
| Frontend framework | React 19 + TypeScript | Component model fits agent-centric UI. Hooks + context sufficient for state complexity. |
| Build tool | Vite 7 | Fast HMR, TypeScript support, simple config. |
| Styling | Tailwind CSS 4 | Utility-first, no component library lock-in. |
| Container runtime | Docker | Standard isolation for sandboxes. Deployable anywhere. |
| Deployment | Google Cloud Run | Managed scaling, pay-per-use, WebSocket support, Cloud SQL integration. |

---

## 5. Building Block View

### Level 1: System Decomposition

```
AICT Platform
├── Frontend SPA          # User interface (React)
├── Backend API           # Core runtime (FastAPI)
│   ├── HTTP Layer        # REST + WebSocket endpoints
│   ├── Service Layer     # Business logic
│   ├── Repository Layer  # Data access (SQLAlchemy)
│   ├── Worker Runtime    # Agent execution (asyncio tasks)
│   ├── LLM Layer         # Provider abstraction
│   ├── Prompt System     # Prompt assembly + budgets
│   └── Tool System       # Agent tool dispatch
├── PostgreSQL            # State store
└── Sandbox System        # Isolated agent execution
    ├── Pool Manager      # Container lifecycle
    └── Sandbox Containers # Per-agent environments
```

### Level 2: Backend Internals

| Component | Responsibility | Key Files |
|-----------|---------------|-----------|
| **Public API** | User-facing REST endpoints. Firebase auth. | `backend/api/v1/` |
| **Internal API** | Agent tool call endpoints. Bearer token auth. | `backend/api_internal/` |
| **WebSocket** | Real-time event broadcasting to connected clients. | `backend/websocket/` |
| **WorkerManager** | Spawns, tracks, respawns AgentWorker tasks. | `backend/workers/worker_manager.py` |
| **AgentWorker** | Per-agent outer loop. Blocks on queue, runs inner loop. | `backend/workers/agent_worker.py` |
| **Inner Loop** | Universal LLM + tool execution loop. | `backend/workers/loop.py` |
| **MessageRouter** | In-process wake-up notification bus. | `backend/workers/message_router.py` |
| **Reconciler** | Background self-healing (30s cycle). | `backend/workers/reconciler.py` |
| **Services** | Business logic layer. | `backend/services/` |
| **Repositories** | Data access layer (SQLAlchemy). | `backend/db/repositories/` |
| **LLM Layer** | Provider router + SDK adapters. | `backend/llm/` |
| **Prompt System** | Prompt assembly, block ordering, token budgets. | `backend/prompts/` |
| **Tool System** | Role-based tool registry + handlers. | `backend/tools/` |

---

## 6. Runtime View

### Scenario: User sends a message to an agent

```
User Browser          Frontend SPA         Backend API          PostgreSQL       Agent Worker
     │                     │                    │                    │                 │
     │  Type + Send        │                    │                    │                 │
     │────────────────────▶│                    │                    │                 │
     │                     │  POST /messages    │                    │                 │
     │                     │───────────────────▶│                    │                 │
     │                     │     202 Accepted   │                    │                 │
     │                     │◀───────────────────│                    │                 │
     │                     │                    │  INSERT message    │                 │
     │                     │                    │───────────────────▶│                 │
     │                     │                    │                    │                 │
     │                     │                    │  router.notify()   │                 │
     │                     │                    │───────────────────────────────────▶│
     │                     │                    │                    │   queue.get()   │
     │                     │                    │                    │   (wakes up)    │
     │                     │                    │                    │                 │
     │                     │                    │                    │  SELECT unread  │
     │                     │                    │                    │◀────────────────│
     │                     │                    │                    │                 │
     │                     │                    │                    │  LLM call       │
     │                     │                    │                    │                 │
     │                     │  WS: agent_text    │                    │                 │
     │  Live streaming     │◀───────────────────│◀───────────────────────────────────│
     │◀────────────────────│                    │                    │                 │
     │                     │                    │                    │                 │
     │                     │  WS: agent_message │                    │                 │
     │  Agent reply        │◀───────────────────│◀───────────────────────────────────│
     │◀────────────────────│                    │                    │                 │
```

### Scenario: Self-healing (Reconciler fixes stuck agent)

```
Reconciler              PostgreSQL              WorkerManager
     │                       │                        │
     │  SELECT agents        │                        │
     │  WHERE status='active'│                        │
     │──────────────────────▶│                        │
     │  (Agent-X, active     │                        │
     │   for 15 min, no      │                        │
     │   running session)    │                        │
     │◀──────────────────────│                        │
     │                       │                        │
     │  UPDATE Agent-X       │                        │
     │  SET status='sleeping'│                        │
     │──────────────────────▶│                        │
     │                       │                        │
     │  ensure_workers()     │                        │
     │───────────────────────────────────────────────▶│
     │                       │              (spawn if missing)
```

---

## 7. Deployment View

```
┌──────────────────────────────────────────────────────────────────┐
│  Google Cloud Platform                                           │
│                                                                  │
│  ┌────────────────────┐    ┌────────────────────────────────┐   │
│  │  Cloud Run          │    │  Cloud SQL                     │   │
│  │                     │    │                                │   │
│  │  Backend container  │───▶│  PostgreSQL 15                 │   │
│  │  (python:3.11-slim) │    │  Unix socket connection        │   │
│  │                     │    │                                │   │
│  │  min-instances: 1   │    │  Single source of truth        │   │
│  │  cpu-boost: on      │    └────────────────────────────────┘   │
│  └─────────┬───────────┘                                         │
│            │                                                     │
│            │ HTTP REST                                           │
│            ▼                                                     │
│  ┌────────────────────┐                                          │
│  │  Self-hosted VM     │                                          │
│  │  Sandbox Pool Mgr   │                                          │
│  │  (port 9090)        │                                          │
│  │                     │                                          │
│  │  Docker containers  │                                          │
│  │  per agent sandbox  │                                          │
│  └────────────────────┘                                          │
│                                                                  │
│  ┌────────────────────┐    ┌────────────────────────────────┐   │
│  │  Artifact Registry  │    │  Cloud Build                   │   │
│  │  (Docker images)    │    │  (CI/CD pipeline)              │   │
│  └────────────────────┘    └────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────┘

Frontend SPA: Static hosting (Firebase Hosting or equivalent)
```

| Instance | Container | Min | Max | Notes |
|----------|-----------|-----|-----|-------|
| Backend | `python:3.11-slim` | 1 | 1 | min=1 required for always-on workers. Single instance avoids WebSocket routing issues. |
| Sandbox Pool Mgr | `python:3.11-slim` | 1 | 1 | Manages Docker containers on the same VM. |
| Sandbox containers | `ubuntu:22.04` | 0 | N | Created/destroyed per agent session. |
| PostgreSQL | Cloud SQL | 1 | 1 | Managed. |

---

## 8. Crosscutting Concepts

### 8.1 Messaging as a Primitive

All communication flows through `channel_messages`. This includes user-to-agent, agent-to-agent, agent-to-user, broadcasts, and lifecycle notifications. The user is represented by a reserved UUID (`00000000-...`). There is no separate chat system, ticket system, or notification system.

### 8.2 Agent Memory (Two Layers)

| Layer | Storage | Scope | Managed by |
|-------|---------|-------|-----------|
| **L1: Working Memory** | `agents.memory` (JSON) | Cross-session, 2500 token cap | Agent via `update_memory` tool |
| **L2: Full History** | `agent_messages` table | All sessions, unlimited | System (auto-recorded) |

Working memory is injected into every system prompt. Full history is queryable via `read_history` when the agent needs older context.

### 8.3 Context Pressure Management

When the conversation context approaches 70% of the LLM's context window, the loop injects a summarization prompt. The agent condenses important context into `update_memory`, then older messages are truncated from the active context (but preserved in `agent_messages`).

### 8.4 Self-Healing

Four categories of drift are detected and corrected every 30 seconds:

1. **Orphan agents** — agent in DB, no worker → spawn worker
2. **Stuck active** — agent active > 10 min, no running session → reset to sleeping
3. **Orphaned sessions** — session running, agent sleeping → force-end session
4. **Stuck messages** — message sent > 60s ago, not received → re-notify

### 8.5 Observability

- **Backend logs** → Cloud Logging (stdout) + WebSocket broadcast
- **Agent stream** → WebSocket events (text, tool calls, tool results)
- **Session audit trail** → `agent_sessions` + `agent_messages` tables
- **Health endpoints** → `/api/v1/health` (liveness), `/api/v1/health/workers` (worker status)

---

## 9. Architecture Decisions

All significant decisions are recorded as Architecture Decision Records:

| ADR | Title | Status |
|-----|-------|--------|
| [001](adr/001-postgresql-single-source-of-truth.md) | PostgreSQL as single source of truth | Accepted |
| [002](adr/002-universal-agent-execution-loop.md) | Universal agent execution loop | Accepted |
| [003](adr/003-channel-messages-unified-communication.md) | Channel messages as unified communication | Accepted |
| [004](adr/004-in-process-async-workers.md) | In-process async workers | Accepted |
| [005](adr/005-provider-agnostic-llm-layer.md) | Provider-agnostic LLM layer | Accepted |
| [006](adr/006-platform-not-workflow.md) | Platform, not workflow | Accepted |
| [007](adr/007-self-healing-reconciler.md) | Self-healing Reconciler | Accepted |
| [008](adr/008-firebase-auth-separate-github-credentials.md) | Firebase auth with separate GitHub credentials | Accepted |
| [009](adr/009-ephemeral-vs-persistent-sandboxes.md) | Ephemeral vs. persistent sandboxes | Accepted |
| [010](adr/010-frontend-react-context-only.md) | Frontend: React context only | Accepted |

---

## 10. Risks & Technical Debt

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|-----------|
| **Single-instance limit** | High (current) | WebSocket events lost if multi-instance | Planned: Redis Pub/Sub for WebSocket fan-out |
| **Container restart loses file state** | High | Cloned repos lost, re-provisioned on restart | `PROVISION_REPOS_ON_STARTUP` re-clones. Persistent volume planned. |
| **LLM provider rate limits** | Medium | Agent sessions fail mid-execution | Retry logic in LLM layer. Token usage monitoring planned. |
| **Cloud SQL cost** | High (current) | Significant operational cost | Planned: self-hosted PostgreSQL |
| **No horizontal scaling** | Medium | Single container handles all agents | Acceptable for current scale. Worker sharding is a future option. |

### Technical Debt

| Item | Impact | Priority |
|------|--------|----------|
| LangGraph checkpointer still used for Manager-CTO graph (not inner loop) | Inconsistency with "DB is source of truth" principle | Low — works, but could be removed |
| `Project = Repository` alias in models | Naming confusion | Low |
| Hardcoded reconciler/worker thresholds | Not configurable via env vars | Low |
| No API rate limiting or token usage monitoring | Cost risk with scale | High |
| Agent roles stored as `"assistant"` in some contexts | Should reflect actual role | Medium |

---

## 11. Glossary

| Term | Definition |
|------|-----------|
| **Agent** | An AI entity (Manager, CTO, or Engineer) that runs in the AICT platform. Each agent has its own worker, memory, and sandbox. |
| **Inner Loop** | The universal LLM + tool execution loop that all agents run. Defined in `backend/workers/loop.py`. |
| **Outer Loop** | The per-agent event loop that blocks on the notification queue, runs the inner loop on wake-up, and resets to sleeping. |
| **Session** | One run of the inner loop from agent wake-up to END. Tracked in `agent_sessions`. |
| **Channel Message** | A row in `channel_messages`. The universal communication primitive for all agent-to-agent and user-to-agent messaging. |
| **Working Memory** | Agent's self-curated JSON memory block stored in `agents.memory`. Updated via `update_memory`. Injected into every system prompt. |
| **Reconciler** | Background task that detects and fixes system drift every 30 seconds. |
| **Sandbox** | An isolated Docker container where agents execute shell commands, git operations, and code. |
| **Pool Manager** | Service that manages the lifecycle of sandbox containers. |
| **Inspection and Interference** | The interaction model: users observe agent output in real-time and can send messages to any agent at any time. |
| **Platform (not Workflow)** | Design philosophy: AICT provides primitives (agents, messaging, sandboxes, tasks) without prescribing a fixed orchestration flow. |
