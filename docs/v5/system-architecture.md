# AICT System Architecture

> Last updated: 2026-03-26

---

## High-Level Overview

```mermaid
graph TB
    subgraph Users["Users"]
        Browser["Browser SPA"]
    end

    subgraph Frontend["Frontend - Firebase Hosting"]
        React["React 19 + Vite"]
    end

    subgraph Backend["Backend - Cloud Run"]
        API["FastAPI"]
        WS["WebSocket Server"]
        Workers["Worker Manager"]
        Agents["Agent Workers"]
    end

    subgraph Data["Data Layer"]
        PG["PostgreSQL + pgvector"]
        GCS["Google Cloud Storage"]
    end

    subgraph External["External Services"]
        Firebase["Firebase Auth"]
        Stripe["Stripe Billing"]
        LLMs["LLM APIs"]
        Voyage["Voyage AI Embeddings"]
    end

    subgraph Sandbox["Sandbox Infrastructure"]
        Orch["K8s Orchestrator"]
        VM["Legacy VM Pool"]
    end

    Browser --> React
    React -- "REST /api/v1" --> API
    React -- "ws://" --> WS
    React -- "Auth tokens" --> Firebase

    API --> PG
    API --> GCS
    API --> Workers
    Workers --> Agents
    Agents --> LLMs
    Agents --> Sandbox
    Agents --> PG
    WS --> React

    API --> Stripe
    API --> Firebase
    Agents --> Voyage
    Orch --> PG
```

---

## Backend Architecture

```mermaid
graph LR
    subgraph Entry["Entry Point - main.py"]
        Lifespan["Lifespan Manager"]
        CORS["CORS Middleware"]
        Readiness["Readiness Gate"]
    end

    subgraph Routing["Request Routing"]
        Public["Public API<br/>api/v1"]
        Internal["Agent Tool Calls<br/>internal/agent"]
        WSE["WebSocket<br/>ws"]
        Health["Health Check"]
    end

    subgraph Services["Service Layer"]
        AgentSvc["AgentService"]
        MsgSvc["MessageService"]
        TaskSvc["TaskService"]
        SandboxSvc["SandboxService"]
        LLMSvc["LLMService"]
        KnowledgeSvc["KnowledgeService"]
        PromptSvc["PromptService"]
        BillingSvc["StripeService"]
        OAuthSvc["OAuthService"]
    end

    subgraph DB["Database Layer"]
        Models["SQLAlchemy Models"]
        Repos["Repositories"]
        Migrations["Alembic Migrations"]
    end

    Lifespan --> Migrations
    Lifespan --> Readiness
    CORS --> Routing
    Readiness --> Routing

    Public --> Services
    Internal --> Services
    Services --> DB
```

---

## Agent Execution Loop

```mermaid
sequenceDiagram
    participant User
    participant API as REST API
    participant MQ as Message Queue
    participant WM as Worker Manager
    participant AW as Agent Worker
    participant Agent
    participant LLM as LLM Provider
    participant Tools as Tool Executors
    participant WS as WebSocket
    participant DB as PostgreSQL

    User->>API: POST /api/v1/messages
    API->>DB: Persist ChannelMessage
    API->>MQ: Enqueue message
    MQ->>AW: Wake agent

    loop Agent Run Loop
        AW->>Agent: run_loop()
        Agent->>DB: Fetch prompt blocks + context
        Agent->>LLM: Call with tools
        LLM-->>Agent: Response text or tool_use

        alt Tool Use
            Agent->>Tools: execute tool
            Tools->>DB: Read/write state
            Tools-->>Agent: Tool result
            Agent->>DB: Persist AgentMessage
            Agent->>WS: Broadcast stream event
            Agent->>LLM: Continue with tool result
        else Text Response
            Agent->>DB: Persist AgentMessage
            Agent->>WS: Broadcast stream event
        end
    end

    WS-->>User: Real-time updates
```

---

## LLM Provider Routing

```mermaid
graph TD
    Agent["Agent requests model"]
    Router["LLM Router"]

    subgraph Providers["LLM Providers"]
        Anthropic["Anthropic<br/>Claude"]
        OpenAI["OpenAI<br/>GPT / o-series"]
        Google["Google<br/>Gemini"]
        Moonshot["Moonshot<br/>Kimi"]
    end

    subgraph Resolution["Key Resolution"]
        Platform["Platform Keys<br/>config.settings"]
        UserKeys["Per-User Keys<br/>UserAPIKey table"]
    end

    Agent --> Router
    Router --> Resolution
    Resolution --> Providers

    Router -- "model name to provider" --> Providers
    Router -- "fallback if key missing" --> Providers
```

