# ADR-001: PostgreSQL as Single Source of Truth

## Status

Accepted

## Context

AICT runs multiple concurrent AI agents that maintain state across sessions (memory, messages, task progress, session history). The system runs on Cloud Run, where containers can restart at any time. We need a state management strategy that survives restarts, supports concurrent access from multiple agent workers, and avoids split-brain scenarios.

Common approaches in multi-agent systems:
1. **In-memory state + checkpointing** — fast but lost on crash, requires complex recovery
2. **LangGraph checkpointer for all loops** — ties execution state to the orchestration framework
3. **External database as sole state store** — slower writes but crash-safe, simple recovery model
4. **Hybrid** (Redis for hot state, PostgreSQL for cold) — adds operational complexity

LangGraph was initially used for the Manager-CTO consultation flow and includes a `PostgresSaver` checkpointer. Extending this to all agent loops was considered.

## Decision

**PostgreSQL is the single source of truth for all state.** No in-memory state persistence, no LangGraph checkpointer for the inner loop, no Redis, no message queues.

All agent state, memory, messages, sessions, and task data is written to PostgreSQL immediately. The inner loop (`run_inner_loop`) reads from and writes to the database on every iteration. Recovery after a crash is simple: reload agents from DB, replay undelivered messages.

LangGraph's checkpointer is retained only for the Manager-CTO consultation graph (a secondary code path), not for the primary inner loop.

## Consequences

**Positive:**
- Crash recovery is trivial — restart, read DB, continue. No state reconstruction logic needed.
- The Reconciler can fix any drift by querying the database directly.
- No operational burden of Redis or message queues. One database to back up and monitor.
- Concurrent workers cannot conflict because all writes go through SQLAlchemy with proper transactions.
- Complete audit trail — every message, tool call, and session is persisted.

**Negative:**
- Higher write latency compared to in-memory state (mitigated by async SQLAlchemy + asyncpg).
- More database load — every LLM response and tool result triggers a write.
- LangGraph checkpointer for the Manager-CTO graph is an inconsistency that should eventually be removed.

**Risks:**
- Database becomes the bottleneck at high agent counts. Mitigated by connection pooling and the fact that LLM calls (not DB writes) are the actual bottleneck.
