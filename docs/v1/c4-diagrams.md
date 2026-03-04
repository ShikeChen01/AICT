# C4 Architecture Diagrams

## L1 — System Context

Who uses AICT, and what external systems does it depend on?

```mermaid
C4Context
    title AICT — System Context (L1)

    Person(user, "User", "Software developer who orchestrates AI agents to build software")

    System(aict, "AICT Platform", "Multi-agent AI development platform. Users interact with a team of AI agents that autonomously plan, implement, and ship code.")

    System_Ext(firebase, "Firebase Auth", "Google OAuth identity provider. Issues and verifies ID tokens.")
    System_Ext(github, "GitHub", "Git hosting. Repos are created, cloned, and pushed here.")
    System_Ext(llm, "LLM Providers", "Anthropic Claude, Google Gemini, OpenAI GPT. Provide completions for agent reasoning.")
    System_Ext(gcp, "Google Cloud Platform", "Cloud Run (compute), Cloud SQL (database), Artifact Registry (images), Cloud Build (CI)")

    Rel(user, aict, "Sends messages, observes agent output, manages projects", "HTTPS / WSS")
    Rel(aict, firebase, "Verifies user identity tokens", "HTTPS")
    Rel(aict, github, "Creates repos, clones, pushes code, opens PRs", "HTTPS")
    Rel(aict, llm, "Sends prompts, receives completions", "HTTPS")
    Rel(aict, gcp, "Deployed on", "")
```

```
┌─────────────────────────────────────────────────────────────────┐
│                          User                                   │
│         (Developer orchestrating AI coding agents)              │
└──────────────────────────┬──────────────────────────────────────┘
                           │  HTTPS / WSS
                           ▼
┌──────────────────────────────────────────────────────────────────┐
│                                                                  │
│                    AICT Platform                                 │
│                                                                  │
│   Multi-agent AI development platform.                          │
│   Agents plan, implement, and ship code autonomously.           │
│   Users observe and interfere in real time.                     │
│                                                                  │
└───────┬──────────────┬──────────────┬──────────────┬────────────┘
        │              │              │              │
        ▼              ▼              ▼              ▼
  ┌──────────┐  ┌───────────┐  ┌──────────┐  ┌──────────────┐
  │ Firebase │  │  GitHub   │  │   LLM    │  │    GCP       │
  │   Auth   │  │           │  │ Providers│  │ (Cloud Run,  │
  │          │  │ Repo CRUD │  │ Claude   │  │  Cloud SQL,  │
  │ Verifies │  │ Clone     │  │ Gemini   │  │  Artifact    │
  │ ID tokens│  │ Push / PR │  │ GPT      │  │  Registry)   │
  └──────────┘  └───────────┘  └──────────┘  └──────────────┘
```

---

## L2 — Container Diagram

What are the deployable units and how do they communicate?

```mermaid
C4Container
    title AICT — Container Diagram (L2)

    Person(user, "User")

    Container_Boundary(aict, "AICT Platform") {
        Container(spa, "Frontend SPA", "React 19, TypeScript, Vite 7", "Single-page application. Project management, agent chat, kanban board, workflow graph, file browser.")
        Container(backend, "Backend API", "Python 3.11, FastAPI, uvicorn", "REST API, WebSocket endpoint, agent worker runtime, reconciler. Runs as a single Cloud Run container.")
        ContainerDb(db, "PostgreSQL", "Cloud SQL / PostgreSQL 15+", "Single source of truth for all state: users, projects, agents, tasks, messages, sessions.")
        Container(sandbox, "Sandbox Pool Manager", "Python, Docker", "Manages a pool of isolated sandbox containers for agent code execution. REST API on port 9090.")
        Container(sandbox_vm, "Sandbox Container", "Ubuntu 22.04, Docker", "Isolated execution environment per agent. Runs shell commands, git operations, code editing.")
    }

    System_Ext(firebase, "Firebase Auth")
    System_Ext(github, "GitHub")
    System_Ext(llm, "LLM Providers")

    Rel(user, spa, "Uses", "HTTPS")
    Rel(spa, backend, "REST API calls, WebSocket stream", "HTTPS / WSS")
    Rel(backend, db, "Reads/writes all state", "asyncpg / Unix socket")
    Rel(backend, sandbox, "Acquire/release sandboxes", "HTTP REST")
    Rel(sandbox, sandbox_vm, "Creates, manages, destroys containers", "Docker API")
    Rel(backend, sandbox_vm, "Execute commands in sandbox", "HTTP REST")
    Rel(backend, firebase, "Verify ID tokens", "HTTPS")
    Rel(backend, github, "Repo operations", "HTTPS")
    Rel(backend, llm, "LLM completions", "HTTPS")
```

