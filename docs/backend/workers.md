# Worker System

The worker system is the runtime that keeps agents alive, routes messages between them, and self-heals when components fail. It consists of four components that run as asyncio tasks within the FastAPI process.

## Components

| Component | Module | Role |
|-----------|--------|------|
| `WorkerManager` | `backend/workers/worker_manager.py` | Startup orchestrator, agent lifecycle |
| `AgentWorker` | `backend/workers/agent_worker.py` | Per-agent outer loop |
| `MessageRouter` | `backend/workers/message_router.py` | In-process wake-up notification bus |
| `Reconciler` | `backend/workers/reconciler.py` | Background self-healing task |

---

## WorkerManager

`WorkerManager` is a singleton (module-level `_worker_manager` variable, accessed via `get_worker_manager()`). It manages the full lifecycle of all `AgentWorker` asyncio tasks.

### Startup (`start()`)

```
1. Load all Agent rows from DB
2. For each agent: spawn_tracked_worker(agent_id, project_id)
   → Creates AgentWorker, wraps it in asyncio.create_task()
   → Registers done_callback for auto-respawn
3. Wait up to 5s per worker for queue registration (wait_ready)
4. Log "WorkerManager: N agent workers ready"
5. Load undelivered channel_messages (status="sent")
6. router.replay(undelivered) → notify each target agent's queue
7. Set _started = True
```

The startup is intentionally ordered: workers are spawned and their queues registered **before** the replay step. Previously, replay fired before any worker started, causing every undelivered notification to be silently dropped.

### Worker respawn

Each worker task has a `_on_worker_done` callback attached. When a task exits (cancelled, exception, or unexpected return), the callback:
1. Removes the task from internal tracking
2. Checks if this is a planned shutdown or a planned removal (`_removing` set)
3. If not planned: logs a warning and immediately `asyncio.create_task(_spawn_tracked_worker(...))`

This means workers are **immortal** — they always respawn unless explicitly stopped.

### Shutdown (`stop()`)

```
1. Set _shutting_down = True (suppresses respawn in done_callback)
2. Cancel all worker tasks, await their completion
3. Clear all internal tracking structures
4. reset_message_router() — clear the router singleton
```

### Key methods

| Method | Description |
|--------|-------------|
| `start()` | Full startup: load agents, spawn workers, replay messages |
| `stop()` | Cancel all workers, reset router |
| `spawn_worker(agent_id, project_id)` | Spawn a new worker at runtime (e.g., new engineer), wait until ready |
| `remove_worker(agent_id)` | Permanently stop a worker (prevent respawn), deregister queue |
| `interrupt_agent(agent_id)` | Signal a worker to break its inner loop at next iteration |
| `ensure_workers_for_all_agents()` | Spawn workers for any agent in DB with no registered worker (used by Reconciler) |
| `get_status()` | Return serializable dict: `{started, shutting_down, worker_count, agent_ids}` |

### State tracking

```python
_tasks: list[asyncio.Task]              # All worker asyncio tasks
_workers: list[AgentWorker]             # All AgentWorker instances
_task_meta: dict[Task, (UUID, UUID)]    # Task → (agent_id, project_id)
_removing: set[UUID]                    # Agent IDs being permanently removed
_shutting_down: bool                    # Global shutdown flag
_started: bool                          # True after start() completes
```

---

## AgentWorker

One `AgentWorker` per agent. It holds the agent's notification queue and owns the outer loop.

### Key attributes

```python
agent_id: UUID
project_id: UUID
_queue: asyncio.Queue       # Wake-up notification queue (sentinels only)
_interrupt: bool            # Flag set by WorkerManager.interrupt_agent()
_ready: asyncio.Event       # Set after queue is registered with MessageRouter
```

### Outer loop (`run()`)

```python
router.register(self.agent_id, self._queue)
self._ready.set()

while True:
    await self._queue.get()           # Block until woken
    self._interrupt = False
    
    async with AsyncSessionLocal() as db:
        agent = load_agent_from_db()
        project = load_project_from_db()
        
        agent.status = "active"
        await db.flush()
        
        sess = await session_service.create_session(agent.id, project.id)
        
        try:
            end_reason = await run_inner_loop(
                agent, project, sess.id, ..., interrupt_flag=self._interrupt_flag
            )
        except Exception:
            await session_service.end_session_error(sess.id)
            raise
        finally:
            agent.status = "sleeping"
            await db.commit()
```

