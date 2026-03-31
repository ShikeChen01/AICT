# AICT

**Multi-AI Agent Orchestration Platform for Software Engineering**

> **Archive Notice** — Claude Code costs $4,000/month in API usage on top of a $280 subscription. The economics of building on top of frontier LLM APIs are brutal: either you train and build your own model, or you die. This is a near-production-grade implementation layer — a serious attempt, not a toy — but turning it into a sustainable product at these API costs is unrealistic. I'm out. This is a public archive to showcase the features I built.

AICT orchestrates multiple AI agents — Manager, CTO, and Engineers — to collaboratively build software. Each agent runs in an independent async loop with its own LLM, tools, and persistent memory. Agents communicate through structured channels, manage tasks on a kanban board, and execute code in sandboxed desktop environments with full VNC access.

> Build tools for AI to use. Design UI for humans to see what AI is doing.

---

## Dashboard

The project command center shows real-time cost tracking, agent fleet status with live indicators, sandbox VNC previews, and a log of all LLM API calls with per-call cost breakdowns.

![Dashboard](docs/screenshots/DashBoard.png)

---

## Workspace

The workspace is the primary interface for interacting with agents. A split-pane layout combines a live VNC canvas of the agent's desktop (left) with a conversation panel (right) and a tool call stream (bottom).

**Agents autonomously execute tasks** — browsing the web, running commands, and reporting back through the chat. Users can intervene at any point with natural language instructions.

| Agent Working on Desktop | Agent Using Chrome |
|---|---|
| ![Workspace](docs/screenshots/workplace.png) | ![Chrome](docs/screenshots/ChromeOpen.png) |

---

## Sandboxed Desktops

Agents operate in isolated compute environments. **Desktop VMs** are persistent QEMU/KVM virtual machines with full Ubuntu desktops, Chrome, and VNC access. **Headless sandboxes** are ephemeral Docker containers for fast code execution.

The desktop page shows all active VMs with live VNC thumbnails. Click any desktop to enter a full-screen interactive session.

| Desktop Management | Interactive Desktop Session |
|---|---|
| ![Desktops](docs/screenshots/desktops.png) | ![Interactive Desktop](docs/screenshots/interactive-desktop.png) |

**22 agent tools** for GUI automation and shell execution:
- **Desktop tools** (10): screenshot, mouse move/click/scroll, keyboard, open URL, list/focus windows, clipboard get/set
- **Sandbox tools** (12): shell execute, session lifecycle, health check, screenshot, mouse/keyboard, screen recording

---

## Kanban Board

A 6-column kanban board tracks all project tasks: Backlog, Specifying, Assigned, In Progress, In Review, and Done. Agents autonomously create, assign, and advance tasks as they work. Tasks display priority, assigned agent, and creation date.

Switch to **Swimlane View** to see tasks grouped by agent for workload visibility.

| Status View | Swimlane View |
|---|---|
| ![Kanban](docs/screenshots/Kanban.png) | ![Swimlane](docs/screenshots/TaskView.png) |

---

## Agent Prompt Builder

A visual drag-and-drop editor for crafting agent system prompts. Each agent role (Manager, CTO, Engineer) has configurable prompt blocks — rules, history, incoming messages, tool results — with a live **token budget** donut chart showing static vs dynamic pool allocation.

The config panel controls model selection, provider, thinking mode, and temperature per agent.

![Prompt Builder](docs/screenshots/agents.png)

---

## Knowledge Base (RAG)

Upload PDFs, TXT, Markdown, or CSV files to the project knowledge base. Documents are chunked, embedded with vector search, and available to all agents via a retrieval tool. Agents can search the knowledge base to ground their work in project-specific context.

![Knowledge Base](docs/screenshots/RAG.png)

---

## Settings

Project-level configuration includes Git repository integration, agent fleet limits, rate limits, and cost budgets. Per-user encrypted API key management supports BYOK (Bring Your Own Key) for each LLM provider.

![Settings](docs/screenshots/settings.png)

---

## Architecture

