# AICT — Roadmap / TODO

Source: `tmp/todo.txt` (expanded into an implementable roadmap).

## Decisions already locked

- **DB hosting**: keep backend on **Cloud Run**, run Postgres on a **cheap VM** (Docker) and connect over TCP with proper firewalling and SSL/TLS.
- **Images**: implement **full vision** end-to-end (attachments uploaded in the frontend → stored in DB → included in model calls for vision-capable models, with graceful fallback for text-only models).

## Guiding architecture constraints (existing)

- **Postgres is the single source of truth**: `docs/adr/001-postgresql-single-source-of-truth.md`
- **Provider-agnostic LLM layer**: `docs/adr/005-provider-agnostic-llm-layer.md`
- **Unified messaging via `channel_messages`**: `docs/adr/003-channel-messages-unified-communication.md`
- **Universal agent execution loop**: `docs/adr/002-universal-agent-execution-loop.md`
- **Platform, not workflow (CTO optional)**: `docs/adr/006-platform-not-workflow.md`

## Phase 0 — Baseline correctness fixes (unblocks multiple items)

- [x] **Fix OpenAI/ChatGPT wiring** (“chatgpt models not wired to the correct SDK”)
  - [x] `backend/services/llm_service.py`: stop bypassing the provider router/facade and ensure OpenAI models route through the OpenAI SDK provider.
  - [x] Add regression tests for `gpt-*` and `o*` model names routing to `backend/llm/providers/openai_sdk.py`.
- [x] **Fix engineer model override semantics**
  - [x] `backend/llm/model_resolver.py`: ensure `model_override` takes precedence for engineers (not just manager/CTO).
- [x] **Fix project-level max engineers enforcement**
  - [x] `backend/services/agent_service.py`: enforce `project_settings.max_engineers` (not global `settings.max_engineers`).
- [x] **Fix “human input not seen mid-session”**
  - [x] `backend/workers/loop.py`: re-check unread messages during the loop (budgeted) rather than only at session start.
- [x] **Give agents better error messages**
  - [x] Standardize tool errors (tool name, reason, minimal “next action”) so prompts can recover.
  - [x] Update prompt blocks so agents self-correct tool schema usage and handle provider errors deterministically.
- [x] **Prompt system hardening (reduce “1 million things” into concrete work)**
  - [x] Revisit block token budgets and allocations (system vs context vs tool IO) in the prompt assembly layer.
  - [x] Add deterministic “topic switch summarization” hooks (trigger + output target) so context compression isn’t ad-hoc.
  - [x] Ensure tool-call transcripts and error surfaces stay within budget without losing critical debugging information.

## Phase 1 — Infra: self-host Postgres (VM) to cut cost ✅

- [x] Add VM Postgres deployment assets (Docker/Compose)
  - [x] Create `infra/postgres/docker-compose.yml` (Postgres 15/16, volume, healthcheck)
  - [x] Create `infra/postgres/README.md` (setup, backup, restore drill, upgrade notes)
- [x] Secure Cloud Run → VM connectivity
  - [x] Serverless VPC Connector for Cloud Run egress
  - [x] Static egress IP via Cloud NAT (or equivalent) and VM firewall allowlist
  - [x] Require SSL/TLS for DB connections; document `DATABASE_URL` / SSL parameters
- [x] Update docs and verify runtime behavior
  - [x] Update `docs/deployment.md` to reflect VM Postgres topology and ops
  - [x] Validate Alembic migrations still run correctly on deploy/startup

## Phase 2 — Multi-user access + attribution ✅

Goal: "enable user level access, multiple users" with real membership semantics.

- [x] DB migration 009: `repository_memberships` + `channel_messages.from_user_id`
- [x] Centralized `require_project_access()` in `backend/core/project_access.py`
- [x] Membership repository: `backend/db/repositories/membership.py`
- [x] Access checks replaced in all API files (repositories, messages, agents, sessions, tasks)
- [x] Auto-add 'owner' membership on repository create + import
- [x] `MessageService.send_user_to_agent()` persists `from_user_id` for attribution
- [x] `ChannelMessageResponse.from_user_id` in schema + frontend types

## Phase 3 — Project-level model selection + prompt overrides ✅

