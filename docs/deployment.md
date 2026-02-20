# Deployment

## Overview

The AICT backend is deployed as a Docker container on **Google Cloud Run** backed by **Cloud SQL (PostgreSQL)**. The frontend is a static React SPA served separately (e.g., Firebase Hosting or any static host).

---

## Infrastructure

| Component | Service | Notes |
|-----------|---------|-------|
| **Backend** | Google Cloud Run | Single container, managed auto-scaling |
| **Database** | Google Cloud SQL (PostgreSQL 15) | Connected via Unix socket (Cloud SQL proxy) |
| **Container Registry** | Google Artifact Registry | Image tagged as `backend:latest` |
| **Build** | Google Cloud Build | Builds and pushes the Docker image |
| **Sandbox VMs** | Self-hosted pool manager | Separate VM, accessed via HTTP (port 9090) |
| **Auth** | Firebase Authentication | Firebase Admin SDK verifies ID tokens |
| **LLM APIs** | Anthropic / Google / OpenAI | External, configured via API keys |

---

## Docker Image

The `Dockerfile` at the project root builds the backend image:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \      # For health checks
    git \       # For git_service (clone, commit, push)
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt backend/
COPY backend/ backend/

RUN pip install --no-cache-dir -r backend/requirements.txt

ENV PYTHONUNBUFFERED=1
EXPOSE 8080
CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
```

Key design notes:
- `git` is included at the system level because `GitService` calls git commands in the local spec/code repo paths (not in sandboxes)
- `PORT` env var is injected by Cloud Run; defaults to `8080`
- `PYTHONUNBUFFERED=1` ensures log lines are not buffered (important for Cloud Logging)

---

## Build & Deploy Scripts

Scripts live in `scripts/cloud/`:

| Script | Description |
|--------|-------------|
| `build.ps1` | Build Docker image with Cloud Build, push to Artifact Registry |
| `deploy.ps1` | Deploy the pushed image to Cloud Run with environment variables |
| `migrate.ps1` | Run Alembic migrations against the production database |

All scripts load configuration from `.env.development` in the project root.

### Build (`scripts/cloud/build.ps1`)

```powershell
# Uses Google Cloud Build (not local Docker) to build and push
gcloud builds submit --project $ProjectId --tag $ImageTag --timeout=1200 .
```

The build uses Cloud Build so it runs in GCP, avoiding local Docker setup requirements. The timeout is 1200 seconds (20 minutes) to accommodate large dependency installs.

### Deploy (`scripts/cloud/deploy.ps1`)

```powershell
gcloud run deploy aict-backend-dev \
    --project $ProjectId \
    --image $ImageTag \
    --region $Region \
    --platform managed \
    --allow-unauthenticated \
    --add-cloudsql-instances $ConnName \
    --env-vars-file tmp_env_vars.yaml \
    --min-instances 1 \
    --cpu-boost
```

Key Cloud Run flags:
- `--allow-unauthenticated` — Cloud Run IAM bypass; the backend handles its own Firebase auth
- `--add-cloudsql-instances` — Mounts Cloud SQL via Unix socket (no public IP, no connection pooler)
- `--min-instances 1` — Keeps one container warm to avoid cold-start delays (agents must be running)
- `--cpu-boost` — CPU boost at startup helps the heavy asyncio startup (WorkerManager, agent spawning) complete faster

The deploy script writes environment variables to a temporary `tmp_env_vars.yaml` file and deletes it in a `finally` block. This avoids passing secrets on the command line.

---

## Environment Variables

All configuration is read from environment variables via Pydantic `Settings` in `backend/config.py`.

### Database

| Env Var | Description | Example |
|---------|-------------|---------|
| `DATABASE_URL` | Full SQLAlchemy async URL | `postgresql+asyncpg://user:pass@/dbname?host=/cloudsql/project:region:instance` |
| `SQL_CONNECTION_NAME` | Cloud SQL connection name | `project:us-east1:instance` |

In production, the database URL uses the Unix socket path `/cloudsql/{connection_name}` instead of a TCP host. The deploy script constructs this URL automatically from `SQL_CONNECTION_NAME`, `SQL_DB_NAME`, and the password extracted from the source `DATABASE_URL`.

### Authentication