The `finally` block guarantees the agent is always returned to `sleeping` status, regardless of how the loop ended (normal, error, or crash). This prevents agents from being stuck in `active` permanently after a crash — which the Reconciler would also catch, but the `finally` is the first line of defense.

### Interrupt mechanism

`interrupt()` sets `_interrupt = True`. The inner loop checks `interrupt_flag()` at the top of each iteration:

```python
if interrupt_flag():
    await session_service.end_session_force(session_id, "interrupted")
    return "interrupted"
```

The interrupt takes effect at the **next iteration boundary** — the current LLM call or tool execution finishes first. There is no mid-execution cancellation.

### Readiness handshake

`wait_ready(timeout=5.0)` blocks until `_ready` is set (i.e., the queue has been registered with `MessageRouter`). `WorkerManager.spawn_worker()` calls this after creating the task, ensuring the worker's queue is registered before any notifications are sent.

---

## MessageRouter

The `MessageRouter` is an in-process singleton (`get_message_router()`) that holds a `dict[UUID, asyncio.Queue]`. It is the notification layer between the service layer (which writes messages to the DB) and the worker layer (which reads from queues).

**It does not write to the database.** Database writes are handled by `MessageService`.

### API

| Method | Description |
|--------|-------------|
| `register(agent_id, queue)` | Store agent's wake-up queue |
| `unregister(agent_id)` | Remove agent's queue (called when worker stops) |
| `notify(agent_id)` | `queue.put_nowait(None)` — wake the agent |
| `replay(messages)` | For each message in list, call `notify(target_agent_id)` |

### Notify behavior

`notify()` uses `put_nowait()` which is non-blocking. If the queue is full, a warning is logged and the notification is dropped. The queue is unbounded by default (`asyncio.Queue()` with no `maxsize`), so this should not occur in practice.

If no queue is registered for an `agent_id`, a warning is logged: the worker may not have started yet. The Reconciler handles this case — it detects undelivered messages and re-fires `notify()`.

### Replay on startup

```python
async def replay(self, messages: list[ChannelMessage]) -> None:
    async with self._lock:
        for msg in messages:
            if msg.target_agent_id is not None:
                self.notify(msg.target_agent_id)
```

Called by `WorkerManager.start()` **after** all workers have registered their queues. This ensures agents process any messages that arrived while the server was down.

---

## Inner Loop (`run_inner_loop`)

The inner loop is in `backend/workers/loop.py`. It is the universal execution model for all agent roles. See `docs/ARCHITECTURE.md → Agent Execution Loop` for the high-level description. Below are the design choices.

### Context assembly

The loop uses `PromptAssembly` (see `docs/backend/prompt_system.md`) to manage all LLM-facing state. The loop creates one `PromptAssembly` at the start of a session and mutates it via `append_*` methods each iteration. The assembly maintains the system prompt (static for the session), message history (grows each iteration), and tool list (static for the session).

### History loading

At session start, `AgentMessageRepository.list_last_n_sessions()` loads up to the last 5 sessions of `agent_messages` rows for the current agent. This provides continuity across sessions without unbounded context growth. The `PromptAssembly.load_history()` method applies the character-based budget cap and repairs any dangling tool_use IDs from interrupted sessions.

### Unread message resolution

An agent wakes when `MessageRouter.notify()` pushes to its queue. At loop start, the loop reads unread channel messages:

```python
unread = await message_service.get_unread_for_agent(agent.id)
```

If there are no unread messages **and** no assignment context (i.e., no active assigned task in a non-terminal state), the session ends immediately with `normal_end`. This prevents empty loop spins. The assignment context check allows an engineer to wake up and re-examine its assigned task even without a new channel message.

### Tool dispatch

```python
handlers = get_handlers_for_role(agent.role)  # from loop_registry
...
handler = handlers.get(name)
result_text = await handler(ctx, tool_input)
```

Handlers are registered in `backend/tools/loop_registry.py` by role. The `RunContext` passed to each handler contains the DB session, agent, project, services, and WebSocket emit callbacks.

### WebSocket emission

The loop receives four emit callbacks from `AgentWorker.run()`:
- `emit_text(content)` — broadcast `agent_text` WebSocket event
- `emit_tool_call(name, tool_input)` — broadcast `agent_tool_call` event
- `emit_tool_result(name, output)` — broadcast `agent_tool_result` event
- `emit_agent_message(msg)` — broadcast `agent_message` event (when agent sends a message to user)