Goal: "configurable model selection… project level… defaults in backend/config" + "configurable prompt".

- [x] Migration 010: `model_overrides` (JSON) + `prompt_overrides` (JSON) on `project_settings`
- [x] `resolve_model()` accepts `project_model_overrides` (agent override > project > global)
- [x] `loop.py` loads project settings, passes overrides to `resolve_model()` and `PromptAssembly`
- [x] `PromptAssembly` injects role-specific prompt override block (max 2000 chars) into system prompt
- [x] PATCH `/repositories/{id}/settings` handles new fields
- [x] `Settings.tsx`: Model Selection section (per-role inputs + presets datalist)
- [x] `Settings.tsx`: Prompt Customization section (per-role textareas + char counters)
- [x] `types/index.ts` + `api/client.ts`: `ModelOverrides`, `PromptOverrides`, settings types updated

## Phase 4 — API limit monitor + token usage safeguards ✅

Goal: "API limit monitor", "general safeguards… monitor token usage", "loop rate limit".

- [x] Migration 011: `llm_usage_events` table + `project_settings.daily_token_budget`
- [x] `LLMResponse.input_tokens` + `output_tokens` captured in all 3 providers (Anthropic, OpenAI, Gemini)
- [x] `LLMUsageRepository`: `record()`, `daily_rollup()`, `usage_summary()`, `daily_tokens_for_project()`
- [x] `loop.py` records usage after each LLM call (soft-fail on write error)
- [x] Loop checks `daily_token_budget` before each call; ends session with `budget_exhausted` if exceeded
- [x] `GET /api/v1/repositories/{id}/usage` endpoint (today rollup + recent 50 calls)
- [x] `Settings.tsx`: Token Budget section (daily limit input + usage rollup + recent calls table)

## Phase 4b — Rate limiting + cost calculator ✅

Goal: "configure the limit monitor", "cost calculator use price from backend/config.py", "rate limit (query per hour, token per hour)", "soft pause + resume at once when user adjust limits".

- [x] Migration 012: `project_settings.calls_per_hour_limit`, `tokens_per_hour_limit`, `daily_cost_budget_usd`
- [x] `LLM_MODEL_PRICING` dict in `backend/config.py` — USD per 1M tokens, user-editable
- [x] `backend/llm/pricing.py`: `estimate_cost_usd(model, input_tokens, output_tokens)` (exact + prefix match)
- [x] `LLMUsageRepository.daily_cost_usd_for_project()`, `hourly_stats()`, `hourly_rollup()`
- [x] Loop Gate 2: `daily_cost_budget_usd` hard-stop → `cost_budget_exhausted`
- [x] Loop Gate 3: hourly call/token rate limits → soft-pause (5 s poll, 10 min max, resumes if limits raised from UI)
- [x] `GET /repositories/{id}/usage` returns `last_hour` rollup for rate-limit progress bars
- [x] `Settings.tsx`: Rate Limits section (calls/hour + tokens/hour inputs + live progress bars)
- [x] `Settings.tsx`: Daily cost budget input + cost column in usage table + recent calls
- [x] `ProjectSettingsResponse` / `ProjectSettingsUpdate` schemas + frontend types updated

## Phase 5 — Integrate Kimi 2.5 (cheap provider) ✅

- [x] Add Kimi provider adapter + configuration
  - [x] `backend/config.py`: `moonshot_api_key` + `moonshot_base_url` (OpenAI-compatible shape); Kimi K2 + Moonshot pricing entries
  - [x] `backend/llm/router.py`: route `kimi-*` and `moonshot-*` models to Kimi provider
  - [x] `backend/llm/providers/kimi_sdk.py`: thin `KimiSDKProvider` subclass reusing OpenAI SDK with custom base URL
- [x] Surface in UI defaults and presets
  - [x] `Settings.tsx`: model selection converted from free-text + datalist to grouped `<select>` dropdowns; Kimi K2 + Moonshot models added as "Kimi / Moonshot" group
## Phase 6 — Images end-to-end (DB-stored binaries)

Goal: “allow images to flow through… save images as binary in db”.