| Env Var | Description |
|---------|-------------|
| `FIREBASE_CREDENTIALS_PATH` | Path to Firebase service account JSON inside the container |
| `FIREBASE_PROJECT_ID` | Firebase project ID |
| `API_TOKEN` | Bearer token for the internal agent API (`/internal/agent/*`) |

The Firebase credentials JSON (`aict-XXXXX-YYYY.json`) must be available inside the container at the configured path. In the Dockerfile it is copied with the rest of the backend.

### LLM Providers

| Env Var | Description |
|---------|-------------|
| `CLAUDE_API_KEY` | Anthropic API key |
| `GEMINI_API_KEY` | Google Gemini API key |
| `OPENAI_API_KEY` | OpenAI API key (optional) |
| `MANAGER_MODEL_DEFAULT` | Default model for Manager agents |
| `CTO_MODEL_DEFAULT` | Default model for CTO agents |
| `ENGINEER_JUNIOR_MODEL` | Default model for junior engineers |
| `ENGINEER_INTERMEDIATE_MODEL` | Default model for intermediate engineers |
| `ENGINEER_SENIOR_MODEL` | Default model for senior engineers |
| `CLAUDE_MODEL` | Legacy single-model override (deprecated) |
| `GEMINI_MODEL` | Legacy single-model override (deprecated) |
| `LLM_REQUEST_TIMEOUT_SECONDS` | Per-LLM-call timeout (default: 60) |
| `LLM_MAX_TOKENS` | Max tokens per response (default: 1024) |
| `LLM_TEMPERATURE` | Sampling temperature (default: 0.2) |

### Sandbox

| Env Var | Description |
|---------|-------------|
| `SANDBOX_VM_HOST` | Hostname/IP of the sandbox VM pool manager |
| `SANDBOX_VM_POOL_PORT` | Port of the pool manager REST API (default: 9090) |
| `SANDBOX_VM_MASTER_TOKEN` | Bearer token for pool manager authentication |

If `SANDBOX_VM_HOST` is not set, the `SandboxService` returns an "offline" placeholder. Agents can still function without sandboxes (messaging, task management, memory), but `execute_command` and git operations will fail gracefully.

### Git & Repo

| Env Var | Description |
|---------|-------------|
| `GITHUB_TOKEN` | Global GitHub token (fallback when user has no personal token) |
| `SPEC_REPO_PATH` | Filesystem path where spec repos are stored (e.g., `/data/specs`) |
| `CODE_REPO_PATH` | Filesystem path where code repos are cloned (e.g., `/data/repos`) |

### Startup Behavior

| Env Var | Default | Description |
|---------|---------|-------------|
| `AUTO_RUN_MIGRATIONS_ON_STARTUP` | `true` | Run Alembic migrations at startup |
| `PROVISION_REPOS_ON_STARTUP` | `false` | Clone/provision repos at startup |
| `CLONE_CODE_REPO_ON_STARTUP` | `false` | Clone code repos at startup |
| `STARTUP_STEP_TIMEOUT_SECONDS` | `30` | Timeout for soft-fail startup steps |

### Server

| Env Var | Default | Description |
|---------|---------|-------------|
| `HOST` | `0.0.0.0` | Server bind host |
| `PORT` | `8080` | Server port (injected by Cloud Run) |
| `ENV` | `production` | Environment name (`development`, `production`) |

---

## Local Development

For local development, create `.env.development` in the project root:

```env
# Database (local PostgreSQL or Cloud SQL proxy)
DATABASE_URL=postgresql+asyncpg://aict:password@localhost:5432/aict

# Auth
FIREBASE_CREDENTIALS_PATH=./aict-xxxxx.json
FIREBASE_PROJECT_ID=your-firebase-project
API_TOKEN=dev-api-token-change-me

# LLM (at least one required)
CLAUDE_API_KEY=sk-ant-...
GEMINI_API_KEY=AIza...
MANAGER_MODEL_DEFAULT=claude-opus-4-5
CTO_MODEL_DEFAULT=claude-opus-4-5
ENGINEER_JUNIOR_MODEL=claude-haiku-3-5
ENGINEER_INTERMEDIATE_MODEL=claude-sonnet-4-5
ENGINEER_SENIOR_MODEL=claude-opus-4-5

# Repo paths (must be writable)
SPEC_REPO_PATH=./data/specs
CODE_REPO_PATH=./data/repos

# Sandbox (optional for local dev without VMs)
# SANDBOX_VM_HOST=192.168.1.100
# SANDBOX_VM_POOL_PORT=9090
# SANDBOX_VM_MASTER_TOKEN=dev-vm-token

# Startup
AUTO_RUN_MIGRATIONS_ON_STARTUP=true
PROVISION_REPOS_ON_STARTUP=false
```