---

## Tool System

```mermaid
graph TD
    LLM["LLM Response<br/>tool_use block"]
    Dispatch["ToolExecutor.execute"]
    Context["RunContext<br/>db, user, project, sandbox"]

    subgraph Executors["Tool Executors"]
        TaskTools["tasks.py<br/>Create / Update / List"]
        MsgTools["messaging.py<br/>Send to channels"]
        SandboxTools["sandbox.py<br/>Shell / Screenshot / VNC"]
        MemTools["memory.py<br/>Get / Set memory"]
        DocTools["docs.py<br/>Document ops"]
        KnowledgeTools["knowledge.py<br/>RAG queries"]
        AgentTools["agents.py<br/>List / Status"]
        MCPTools["mcp_bridge.py<br/>MCP server tools"]
        MetaTools["meta.py<br/>Self-introspection"]
    end

    LLM --> Dispatch
    Context --> Dispatch
    Dispatch --> Executors
    Executors -- "results" --> LLM
```

---

## Database Schema

```mermaid
erDiagram
    User ||--o{ Project : owns
    User ||--o{ ProjectMembership : has
    User ||--o{ UserAPIKey : stores
    User ||--o{ UserOAuthConnection : has
    User ||--o| Subscription : subscribes

    Project ||--o{ Agent : contains
    Project ||--o{ Task : tracks
    Project ||--o{ ChannelMessage : has
    Project ||--o{ ProjectDocument : stores
    Project ||--o{ KnowledgeDocument : indexes
    Project ||--o{ ProjectSecret : encrypts
    Project ||--o| ProjectSettings : configures

    Agent ||--o{ AgentSession : runs
    Agent ||--o{ AgentMessage : produces
    Agent ||--o{ ToolConfig : enables
    Agent ||--o{ PromptBlockConfig : assembles
    Agent ||--o| Sandbox : uses

    Sandbox ||--o{ SandboxSnapshot : backs_up
    Sandbox ||--o{ SandboxFileSave : archives
    Sandbox ||--o{ SandboxUsageEvent : tracks
    Sandbox }o--|| SandboxConfig : created_from

    User ||--o{ SandboxConfig : defines
    User ||--o{ UsagePeriod : metered

    Project ||--o{ MCPServerConfig : registers
```

---

## Worker & Real-Time System

```mermaid
graph TB
    subgraph WorkerSystem["Worker System"]
        WM["WorkerManager<br/>singleton"]
        R["Reconciler<br/>background"]
        CL["ConfigListener<br/>PG LISTEN/NOTIFY"]

        WM --> AW1["AgentWorker<br/>Agent A"]
        WM --> AW2["AgentWorker<br/>Agent B"]
        WM --> AW3["AgentWorker<br/>Agent N"]
    end

    subgraph MessageRouting["Message Routing"]
        MR["MessageRouter"]
        Q1["asyncio.Queue A"]
        Q2["asyncio.Queue B"]
        Q3["asyncio.Queue N"]

        MR --> Q1
        MR --> Q2
        MR --> Q3
    end

    subgraph WebSocketSystem["WebSocket Pub/Sub"]
        WSM["WebSocket Manager"]
        Ch1["agent_stream"]
        Ch2["messages"]
        Ch3["kanban"]
        Ch4["agents"]
        Ch5["activity"]
        Ch6["backend_logs"]

        WSM --> Ch1
        WSM --> Ch2
        WSM --> Ch3
        WSM --> Ch4
        WSM --> Ch5
        WSM --> Ch6
    end

    Q1 --> AW1
    Q2 --> AW2
    Q3 --> AW3

    AW1 --> WSM
    AW2 --> WSM
    AW3 --> WSM

    CL -- "config change" --> WM
    R -- "reconcile state" --> WM
```

---

## Sandbox Architecture

```mermaid
graph TB
    Agent["Agent Worker"]
    SandboxSvc["SandboxService"]
    Client["SandboxClient"]

    subgraph Modern["Modern - GKE"]
        Orch["K8s Orchestrator"]
        Pod1["Pod (sandbox)"]
        Pod2["Pod (sandbox)"]
    end

    subgraph Legacy["Legacy - GCE VM"]
        Pool["Pool Manager :9090"]
        Docker1["Docker Container"]
        Docker2["Docker Container"]
    end

    Agent --> SandboxSvc
    SandboxSvc --> Client
    Client -- "config: SANDBOX_ORCHESTRATOR_HOST" --> Orch
    Client -- "config: SANDBOX_VM_*" --> Pool

    Orch --> Pod1
    Orch --> Pod2
    Pool --> Docker1
    Pool --> Docker2

    subgraph Operations["Operations"]
        Shell["Shell Exec"]
        Screenshot["Screenshot"]
        VNC["VNC Proxy"]
        Snapshot["Snapshot / Restore"]
        Files["File Upload / Download"]
    end

    Client --> Operations
```

