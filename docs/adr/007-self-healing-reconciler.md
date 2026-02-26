# ADR-007: Self-Healing Reconciler

## Status

Accepted

## Context

AICT runs long-lived background tasks (AgentWorkers) inside a Cloud Run container that can restart at any time. Several failure modes can leave the system in an inconsistent state:

1. **Container crash mid-session** — agent stuck in `active` status, session stuck in `running`, messages stuck in `sent`.
2. **Worker task crashes** — the `finally` block in `AgentWorker.run()` resets the agent to `sleeping`, but the session row may not be closed.
3. **Message notification dropped** — `MessageRouter.notify()` fires before the worker's queue is registered.
4. **Agent created without a worker** — race condition during startup or agent spawn.

Without automatic recovery, these require manual intervention (resetting database rows, restarting the container).

Options:
1. **Manual recovery** — operator watches logs, fixes stuck state. Unacceptable for a solo-developer project.
2. **Transactional guarantees only** — use DB transactions to prevent inconsistency. Insufficient because the inconsistency is between DB state and in-process state (asyncio tasks).
3. **Periodic reconciliation loop** — a background task that detects and fixes drift. Adds complexity but eliminates manual intervention.

## Decision

**A Reconciler background task runs every 30 seconds and corrects four categories of drift:**

| Category | Detection | Fix |
|----------|-----------|-----|
| Orphan agents | Agent in DB, no registered worker | Spawn worker |
| Stuck active | Agent status `active` > 10 min, no running session | Reset to `sleeping`, force-end session |
| Orphaned sessions | Session `running`, agent `sleeping` | Force-end session (`reconciler_orphaned`) |
| Stuck messages | Message `sent` > 60s | Re-fire `router.notify()` |

Each category is wrapped in its own `try/except` so a failure in one does not prevent the others from running. The reconciler never creates new state — it only corrects existing state toward the expected steady state.

## Consequences

**Positive:**
- The system self-heals without manual intervention. Container restarts, worker crashes, and race conditions are automatically resolved.
- The operator can trust that the system converges to a healthy state within 30 seconds of any failure.
- The reconciler serves as documentation of all known failure modes — reading the reconciler code reveals every inconsistency the system can produce.

**Negative:**
- 30-second detection delay — an agent can be stuck for up to 30 seconds before the reconciler notices.
- The reconciler queries the database every 30 seconds, adding minor load. Acceptable because the queries are lightweight (indexed columns, small result sets).
- Risk of reconciler creating cascading fixes — e.g., resetting an agent to sleeping causes the reconciler on the next pass to see an orphaned session, which it also fixes. This is correct behavior but can produce multiple log entries for a single root cause.

**Thresholds (hardcoded, not env-configurable):**
- Reconcile interval: 30s
- Stuck active threshold: 600s (10 min)
- Stuck message threshold: 60s
- Stuck messages per pass cap: 50
