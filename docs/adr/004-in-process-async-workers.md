# ADR-004: In-Process Async Workers

## Status

Accepted

## Context

Each AI agent needs a persistent runtime that blocks until a message arrives, then runs the inner loop. The question is how to host these runtimes.

Options considered:
1. **Separate processes per agent** (e.g., Celery workers, separate containers) — strong isolation, complex coordination, high resource overhead.
2. **Thread pool** — one thread per agent. Simpler than processes but GIL contention with CPU-bound LLM post-processing.
3. **Asyncio tasks within the FastAPI process** — all agents share one event loop. Lightest resource usage, simplest coordination, but no isolation.

Key factors:
- Agent work is I/O-bound (LLM API calls, DB queries, sandbox HTTP calls). CPU-bound work is minimal.
- Agents need to communicate via in-process queues (`MessageRouter`). Cross-process messaging would require Redis or a message broker.
- Cloud Run provides a single container. Running multiple processes inside complicates health checks and lifecycle management.

## Decision

**All agent workers run as `asyncio.Task` objects within the FastAPI uvicorn event loop.** The `WorkerManager` spawns one `asyncio.create_task()` per agent. Workers block on `await queue.get()` (zero CPU cost when sleeping) and share the event loop with API request handlers and the WebSocket server.

`MessageRouter` is a simple `dict[UUID, asyncio.Queue]` — in-process, no serialization, no network hops.

## Consequences

**Positive:**
- Zero overhead for sleeping agents (awaiting on a queue is essentially free).
- `MessageRouter.notify()` is a synchronous `put_nowait()` — instant, no network, no serialization.
- One process to deploy, monitor, and health-check on Cloud Run.
- Shared DB connection pool across all workers — efficient resource usage.
- Worker respawn is trivial: `asyncio.create_task()` again.

**Negative:**
- No isolation: a segfault or infinite loop in one agent's tool execution could affect all agents. Mitigated by: async tools never block the event loop; sandbox commands execute in separate containers; the Reconciler detects stuck agents.
- Cannot scale beyond one machine's capacity. All agents run in one process. Acceptable for current scale (tens of agents, not thousands).
- A misbehaving agent that consumes excessive memory affects all agents in the process.

**Future consideration:**
- If scale requires it, workers could be moved to separate processes with Redis-backed MessageRouter. The interface (`register`, `notify`, `unregister`) is designed to be swappable.