- [ ] DB schema
  - [ ] Add `attachments` table (bytea/blob, mime, sha256, size, created_at, uploaded_by_user_id, project_id)
  - [ ] Add message↔attachment link (message_id, attachment_id)
- [ ] API
  - [ ] `POST /api/v1/attachments` (multipart upload) returns attachment ids
  - [ ] `GET /api/v1/attachments/{id}` streams bytes with auth/membership checks
  - [ ] Extend message send API to accept `attachment_ids`
- [ ] Frontend
  - [ ] Chat input: pick image(s), preview, upload, then send message referencing attachment ids
  - [ ] Message list: render images inline for messages with attachments
- [ ] LLM contracts + providers
  - [ ] Extend `backend/llm/contracts.py` to support multimodal message parts (text + images)
  - [ ] Implement provider-specific formatting + capability gating:
    - [ ] OpenAI vision format
    - [ ] Anthropic image blocks
    - [ ] Gemini inlineData parts
  - [ ] Fallback behavior: when model is text-only, return actionable error or require user-provided description mode

## Phase 7 — Tooling & loop cleanup (merged Phase 7 + 8) ✅

Goal: delete the legacy LangGraph tool layer, rename ambiguous sandbox naming, remove redundant git tools, introduce structured tool results and error taxonomy, and split the monolithic registry.

### 7a — Delete legacy LangGraph tool layer

- [x] Delete dead tool files: `backend/tools/e2b.py`, `e2b_tool.py`, `files.py`, `git.py`, `git_tool.py`, `tasks.py`, `task_tool.py`, `agents.py`, `sandbox_vm.py`, `context.py`, `registry.py`
- [x] Delete `backend/services/e2b_service.py` (fully replaced by `SandboxService`)
- [x] Remove all `from e2b import AsyncSandbox` and E2B SDK references across the codebase
- [x] Audit `backend/api_internal/files.py` — rewrote to use `SandboxService`
- [ ] Remove `e2b` from dependency list (`requirements.txt`)

### 7b — Rename sandbox layer for clarity

- [x] Remove all E2B terminology from `sandbox_service.py` comments and log messages
- [x] Deduplicate: `_run_start_sandbox` alias removed; `sandbox_start_session` is the single entry point
- [x] Audit `tool_descriptions.json` for residual E2B references — cleaned

### 7c — Remove dedicated git tools; promote `execute_command`

- [x] Remove from `loop_registry.py`: `_run_list_branches`, `_run_view_diff`, `_run_create_branch`, `_run_create_pull_request` and `subprocess` import
- [x] Remove from `tool_descriptions.json`: `list_branches`, `view_diff`, `create_branch`, `create_pull_request`, `start_sandbox` alias
- [x] Keep `GitService` only for the API layer — not callable from agent tools
- [x] Updated `backend/prompts/blocks/tool_io_engineer.md` with full git workflow via `execute_command`

### 7d — Structured tool results & error taxonomy

- [x] `backend/tools/result.py`: `ToolExecutionError(message, error_code, hint)` with standard codes
- [x] `backend/tools/base.py`: `parse_tool_uuid` now raises `ToolExecutionError` instead of bare `RuntimeError`
- [x] All executors raise `ToolExecutionError` instead of returning `"Error: ..."` strings
- [x] `PromptAssembly.append_tool_error` formats `[ERROR: code] message. Hint: ...` for `ToolExecutionError`
- [x] `backend/prompts/blocks/tool_io_base.md` updated with error code taxonomy

### 7e — Split `loop_registry.py` into domain modules

- [x] `backend/tools/base.py` — `RunContext`, `LoopTool`, `ToolExecutor`, shared helpers
- [x] `backend/tools/executors/messaging.py` — `send_message`, `broadcast_message`
- [x] `backend/tools/executors/memory.py` — `update_memory`, `read_history`, `list_sessions`
- [x] `backend/tools/executors/tasks.py` — `create_task`, `assign_task`, `update_task_status`, `abort_task`, `list_tasks`, `get_task_details`
- [x] `backend/tools/executors/sandbox.py` — `execute_command`, all `sandbox_*` tools
- [x] `backend/tools/executors/agents.py` — `spawn_engineer`, `list_agents`, `remove_agent`, `interrupt_agent`
- [x] `backend/tools/executors/meta.py` — `get_project_metadata`, `sleep`
- [x] `backend/tools/loop_registry.py` slim registry: builds `_TOOLS`, hosts `describe_tool`, exports public API

