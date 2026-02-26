# ADR-003: Channel Messages as Unified Communication

## Status

Accepted

## Context

AICT agents need to communicate with each other and with the user. Early iterations had multiple communication mechanisms:
- `chat_messages` for user-GM conversation
- `tickets` and `ticket_messages` for task-related discussions
- Separate WebSocket event types for each

This led to:
- Multiple code paths for sending and receiving messages
- Confusion about which system to use for which purpose
- Duplicate notification logic

The user is represented by a special constant UUID (`00000000-0000-0000-0000-000000000000`), not a row in the `agents` table.

## Decision

**All communication flows through the `channel_messages` table.** There is one table, one `MessageService`, one `MessageRouter`, and one delivery flow.

- Agent-to-agent, agent-to-user, user-to-agent, and broadcasts all use the same table and API.
- The user is identified by `USER_AGENT_ID` (reserved UUID). Messages targeting the user are delivered via WebSocket push instead of agent queue notification.
- Message types (`normal`, `system`) and the `broadcast` flag differentiate behavior without separate tables.
- Legacy tables (`chat_messages`, `tickets`, `ticket_messages`) were dropped in migration 006.

## Consequences

**Positive:**
- One protocol to understand and maintain. New agents automatically participate in the messaging system.
- The `MessageRouter` has a single code path: `notify(target_agent_id)`.
- The Reconciler has a single query for stuck messages.
- Frontend has one API surface for all conversations (`/api/v1/messages/*`).
- Adding a new communication pattern (e.g., agent-to-agent-group) requires only new query filters, not new tables.

**Negative:**
- The `channel_messages` table grows quickly — every message in the system lands here. Requires archival strategy at scale.
- `from_agent_id` and `target_agent_id` cannot be foreign keys to `agents.id` because the user UUID is not in the `agents` table. This sacrifices referential integrity for protocol simplicity.
- No built-in threading or conversation grouping. Messages are a flat timeline per project. Agents use their memory and context to maintain conversational continuity.