```
┌───────────────────────────────────────────────────────────────────────────────────┐
│  AICT Platform                                                                    │
│                                                                                   │
│  ┌─────────────────────────┐         ┌────────────────────────────────────────┐  │
│  │   Frontend SPA          │  REST   │         Backend API                    │  │
│  │                         │  WSS    │                                        │  │
│  │  React 19 + TypeScript  │────────▶│  FastAPI + uvicorn (Cloud Run)        │  │
│  │  Vite 7                 │         │                                        │  │
│  │  Tailwind CSS 4         │         │  ┌──────────────┐ ┌────────────────┐  │  │
│  │                         │         │  │ REST API     │ │ WebSocket      │  │  │
│  │  Pages:                 │         │  │ /api/v1/*    │ │ /ws            │  │  │
│  │  - Workspace (chat)     │         │  └──────────────┘ └────────────────┘  │  │
│  │  - Kanban board         │         │  ┌──────────────┐ ┌────────────────┐  │  │
│  │  - Workflow graph       │         │  │ Internal API │ │ Worker Runtime │  │  │
│  │  - Artifacts            │         │  │ /internal/*  │ │ (AgentWorkers) │  │  │
│  │  - Settings             │         │  └──────────────┘ └────────────────┘  │  │
│  └─────────────────────────┘         │  ┌──────────────┐ ┌────────────────┐  │  │
│                                      │  │ Reconciler   │ │ MessageRouter  │  │  │
│                                      │  │ (30s cycle)  │ │ (in-process)   │  │  │
│                                      │  └──────────────┘ └────────────────┘  │  │
│                                      └───────┬───────────────┬───────────────┘  │
│                                              │               │                   │
│                                     asyncpg  │               │ HTTP REST         │
│                                              ▼               ▼                   │
│  ┌─────────────────────────┐         ┌────────────────────────────────────────┐  │
│  │   PostgreSQL            │         │   Sandbox Pool Manager                 │  │
│  │   (Cloud SQL)           │         │   (port 9090)                          │  │
│  │                         │         │                                        │  │
│  │   Tables:               │         │   Manages Docker containers:           │  │
│  │   - users               │         │   ┌────────┐ ┌────────┐ ┌────────┐   │  │
│  │   - repositories        │         │   │ Sandbox│ │ Sandbox│ │ Sandbox│   │  │
│  │   - agents              │         │   │   #1   │ │   #2   │ │  #N    │   │  │
│  │   - tasks               │         │   │Ubuntu  │ │Ubuntu  │ │Ubuntu  │   │  │
│  │   - channel_messages    │         │   └────────┘ └────────┘ └────────┘   │  │
│  │   - agent_sessions      │         └────────────────────────────────────────┘  │
│  │   - agent_messages      │                                                     │
│  └─────────────────────────┘                                                     │
└───────────────────────────────────────────────────────────────────────────────────┘
         ▲                         ▲                         ▲
         │                         │                         │
  Firebase Auth              GitHub API              LLM Providers
  (token verify)          (repo ops, PRs)        (Claude, Gemini, GPT)
```

---

## L3 — Component Diagram: Backend