Each emit is wrapped in `asyncio.create_task(...)` so they run concurrently with the next iteration without blocking.

### Fallback messages

When the loop ends abnormally (`error`, `max_loopbacks`, `max_iterations`), it sends a fallback `channel_message` targeting `USER_AGENT_ID` via `_send_fallback_message()`. This ensures the user is never left with no response after a session failure.

---

## Reconciler

The Reconciler runs as a background task (`_run_reconciler_forever()` in `main.py`) and performs a pass every `RECONCILE_INTERVAL_SECONDS = 30` seconds.

### Pass 1: Orphan agents

```python
spawned = await wm.ensure_workers_for_all_agents()
```

Queries all agents from DB, compares with registered workers, spawns any missing workers. This handles agents created while the server was down or workers that failed to spawn during startup.

### Pass 2: Stuck active agents

Queries `agents` where `status = "active"`. For each:
- If no running session exists → reset to `sleeping`
- If running session exists but `started_at` > `STUCK_ACTIVE_THRESHOLD_SECONDS = 600` ago → reset to `sleeping`, force-end the session with `end_reason = "reconciler_orphaned"`

This catches agents stuck in `active` after a crash that bypassed the `finally` block in `AgentWorker.run()`.

### Pass 3: Orphaned sessions

Queries `agent_sessions` where `status = "running"` and the agent's current status is `"sleeping"`. Force-ends all such sessions with `end_reason = "reconciler_orphaned"`.

This is complementary to Pass 2: Pass 2 fixes agents stuck in active, Pass 3 fixes sessions whose agent was already reset to sleeping (e.g., by a previous reconciler pass or the `finally` block) but whose session row was never closed.

### Pass 4: Stuck messages

```python
stuck = channel_messages where status="sent" AND target_agent_id IS NOT NULL
        AND created_at < now - STUCK_MESSAGE_THRESHOLD_SECONDS (60s)
```

For each stuck message, call `router.notify(target_agent_id)`. Capped at 50 messages per pass to prevent thundering herds.

This handles the case where a message was persisted to DB but the `MessageRouter.notify()` call was dropped (e.g., the worker wasn't registered yet during startup, or a `QueueFull` condition).

### Error isolation

Each reconciliation category is wrapped in its own `try/except`. A failure in one category does not prevent the others from running. All errors are logged at `WARNING` level.

---

## Concurrency Model

The entire worker system runs within a single Python asyncio event loop (uvicorn's event loop). Key concurrency properties:

- `AgentWorker` tasks are `asyncio.Task` objects — they share the event loop with FastAPI request handlers, WebSocket handlers, and the Reconciler
- All DB operations use async SQLAlchemy + asyncpg — they never block the event loop
- LLM calls use async providers — they never block the event loop
- Sandbox HTTP calls use `httpx.AsyncClient` — non-blocking
- `MessageRouter.notify()` uses `put_nowait()` — synchronous, non-blocking, safe to call from any coroutine

**No thread safety concerns** within the worker system because asyncio is single-threaded. The exception is the backend log stream broadcaster, which bridges a Python `logging.Handler` (which runs on arbitrary threads) to the asyncio event loop via a thread-safe queue.

---

## Configuration

| Setting | Env Var | Default | Description |
|---------|---------|---------|-------------|
| Worker startup retries | hardcoded | 3 | Max attempts before container crash |
| Worker startup retry delay | hardcoded | 5s | Delay between startup attempts |
| Worker startup timeout | hardcoded | 120s | Per-attempt timeout for `manager.start()` |
| Reconcile interval | hardcoded | 30s | How often the Reconciler runs |
| Stuck active threshold | hardcoded | 600s | How long before an "active" agent is declared stuck |
| Stuck message threshold | hardcoded | 60s | How long before a "sent" message is re-notified |
| Startup step timeout | `STARTUP_STEP_TIMEOUT_SECONDS` | varies | Timeout for soft-fail startup steps |
| Auto-run migrations | `AUTO_RUN_MIGRATIONS_ON_STARTUP` | `true` | Whether to run Alembic at startup |
| Provision repos on startup | `PROVISION_REPOS_ON_STARTUP` | `false` | Whether to provision repos at startup |