**Start the backend:**
```bash
cd AICT
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8080
```

**Start the frontend:**
```bash
cd frontend
npm run dev
```

---

## Database Migrations

Migrations run automatically at startup when `AUTO_RUN_MIGRATIONS_ON_STARTUP=true`. To run them manually:

```powershell
# Using the cloud migration script (against production DB)
.\scripts\cloud\migrate.ps1

# Locally (from project root)
alembic -c backend/migrations/env.py upgrade head
```

Migration files are in `backend/migrations/versions/`. Each migration is a numbered Python file:

| Migration | Description |
|-----------|-------------|
| `001_init_mvp0_schema.py` | Initial schema |
| `002_add_project_git_token.py` | GitHub token on projects |
| `003_add_engineer_jobs.py` | Engineer job tracking (since replaced) |
| `004_add_users_and_repositories.py` | User + repository tables |
| `005_add_abort_and_user_ticket_replies.py` | Ticket/abort fields (since deprecated) |
| `006_data_and_messaging_foundation.py` | channel_messages, agent_sessions, agent_messages, project_settings |
| `007_deprecate_om_use_cto.py` | Rename OM → CTO role |
| `008_add_agent_tier_column.py` | `agents.tier` column for engineer seniority |

---

## Cloud Run Considerations

### Startup time

Cloud Run has a startup timeout. The WorkerManager startup is the bottleneck:
1. Load all agents from DB (fast)
2. Spawn all AgentWorker tasks (fast)
3. Wait for each worker to register its queue (up to 5s per worker)
4. Replay undelivered messages

With many agents, this can take 20–30 seconds. The `--cpu-boost` flag helps by giving the instance extra CPU during startup.

### Stateful background tasks

Cloud Run containers can be restarted at any time. The worker system is designed for this:
- All state is in PostgreSQL (no in-memory state to lose)
- On restart, WorkerManager reloads all agents and replays undelivered messages
- The Reconciler catches any inconsistencies left by the previous instance

### Min instances = 1

`--min-instances 1` is required for correct operation. If the instance scales to zero:
- All AgentWorker tasks stop
- Any in-flight agent sessions are interrupted
- Messages sent while the instance is down will be replayed on next startup (via reconciler / replay)

This means there is a gap period during cold starts where user messages are queued but not processed.

### WebSocket connections

WebSocket connections are per-instance. If Cloud Run scales to multiple instances, each client connects to one instance, and WebSocket events from agents running on other instances will not reach that client. For single-instance deployments (min=max=1), this is not an issue.

For multi-instance scaling, a WebSocket message broker (e.g., Redis Pub/Sub) would be needed. This is not currently implemented.

### File system

The container's file system is ephemeral. Spec repo files and code repo clones (`SPEC_REPO_PATH`, `CODE_REPO_PATH`) written to the local filesystem are lost on container restart. For production, these should be on a persistent volume or mounted storage. Currently, `PROVISION_REPOS_ON_STARTUP=true` re-clones repos at startup.

---

## Monitoring & Logs

Cloud Run automatically captures stdout/stderr logs and sends them to **Cloud Logging**. The backend uses `PYTHONUNBUFFERED=1` to ensure logs are not buffered.

Key log filters in Cloud Logging:
- `"WorkerManager started"` — confirms startup health
- `"Reconciler:"` — self-healing actions
- `"AgentWorker task for agent"` — worker crash/respawn events
- `"LLM call failed"` — LLM errors per agent
- `"Stuck active"` — agents stuck in active state

The `/api/v1/health/workers` endpoint returns the WorkerManager status: `{started, shutting_down, worker_count, agent_ids}`. This can be polled externally for monitoring.