---

## Frontend Architecture

```mermaid
graph TB
    subgraph Contexts["React Contexts"]
        Auth["AuthContext<br/>Firebase"]
        Proj["ProjectContext"]
        Theme["ThemeContext"]
        Stream["AgentStreamContext"]
    end

    subgraph Pages["Pages"]
        Login["LoginPage"]
        Projects["ProjectsPage"]
        Workspace["WorkspacePage"]
        AgentsPage["AgentsPage"]
        AgentBuild["AgentBuildPage"]
        SandboxPage["SandboxPage"]
        Monitor["MonitorPage"]
        Settings["SettingsPage"]
        Billing["BillingPage"]
    end

    subgraph Components["Key Components"]
        Chat["AgentChat<br/>messages + stream"]
        Kanban["Kanban Board<br/>drag-drop"]
        Activity["Activity Feed"]
        Desktop["VNC Desktop Viewer"]
        Logs["Backend Log Viewer"]
    end

    subgraph DataLayer["Data Layer"]
        APIClient["api/client.ts<br/>REST + fetch"]
        WSHook["useWebSocket()"]
        Hooks["Data Hooks<br/>useAgents, useTasks, etc"]
    end

    Auth --> Pages
    Proj --> Pages
    Pages --> Components
    Components --> DataLayer

    APIClient -- "REST" --> Backend["Backend API"]
    WSHook -- "WebSocket" --> Backend
```

---

## Auth & Access Control

```mermaid
sequenceDiagram
    participant Browser
    participant Firebase as Firebase Auth
    participant API as Backend API
    participant ACL as Access Control
    participant DB as PostgreSQL

    Browser->>Firebase: Sign in via email or OAuth
    Firebase-->>Browser: ID Token JWT

    Browser->>API: Request with Bearer JWT token
    API->>Firebase: Verify ID token
    Firebase-->>API: Decoded claims uid + email
    API->>DB: Find/create User by firebase_uid
    DB-->>API: User record

    API->>ACL: Check project membership
    ACL->>DB: Query ProjectMembership
    DB-->>ACL: Role owner/member/viewer
    ACL-->>API: Authorized / Denied
```

---

## CI/CD Pipeline

```mermaid
graph LR
    subgraph Trigger["Trigger"]
        Push["Push to main"]
    end

    subgraph Detect["Change Detection"]
        BE_Change["backend/** changed?"]
        FE_Change["frontend/** changed?"]
    end

    subgraph BackendPipeline["Backend Pipeline"]
        Build["Cloud Build<br/>Docker Image"]
        Migrate["Cloud Run Job<br/>DB Migrations"]
        Deploy["Cloud Run<br/>Deploy Service"]
    end

    subgraph FrontendPipeline["Frontend Pipeline"]
        FE_Build["npm run build<br/>VITE_BACKEND_URL baked in"]
        FE_Deploy["Firebase Hosting<br/>Deploy"]
    end

    subgraph Tests["Test Gate (PR / develop)"]
        Unit["Backend Unit<br/>(SQLite)"]
        Integration["Backend Integration<br/>(PostgreSQL)"]
        Lint["Frontend Lint<br/>+ Vitest"]
        E2E["Playwright E2E"]
    end

    Push --> Detect
    BE_Change -->|yes| Build --> Migrate --> Deploy
    FE_Change -->|yes| FE_Build --> FE_Deploy

    Push --> Tests
```

---

## Data Flow: End-to-End Message

```mermaid
graph LR
    U["User types message"] --> FE["Frontend<br/>POST /api/v1/messages"]
    FE --> API["API Layer<br/>Persist + Route"]
    API --> DB1["DB: ChannelMessage"]
    API --> MR["MessageRouter<br/>enqueue"]
    MR --> AW["AgentWorker<br/>wake"]
    AW --> PS["PromptService<br/>assemble"]
    PS --> LLM["LLM API<br/>call"]
    LLM --> TE["Tool Execution"]
    TE --> DB2["DB AgentMessage"]
    TE --> LLM
    LLM --> DB3["DB Final response"]
    DB3 --> WS["WebSocket<br/>broadcast"]
    WS --> FE2["Frontend<br/>live update"]
    FE2 --> U2["User sees response"]
```
