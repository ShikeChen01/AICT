# Database Schema

## Overview

The database is the single source of truth for all state. No LangGraph checkpointer, no in-memory state persistence. PostgreSQL with SQLAlchemy async ORM and Alembic migrations.

### Tables

| Table              | Status      | Purpose                                          |
|--------------------|-------------|--------------------------------------------------|
| `users`            | Keep        | Authenticated users with GitHub credentials      |
| `repositories`     | Keep        | Per-repository/project config                    |
| `project_settings` | **New**     | Per-project configurables (max engineers, sandbox count) |
| `agents`           | Modify      | Agent definitions with new `memory` column       |
| `tasks`            | Keep        | Kanban cards with 2D priority                    |
| `agent_messages`   | **New**     | Persistent message log (Layer 2 memory)          |
| `channel_messages` | **New**     | Inter-agent/user communication channel           |
| `agent_sessions`   | **New**     | Tracks each agent work session (wake-to-END)     |
| `chat_messages`    | **Drop**    | Replaced by `channel_messages` (user = agent ID 0) |
| `tickets`          | **Drop**    | Deprecated, replaced by `channel_messages`       |
| `ticket_messages`  | **Drop**    | Deprecated, replaced by `channel_messages`       |
| `engineer_jobs`    | **Drop**    | Replaced by `agent_sessions`                     |

---

## Users

No changes from current schema.

```
users
  id              UUID        PK, default uuid4
  firebase_uid    String(128) UNIQUE, NOT NULL
  email           String(255) UNIQUE, NOT NULL
  display_name    String(100) nullable
  github_token    String(512) nullable
  created_at      DateTime    NOT NULL, default utcnow
  updated_at      DateTime    NOT NULL, default utcnow, onupdate utcnow
```

Relationships:
- `users.id` <-- `repositories.owner_id`

---

## Repositories

No changes from current schema. `Project` alias kept for backward compatibility.

```
repositories
  id              UUID        PK, default uuid4
  owner_id        UUID        FK(users.id), ON DELETE SET NULL, nullable
  name            String(255) NOT NULL
  description     Text        nullable
  spec_repo_path  String(512) NOT NULL
  code_repo_url   String(512) NOT NULL
  code_repo_path  String(512) NOT NULL
  created_at      DateTime    NOT NULL, default utcnow
  updated_at      DateTime    NOT NULL, default utcnow, onupdate utcnow
```

Relationships:
- `repositories.id` <-- `agents.project_id`
- `repositories.id` <-- `tasks.project_id`
- `repositories.id` <-- `channel_messages.project_id`
- `repositories.id` <-- `agent_messages.project_id`
- `repositories.id` <-- `project_settings.project_id`

---

## Project Settings (NEW)

Per-project configurables. One row per project.

```
project_settings
  id                        UUID        PK, default uuid4
  project_id                UUID        FK(repositories.id), ON DELETE CASCADE, UNIQUE, NOT NULL
  max_engineers              Integer     NOT NULL, default 5
  persistent_sandbox_count   Integer     NOT NULL, default 1
  created_at                DateTime    NOT NULL, default utcnow
  updated_at                DateTime    NOT NULL, default utcnow, onupdate utcnow
```

Notes:
- One-to-one with `repositories` (enforced by UNIQUE on `project_id`)
- `max_engineers`: dynamic limit on how many engineers can be spawned
- `persistent_sandbox_count`: how many E2B sandbox slots survive across agent sessions. Allocated first-come-first-serve to GM, CTO, and Engineers. When all persistent slots are taken, additional sandboxes are non-persistent (destroyed at session end). When a persistent slot is released, a non-persistent sandbox can be promoted. See `tools.md` Sandbox Pool for the full allocation flow.
- Extensible: add more columns as future configurables are needed

---

## Agents (MODIFIED)

Changes from current schema:
- Added `memory` column (JSON) for the self-define prompt block
- Cleaned up roles: removed deprecated `gm`, `om`. Valid roles are now `manager`, `cto`, `engineer`
- Removed `priority` column (hierarchy is implicit from role)

```
agents
  id              UUID        PK, default uuid4
  project_id      UUID        FK(repositories.id), ON DELETE CASCADE, NOT NULL
  role            String(50)  NOT NULL          -- 'manager', 'cto', 'engineer'
  display_name    String(100) NOT NULL          -- e.g. 'GM', 'CTO', 'Engineer-3'
  model           String(100) NOT NULL          -- e.g. 'claude-4.6-opus', 'claude-4-sonnet'
  status          String(20)  NOT NULL, default 'sleeping'  -- 'sleeping', 'active', 'busy'
  current_task_id UUID        FK(tasks.id), nullable
  sandbox_id      String(255) nullable
  sandbox_persist Boolean     NOT NULL, default false
  memory          JSON        nullable          -- NEW: self-define prompt block (Layer 1)
  created_at      DateTime    NOT NULL, default utcnow
  updated_at      DateTime    NOT NULL, default utcnow, onupdate utcnow
```

