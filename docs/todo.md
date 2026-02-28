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

## Phase 7 — Tooling & loop cleanup (merged Phase 7 + 8)

Goal: delete the legacy LangGraph tool layer, rename ambiguous sandbox naming, remove redundant git tools, introduce structured tool results and error taxonomy, and split the monolithic registry.

### 7a — Delete legacy LangGraph tool layer

- [ ] Delete dead tool files: `backend/tools/e2b.py`, `e2b_tool.py`, `files.py`, `git.py`, `git_tool.py`, `tasks.py`, `task_tool.py`, `agents.py`, `sandbox_vm.py`, `context.py`, `registry.py`
- [ ] Delete `backend/services/e2b_service.py` (fully replaced by `SandboxService`)
- [ ] Remove all `from e2b import AsyncSandbox` and E2B SDK references across the codebase
- [ ] Audit `backend/api_internal/files.py` — if it uses `E2BService`, rewrite to use `SandboxService` or delete
- [ ] Remove `e2b` from dependency list (`requirements.txt`)

### 7b — Rename sandbox layer for clarity

- [ ] Remove all E2B terminology from `sandbox_service.py` comments and log messages
- [ ] Deduplicate: `_run_start_sandbox` and `_run_sandbox_start_session` in `loop_registry.py` are near-identical — collapse into one tool entry
- [ ] Audit `tool_descriptions.json` for any residual E2B references in descriptions/detailed_descriptions and update them

### 7c — Remove dedicated git tools; promote `execute_command`

- [ ] Remove from `loop_registry.py`: `_run_list_branches`, `_run_view_diff`, `_run_create_branch`, `_run_create_pull_request` and their `_TOOL_EXECUTORS` entries (these run `subprocess` against the **host**, not the sandbox)
- [ ] Remove from `tool_descriptions.json`: `list_branches`, `view_diff`, `create_branch`, `create_pull_request`
- [ ] Keep `GitService` only for the API layer (repo import, GitHub webhook endpoints) — not callable from agent tools
- [ ] Update `backend/prompts/blocks/` to tell engineers: "use `execute_command` for all git operations — git is available in your sandbox"
- [ ] If PR creation via GitHub API is still needed as an agent action, replace the removed tool with a single `create_pull_request` that takes `branch_name` as input and calls `GitService.create_pr()` — no host-side `subprocess` calls

### 7d — Structured tool results & error taxonomy

- [ ] Define `ToolResult` dataclass in `backend/tools/result.py`: `success: bool`, `output: str`, `error_code: str | None`, `hint: str | None`
  - Error codes: `INVALID_INPUT`, `PERMISSION_DENIED`, `SANDBOX_TIMEOUT`, `SANDBOX_UNAVAILABLE`, `NOT_FOUND`, `PROVIDER_ERROR`
- [ ] Define `ToolExecutionError(error_code, message, hint)` exception class
- [ ] Refactor all executors to `raise ToolExecutionError` instead of returning `"Error: ..."` strings
- [ ] Update loop dispatch in `backend/workers/loop.py` to format results as `[OK] output` vs `[ERROR: code] message. Hint: hint`
- [ ] Update `PromptAssembly.append_tool_error` / `append_tool_result` to use `ToolResult`
- [ ] Update `backend/prompts/blocks/tool_io_base.md` with the new error format so the LLM knows how to parse and act on errors

### 7e — Split `loop_registry.py` into domain modules

- [ ] `backend/tools/executors/messaging.py` — `send_message`, `broadcast_message`
- [ ] `backend/tools/executors/memory.py` — `update_memory`, `read_history`, `list_sessions`
- [ ] `backend/tools/executors/tasks.py` — `create_task`, `assign_task`, `update_task_status`, `abort_task`, `list_tasks`, `get_task_details`
- [ ] `backend/tools/executors/sandbox.py` — `execute_command`, all `sandbox_*` tools
- [ ] `backend/tools/executors/agents.py` — `spawn_engineer`, `list_agents`, `remove_agent`, `interrupt_agent`
- [ ] `backend/tools/executors/meta.py` — `describe_tool`, `get_project_metadata`, `sleep`
- [ ] `backend/tools/loop_registry.py` becomes a slim registry: `RunContext`, `LoopTool`, `ToolResult`, role filtering, `_TOOL_EXECUTORS` map, and public API (`get_tool_defs_for_role`, `get_handlers_for_role`, `validate_tool_input`)

### 7f — Emergency stop button (frontend)

- [ ] `POST /api/v1/agents/{id}/stop` endpoint — calls `worker_manager.interrupt_agent()` and sets agent status to `idle`
- [ ] Frontend: render a "Stop" button whenever an agent's status is `running`; disable/hide when `idle`
- [ ] Emit a WS event (`agent_stopped`) so all connected clients update agent status in real time without polling
- [ ] Show a confirmation toast: "Agent stopped." with the agent display name

## Phase 9 — Sandbox enhancements + pressure tests

- [ ] Sandbox image upgrades
  - [ ] Update `sandbox/Dockerfile` to install `git` and `chromium` (+ deps/fonts)
- [ ] Pressure tests
  - [ ] Add load tests: spawn N agents, send messages, validate no dropped wakeups and stable WS streaming under load

## Phase 10 — Per-project “single source of truth” architecture entry + templates

Goal: “per project, a single source of truth… manager-only write… templates: C4, arc42-lite, ADRs”.

- [ ] Add a typed document store in DB
  - [ ] New table (e.g., `project_documents`) for:
    - [ ] `architecture_source_of_truth` (single long entry)
    - [ ] `arc42_lite`
    - [ ] `c4_diagrams`
    - [ ] `adrs/*`
  - [ ] Enforce manager-only write access; everyone read
- [ ] API + UI
  - [ ] Add endpoints to read/update docs
  - [ ] Frontend: “Architecture” page rendering templates and current content

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