```
                         Firebase Auth
                              |
                    +---------+---------+
                    |                   |
              React SPA            FastAPI Backend
           (Firebase Hosting)      (Cloud Run)
                    |                   |
                    +-------+-----------+
                            |
              +-------------+-------------+
              |             |             |
         PostgreSQL    Pool Manager    LLM Providers
         (GCE VM)     (GCE N2 VM)    (BYOK API Keys)
                            |
              +-------------+-------------+
              |                           |
        Docker Containers           QEMU/KVM VMs
        (Headless Sandboxes)        (Desktop VMs)
              |                           |
         Xvfb + Tools              Xvfb + x11vnc
                                   + Chrome + VNC
```

### Stack

| Layer | Technology |
|---|---|
| **Frontend** | React 19, TypeScript, Vite, Tailwind CSS |
| **Backend** | Python 3.12, FastAPI, SQLAlchemy 2.x (async), Alembic |
| **Database** | PostgreSQL 16 with pgvector |
| **Auth** | Firebase Authentication (Google OAuth) |
| **LLM** | Anthropic Claude, OpenAI GPT/o-series, Google Gemini, Moonshot Kimi |
| **Sandbox** | Docker containers (headless) + QEMU/KVM sub-VMs (desktop) |
| **VNC** | noVNC (browser) + x11vnc (server) + WebSocket proxy chain |
| **Payments** | Stripe (subscriptions, webhooks, billing portal) |
| **CI/CD** | GitHub Actions, Cloud Run, Firebase Hosting, Artifact Registry |

---

## Self-Hosting Guide

### Prerequisites

- Python 3.10+
- Node.js 18+
- PostgreSQL 16
- Firebase project (for authentication)
- At least one LLM API key (Anthropic, OpenAI, Google, or Moonshot)
- (Optional) GCE VM for sandbox compute

### 1. Clone & Install

```bash
git clone https://github.com/ShikeChen01/AICT.git
cd AICT

# Backend
pip install -r backend/requirements.txt

# Frontend
cd frontend && npm ci && cd ..
```

### 2. Configure Environment

Create `.env.development` in the project root:

```bash
# -- Core --
ENV=development
API_TOKEN=your-secure-api-token
SECRET_ENCRYPTION_KEY=your-fernet-key          # python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# -- Database --
DATABASE_URL=postgresql+asyncpg://aict:password@localhost:5432/aict

# -- Firebase Auth --
FIREBASE_PROJECT_ID=your-firebase-project-id
FIREBASE_CREDENTIALS_PATH=path/to/serviceAccountKey.json

# -- LLM API Keys (add whichever you use) --
CLAUDE_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
GEMINI_API_KEY=AIza...
MOONSHOT_API_KEY=sk-...

# -- LLM Model Defaults --
MANAGER_MODEL_DEFAULT=claude-sonnet-4-6
CTO_MODEL_DEFAULT=claude-opus-4-6
ENGINEER_MODEL_DEFAULT=claude-sonnet-4-6

# -- GitHub (optional, for repo cloning) --
GITHUB_TOKEN=ghp_...

# -- Stripe (optional, for billing) --
STRIPE_SECRET_KEY=sk_test_...
STRIPE_INDIVIDUAL_PRICE_ID=price_...
STRIPE_TEAM_PRICE_ID=price_...
STRIPE_WEBHOOK_SECRET=whsec_...

# -- Sandbox VM (optional) --
# SANDBOX_VM_HOST=34.x.x.x
# SANDBOX_VM_INTERNAL_HOST=10.x.x.x
# SANDBOX_VM_POOL_PORT=9090
# SANDBOX_VM_MASTER_TOKEN=...
```

### 3. Set Up the Database

```bash
createdb aict
PYTHONPATH=. alembic -c backend/alembic.ini upgrade head
```

### 4. Set Up Firebase

