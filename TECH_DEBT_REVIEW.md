# AICT Technical Debt Review

**Date:** March 6, 2026
**Scope:** Full-stack review — backend (Python/FastAPI), frontend (React/TypeScript), infrastructure
**Codebase:** ~20k LOC backend, ~14k LOC frontend, 96 component files, 15+ DB models

---

## Critical Findings (Fix Immediately)

### 1. SSL Certificate Verification Disabled

**File:** `backend/db/session.py:18-24`

```python
ctx = _ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = _ssl.CERT_NONE
```

When `db_ssl_mode == "require"`, the code creates an SSL context but immediately disables all certificate verification. This makes the database connection vulnerable to man-in-the-middle attacks even with SSL enabled. `verify_mode` should be `CERT_REQUIRED` and `check_hostname` should be `True`, with a proper CA certificate configured.

### 2. Hardcoded Credentials in Source

**File:** `backend/config.py:62-67`

```python
test_login_email: str = "aicttest@aict.com"
test_login_password: str = "f8a9sfa32!@#%Daf342q98v!%#@dscx90"
```

Test credentials are committed to source. The comment says "safe to keep" but this violates the principle of least surprise — any credential in source is one leaked repo away from exploitation. Move to environment-only configuration with an `.env.example` placeholder.

### 3. Placeholder API Token in Source

**File:** `backend/config.py:20`

```python
api_token: str = "change-me-in-production"
```

A literal placeholder string as the default. No startup validation prevents deployment with this value. If a production `.env` file is misconfigured, the app silently runs with a guessable token.

### 4. Weak Encryption Key Derivation

**File:** `backend/db/repositories/project_secrets.py:36`

```python
b = k.encode("utf-8")[:32].ljust(32, b"\0")
```

When a raw key is provided (not base64-encoded), it's truncated/padded with null bytes. This is not a proper key derivation function — it reduces entropy and creates predictable keys. Use PBKDF2, scrypt, or Argon2 for key derivation.

### 5. Unencrypted GitHub Tokens

**File:** `backend/db/models.py:48`

```python
github_token = Column(String(512), nullable=True)
```

GitHub tokens stored as plaintext strings in the database. Unlike `ProjectSecret` (which at least attempts encryption), user GitHub tokens get zero protection at rest. Anyone with database read access gets all GitHub tokens.

---

## High Severity (Address This Sprint)

### 6. No Startup Validation for Required Config

**File:** `backend/config.py`

Multiple critical settings default to empty strings (`claude_api_key`, `firebase_credentials_path`, `github_token`, `sandbox_vm_host`). The app starts successfully with missing values and only fails at runtime when those services are first called. Add a startup validator that checks required keys and fails fast.

### 7. N+1 Query Patterns

**File:** `backend/api/v1/agents.py` — `list_agent_status` fetches all agents, then issues a separate query for pending message counts per agent.
**File:** `backend/api/v1/sandboxes.py` — `list_sandboxes` fetches agents, then queries sandbox configs separately.

Both should use a single query with JOIN and aggregation. As the number of agents grows, these become linear-time database round trips.

### 8. Broad Exception Silencing

Multiple files catch `Exception` and do nothing:

- `backend/api/v1/sandboxes.py:94` — silently ignores pool manager errors
- `backend/websocket/endpoint.py:94-95` — `WebSocketDisconnect` caught with bare `pass`, no logging
- Several services use `except Exception: pass` patterns

These make production debugging extremely difficult. At minimum, log at `warning` level with the exception details.

### 9. Missing Input Validation

- `TaskCreate.title` — no max length constraint (can store arbitrarily long strings)
- `ChannelMessageSend.content` — only `min_length=1`, no upper bound
- `code_repo_url` — accepted as-is without URL format validation
- `message_type` — accepts any string instead of a validated enum

Without limits, these are vectors for database bloat, OOM, or injection.

### 10. No React Error Boundary

**File:** `frontend/src/App.tsx`

The app has no `ErrorBoundary` component. An unhandled exception in any component propagates up and crashes the entire app. Add a top-level error boundary that shows a recovery UI instead of a white screen.

### 11. 53+ `any`/`unknown` Type Casts in Frontend

Throughout the frontend, `any` and `unknown` casts bypass TypeScript's type system. Notable examples:

- `AgentStreamContext.tsx:166` — WebSocket event data cast to `Record<string, unknown>`
- `client.ts:809` — JSON response cast inline
- Tool input data piped through as `Record<string, unknown>` without validation

This defeats the purpose of using TypeScript and hides bugs that would otherwise be caught at compile time.

---

## Medium Severity (Address Next 2-4 Weeks)

### 12. Circular Dependency Workarounds

Multiple files use lazy imports inside functions to avoid circular imports:

- `task_service.py` lazily imports `OrchestratorService`
- `agents/agent.py` lazily imports `get_tool_defs_for_role`
- `messages.py` lazily imports `get_message_router`

Lazy imports with side effects (especially as `@property`) are an anti-pattern. They indicate tight coupling between modules. Consider introducing a dependency injection container or restructuring the module graph.

### 13. Duplicated Authorization Logic

The pattern of "fetch entity → check if exists → verify project access" is repeated verbatim in `agents.py`, `tasks.py`, and `sandboxes.py`. Extract a shared `ensure_entity_access(db, entity_type, entity_id, user_id)` utility.

### 14. Dual WebSocket Clients Without Unified Status

**File:** `frontend/src/contexts/AgentStreamContext.tsx:78-79`

