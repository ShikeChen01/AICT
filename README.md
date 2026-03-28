# AICT

**Multi-AI Agent Orchestration Platform for Software Engineering**

AICT orchestrates multiple AI agents — Manager, CTO, and Engineers — to collaboratively build software. Each agent runs in an independent async loop with its own LLM, tools, and persistent memory. Agents communicate through structured channels, manage tasks on a kanban board, and execute code in sandboxed desktop environments with full VNC access.

> Build tools for AI to use. Design UI for humans to see what AI is doing.

---

## Screenshots

| Dashboard | Agents & Prompt Builder |
|---|---|
| ![Dashboard](docs/screenshots/dashboard.png) | ![Agents](docs/screenshots/agents.png) |

| Workspace (VNC + Chat) | Desktops |
|---|---|
| ![Workspace](docs/screenshots/workspace.png) | ![Desktops](docs/screenshots/desktops.png) |

| Kanban Board | Settings |
|---|---|
| ![Kanban](docs/screenshots/kanban.png) | ![Settings](docs/screenshots/settings.png) |

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

## Features

### Agent Orchestration
- **Hierarchical agent fleet** — Manager coordinates CTOs and Engineers with role-specific system prompts, tools, and thinking stages
- **Prompt Builder** — Visual drag-and-drop editor for system prompt blocks with live token budget visualization (static vs dynamic pool allocation)
- **Runtime injections** — Dynamic context injected into agent prompts at call time (incoming messages, memory, session history)
- **Independent async loops** — Each agent runs its own event loop, no LangGraph chains. Agents wake on message, process, sleep
- **Multi-LLM support** — Per-agent model selection across Claude, GPT, Gemini, and Kimi. BYOK API keys per provider

### Workspace
- **Split-pane IDE layout** — VNC canvas (left) + conversation panel (right) + agent stream (bottom)
- **Real-time streaming** — WebSocket-powered live updates of agent thinking, tool calls, and responses
- **Agent switching** — Jump between any agent's conversation with full history
- **Image/file attachments** — Drag-and-drop multimodal input to agents

### Sandboxed Desktops
- **Headless containers** — Docker-based ephemeral sandboxes (5s boot, 256MB RAM) for agent code execution
- **Desktop VMs** — QEMU/KVM sub-VMs with full Ubuntu desktop, Chrome, and VNC (180s boot, 1.5GB RAM)
- **VNC in browser** — Three-tier proxy chain: Browser (noVNC) -> Cloud Run -> Pool Manager -> VM x11vnc
- **Pool manager** — Capacity budgeting (CPU/RAM/disk), health monitoring (30s checks), idle reaping, watchdog supervision
- **Agent assignment** — Assign desktops to agents for interactive GUI automation

### Task Management
- **Kanban board** — 6-column workflow: Backlog -> Specifying -> Assigned -> In Progress -> In Review -> Done
- **Swimlane view** — Group tasks by agent for workload visibility
- **Agent-driven tasks** — Agents create, update, and complete tasks autonomously during work sessions

### Billing & Tiers
- **Subscription tiers** — Free (15h), Individual $20/mo (200h), Team $50/mo (1000h) sandbox compute
- **Stripe integration** — Checkout, billing portal, webhook handlers for subscription lifecycle
- **Usage tracking** — Per-user monthly usage periods with headless/desktop hour accounting
- **Hard caps** — No overage billing. Usage is capped at tier limits with clear upgrade prompts

### Settings & Configuration
- **Project settings** — Git integration, agent limits, rate limits, cost budgets
- **Per-user API keys** — Encrypted BYOK key management for each LLM provider
- **Tier badge** — Always-visible membership tier indicator

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
# ── Core ──────────────────────────────────────────────
ENV=development
API_TOKEN=your-secure-api-token
SECRET_ENCRYPTION_KEY=your-fernet-key          # python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# ── Database ──────────────────────────────────────────
# Local PostgreSQL
DATABASE_URL=postgresql+asyncpg://aict:password@localhost:5432/aict