1. Go to [Firebase Console](https://console.firebase.google.com)
2. Create a project and enable **Authentication** with Google sign-in
3. Download the service account key JSON
4. Create a web app and note the config values
5. Set `FIREBASE_PROJECT_ID` and `FIREBASE_CREDENTIALS_PATH` in your env

For the frontend, create `frontend/.env.local`:

```bash
VITE_FIREBASE_API_KEY=...
VITE_FIREBASE_AUTH_DOMAIN=...
VITE_FIREBASE_PROJECT_ID=...
VITE_BACKEND_URL=http://localhost:8000
```

### 5. Run

```bash
# Terminal 1: Backend
PYTHONPATH=. ENV=development uvicorn backend.main:app --reload --port 8000

# Terminal 2: Frontend
cd frontend && npm run dev
```

Open `http://localhost:3000`. Sign in with Google. Create a project and start orchestrating.

---

## Sandbox Setup (Optional)

The sandbox system runs on a separate GCE VM with Docker + QEMU/KVM.

```bash
# Create an N2 VM with nested virtualization
gcloud compute instances create sandbox-dev \
  --zone=us-central1-a \
  --machine-type=n2-standard-2 \
  --enable-nested-virtualization \
  --image-family=ubuntu-2204-lts \
  --image-project=ubuntu-os-cloud \
  --boot-disk-size=100GB

# Deploy sandbox code
bash sandbox/scripts/deploy_to_vm.sh

# Build desktop base image (on the VM)
sudo bash sandbox/scripts/build_desktop_image.sh
```

Add to `.env.development`:

```bash
SANDBOX_VM_HOST=<external-ip>
SANDBOX_VM_INTERNAL_HOST=<internal-ip>
SANDBOX_VM_POOL_PORT=9090
SANDBOX_VM_MASTER_TOKEN=<from deploy output>
```

---

## Deployment (Cloud)

Push to `main` triggers CI/CD (`.github/workflows/deploy.yml`):

- **Backend**: Docker build -> Artifact Registry -> Alembic migrations -> Cloud Run deploy
- **Frontend**: Vite build -> Firebase Hosting deploy
- **Post-deploy**: Health checks and API smoke tests

---

## Project Structure

```
AICT/
├── backend/
│   ├── agents/          # Agent loop, prompt builder, thinking stages
│   ├── api/v1/          # REST endpoints (agents, tasks, sandboxes, billing)
│   ├── db/              # SQLAlchemy models, repositories, migrations
│   ├── llm/             # Multi-provider LLM abstraction (Claude, GPT, Gemini, Kimi)
│   ├── services/        # Business logic (sandbox, billing, tier, stripe)
│   ├── tools/           # Agent tool definitions and executors (22 sandbox/desktop tools)
│   ├── websocket/       # Real-time streaming, VNC proxy
│   └── workers/         # Worker manager, reconciler, message router
├── frontend/
│   ├── src/pages/       # Dashboard, Agents, Workspace, Desktops, Kanban, Settings
│   ├── src/components/  # Prompt builder, VNC viewer, Kanban board, chat
│   └── src/api/         # Typed API client
├── sandbox/
│   ├── pool_manager/    # FastAPI pool manager (capacity, health, VNC proxy)
│   ├── server/          # In-container sandbox server (shell, VNC, display)
│   ├── scripts/         # VM provisioning, deployment, smoke tests
│   └── Dockerfile       # Sandbox container image
├── docs/                # Architecture docs, design specs
└── .github/workflows/   # CI/CD pipelines
```

---

## Design Philosophy

In the near future, everyone will be using AI to complete their tasks. AI, at its core, is an **intellectual computing unit**. Just like our brains, how we organize these intellectual computing units to build products will be the theme for the next 10 years.

This project addresses one piece of that puzzle: **multi-AI orchestration of programming**.

### Principles

1. **Build tools for AI, design UI for humans** — Agents get powerful tools. Humans get visibility.
2. **Independent agents, not chains** — Each agent runs its own async loop. No rigid LangGraph pipelines.
3. **Persistent desktops, ephemeral sandboxes** — Users control desktops (interactive, VNC). Agents own sandboxes (headless, temporary).
4. **BYOK everything** — Users bring their own LLM API keys. Platform charges for compute, not intelligence.

---

## License

This project is for portfolio/showcase purposes.

## Author

Built by [Shike Chen](https://github.com/ShikeChen01).