### 7f — Emergency stop button (frontend)

- [x] `POST /api/v1/agents/{id}/stop` endpoint — interrupts worker, broadcasts `agent_stopped` WS event
- [x] `EventType.AGENT_STOPPED` added to `backend/websocket/events.py`
- [x] `ws_manager.broadcast_agent_stopped()` in `backend/websocket/manager.py`
- [x] Frontend: red Stop button (square icon) shown on running agents; spinner while stopping
- [x] Toast confirmation: `Agent "X" stopped.` auto-dismisses after 3s
- [x] Agent list auto-refreshes on `agent_stopped` WS event

## Phase 9 — Sandbox enhancements + pressure tests

> **Current state (audited):** Ubuntu 22.04 VM, 4-core, `(4.0 - 0.2) / 0.5 = 7` max concurrent containers (each: 0.5 CPU, 256 MB). Xvfb virtual display `:99` at 1024×768×24 already running. Screenshot via `ffmpeg x11grab` already wired (`sandbox_screenshot` tool). **No chromium installed. No window manager installed** (bare Xvfb only). Port range 30001-30100 gives 100 slots — not the bottleneck.

### 9b — Memory leak audit

- [x] Audit `sandbox/pool_manager/main.py` container teardown path: verify `docker rm -f` is called on every `reset` and `remove` code path (including error branches)
- [x] Audit volume lifecycle: check that Docker volumes created per-container are pruned on container destruction — no orphaned volumes
- [x] Audit port reclaim: verify `port_range` set in pool manager state is always returned to the free pool after container removal, even on exception
- [x] Audit `sandbox/pool_manager/main.py` idle TTL path: confirm containers that exceed `IDLE_TTL_SECONDS = 1800` are actually reaped by the health-check loop, not just marked stale
- [x] Add a `GET /pool/debug` endpoint to pool manager that returns: container count, port occupancy, memory per container (`docker stats` snapshot) — for observability without SSH

### 9c — GUI desktop + headed browser setup

- [x] **Install chromium + git in `sandbox/Dockerfile`:**
  - Add `git`, `google-chrome-stable` (via Google apt repo — chromium-browser on Ubuntu 22.04 is a snap stub and does not work in Docker), `fonts-liberation`, `fonts-noto-color-emoji`, `fonts-noto-cjk`, `libnss3`, `libatk-bridge2.0-0`, `libxss1`, `dbus-x11`
  - Add Google apt repo: `https://dl.google.com/linux/linux_signing_key.pub` + `deb [arch=amd64] https://dl.google.com/linux/chrome/deb/ stable main`
- [x] **Install a minimal window manager** (`openbox`) so Chrome windows are properly positioned and composited on the Xvfb display; add `openbox --sm-disable &` to `entrypoint.sh` after Xvfb start
- [x] **Verify screenshot captures browser correctly:** after Dockerfile changes, run `google-chrome-stable --display=:99 --no-sandbox --disable-dev-shm-usage https://example.com &` then `sandbox_screenshot` and confirm browser window appears in the JPEG output
- [x] Update `sandbox/scripts/setup_vm.sh` and `sandbox/scripts/deploy_to_vm.sh` to rebuild the `sandbox-base` Docker image after Dockerfile changes

## Phase 10 — Per-project "single source of truth" architecture entry + templates

Goal: "per project, a single source of truth… manager-only write… templates: C4, arc42-lite, ADRs".

> **Design decisions (locked):** Write access is manager **agent** only (not users) — manager calls a tool that upserts the document. Users get read-only REST. Content is plain Markdown (rendered in frontend). Real-time updates via WebSocket event. The existing `/artifacts` route in the frontend is repurposed as the Architecture page.

### 10a — DB migration

