# Backend docs-first gap checklist

Source: `docs/backend/backend&API.md`, `docs/db.md`. Locked deprecation targets and missing contracts.

## Change report (implementation complete)

- **Deprecation:** Removed `api/v1/engineers.py`, `api/v1/tickets.py`, `api/v1/jobs.py`, `api_internal/tickets.py`, `tools/tickets.py`, `services/ticket_service.py`, `services/engineer_graph_service.py`, `services/engineer_worker.py`, `schemas/ticket.py`, `schemas/job.py`. Dropped engineers router; registry no longer uses tickets, dispatch_to_engineer, or file tools for engineers.
- **WebSocket:** Channels aligned to docs: `agent_stream`, `messages`, `kanban`, `agents`, `activity`, `workflow`, `all`. Added event types and factories: `agent_text`, `agent_tool_call`, `agent_tool_result`, `agent_message`. Removed job/ticket event types and broadcast methods.
- **New endpoints:** `GET/POST /api/v1/sessions`, `GET /api/v1/sessions/{id}`, `GET /api/v1/sessions/{id}/messages`; `GET/PATCH /api/v1/repositories/{id}/settings`; `GET /api/v1/agents/{id}/memory`, `POST /api/v1/agents/{id}/interrupt`, `POST /api/v1/agents/{id}/wake`. Pending message count wired in agent status from channel_messages (status=sent).
- **Tests:** Deprecated ticket/job tests skipped or updated; websocket tests use new channels; agent status test uses `pending_message_count` and message_service; sessions and repository settings contract tests added.
- **Remaining risks:** Internal API path contract (docs use `/send-message`, `/broadcast`, etc.; current uses `/messaging/send`, `/messaging/broadcast`). Optional: add `read-messages`, `mark-received` internal endpoints. Frontend may need to switch WebSocket channels from `chat` to `agent_stream`/`messages`/`agents`.

## Deprecation target list (locked)

### Public API (`api/v1`)
| Target | Action | Replacement / notes |
|--------|--------|---------------------|
| `api/v1/engineers.py` | Remove router include + delete file | Merged into `api/v1/agents.py` (spawn_engineer already in agents) |
| `api/v1/jobs.py` | Delete file | Replaced by `api/v1/sessions.py` (to add) |
| `api/v1/tickets.py` | Delete file | Dropped; messaging replaces tickets |

### Internal API (`api_internal`)
| Target | Action | Replacement / notes |
|--------|--------|---------------------|
| `api_internal/tickets.py` | Delete file | Dropped; use messaging |
| `api_internal/files.py` | Remove or replace | Docs: `api_internal/sandbox.py` for execute_command |

### Services
| Target | Action | Replacement / notes |
|--------|--------|---------------------|
| `services/ticket_service.py` | Delete after API/tools removed | Dropped |
| `services/engineer_worker.py` | Delete | Replaced by `workers/agent_worker.py` |
| `services/engineer_graph_service.py` | Delete or stub | Dropped (no graph execution) |

### Tools
| Target | Action | Replacement / notes |
|--------|--------|---------------------|
| `tools/tickets.py` | Remove from registry + delete | Dropped |
| `tools/files.py` | Remove from registry + delete | File ops via execute_command |
| `tools/agents.py` | Refactor to `tools/management.py` | spawn_engineer, list_agents, interrupt_agent (no dispatch_to_engineer, no tickets) |
| `tools/e2b.py`, `tools/e2b_tool.py` | Replace with `tools/sandbox.py` | Per docs (keep e2b if sandbox.py wraps it) |

### Schemas
| Target | Action | Replacement / notes |
|--------|--------|---------------------|
| `schemas/ticket.py` | Delete after no references | Dropped |
| `schemas/job.py` | Delete after no references | Replaced by `schemas/session.py` |

### WebSocket
| Target | Action | Replacement / notes |
|--------|--------|---------------------|
| Channel `chat` | Rename/repurpose | Docs: `agent_stream`, `messages` channels |
| Events `gm_status`, `chat_message`, `job_*`, `ticket_*` | Add docs events; deprecate legacy | Docs: `agent_text`, `agent_tool_call`, `agent_tool_result`, `agent_message` |

---

## Missing or incomplete (docs contract)

### Public API
- [ ] `GET/POST /api/v1/sessions` (list, get, get messages) — not implemented
- [ ] `GET/PATCH /api/v1/repositories/{id}/settings` — not implemented
- [ ] `GET /api/v1/agents/{id}/memory` — not implemented
- [ ] `POST /api/v1/agents/{id}/interrupt` — not implemented
- [ ] `POST /api/v1/agents/{id}/wake` — not implemented
- [ ] `pending_message_count` in agent status — currently 0 placeholder

### Internal API (path contract)
- [ ] Docs: `POST /internal/agent/send-message` — current: `POST /internal/agent/messaging/send`
- [ ] Docs: `POST /internal/agent/broadcast` — current: `POST /internal/agent/messaging/broadcast`
- [ ] Docs: `GET /internal/agent/read-messages` — not implemented
- [ ] Docs: `POST /internal/agent/mark-received` — not implemented
- [ ] Docs: `POST /internal/agent/interrupt` — current: lifecycle has wake/sleep/restart only
- [ ] Docs: `POST /internal/agent/execute` (sandbox) — not under internal (files exist)

### WebSocket
- [ ] Channels: `agent_stream`, `messages` (docs) vs current `chat`, `kanban`, `workflow`, `activity`
- [ ] Event types: `agent_text`, `agent_tool_call`, `agent_tool_result`, `agent_message`

---

## Reference: docs “Files to drop”

- `api/v1/chat.py` → already removed
- `api/v1/tickets.py` → drop
- `api/v1/engineers.py` → drop (merge into agents)
- `api/v1/jobs.py` → drop (sessions replace)
- `api_internal/tickets.py` → drop
- `services/chat_service.py` → already removed
- `services/ticket_service.py` → drop
- `services/engineer_worker.py` → drop
- `services/engineer_graph_service.py` → drop
- `tools/tickets.py` → drop
- `schemas/chat.py` → already removed
- `schemas/ticket.py` → drop
- `schemas/job.py` → drop