Valid roles: `manager`, `cto`, `engineer`
Valid statuses: `sleeping`, `active`, `busy`

Notes:
- `memory`: JSON field storing the agent's self-curated working memory. Updated via the `update_memory` tool. Included in every prompt as the Self-Define Block.
- `manager` role = GM (General Manager). One per project, auto-created. GM gets a sandbox from the pool when using execute_command or git tools.
- `cto` role = CTO. One per project, auto-created. Sandbox is on-demand (created when CTO first uses execute_command or a git tool).
- `engineer` role = dynamically spawned. Count limited by `project_settings.max_engineers`.
- `sandbox_id`: the E2B sandbox currently assigned to this agent. NULL when the agent has no sandbox active (e.g. before first execute_command or git tool use in session for GM/CTO).
- `sandbox_persist`: dynamically managed by the sandbox pool. When an agent holds a persistent slot, this is `true`. Promotion and release are handled by the pool allocator (see `tools.md` Sandbox Pool).
- `priority` column removed: the hierarchy (manager > cto > engineer) is implicit from role.
- `gm` and `om` roles are deprecated and removed.

---

## Tasks

Minimal changes. Removed abort-related fields (abort handled via messaging now). Kept the rest.

```
tasks
  id                UUID        PK, default uuid4
  project_id        UUID        FK(repositories.id), ON DELETE CASCADE, NOT NULL
  title             String(255) NOT NULL
  description       Text        nullable
  status            String(50)  NOT NULL, default 'backlog'
  critical          Integer     NOT NULL, default 5       -- 0-10, 0=most critical
  urgent            Integer     NOT NULL, default 5       -- 0-10, 0=most urgent
  assigned_agent_id UUID        FK(agents.id), ON DELETE SET NULL, nullable
  module_path       String(512) nullable
  git_branch        String(255) nullable
  pr_url            String(512) nullable
  parent_task_id    UUID        FK(tasks.id), ON DELETE SET NULL, nullable
  created_by_id     UUID        FK(agents.id), ON DELETE SET NULL, nullable
  created_at        DateTime    NOT NULL, default utcnow
  updated_at        DateTime    NOT NULL, default utcnow, onupdate utcnow
```

Valid statuses: `backlog`, `specifying`, `assigned`, `in_progress`, `in_review`, `done`, `aborted`

Notes:
- `abort_reason`, `abort_documentation`, `aborted_by_id` removed. Abort is now handled via messaging: the agent sends a message explaining the abort, updates task status to `aborted`, and calls END.
- `assigned_agent_id` tracks who is working on the task.
- `created_by_id` tracks which agent created the task.
- Subtask support via `parent_task_id` self-reference.

---

## Channel Messages (NEW)

Inter-agent and user-agent communication. All messages in the system flow through this table.

```
channel_messages
  id              UUID        PK, default uuid4
  project_id      UUID        FK(repositories.id), ON DELETE CASCADE, NOT NULL
  from_agent_id   UUID        nullable          -- NULL for system messages. User = reserved ID (UUID 0)
  target_agent_id UUID        nullable          -- NULL for broadcast. User = reserved ID (UUID 0)
  content         Text        NOT NULL
  message_type    String(20)  NOT NULL, default 'normal'  -- 'normal', 'system'
  status          String(20)  NOT NULL, default 'sent'    -- 'sent', 'received'
  broadcast       Boolean     NOT NULL, default false
  created_at      DateTime    NOT NULL, default utcnow

  INDEX ix_channel_target_status (target_agent_id, status, created_at)
  INDEX ix_channel_project (project_id, created_at)
```

Notes:
- `from_agent_id` and `target_agent_id` are NOT foreign keys to `agents.id` because user uses a reserved UUID (all zeros: `00000000-0000-0000-0000-000000000000`). This UUID never exists in the `agents` table.
- For broadcast messages: `target_agent_id = NULL`, `broadcast = true`. Each agent queries for broadcast messages separately.
- `status` tracks delivery: `sent` means the target hasn't read it yet, `received` means it has been consumed. This enables recovery after restart.
- Messages to user (`target_agent_id = USER_AGENT_ID`) are pushed via WebSocket, not read from DB by a loop.
- The primary index on `(target_agent_id, status, created_at)` enables the core query: "get all unread messages for this agent, ordered by time."

Replaces: `chat_messages`, `tickets`, `ticket_messages`

---

## Agent Messages (NEW)

Persistent log of every message in an agent's loop conversation. This is Layer 2 memory.

```
agent_messages
  id              UUID        PK, default uuid4
  agent_id        UUID        FK(agents.id), ON DELETE CASCADE, NOT NULL
  session_id      UUID        FK(agent_sessions.id), ON DELETE CASCADE, nullable
  project_id      UUID        FK(repositories.id), ON DELETE CASCADE, NOT NULL
  role            String(20)  NOT NULL          -- 'system', 'user', 'assistant', 'tool'
  content         Text        NOT NULL
  tool_name       String(100) nullable          -- set when role='tool'
  tool_input      JSON        nullable          -- tool call arguments
  tool_output     Text        nullable          -- tool return value
  loop_iteration  Integer     NOT NULL          -- which iteration within the session
  created_at      DateTime    NOT NULL, default utcnow

  INDEX ix_agent_messages_agent_time (agent_id, created_at)
  INDEX ix_agent_messages_session (session_id, loop_iteration)
```