- [x] Create `backend/migrations/versions/013_project_documents.py`:
  - New table `project_documents`:
    - `id` — `UUID`, PK, `server_default=uuid_generate_v4()`
    - `project_id` — `UUID`, FK → `repositories.id` ON DELETE CASCADE, not null
    - `doc_type` — `VARCHAR(100)`, not null (values: `"architecture_source_of_truth"`, `"arc42_lite"`, `"c4_diagrams"`, `"adr/{slug}"`)
    - `title` — `VARCHAR(255)`, nullable
    - `content` — `TEXT`, nullable (raw Markdown)
    - `updated_by_agent_id` — `UUID`, FK → `agents.id` ON DELETE SET NULL, nullable
    - `created_at` — `TIMESTAMPTZ`, `server_default=now()`
    - `updated_at` — `TIMESTAMPTZ`, `server_default=now()`, updated on write
  - Unique constraint: `(project_id, doc_type)`

### 10b — SQLAlchemy model

- [x] Add `ProjectDocument` model to `backend/db/models.py` following the `ProjectSettings` pattern (UUID PK, FK with cascade, `_utcnow` default, relationship back to `Repository`)

### 10c — Repository

- [x] Create `backend/db/repositories/project_documents.py` extending `BaseRepository[ProjectDocument]`:
  - `list_by_project(project_id) → list[ProjectDocument]`
  - `get_by_type(project_id, doc_type) → ProjectDocument | None`
  - `upsert(project_id, doc_type, content, title, agent_id) → ProjectDocument` — INSERT … ON CONFLICT (project_id, doc_type) DO UPDATE

### 10d — Agent write tool (`write_architecture_doc`)

- [x] Add `write_architecture_doc` to `backend/tools/executors/meta.py` (or a new `docs.py` executor):
  - Parameters: `doc_type: str`, `content: str`, `title: str | None`
  - Guard: only callable by `role == "manager"` agents — raise `ToolExecutionError(PERMISSION_DENIED)` otherwise
  - Upserts via `ProjectDocumentRepository.upsert()`
  - After write: broadcast `DOCUMENT_UPDATED` WebSocket event (see 10e)
- [x] Register `write_architecture_doc` in `backend/tools/loop_registry.py`
- [x] Add entry to `backend/tools/tool_descriptions.json` with `doc_type` allowed values and Markdown content guidance
- [x] Update manager system prompt block (`backend/prompts/blocks/`) to describe when and how to call `write_architecture_doc` (after significant architectural decisions, ADR discussions, etc.)

### 10e — WebSocket event

- [x] Add `DOCUMENT_UPDATED = "document_updated"` to `EventType` in `backend/websocket/events.py`
- [x] Add `create_document_updated_event(project_id, doc_type, title)` factory in `backend/websocket/events.py`
- [x] Add `broadcast_document_updated(project_id, doc_type, title)` to `backend/websocket/manager.py`

### 10f — Backend read-only API

- [x] Add Pydantic schemas to `backend/schemas/project_documents.py`:
  - `ProjectDocumentResponse` — `id`, `doc_type`, `title`, `content`, `updated_by_agent_id`, `updated_at`
  - `ProjectDocumentListResponse` — list of `ProjectDocumentResponse`
- [x] Add endpoints to `backend/api/v1/repositories.py` (or a new `documents.py` router):
  - `GET /repositories/{repository_id}/documents` — returns `ProjectDocumentListResponse` (all docs for project, content omitted for list view)
  - `GET /repositories/{repository_id}/documents/{doc_type}` — returns full `ProjectDocumentResponse`; `doc_type` path param is URL-encoded for ADR slugs
  - Both require `require_project_access()` (any member can read); no POST/PATCH/DELETE for users

### 10g — Frontend — Architecture page

> **No user editing.** The page is strictly read-only for users. Documents are written exclusively by the manager agent via `write_architecture_doc`. Do not add a textarea, markdown editor, or any save/edit button.

- [x] Rename "Artifacts" nav label to "Architecture" in `frontend/src/components/Workspace/Sidebar.tsx`
- [x] Create `frontend/src/components/Architecture/ArchitecturePage.tsx`:
  - On mount: `GET /repositories/{id}/documents` to populate tab list
  - Tabs for each doc_type: "Source of Truth", "arc42-lite", "C4 Diagrams", "ADRs"
  - Render content as read-only with `react-markdown` (install if not already present); show empty-state placeholder when `content` is null
  - Subscribe to WS `document_updated` events — on match for current project, re-fetch and re-render the updated document without page reload