# ── Firebase Auth ─────────────────────────────────────
FIREBASE_PROJECT_ID=your-firebase-project-id
FIREBASE_CREDENTIALS_PATH=path/to/serviceAccountKey.json

# ── LLM API Keys (add whichever you use) ──────────────
CLAUDE_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
GEMINI_API_KEY=AIza...
MOONSHOT_API_KEY=sk-...

# ── LLM Model Defaults ───────────────────────────────
MANAGER_MODEL_DEFAULT=claude-sonnet-4-6
CTO_MODEL_DEFAULT=claude-opus-4-6
ENGINEER_MODEL_DEFAULT=claude-sonnet-4-6

# ── GitHub (optional, for repo cloning) ───────────────
GITHUB_TOKEN=ghp_...

# ── Stripe (optional, for billing) ────────────────────
STRIPE_SECRET_KEY=sk_test_...
STRIPE_INDIVIDUAL_PRICE_ID=price_...
STRIPE_TEAM_PRICE_ID=price_...
STRIPE_WEBHOOK_SECRET=whsec_...

# ── Sandbox VM (optional) ─────────────────────────────
# SANDBOX_VM_HOST=34.x.x.x
# SANDBOX_VM_INTERNAL_HOST=10.x.x.x
# SANDBOX_VM_POOL_PORT=9090
# SANDBOX_VM_MASTER_TOKEN=...
```

### 3. Set Up the Database

```bash
# Create the database
createdb aict

# Run migrations
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

The sandbox system runs on a separate GCE VM with Docker + QEMU/KVM. This enables agents to execute code in isolated containers and interactive desktop VMs.

### Provision the VM

```bash
# Create an N2 VM with nested virtualization (for KVM desktop VMs)
gcloud compute instances create sandbox-dev \
  --zone=us-central1-a \
  --machine-type=n2-standard-2 \
  --enable-nested-virtualization \
  --image-family=ubuntu-2204-lts \
  --image-project=ubuntu-os-cloud \
  --boot-disk-size=100GB

# Deploy sandbox code
bash sandbox/scripts/deploy_to_vm.sh
```

The deploy script:
1. Syncs `sandbox/` to the VM via `gcloud compute scp`
2. Installs Docker, Python, QEMU/KVM, libvirt
3. Builds the sandbox Docker image
4. Starts the pool manager as a systemd service on port 9090

### Build Desktop Base Image

```bash
# On the VM:
sudo bash sandbox/scripts/build_desktop_image.sh
```

This creates an Ubuntu desktop QCOW2 image with Xvfb, x11vnc, Chrome, and the sandbox server pre-installed.

### Connect Backend to Sandbox

Add to your `.env.development`:

```bash
SANDBOX_VM_HOST=<external-ip>
SANDBOX_VM_INTERNAL_HOST=<internal-ip>   # If using VPC connector
SANDBOX_VM_POOL_PORT=9090
SANDBOX_VM_MASTER_TOKEN=<from deploy output>
```

---

## Deployment (Cloud)

### Backend (Cloud Run)

```powershell
# Build and push image
./scripts/cloud/build.ps1

# Run migrations
./scripts/cloud/migrate.ps1

# Deploy
./scripts/cloud/deploy.ps1
```

Or via CI/CD: push to `main` triggers `.github/workflows/deploy.yml` which builds, migrates, and deploys automatically.

### Frontend (Firebase Hosting)

```bash
cd frontend
VITE_BACKEND_URL=https://your-cloud-run-url npm run build
firebase deploy --only hosting
```

### CI/CD Pipeline

The GitHub Actions workflow (`deploy.yml`) handles:
- **Path-filtered deploys** — only builds what changed (backend/frontend)
- **Backend**: Docker build -> Artifact Registry -> Alembic migrations -> Cloud Run deploy
- **Frontend**: Vite build -> Firebase Hosting deploy
- **Post-deploy**: Health checks and smoke tests

The test pipeline (`test.yml`) runs on PRs:
- Backend unit tests (SQLite, fast)
- Backend integration tests (PostgreSQL container)
- Frontend lint + Vitest
- E2E Playwright tests

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
│   ├── tools/           # Agent tool definitions and executors
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