The frontend maintains two independent WebSocket connections (`primaryClientRef` for agent events, `backendLogClientRef` for logs). Each has its own reconnection logic. If one fails silently, users have no indication. Merge into a single multiplexed connection or add unified connection health UI.

### 15. Missing Database Indexes

`ChannelMessage` is queried frequently by `target_agent_id` and `from_agent_id`. `Task` is queried by `assigned_agent_id` and `status`. None of these columns have explicit indexes in the model definitions. As data grows, these become full table scans.

### 16. Memory Leak Vectors

**Backend:** `main.py:32` — `_background_tasks` list only cleared on graceful shutdown; crashed/respawned tasks accumulate.
**Backend:** Rate limiting store (`test_login.py:27`) uses `defaultdict(deque)` keyed by IP; never purged, grows with unique IPs.
**Frontend:** `AgentStreamContext` buffers up to 500 chunks, 400 activity items, 500 usage events, but never clears when switching sessions.

### 17. Inconsistent Error Handling Patterns

Backend mixes `HTTPException` with hardcoded status codes (e.g., `404`) and imported constants (`status.HTTP_404_NOT_FOUND`). Error response shapes differ between global exception handlers and route-level handlers. Standardize on one pattern.

### 18. No Dependency Lock File

**File:** `backend/requirements.txt`

Dependencies use loose version ranges (`>=0.109.0,<1.0.0`). No lock file (`pip freeze` output or `poetry.lock`) is committed. Different environments may install different patch versions, causing unreproducible bugs. Pin exact versions or adopt a lock-file-based tool.

### 19. `settings` Imported Globally Everywhere

`from backend.config import settings` appears in 20+ files as a module-level import. This global singleton makes unit testing painful (requires monkeypatching the import) and hides dependencies. Consider passing settings explicitly or using FastAPI's dependency injection.

### 20. Frontend Missing List Virtualization

`ActivityFeed.tsx` renders up to 400 items without virtualization. `MessageList.tsx` has no windowing for large message histories. Both can create thousands of DOM nodes, degrading scroll performance. Use `react-window` or `react-virtuoso`.

---

## Low Severity (Backlog)

### 21. Hardcoded Magic Numbers

Timeouts, buffer sizes, and retry counts are scattered as module-level constants across many files (`_MAX_ATTEMPTS = 30`, `_RECONNECT_DELAY_S = 5`, `MAX_CHUNKS = 500`, etc.). Consolidate into a shared constants module or make configurable.

### 22. `USER_AGENT_ID` Duplicated

The sentinel UUID `00000000-0000-0000-0000-000000000000` is defined independently in both `useMessages.ts` and `MessageList.tsx`. Extract to a single constant in the types module.

### 23. God Components

- `AgentStreamContext.tsx` (470 lines) — manages two WebSocket clients, buffering, event dispatch
- `PromptBuilderPage.tsx` (416 lines) — 10+ `useState` hooks
- `Workspace.tsx` (272 lines) — resizable panes, agent selection, tab management

Break these into smaller, focused components/hooks.

### 24. Inconsistent Logging

Some places use `logger.exception()` (which includes the traceback), others use `logger.error()` with manual string formatting. No correlation IDs for tracing requests across services. Establish a logging standard and enforce it.

### 25. Frontend Accessibility Gaps

- Icon-only buttons without `aria-label`
- Color-only role indicators (`ROLE_COLOR` in `MessageList.tsx`)
- Modal focus management not implemented
- No WCAG color-contrast validation on the agent role palette

### 26. LLM Model Pricing Hardcoded

**File:** `backend/config.py:111-140`

Pricing data for 15+ models is hardcoded in the settings file. No versioning, no audit trail, no ability for admins to update without a code deploy. Consider moving to database or a configurable JSON file.

### 27. No Rate Limiting on Public API

Rate limiting exists only on the test-login endpoint (`test_login.py`), using an in-memory dict that doesn't work across multiple containers. The public REST API has no rate limiting at all.

### 28. Missing Test Coverage

- ~18% of frontend components have corresponding test files (9 test files vs 51 components)
- Database repository classes have no visible test coverage
- No integration tests for the full request→service→DB path
- No load testing to catch N+1 queries or performance regressions

---

## Architecture Observations

**What's working well:**

- Clean separation between API, services, repositories, and models
- Provider-agnostic LLM layer with multi-provider support
- Well-documented architecture decisions (10 ADRs)
- Universal agent execution loop — avoids role-specific code duplication
- Self-healing reconciler for state consistency

**What needs attention:**

- The module dependency graph has cycles (evidenced by 3+ circular import workarounds)
- The global `settings` singleton creates implicit coupling everywhere
- Transaction boundaries are implicit (auto-commit on endpoint success), which is fragile for multi-step operations
- The dual frontend WebSocket approach adds complexity without clear benefit over a single multiplexed connection
- No circuit breaker or retry logic for LLM provider failures beyond basic fallback

---

## Recommended Priority Order

| Phase | Items | Effort | Impact |
|-------|-------|--------|--------|
| **Immediate** | #1 SSL fix, #2-3 credentials, #4-5 encryption | 1-2 days | Security |
| **This sprint** | #6 startup validation, #7 N+1, #8-9 validation, #10 error boundary | 3-5 days | Reliability |
| **Next sprint** | #12-13 refactoring, #14-15 WebSocket + indexes, #16-17 memory/error cleanup | 1-2 weeks | Maintainability |
| **Backlog** | #18-28 linting, testing, accessibility, observability | Ongoing | Quality |
