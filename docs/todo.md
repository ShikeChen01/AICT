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

## Phase 1 — Infra: self-host Postgres (VM) to cut cost

- [ ] Add VM Postgres deployment assets (Docker/Compose)
  - [ ] Create `infra/postgres/docker-compose.yml` (Postgres 15/16, volume, healthcheck)
  - [ ] Create `infra/postgres/README.md` (setup, backup, restore drill, upgrade notes)
- [ ] Secure Cloud Run → VM connectivity
  - [ ] Serverless VPC Connector for Cloud Run egress
  - [ ] Static egress IP via Cloud NAT (or equivalent) and VM firewall allowlist
  - [ ] Require SSL/TLS for DB connections; document `DATABASE_URL` / SSL parameters
- [ ] Update docs and verify runtime behavior
  - [ ] Update `docs/deployment.md` to reflect VM Postgres topology and ops
  - [ ] Validate Alembic migrations still run correctly on deploy/startup

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

## Phase 5 — Integrate Kimi 2.5 (cheap provider)

- [ ] Add Kimi provider adapter + configuration
  - [ ] `backend/config.py`: add key/base_url config (OpenAI-compatible shape)
  - [ ] `backend/llm/router.py`: route `kimi-*` models to Kimi provider
  - [ ] Add a provider implementation (prefer reusing OpenAI-compatible client with custom base URL)
- [ ] Surface in UI defaults and presets
  - [ ] Add “cheap preset” model choices in frontend dropdowns

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

## Phase 7 — Streaming + messaging upgrades

Goals: “abstract the messaging system”, “structured streaming”, “filter by category”, “agent messaging maybe unnecessary”.

- [ ] Structured WS event schema (backward compatible)
  - [ ] Extend `backend/websocket/events.py` payloads with `category`, `severity`, `source`, `correlation_id`
  - [ ] Frontend: extend `ActivityFeed` filtering beyond `log_type`
- [ ] Decide chat semantics (important)
  - [ ] Option: treat streamed `agent_text` as the canonical assistant reply (platform-style)
  - [ ] Option: keep explicit `agent_message` writes for “final answers”
  - [ ] Implement whichever is chosen in `frontend/src/hooks/useMessages.ts` and the backend loop/router
- [ ] Decide persistence boundary for “activity logs”
  - [ ] Option: activity logs are ephemeral (frontend-only, filterable, not persisted)
  - [ ] Option: activity logs are persisted (auditable/history, but higher DB/storage cost)
  - [ ] Implement the chosen boundary consistently (DB schema + WS + UI expectations)
- [ ] Re-evaluate agent “send message” capability
  - [ ] If frontend monitoring replaces explicit agent chat sends, restrict or repurpose `send_message` tool to avoid redundant DB writes.
- [ ] END tool batching rule (explicit decision)
  - [ ] Current behavior forbids `end` mixed with other tools; if you want to allow it, change loop semantics + prompt docs + tests

## Phase 8 — Subagent pattern + async tooling

- [ ] Define the “subagent” abstraction you want
  - [ ] Option A: current “spawn engineers” is the subagent pattern → improve ergonomics (scoping, retries, assignments)
  - [ ] Option B: ephemeral in-session subagents with scoped toolsets and bounded context (requires DB + UI support)
- [ ] Async tooling safety model
  - [ ] Decide whether tools remain strictly sequential (current) or allow safe concurrent tool classes
  - [ ] Add timeouts, cancellation, and idempotency guidance at the tool contract boundary

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
  - [ ] Ensure Phase 4 yields enough usage data to justify and explain costs

---

## Coverage check: each `tmp/todo.txt` item mapped

- **self host Postgres / set up selfhosting postgres** → Phase 1
- **configurable model selection (frontend, project-level, defaults in config)** → Phase 3
- **configurable prompt per model/project** → Phase 3
- **API limit monitor / monitor token usage / safeguards** → Phase 4
- **multiple users** → Phase 2
- **integrate Kimi2.5** → Phase 5
- **images flow + store binary in DB** → Phase 6
- **async tooling** → Phase 8
- **abstract messaging system / structured streaming / category filtering** → Phase 7
- **no need to let agent send message if frontend monitors** → Phase 7 (decision + implementation)
- **subagent pattern** → Phase 8
- **agent roles stored** → already present in DB (`agents.role`, `agents.tier`); remaining work is making UI/prompts/APIs use it consistently
- **add git chromium to sandbox** → Phase 9
- **pressure tests** → Phase 9
- **prompt fixes / block allocation reallocation** → Phase 0 + Phase 3 (prompt overrides) + ongoing prompt-system work
- **agent proper error messages** → Phase 0
- **agent didn’t see human input within session** → Phase 0
- **chatgpt models not wired to correct SDK** → Phase 0
- **summarize context immediately on topic switch** → Phase 0 (prompt system hardening) + explicit UX trigger (also listed in “Missing” because it wasn’t in `tmp/todo.txt`)
- **END tool can be called with other tools** → Phase 7 (explicit decision + change)
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
- **Security**: attachment size/type limits (and scanning later), API rate limiting, audit logs for membership/settings changes.
- **Migration + rollout strategy**: feature flags for new providers/multimodal, staging, and test coverage targets.
- **UX affordance for “topic switch summarization”**: explicit UI trigger + loop integration to write a summary artifact.
- **Error taxonomy**: consistent error codes across REST, WS, tool results, and provider failures for actionable frontend rendering.
