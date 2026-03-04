# Database Schema

## Overview

PostgreSQL is the single source of truth for all AICT state. No LangGraph checkpointer, no in-memory state persistence. All agent state, memory, sessions, messages, and project data live here.

**ORM**: SQLAlchemy async (`sqlalchemy[asyncio]` + `asyncpg`)  
**Migrations**: Alembic (auto-run at startup via `run_startup_migrations()`)  
**Session management**: `AsyncSessionLocal` (worker loops) and `get_db` dependency (API routes)

---

## Tables

| Table | Purpose |
|-------|---------|
| `users` | Firebase-authenticated users with GitHub credentials |
| `repositories` | Projects — git repos with local paths |
| `repository_memberships` | User access to projects (roles: `owner`, `member`, `viewer`) |
| `project_settings` | Per-project configurables: max engineers, model/prompt overrides, token/cost/rate budgets |
| `agents` | Agent definitions (role, model, status, memory, sandbox) |
| `tasks` | Kanban board items with 2D priority |
| `channel_messages` | Inter-agent and user-to-agent communication channel; includes `from_user_id` for attribution |
| `agent_sessions` | Session tracking (one row per agent wake→END cycle) |
| `agent_messages` | Persistent LLM message log (every prompt, response, tool call) |
| `llm_usage_events` | One row per LLM API call: provider, model, token counts, estimated cost |
| `attachments` | Binary image blobs (bytea, ≤10 MB, image/* only) stored in Postgres |
| `message_attachments` | Junction table linking channel messages to attachments |
| `project_documents` | Manager-writable architecture documents (arc42, ADRs, C4, etc.) |

---

## users

Authenticated users. Firebase is the identity provider; AICT stores a local record keyed by `firebase_uid`.

```
users
  id              UUID        PK, default uuid4
  firebase_uid    String(128) UNIQUE NOT NULL    -- Firebase UID from JWT
  email           String(255) UNIQUE NOT NULL
  display_name    String(100) nullable
  github_token    String(512) nullable            -- Personal GitHub Access Token (for repo/git ops)
  created_at      DateTime(tz) NOT NULL, default utcnow
  updated_at      DateTime(tz) NOT NULL, default utcnow, onupdate utcnow
```

Relationships:
- `users.id` ← `repositories.owner_id` (SET NULL on delete)

Notes:
- `github_token` is per-user and separate from Firebase authentication. It is used by `GitService` for creating/cloning repositories and by sandbox git operations. The API returns only `github_token_set: bool`, never the token value.
- `firebase_uid` is extracted from the Firebase ID token on every request and used to look up or create the user record.

---

## repositories

Projects. Each project is a GitHub repository with two local path references: the spec path (for project documentation) and the code path (cloned working copy).

```
repositories
  id              UUID        PK, default uuid4
  owner_id        UUID        FK(users.id), ON DELETE SET NULL, nullable
  name            String(255) NOT NULL
  description     Text        nullable
  spec_repo_path  String(512) NOT NULL    -- Local filesystem path for spec/docs
  code_repo_url   String(512) NOT NULL    -- GitHub HTTPS clone URL
  code_repo_path  String(512) NOT NULL    -- Local filesystem path for cloned code
  created_at      DateTime(tz) NOT NULL, default utcnow
  updated_at      DateTime(tz) NOT NULL, default utcnow, onupdate utcnow
```

Relationships:
- `repositories.id` ← `agents.project_id` (CASCADE delete)
- `repositories.id` ← `tasks.project_id` (CASCADE delete)
- `repositories.id` ← `channel_messages.project_id` (CASCADE delete)
- `repositories.id` ← `agent_sessions.project_id` (CASCADE delete)
- `repositories.id` ← `agent_messages.project_id` (CASCADE delete)
- `repositories.id` ← `project_settings.project_id` (CASCADE delete, 1:1)

Notes:
- `Project` is kept as a backward-compat alias: `Project = Repository` in `models.py`.
- `owner_id` is `SET NULL` on user delete so projects survive user deletion.
- When a repository is deleted via `DELETE /api/v1/repositories/{id}`, agent workers are removed first (`WorkerManager.remove_worker()`), then `agents.current_task_id` is nulled to break cross-references before the cascade delete proceeds.

---

## project_settings

One row per project (enforced by UNIQUE on `project_id`). Holds per-project configurables.

```
project_settings
  id                       UUID     PK, default uuid4
  project_id               UUID     FK(repositories.id), ON DELETE CASCADE, UNIQUE NOT NULL
  max_engineers             Integer  NOT NULL, default 5
  persistent_sandbox_count  Integer  NOT NULL, default 1
  model_overrides           JSON     nullable    -- per-role model override map, e.g. {"manager": "claude-opus-4-6"}
  prompt_overrides          JSON     nullable    -- per-role extra system prompt text (max 2,000 chars per role)
  daily_token_budget        Integer  NOT NULL, default 0   -- 0 = unlimited. Hard stop.
  calls_per_hour_limit      Integer  NOT NULL, default 0   -- 0 = unlimited. Soft pause.
  tokens_per_hour_limit     Integer  NOT NULL, default 0   -- 0 = unlimited. Soft pause.
  daily_cost_budget_usd     Float    NOT NULL, default 0.0 -- 0.0 = unlimited. Hard stop.
  created_at               DateTime(tz) NOT NULL, default utcnow
  updated_at               DateTime(tz) NOT NULL, default utcnow, onupdate utcnow
```

Notes:
- `max_engineers`: the `spawn_engineer` tool checks this before creating a new engineer. Returns an error if at limit.
- `persistent_sandbox_count`: how many sandbox slots survive across agent sessions. Currently stored but sandbox persistence is managed by the `SandboxService` / `PoolManagerClient`.
- `model_overrides`: JSONB map of role → model string, e.g. `{"manager": "claude-opus-4-6"}`. Part of the three-tier model resolution (agent override > project override > global default).
- `prompt_overrides`: JSONB map of role → extra text appended to the system prompt. Capped at 2,000 characters per role at injection time.
- `daily_token_budget` / `daily_cost_budget_usd`: hard stops enforced at the top of each loop iteration. UTC day boundary.
- `calls_per_hour_limit` / `tokens_per_hour_limit`: soft pauses — the loop sleeps in 5-second cycles until the window clears or 10 minutes elapse.
- Row is created lazily via `ProjectSettingsRepository.get_or_create_defaults()` when first accessed.

---

## agents

Agent definitions. One Manager and one CTO per project (auto-created at project creation). Engineers are spawned on demand by the Manager.

```
agents
  id              UUID        PK, default uuid4
  project_id      UUID        FK(repositories.id), ON DELETE CASCADE NOT NULL
  role            String(50)  NOT NULL    -- 'manager' | 'cto' | 'engineer'
  display_name    String(100) NOT NULL    -- e.g. 'Manager', 'CTO', 'Engineer-1'
  tier            String(50)  nullable    -- Engineer seniority: 'junior' | 'intermediate' | 'senior'
  model           String(100) NOT NULL    -- LLM model string (e.g. 'claude-opus-4-5')
  status          String(20)  NOT NULL, default 'sleeping'   -- 'sleeping' | 'active' | 'busy'
  current_task_id UUID        FK(tasks.id, use_alter, name='fk_agent_current_task'), nullable
  sandbox_id      String(255) nullable    -- Pool-assigned sandbox ID
  sandbox_persist Boolean     NOT NULL, default false
  memory          JSON        nullable    -- Layer 1 self-define working memory block
  created_at      DateTime(tz) NOT NULL, default utcnow
  updated_at      DateTime(tz) NOT NULL, default utcnow, onupdate utcnow
```

Valid roles: `manager`, `cto`, `engineer`  
Valid statuses: `sleeping`, `active`, `busy`

Notes:
- `memory`: JSON field storing the agent's self-curated working memory. Updated via `update_memory` tool. Injected into the system prompt on every LLM call as the Memory Block. Hard cap: 2,500 tokens (~10,000 chars).
- `tier`: engineer seniority level. Used by `model_resolver.resolve_model()` to select the appropriate default model. Stored as a string; validated by `normalize_seniority()`.
- `status` lifecycle: `sleeping` → `active` (woken by message) → `sleeping` (after END). The `AgentWorker.run()` `finally` block guarantees `sleeping` is always restored after a session.
- `sandbox_id`: the VM pool sandbox currently assigned to this agent. `None` when the agent has no active sandbox. Set by `SandboxService.ensure_running_sandbox()`.
- `sandbox_persist`: whether the agent holds a persistent sandbox slot. Managed by `SandboxService`.
- `current_task_id`: uses `use_alter=True` in the FK definition to break the circular reference between `agents` and `tasks` (both reference each other). The FK is added as an ALTER TABLE after both tables are created.
- Auto-created agents: when a project is created, the repository creation endpoint creates a Manager (`role=manager`, `sandbox_persist=True`) and a CTO (`role=cto`, `sandbox_persist=True`).

---

## tasks

Kanban board items. Tasks flow through statuses from `backlog` to `done` (or `aborted`).

```
tasks
  id                UUID        PK, default uuid4
  project_id        UUID        FK(repositories.id), ON DELETE CASCADE NOT NULL
  title             String(255) NOT NULL
  description       Text        nullable
  status            String(50)  NOT NULL, default 'backlog'
  critical          Integer     NOT NULL, default 5    -- 0-10, 0=most critical
  urgent            Integer     NOT NULL, default 5    -- 0-10, 0=most urgent
  assigned_agent_id UUID        FK(agents.id, ON DELETE SET NULL), nullable
  module_path       String(512) nullable    -- e.g. 'src/auth/login.py'
  git_branch        String(255) nullable
  pr_url            String(512) nullable
  parent_task_id    UUID        FK(tasks.id, ON DELETE SET NULL), nullable    -- Subtask hierarchy
  created_by_id     UUID        FK(agents.id, ON DELETE SET NULL), nullable
  created_at        DateTime(tz) NOT NULL, default utcnow
  updated_at        DateTime(tz) NOT NULL, default utcnow, onupdate utcnow
```

Valid statuses: `backlog`, `specifying`, `assigned`, `in_progress`, `review`, `done`, `aborted`

Notes:
- **2D priority**: `critical` (importance) and `urgent` (time pressure). Both are 0–10 where 0 = highest priority. The Manager sorts tasks using both dimensions.
- `assigned_agent_id`: the engineer currently working on this task. `SET NULL` on agent delete.
- `created_by_id`: which agent created the task (typically the Manager). `SET NULL` on agent delete.
- `parent_task_id`: self-referential FK for subtask hierarchies. `SET NULL` on parent delete (subtasks become top-level).
- `module_path`: optional path hint indicating which module/file this task relates to. Used by the Manager when assigning tasks to engineers.
- `git_branch` and `pr_url`: set by engineers via the `create_branch` and `create_pull_request` tools.
- Abort handling: the `abort_task` tool sets `status='aborted'`, sends a channel message to the assigner, and ends the session. There are no abort-specific columns — the reason is conveyed via channel messages.

---

## channel_messages

Inter-agent and user-to-agent communication. All messages in the system flow through this table. The user is represented by the reserved `USER_AGENT_ID = UUID("00000000-0000-0000-0000-000000000000")`.

```
channel_messages
  id              UUID      PK, default uuid4
  project_id      UUID      FK(repositories.id), ON DELETE CASCADE NOT NULL
  from_agent_id   UUID      nullable    -- NULL = system. User = USER_AGENT_ID (not a FK)
  target_agent_id UUID      nullable    -- NULL = broadcast. User = USER_AGENT_ID (not a FK)
  from_user_id    UUID      FK(users.id), ON DELETE SET NULL, nullable  -- real user FK for attribution (set when sent from REST API)
  content         Text      NOT NULL
  message_type    String(20) NOT NULL, default 'normal'   -- 'normal' | 'system'
  status          String(20) NOT NULL, default 'sent'     -- 'sent' | 'received'
  broadcast       Boolean   NOT NULL, default false
  created_at      DateTime(tz) NOT NULL, default utcnow

  INDEX ix_channel_target_status (target_agent_id, status, created_at)
  INDEX ix_channel_project (project_id, created_at)
```

Notes:
- `from_agent_id` and `target_agent_id` are **not foreign keys** to `agents.id`. The user UUID (`00000000-0000-0000-0000-000000000000`) never exists in `agents`, so a FK would violate the constraint.
- `from_user_id` is a real FK to `users.id`. It is set when a message is sent from the public REST API (`POST /api/v1/messages/send`) and is `NULL` for agent-to-agent messages. This enables per-user attribution in the frontend without a schema join on `from_agent_id`.
- `status = 'sent'` → message is unread by the target. `'received'` → message was consumed by the target's inner loop.
- Delivery flow: after writing a message, `MessageService.send()` calls `MessageRouter.notify(target_agent_id)` to push a wake-up signal to the target's asyncio queue.
- Messages targeting `USER_AGENT_ID` are pushed via WebSocket `agent_message` event to the browser — they are never "received" by a worker queue.
- Broadcast messages (`broadcast=True`, `target_agent_id=None`) are passive — they do not wake any agent.
- The `ix_channel_target_status` index is the hot query path: `WHERE target_agent_id = ? AND status = 'sent' ORDER BY created_at` (get unread messages for this agent).
- Replaces the former `chat_messages`, `tickets`, and `ticket_messages` tables.

---

## agent_sessions

Tracks each agent work session. A session = one run of the inner loop from wake-up to END. Created when an agent wakes, updated when the session ends.

```
agent_sessions
  id                 UUID      PK, default uuid4
  agent_id           UUID      FK(agents.id), ON DELETE CASCADE NOT NULL
  project_id         UUID      FK(repositories.id), ON DELETE CASCADE NOT NULL
  task_id            UUID      FK(tasks.id, ON DELETE SET NULL), nullable
  trigger_message_id UUID      FK(channel_messages.id, ON DELETE SET NULL), nullable
  status             String(20) NOT NULL, default 'running'
  end_reason         String(50) nullable
  iteration_count    Integer   NOT NULL, default 0
  started_at         DateTime(tz) NOT NULL, default utcnow
  ended_at           DateTime(tz) nullable

  INDEX ix_agent_sessions_agent (agent_id, started_at)
  INDEX ix_agent_sessions_status (status)
```

Valid statuses: `running`, `completed`, `force_ended`, `error`  
Valid end_reasons: `normal_end`, `max_iterations`, `max_loopbacks`, `interrupted`, `aborted`, `error`, `reconciler_orphaned`

Notes:
- `task_id`: which task the agent was working on (nullable — Manager may process a user message with no specific task).
- `trigger_message_id`: the `channel_message` that woke the agent for this session (nullable — some sessions start from assignment context rather than a new message).
- `iteration_count`: incremented by `SessionService.increment_iteration()` after each LLM call. Used for diagnostics.
- `status = 'force_ended'`: used by the Reconciler when it detects an orphaned session (agent is sleeping but session is still "running").
- `end_reason = 'reconciler_orphaned'`: set by the Reconciler when force-ending a stuck session.
- Replaces the former `engineer_jobs` table. The concept is universal — works for all agent roles.

---

## agent_messages

Persistent log of every LLM message within every agent session. This is the agent's "Layer 2" memory — the complete history of every prompt, response, tool call, and tool result across all sessions.

```
agent_messages
  id              UUID      PK, default uuid4
  agent_id        UUID      FK(agents.id), ON DELETE CASCADE NOT NULL
  session_id      UUID      FK(agent_sessions.id, ON DELETE CASCADE), nullable
  project_id      UUID      FK(repositories.id), ON DELETE CASCADE NOT NULL
  role            String(20) NOT NULL    -- 'system' | 'user' | 'assistant' | 'tool'
  content         Text      NOT NULL
  tool_name       String(100) nullable   -- set when role='tool'
  tool_input      JSON      nullable     -- tool call arguments (or {'__tool_calls__': [...]})
  tool_output     Text      nullable     -- tool return value
  loop_iteration  Integer   NOT NULL     -- iteration number within the session
  created_at      DateTime(tz) NOT NULL, default utcnow

  INDEX ix_agent_messages_agent_time (agent_id, created_at)
  INDEX ix_agent_messages_session (session_id, loop_iteration)
```

Notes:
- Every message the inner loop processes is written here automatically. The loop always calls `agent_msg_repo.create_message()` for assistant responses, incoming messages, and tool results.
- `role` follows LLM convention: `user` (incoming messages, loopback prompts), `assistant` (LLM responses), `tool` (tool results).
- For `role='assistant'` with tool calls: `tool_input` stores `{'__tool_calls__': [...]}` — the list of tool call dicts from the LLM response.
- For `role='tool'`: `tool_name` and `tool_output` are set; `tool_input` stores `{'__tool_use_id__': '...', ...tool_args}`.
- `loop_iteration`: resets to 0 at the start of each session. Used by `PromptAssembly` to rebuild conversation order.
- History is loaded by `AgentMessageRepository.list_last_n_sessions()` — returns up to the last 5 sessions of messages, ordered oldest-first, for use in `PromptAssembly.load_history()`.
- The `read_history` agent tool queries this table directly for on-demand access to older context outside the current context window.
- Future: `embedding Vector(1536)` column for pgvector RAG can be added without schema changes to other tables.

---

## repository_memberships

Tracks which users have access to which repositories and at what role level.

```
repository_memberships
  id              UUID        PK, default uuid4
  repository_id   UUID        FK(repositories.id), ON DELETE CASCADE NOT NULL
  user_id         UUID        FK(users.id), ON DELETE CASCADE NOT NULL
  role            String(50)  NOT NULL, default 'member'   -- 'owner' | 'member' | 'viewer'
  created_at      DateTime(tz) NOT NULL, default utcnow

  UNIQUE INDEX ix_repo_memberships_repo_user (repository_id, user_id)
  INDEX ix_repo_memberships_user (user_id)
```

Notes:
- Every API endpoint that touches a project calls `require_project_access(db, project_id, user_id)` from `backend/core/project_access.py`. This checks for a matching membership row and falls back to the legacy `owner_id IS NULL` pattern for backwards compatibility.
- `owner` role grants full control including settings changes. `member` grants read/write. `viewer` is read-only.
- On `POST /api/v1/repositories` and import, `add_owner_membership()` auto-creates an `owner` row for the creating user.

---

## llm_usage_events

One row per LLM API call. Used for cost attribution, daily budget enforcement, and the usage dashboard.

```
llm_usage_events
  id              UUID        PK, default uuid4
  project_id      UUID        FK(repositories.id), ON DELETE CASCADE NOT NULL
  agent_id        UUID        FK(agents.id), ON DELETE SET NULL, nullable
  session_id      UUID        FK(agent_sessions.id), ON DELETE SET NULL, nullable
  user_id         UUID        FK(users.id), ON DELETE SET NULL, nullable
  provider        String(50)  NOT NULL    -- 'anthropic' | 'google' | 'openai'
  model           String(100) NOT NULL    -- exact model name string
  input_tokens    Integer     NOT NULL, default 0
  output_tokens   Integer     NOT NULL, default 0
  request_id      String(255) nullable    -- provider-side request ID for debugging

  created_at      DateTime(tz) NOT NULL, default utcnow

  INDEX ix_llm_usage_project_time (project_id, created_at)
  INDEX ix_llm_usage_agent (agent_id)
  INDEX ix_llm_usage_session (session_id)
```

Notes:
- Written after every LLM call in `run_inner_loop()` via `LLMUsageRepository.record()`. The write is soft-fail — a write error does not abort the agent loop.
- `GET /api/v1/repositories/{id}/usage` returns today's rollup (total calls, tokens, estimated cost USD), the last-hour rollup (for rate-limit progress bars), and the most recent 50 individual call records.
- Cost estimation is done at read time via `backend/llm/pricing.py`, which looks up `LLM_MODEL_PRICING` in `config.py` by exact model name then longest-prefix match.

---

## attachments

Binary image blobs stored directly in Postgres. Linked to channel messages via `message_attachments`.

```
attachments
  id                    UUID        PK, default uuid4
  project_id            UUID        FK(repositories.id), ON DELETE CASCADE NOT NULL
  uploaded_by_user_id   UUID        FK(users.id), ON DELETE SET NULL, nullable
  filename              String(255) NOT NULL
  mime_type             String(100) NOT NULL    -- must be image/jpeg | image/png | image/gif | image/webp
  size_bytes            Integer     NOT NULL    -- capped at 10 MB (10 * 1024 * 1024)
  sha256                String(64)  NOT NULL    -- SHA-256 hex digest for integrity
  data                  LargeBinary NOT NULL    -- raw binary blob (bytea in Postgres)
  created_at            DateTime(tz) NOT NULL, default utcnow

  INDEX ix_attachments_project (project_id, created_at)
```

Notes:
- Uploaded via `POST /api/v1/attachments` (multipart/form-data). Only `image/*` MIME types are accepted; all others return `400`.
- Maximum size is 10 MB per file. Oversized uploads return `400`.
- SHA-256 is computed server-side and stored for integrity verification.
- The blob is served back via `GET /api/v1/attachments/{id}` with the correct `Content-Type` header.

---

## message_attachments

Junction table linking a `channel_message` to one or more `attachment` rows. Supports multiple images per message with ordering.

```
message_attachments
  id              UUID     PK, default uuid4
  message_id      UUID     FK(channel_messages.id), ON DELETE CASCADE NOT NULL
  attachment_id   UUID     FK(attachments.id), ON DELETE CASCADE NOT NULL
  position        Integer  NOT NULL, default 0    -- display order within the message

  INDEX ix_msg_attachments_message (message_id)
  INDEX ix_msg_attachments_attachment (attachment_id)
```

Notes:
- Loaded via `selectin` relationship on `ChannelMessage` to avoid N+1 queries when listing messages.
- The `attachment_ids` property on `ChannelMessage` exposes IDs only when the relationship is already loaded (avoids sync IO from Pydantic serialization).

---

## project_documents

Manager-agent-writable architecture documents. Read-only for users via REST. Used to store living documents that the Manager maintains as the project evolves.

```
project_documents
  id                  UUID        PK, default uuid4
  project_id          UUID        FK(repositories.id), ON DELETE CASCADE NOT NULL
  doc_type            String(100) NOT NULL    -- well-known type slug (see below)
  title               String(255) nullable
  content             Text        nullable
  updated_by_agent_id UUID        FK(agents.id), ON DELETE SET NULL, nullable

  created_at          DateTime(tz) NOT NULL, default utcnow
  updated_at          DateTime(tz) NOT NULL, default utcnow, onupdate utcnow

  UNIQUE INDEX ix_project_documents_project_type (project_id, doc_type)
```

Well-known `doc_type` values:
- `architecture_source_of_truth` — single canonical architecture description
- `arc42_lite` — arc42-lite template content
- `c4_diagrams` — C4 model diagrams (Markdown + PlantUML/Mermaid)
- `adr/<slug>` — individual Architecture Decision Records

Notes:
- `GET /api/v1/documents?project_id={uuid}` lists all documents for a project. `GET /api/v1/documents/{project_id}/{doc_type}` fetches a single document.
- Write access is restricted to agent internal API calls; users have read-only access.
- `updated_by_agent_id` tracks which agent last modified the document (nullable for legacy/seed data).
- The UNIQUE constraint on `(project_id, doc_type)` enforces one document per type per project; upsert semantics are used for writes.

---

## Entity Relationship Diagram

```
users ──────────────< repositories
  │                       │
  │                       ├──────────────< repository_memberships >──── users
  │                       │
  │                       ├──────────────< project_settings (1:1)
  │                       │
  │                       ├──────────────< agents
  │                       │                  │
  │                       │                  ├──────────────< agent_sessions
  │                       │                  │                     │
  │                       │                  │                     └──────< agent_messages
  │                       │                  │                     │
  │                       │                  │                     └──────< llm_usage_events
  │                       │                  │
  │                       │                  └──(assigned_agent_id)──< tasks
  │                       │
  │                       ├──────────────< tasks (project_id)
  │                       │
  │                       ├──────────────< channel_messages (project_id)
  │                       │                     │
  │                       │                     └──────< message_attachments >──── attachments
  │                       │
  │                       ├──────────────< attachments (project_id)
  │                       │
  │                       └──────────────< project_documents (project_id)
  │
  └──────────────(uploaded_by_user_id)──< attachments
```

Key relationships:
- `repositories` 1:1 `project_settings`
- `repositories` 1:N `agents`, `tasks`, `channel_messages`, `attachments`, `project_documents`
- `users` N:M `repositories` (via `repository_memberships`)
- `agents` 1:N `agent_sessions`, `llm_usage_events`
- `agent_sessions` 1:N `agent_messages`, `llm_usage_events`
- `agents` N:1 `tasks` (via `assigned_agent_id`, `current_task_id`)
- `channel_messages` N:M `attachments` (via `message_attachments`)
- `channel_messages` references agents by UUID but NOT via FK (user uses reserved UUID)

---

## Reserved Constants

```python
USER_AGENT_ID = UUID("00000000-0000-0000-0000-000000000000")
```

This UUID represents the user in `channel_messages.from_agent_id` and `channel_messages.target_agent_id`. It never exists in the `agents` table. The constant is defined in `backend/core/constants.py`.

---

## Migration History

| Migration | Description |
|-----------|-------------|
| `001_init_mvp0_schema.py` | Initial schema |
| `002_add_project_git_token.py` | Per-project GitHub token |
| `003_add_engineer_jobs.py` | Engineer job tracking (superseded by agent_sessions) |
| `004_add_users_and_repositories.py` | Users and repositories tables |
| `005_add_abort_and_user_ticket_replies.py` | Ticket/abort fields (superseded) |
| `006_data_and_messaging_foundation.py` | `channel_messages`, `agent_sessions`, `agent_messages`, `project_settings`; drops legacy tables |
| `007_deprecate_om_use_cto.py` | Renames `om` role → `cto`; removes deprecated agents |
| `008_add_agent_tier_column.py` | `agents.tier` column for engineer seniority |
| `009_memberships_and_attribution.py` | `repository_memberships` table; `channel_messages.from_user_id` for user attribution |
| `010_project_settings_overrides.py` | `project_settings.model_overrides` + `prompt_overrides` columns |
| `011_llm_usage_events.py` | `llm_usage_events` table; `project_settings.daily_token_budget` |
| `012_rate_limits_and_cost_budget.py` | `project_settings.calls_per_hour_limit`, `tokens_per_hour_limit`, `daily_cost_budget_usd` |
| `013_attachments.py` | `attachments` + `message_attachments` tables |
| `014_project_documents.py` | `project_documents` table |

---

## Indexes

Critical indexes for query performance:

| Index | Table | Columns | Query |
|-------|-------|---------|-------|
| `ix_channel_target_status` | `channel_messages` | `(target_agent_id, status, created_at)` | Get unread messages for agent |
| `ix_channel_project` | `channel_messages` | `(project_id, created_at)` | List all messages for project |
| `ix_agent_sessions_agent` | `agent_sessions` | `(agent_id, started_at)` | Session history for agent |
| `ix_agent_sessions_status` | `agent_sessions` | `(status)` | Reconciler: find all running sessions |
| `ix_agent_messages_agent_time` | `agent_messages` | `(agent_id, created_at)` | Read history for agent |
| `ix_agent_messages_session` | `agent_messages` | `(session_id, loop_iteration)` | Messages within a session |
| `ix_repo_memberships_repo_user` | `repository_memberships` | `(repository_id, user_id)` UNIQUE | Access control check |
| `ix_repo_memberships_user` | `repository_memberships` | `(user_id)` | Projects visible to a user |
| `ix_llm_usage_project_time` | `llm_usage_events` | `(project_id, created_at)` | Daily/hourly usage rollup |
| `ix_llm_usage_agent` | `llm_usage_events` | `(agent_id)` | Per-agent cost attribution |
| `ix_llm_usage_session` | `llm_usage_events` | `(session_id)` | Per-session token usage |
| `ix_attachments_project` | `attachments` | `(project_id, created_at)` | Attachments for a project |
| `ix_project_documents_project_type` | `project_documents` | `(project_id, doc_type)` UNIQUE | Fetch single doc by type |

The `ix_channel_target_status` index is the hottest path in the system: it is queried every time any agent wakes up to read its unread messages.