- [x] Floating conversation bar (bottom-right overlay on Architecture page only):
  - Collapsed "Chat with Manager" button; expands to a compact chat input
  - On send: POST to existing message-send API targeting the manager agent's channel (reuse existing channel resolution logic)
  - Collapses back after send; does not replace the main WorkspacePage chat
- [x] Update `App.tsx` to render `ArchitecturePage` for the `artifacts` view

## Product positioning tasks

- [ ] Pricing story
  - [ ] Document `$20 base tier + API cost` vs `$200+ infra deployment`
  - [x] Phase 4/4b now records per-call token + cost data — sufficient usage data exists to justify and explain costs

---

## Coverage check: each `tmp/todo.txt` item mapped

- **self host Postgres / set up selfhosting postgres** → Phase 1 ✅
- **configurable model selection (frontend, project-level, defaults in config)** → Phase 3 ✅
- **configurable prompt per model/project** → Phase 3 ✅
- **API limit monitor / monitor token usage / safeguards** → Phase 4 ✅
- **cost calculator + per-hour rate limits** → Phase 4b ✅
- **multiple users** → Phase 2 ✅
- **integrate Kimi2.5** → Phase 5
- **images flow + store binary in DB** → Phase 6
- **async tooling** → Phase 7 (7d/7e)
- **abstract messaging system / structured streaming / category filtering** → Phase 7 (tooling cleanup supersedes old Phase 7)
- **no need to let agent send message if frontend monitors** → Phase 7 (7c prompt update)
- **subagent pattern** → Phase 7 (7e agent executor module)
- **agent roles stored** → already present in DB (`agents.role`, `agents.tier`); remaining work is making UI/prompts/APIs use it consistently
- **add git chromium to sandbox** → Phase 9
- **pressure tests** → Phase 9
- **prompt fixes / block allocation reallocation** → Phase 0 + Phase 3 (prompt overrides) + ongoing prompt-system work
- **agent proper error messages** → Phase 0
- **agent didn’t see human input within session** → Phase 0
- **chatgpt models not wired to correct SDK** → Phase 0
- **summarize context immediately on topic switch** → Phase 0 (prompt system hardening) + explicit UX trigger (also listed in “Missing” because it wasn’t in `tmp/todo.txt`)
- **END tool can be called with other tools** → Phase 7 (7d loop semantics update)
- **remove CTO from picture** → ADR-006 already aligns; implement as UI defaults + optional role (platform not workflow)

## Architectural decisions this should explicitly outline (ADR-worthy)

These choices change interfaces and long-term cost; they must be written down (ADRs) before heavy implementation:

1) **Multi-tenancy model**: membership roles, invites, and whether “unowned/public” repositories exist.
2) **Usage metering semantics**: what counts toward limits (failed calls, retries, tool loops), and what the user sees (tokens vs cost vs both).
3) **Multimodal contract shape**: attachments linked-to-messages vs inline parts; capability matrix; fallback UX.
4) **WebSocket event versioning**: schema evolution + compatibility between frontend/backend.
5) **Conversation semantics**: streamed `agent_text` vs explicit persisted “agent replies”.
6) **END/tool batching semantics**: strict “end must be alone” vs “tools then end”.
7) **Async tooling safety**: timeouts, cancellation, idempotency, and partial-failure handling.
8) **Operational security**: secrets management, TLS rotation, backups, restore drills, and incident response (especially for self-hosted DB).

## What’s missing from `tmp/todo.txt` (but needed for robustness)

- **Data retention/cleanup**: `channel_messages` / `agent_messages` growth requires archival/pruning policy.
- **Security**: attachment size/type limits (and scanning later), audit logs for membership/settings changes. *(Project-level LLM rate limiting is now done — Phase 4b. HTTP-level API rate limiting is still missing.)*
- **Migration + rollout strategy**: feature flags for new providers/multimodal, staging, and test coverage targets.
- **UX affordance for “topic switch summarization”**: explicit UI trigger + loop integration to write a summary artifact.
- **Error taxonomy**: consistent error codes across REST, WS, tool results, and provider failures for actionable frontend rendering.