Notes:
- Every prompt, response, tool call, and tool result is persisted here automatically by the loop.
- `session_id` links to `agent_sessions` so you can query "all messages from session X."
- `loop_iteration` is the iteration counter within a session (resets each session).
- `role` follows LLM convention: `system` (prompt blocks), `user` (incoming messages, loopback prompts), `assistant` (LLM responses), `tool` (tool results).
- Agent queries this via the `read_history` tool (pagination with limit/offset).
- Frontend inspector reads from this for debugging.
- Future: add `embedding Vector(1536)` column for RAG (pgvector). No schema change needed for the rest of the system.

---

## Agent Sessions (NEW)

Tracks each agent work session. A session = one run of the inner loop (wake up to END).

```
agent_sessions
  id                UUID        PK, default uuid4
  agent_id          UUID        FK(agents.id), ON DELETE CASCADE, NOT NULL
  project_id        UUID        FK(repositories.id), ON DELETE CASCADE, NOT NULL
  task_id           UUID        FK(tasks.id), ON DELETE SET NULL, nullable
  trigger_message_id UUID       FK(channel_messages.id), ON DELETE SET NULL, nullable
  status            String(20)  NOT NULL, default 'running'
  end_reason        String(50)  nullable
  iteration_count   Integer     NOT NULL, default 0
  started_at        DateTime    NOT NULL, default utcnow
  ended_at          DateTime    nullable

  INDEX ix_agent_sessions_agent (agent_id, started_at)
  INDEX ix_agent_sessions_status (status)
```

Valid statuses: `running`, `completed`, `force_ended`, `error`
Valid end_reasons: `normal_end`, `max_iterations`, `max_loopbacks`, `interrupted`, `aborted`, `error`

Notes:
- One row per session. Created when agent wakes up, updated when session ends.
- `task_id`: which task the agent was working on during this session (nullable -- GM may wake up to answer a user question without a specific task).
- `trigger_message_id`: the channel message that woke the agent and started this session.
- `iteration_count`: how many iterations the inner loop ran.
- `end_reason`: why the session ended. `normal_end` = agent called END. Others are safeguard triggers.
- Replaces `engineer_jobs` with a universal concept that works for all agent types.

---

## Dropped Tables

### chat_messages -- DROPPED

Replaced by `channel_messages`. User messages to GM and GM responses to user are now standard channel messages with the reserved user UUID.

### tickets -- DROPPED

Deprecated. All ticket functionality replaced by `channel_messages`:
- Questions/help requests --> normal channel message
- Emergency interrupts --> system channel message
- Human-in-the-loop --> user sends channel message directly

### ticket_messages -- DROPPED

Deprecated along with `tickets`. Conversation history preserved in `agent_messages` (the persistent log).

### engineer_jobs -- DROPPED

Replaced by `agent_sessions`. The session concept is universal (works for GM, CTO, and Engineers), while `engineer_jobs` only tracked engineers.

---

## Entity Relationship Diagram

```
users ----< repositories
                |
                |----< project_settings (1:1)
                |
                |----< agents
                |        |
                |        |----< agent_sessions
                |        |        |
                |        |        |----< agent_messages
                |        |
                |        |----< tasks (assigned_agent_id)
                |
                |----< tasks (project_id)
                |
                |----< channel_messages (project_id)
```

Key relationships:
- `repositories` 1:1 `project_settings`
- `repositories` 1:N `agents`
- `agents` 1:N `agent_sessions`
- `agent_sessions` 1:N `agent_messages`
- `agents` N:1 `tasks` (via `assigned_agent_id`, `current_task_id`)
- `channel_messages` references agents by UUID but NOT via FK (user uses reserved UUID)

---

## Reserved Constants

```
USER_AGENT_ID = UUID("00000000-0000-0000-0000-000000000000")
```

This UUID represents the user in `channel_messages.from_agent_id` and `channel_messages.target_agent_id`. It never exists in the `agents` table.

---

## Migration Plan

The migration from the current schema to the new schema:

1. **Add** `project_settings` table
2. **Add** `memory` column to `agents` table (nullable JSON)
3. **Add** `agent_sessions` table
4. **Add** `agent_messages` table
5. **Add** `channel_messages` table
6. **Remove** `priority` column from `agents`
7. **Remove** `abort_reason`, `abort_documentation`, `aborted_by_id` from `tasks`
8. **Update** `agents.role` values: `gm` --> `manager`, `om` --> delete OM agents
9. **Migrate** `chat_messages` data into `channel_messages` (with `from_agent_id`/`target_agent_id` mapped)
10. **Drop** `chat_messages` table
11. **Drop** `tickets` table
12. **Drop** `ticket_messages` table
13. **Drop** `engineer_jobs` table