What are the major components inside the Backend container?

```mermaid
C4Component
    title AICT Backend — Component Diagram (L3)

    Container_Boundary(backend, "Backend API (FastAPI)") {
        Component(public_api, "Public REST API", "/api/v1/*", "User-facing endpoints: repos, agents, tasks, messages, sessions, health. Firebase auth.")
        Component(internal_api, "Internal Agent API", "/internal/agent/*", "Agent tool call endpoints: lifecycle, messaging, memory, management, git, files, tasks. Bearer token auth.")
        Component(ws, "WebSocket Endpoint", "/ws", "Project-scoped real-time stream. Broadcasts agent output, messages, task updates, status changes.")

        Component(worker_mgr, "WorkerManager", "Singleton", "Spawns/tracks/respawns AgentWorker tasks. Handles agent lifecycle, interrupt, startup/shutdown.")
        Component(agent_worker, "AgentWorker × N", "asyncio.Task", "Per-agent outer loop. Blocks on queue, wakes on message, runs inner loop, resets to sleeping.")
        Component(inner_loop, "Inner Loop", "run_inner_loop()", "Universal LLM + tool execution loop. Shared by all agent roles. Prompt assembly → LLM call → tool dispatch → repeat.")
        Component(msg_router, "MessageRouter", "Singleton", "In-process dict[UUID, asyncio.Queue]. Routes wake-up notifications to agent workers.")
        Component(reconciler, "Reconciler", "Background task", "Runs every 30s. Fixes orphan agents, stuck sessions, stuck messages, orphaned workers.")

        Component(services, "Service Layer", "Python classes", "Business logic: MessageService, SessionService, AgentService, TaskService, SandboxService, GitService, LLMService.")
        Component(repos, "Repository Layer", "SQLAlchemy", "Data access: AgentRepository, TaskRepository, MessageRepository, SessionRepository, AgentMessageRepository.")
        Component(llm_layer, "LLM Layer", "Provider abstraction", "ProviderRouter → AnthropicProvider / GeminiProvider / OpenAIProvider. Model resolver maps role → model.")
        Component(prompts, "Prompt System", "PromptAssembly", "Assembles system prompt blocks + conversation history + tool schemas. Token budget management.")
        Component(tools, "Tool Registry", "loop_registry.py", "Role-based tool dispatch. Core, management, task, git, sandbox tool handlers.")
    }

    ContainerDb(db, "PostgreSQL")
    Container(sandbox, "Sandbox Pool Manager")
    System_Ext(llm, "LLM Providers")
    System_Ext(firebase, "Firebase Auth")

    Rel(public_api, services, "Calls")
    Rel(internal_api, services, "Calls")
    Rel(services, repos, "Reads/writes via")
    Rel(repos, db, "SQL queries")
    Rel(worker_mgr, agent_worker, "Spawns, tracks, respawns")
    Rel(agent_worker, inner_loop, "Runs per session")
    Rel(inner_loop, llm_layer, "LLM completions")
    Rel(inner_loop, tools, "Tool dispatch")
    Rel(inner_loop, prompts, "Prompt assembly")
    Rel(inner_loop, ws, "Emits stream events")
    Rel(msg_router, agent_worker, "Wake-up notifications")
    Rel(services, msg_router, "notify() on message send")
    Rel(reconciler, worker_mgr, "Spawns missing workers")
    Rel(reconciler, repos, "Queries for drift")
    Rel(llm_layer, llm, "HTTP calls")
    Rel(services, sandbox, "Sandbox acquire/release/exec")
    Rel(public_api, firebase, "Token verification")
```

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│  Backend API (FastAPI + uvicorn)                                                       │
│                                                                                        │
│  ┌─────────────────────────────────────────────────────────────────────────────────┐   │
│  │  HTTP / WebSocket Layer                                                         │   │
│  │                                                                                 │   │
│  │  ┌──────────────┐   ┌──────────────────┐   ┌───────────────────────────────┐   │   │
│  │  │ Public API   │   │ Internal API     │   │ WebSocket Endpoint            │   │   │
│  │  │ /api/v1/*    │   │ /internal/agent/*│   │ /ws?token=...&project_id=...  │   │   │
│  │  │              │   │                  │   │                               │   │   │
│  │  │ Firebase JWT │   │ Bearer token     │   │ Channels:                     │   │   │
│  │  │              │   │                  │   │ agent_stream, messages,       │   │   │
│  │  │ Endpoints:   │   │ Endpoints:       │   │ kanban, agents, activity,     │   │   │
│  │  │ repos, agents│   │ lifecycle,       │   │ backend_logs                  │   │   │
│  │  │ tasks, msgs  │   │ messaging,       │   │                               │   │   │
│  │  │ sessions,    │   │ memory, mgmt,    │   │                               │   │   │
│  │  │ health       │   │ git, files, tasks│   │                               │   │   │
│  │  └──────┬───────┘   └────────┬─────────┘   └──────────────▲────────────────┘   │   │
│  └─────────┼────────────────────┼────────────────────────────┼────────────────────┘   │
│            │                    │                             │                         │
│            ▼                    ▼                             │ emit events              │
│  ┌──────────────────────────────────────┐                    │                         │
│  │  Service Layer                       │                    │                         │
│  │  MessageService, SessionService,     │──notify()──┐      │                         │
│  │  AgentService, TaskService,          │            │      │                         │
│  │  SandboxService, GitService,         │            │      │                         │
│  │  LLMService                          │            │      │                         │
│  └──────────┬───────────────────────────┘            │      │                         │
│             │                                        ▼      │                         │
│             ▼                              ┌──────────────┐ │                         │
│  ┌────────────────────┐                    │ Message      │ │                         │
│  │  Repository Layer  │                    │ Router       │ │                         │
│  │  (SQLAlchemy ORM)  │                    │ dict[UUID,Q] │ │                         │
│  └────────┬───────────┘                    └──────┬───────┘ │                         │
│           │                                       │         │                         │
│           │ SQL                          wake-up   │         │                         │
│           ▼                                       ▼         │                         │
│  ┌─────────────┐   ┌──────────────────────────────────────────────────────────────┐   │
│  │ PostgreSQL  │   │  Worker Runtime                                              │   │
│  │             │   │                                                              │   │
│  │ users       │   │  ┌───────────────┐                                          │   │
│  │ repositories│   │  │ WorkerManager │──spawns──┐                               │   │
│  │ agents      │   │  │ (singleton)   │          │                               │   │
│  │ tasks       │   │  └───────┬───────┘          ▼                               │   │
│  │ channel_msgs│   │          │           ┌─────────────┐  ┌─────────────┐       │   │
│  │ sessions    │   │     respawns         │AgentWorker  │  │AgentWorker  │ ...   │   │
│  │ agent_msgs  │   │                      │ (Manager)   │  │ (Eng-1)     │       │   │
│  │             │   │                      └──────┬──────┘  └──────┬──────┘       │   │
│  └─────────────┘   │                             │                │               │   │
│                    │                             ▼                ▼               │   │
│                    │                      ┌───────────────────────────┐           │   │
│                    │                      │ run_inner_loop()          │──────────▶│   │
│                    │                      │                           │  WS emit  │   │
│                    │                      │ PromptAssembly → LLM →   │           │   │
│                    │                      │ Tool dispatch → repeat   │           │   │
│                    │                      └──────────┬───────────────┘           │   │
│                    │                                 │                            │   │
│                    │  ┌───────────────┐               │                            │   │
│                    │  │ Reconciler    │               ▼                            │   │
│                    │  │ (every 30s)   │        ┌─────────────┐  ┌──────────────┐  │   │
│                    │  │               │        │ LLM Layer   │  │ Tool         │  │   │
│                    │  │ Fix orphans,  │        │             │  │ Registry     │  │   │
│                    │  │ stuck agents, │        │ Router →    │  │              │  │   │
│                    │  │ stuck msgs    │        │ Anthropic / │  │ core, mgmt,  │  │   │
│                    │  └───────────────┘        │ Gemini /    │  │ task, git,   │  │   │
│                    │                           │ OpenAI      │  │ sandbox      │  │   │
│                    │                           └─────────────┘  └──────────────┘  │   │
│                    └──────────────────────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## L3 — Component Diagram: Frontend

What are the major components inside the Frontend SPA?

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│  Frontend SPA (React 19 + TypeScript + Vite 7)                                   │
│                                                                                  │
│  ┌────────────────────────────────────────────────────────────────────────────┐  │
│  │  Context Providers                                                         │  │
│  │                                                                            │  │
│  │  ┌──────────────┐  ┌─────────────────┐  ┌───────────────────────────┐     │  │
│  │  │ AuthProvider  │  │ ProjectProvider │  │ AgentStreamProvider       │     │  │
│  │  │              │  │                 │  │                           │     │  │
│  │  │ Firebase     │  │ Active project  │  │ WebSocket connection      │     │  │
│  │  │ token, user  │  │ Project list    │  │ Per-agent stream buffers  │     │  │
│  │  │ Login state  │  │ Selection       │  │ Inspected agent tracking  │     │  │
│  │  └──────────────┘  └─────────────────┘  └───────────────────────────┘     │  │
│  └────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                  │
│  ┌────────────────────────────────────────────────────────────────────────────┐  │
│  │  Pages                                                                     │  │
│  │                                                                            │  │
│  │  ┌────────────┐ ┌──────────────────────────────────────────────────┐       │  │
│  │  │ Login /    │ │ Workspace                                       │       │  │
│  │  │ Register   │ │ Three-column layout:                            │       │  │
│  │  └────────────┘ │ ┌──────────┬──────────────────┬──────────────┐ │       │  │
│  │  ┌────────────┐ │ │ Sidebar  │  Main Content     │ Agents Panel │ │       │  │
│  │  │ Projects   │ │ │          │  - AgentChat      │              │ │       │  │
│  │  │ (list,     │ │ │ Nav +    │  - KanbanBoard    │ Status +     │ │       │  │
│  │  │  create,   │ │ │ Repo     │  - WorkflowGraph  │ Inspector    │ │       │  │
│  │  │  import)   │ │ │ Select   │  - ArtifactBrowser│              │ │       │  │
│  │  └────────────┘ │ └──────────┴──────────────────┴──────────────┘ │       │  │
│  │  ┌────────────┐ └──────────────────────────────────────────────────┘       │  │
│  │  │ Settings   │                                                            │  │
│  │  │ (user +    │                                                            │  │
│  │  │  project)  │                                                            │  │
│  │  └────────────┘                                                            │  │
│  └────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                  │
│  ┌────────────────────────────────────────────────────────────────────────────┐  │
│  │  Hooks                                                                     │  │
│  │                                                                            │  │
│  │  useAgents    useMessages    useAgentStream    useSessions    useTasks     │  │
│  │  (poll+WS)    (REST+WS)     (WS buffer)       (REST)         (REST+WS)    │  │
│  └────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                  │
│  ┌────────────────────────────────────────────────────────────────────────────┐  │
│  │  API Client (api/client.ts)                                                │  │
│  │                                                                            │  │
│  │  ┌───────────────────────┐   ┌────────────────────────────────────┐        │  │
│  │  │ REST Client           │   │ WebSocket Client                   │        │  │
│  │  │ request<T>(method,    │   │ connect(), disconnect(),           │        │  │
│  │  │   path, body)         │   │ subscribe(handler),                │        │  │
│  │  │ Auth header injection │   │ Exponential backoff reconnect     │        │  │
│  │  └───────────────────────┘   └────────────────────────────────────┘        │  │
│  └────────────────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────────────┘
```
