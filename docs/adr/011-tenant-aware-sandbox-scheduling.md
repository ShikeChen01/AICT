# ADR-011: Tenant-Aware Sandbox Scheduling in the Pool Manager

**Status:** Proposed
**Date:** 2026-03-06
**Deciders:** Engineering team

## Context

### Current Architecture

The sandbox system has three layers:

```
Backend (Cloud Run)                    Sandbox VM
┌─────────────────────┐               ┌──────────────────────────────┐
│ SandboxService      │               │ Pool Manager (:9090)         │
│   └── PoolMgrClient │── HTTP REST ──▶   PoolState                  │
│                     │               │     _sandboxes: {id → State} │
│ SandboxClient (mux) │               │     _agent_map: {agent → id} │
│   └── _connections  │── WS/HTTP ───▶│                              │
│       {id → Conn}   │               │ Docker containers (≤35)      │
└─────────────────────┘               │   sandbox-{id} per agent     │
                                      └──────────────────────────────┘
```

The **backend** `SandboxClient` is a connection multiplexer keyed by `sandbox_id`. It routes shell commands and GUI operations from agents to the correct container. It has no concept of users, projects, or tenants — it is purely a connection registry.

The **pool manager** (`sandbox/pool_manager/`) manages Docker container lifecycle. Its `PoolState` maps `agent_id → sandbox_id`. Its scheduling logic is first-come-first-served:

1. Agent already assigned → return existing sandbox
2. Idle sandbox available → assign first idle
3. Capacity left → create new container
4. At capacity → 503

The pool manager also has **no concept of users, projects, or backend instances**. Every `session_start(agent_id)` is treated as an independent, equally-weighted request.

### The Problem

As AICT moves toward multi-user and eventually multi-tenant operation, this design creates three issues:

**1. Resource monopolization.** If User A has a project with 5 engineers, they consume 7 sandboxes (Manager + CTO + 5 Engineers). User B arrives and gets the remaining capacity. If User A's engineers are all idle but assigned (persistent CTO/Manager, ephemeral but in-session engineers), User B may hit a 503 even though half the VM is effectively idle.

**2. No user-level scheduling.** The pool manager sees 10 `agent_id` values; it has no way to know that 7 belong to User A and 3 to User B. It cannot enforce per-user quotas, prioritize new-user requests, or preempt low-priority sandboxes.

**3. Multi-backend readiness.** The architecture roadmap includes horizontal scaling of the backend (multiple Cloud Run instances). When multiple backends call the same pool manager, each backend's `SandboxClient` is an independent in-memory mux. The pool manager must be the single coordination point — but it currently has no metadata to coordinate across backends or users.

### Forces at Play

- **Single VM constraint.** The sandbox VM has finite CPU, memory, and Docker resources. MAX_CONTAINERS=35 is a hard ceiling based on the VM's capacity (256 MB per container × 35 ≈ 9 GB).
- **Commercial-grade fairness.** Paying users expect predictable sandbox availability. One user's burst workload should not starve another.
- **Backend is the trust boundary.** The backend authenticates users (Firebase) and owns project/agent relationships. The pool manager trusts the backend via `MASTER_TOKEN`. Any user metadata sent to the pool manager must originate from the backend.
- **Pool manager is stateful.** It already persists `PoolState` to JSON and reconciles against Docker on restart. Adding tenant metadata fits this model.

## Decision

**Add tenant-aware scheduling to the pool manager.**

The pool manager will track `tenant_id` (= user ID or organization ID) alongside `agent_id` for every sandbox. The backend sends `tenant_id` in `session_start` requests. The pool manager uses this to enforce per-tenant quotas and fair scheduling.

### Data Model Changes

#### `SandboxState` — new fields

```python
@dataclass
class SandboxState:
    # ... existing fields ...
    tenant_id: str | None = None       # User/org who owns this sandbox
    project_id: str | None = None      # Project context (for grouping)
    priority: int = 0                  # 0 = normal, -1 = low, 1 = high
```

#### `PoolState` — new index

```python
class PoolState:
    _sandboxes: dict[str, SandboxState]
    _agent_map: dict[str, str]         # existing
    _tenant_map: dict[str, set[str]]   # NEW: tenant_id → {sandbox_id, ...}

    def sandboxes_for_tenant(self, tenant_id: str) -> list[SandboxState]: ...
    def tenant_count(self, tenant_id: str) -> int: ...
```

#### `TenantQuota` — new scheduling policy

```python
@dataclass
class TenantQuota:
    max_sandboxes: int              # Hard limit per tenant (0 = use global)
    max_concurrent_active: int      # Max simultaneously active sandboxes
    burst_allowed: bool             # Can temporarily exceed max_sandboxes?
```

### API Changes

#### `POST /api/sandbox/session/start` — extended request body

```python
class SessionStartRequest(BaseModel):
    agent_id: str
    persistent: bool = False
    setup_script: str | None = None
    # NEW fields
    tenant_id: str | None = None    # Required in multi-tenant mode
    project_id: str | None = None   # Optional grouping metadata
```

#### New endpoint: `GET /api/tenants/{tenant_id}/sandboxes`

Returns all sandboxes for a tenant with usage statistics.

#### New endpoint: `GET /api/tenants/summary`

Returns per-tenant sandbox counts and resource usage (for operator dashboards).

### Scheduling Algorithm

Replace the current FCFS logic in `session_start` with a tenant-aware scheduler:

```
session_start(agent_id, tenant_id, ...):

  1. Already assigned → return existing (unchanged)

  2. Check tenant quota:
     tenant_current = pool.tenant_count(tenant_id)
     if tenant_current >= tenant_quota.max_sandboxes:
       → 429 Too Many Requests (not 503)

  3. Idle sandbox available → assign (prefer same-tenant idle sandbox)

  4. Capacity available → create new, assign

  5. At global capacity → attempt preemption:
     a. Find idle sandbox from tenant with most idle sandboxes
     b. If found → reclaim (mark resetting), create new for requesting tenant
     c. If not → 503 Service Unavailable
```

The key change is step 2 (per-tenant quota check) and step 5 (fair preemption).

### Backend Changes

#### `PoolManagerClient.session_start()` — pass tenant context

```python
async def session_start(self, agent_id: str, persistent: bool = False,
                        setup_script: str | None = None,
                        tenant_id: str | None = None,
                        project_id: str | None = None) -> dict:
```

#### `SandboxService.ensure_running_sandbox()` — extract tenant context

```python
async def ensure_running_sandbox(self, session, agent, *, persistent=None):
    # ... existing logic ...
    # NEW: resolve tenant_id from agent → project → owner
    project = await self._get_project(session, agent)
    tenant_id = str(project.owner_id) if project else None

    data = await self._pool.session_start(
        agent_id,
        persistent=is_persistent,
        setup_script=setup_script,
        tenant_id=tenant_id,           # NEW
        project_id=str(agent.project_id),  # NEW
    )
```

### Configuration

```python
# config.py — pool manager
TENANT_MODE: str = os.getenv("TENANT_MODE", "off")  # "off" | "quota" | "fair"
DEFAULT_TENANT_MAX_SANDBOXES: int = int(os.getenv("DEFAULT_TENANT_MAX_SANDBOXES", "10"))
DEFAULT_TENANT_MAX_CONCURRENT: int = int(os.getenv("DEFAULT_TENANT_MAX_CONCURRENT", "5"))
PREEMPTION_ENABLED: bool = os.getenv("PREEMPTION_ENABLED", "false").lower() == "true"
```

**Three modes:**
- `off` — Current behavior. `tenant_id` is stored but not enforced. Zero-risk migration.
- `quota` — Per-tenant limits enforced. No preemption. Simplest production mode.
- `fair` — Per-tenant limits + idle preemption for fair sharing. Full multi-tenant.

## Options Considered

### Option A: Tenant-aware pool manager (this decision)

| Dimension | Assessment |
|-----------|------------|
| Complexity | Medium — adds ~200 LOC to pool manager, minor backend changes |
| Risk | Low — `TENANT_MODE=off` is backward-compatible |
| Scalability | Good — works with multiple backends pointing at same VM |
| Multi-backend ready | Yes — pool manager is the single coordinator |
| Fairness | Strong — per-tenant quotas + optional preemption |

**Pros:**
- Single coordination point on the VM — works regardless of how many backends connect
- Backward-compatible via `TENANT_MODE=off`
- Clean separation: backend resolves tenant identity, pool manager enforces quotas
- Observable: new `/api/tenants/summary` gives operators per-user visibility

**Cons:**
- Pool manager takes on scheduling complexity it didn't have before
- `tenant_id` must be passed on every `session_start` — if a backend omits it, the sandbox is "untenanted" (falls back to global limits only)
- Preemption (step 5) can cause sandbox churn if many tenants are competing

### Option B: Backend-side user-aware mux

| Dimension | Assessment |
|-----------|------------|
| Complexity | Low — changes only in backend `SandboxService` |
| Risk | Low — no pool manager changes |
| Scalability | Poor — each backend mux is independent; no coordination across instances |
| Multi-backend ready | No — requires shared state (Redis/DB) to coordinate |
| Fairness | Weak — can only limit within one backend process |

**Pros:**
- No changes to the pool manager
- Backend already knows user identity

**Cons:**
- Breaks immediately with multiple backend instances (each has its own `SandboxClient` singleton with no shared state)
- Pool manager still does FCFS — a misbehaving backend can still monopolize the VM
- Requires adding Redis or DB-backed coordination to the backend, violating ADR-001's "PostgreSQL is the sole state store" principle for what is essentially a VM-local scheduling concern

### Option C: Separate scheduling proxy between backend and pool manager

| Dimension | Assessment |
|-----------|------------|
| Complexity | High — new service to build, deploy, and monitor |
| Risk | Medium — new failure point in the critical path |
| Scalability | Excellent — can scale independently |
| Multi-backend ready | Yes — proxy is the coordinator |
| Fairness | Strong — full control over scheduling |

**Pros:**
- Clean separation of concerns
- Could handle cross-VM scheduling in the future

**Cons:**
- New service to maintain (ops burden for a small team)
- Added latency on every sandbox operation
- Overkill for the current single-VM topology

## Trade-off Analysis

The core trade-off is **where scheduling intelligence lives**:

- **Option A** puts it in the pool manager. This is natural because the pool manager already owns the container lifecycle and is the single point of coordination even when backends scale horizontally. The added complexity (~200 LOC) is modest.

- **Option B** keeps the pool manager simple but sacrifices multi-backend coordination. It would require rework when horizontal scaling arrives.

- **Option C** is architecturally clean but introduces operational overhead that doesn't justify itself for a single-VM deployment.

Option A is the right balance for commercial-grade fairness with minimal architectural disruption. The `TENANT_MODE=off` default means zero risk to existing behavior.

## Consequences

### What becomes easier

- **Per-user sandbox quotas** — operators can limit how many sandboxes any one user consumes, preventing monopolization.
- **Multi-backend scaling** — when the backend moves to multiple Cloud Run instances, the pool manager already understands tenants. No rework needed.
- **Operator visibility** — `/api/tenants/summary` gives a per-user resource breakdown that doesn't exist today.
- **Fair scheduling** — in `fair` mode, idle sandbox preemption ensures that capacity is shared equitably.

### What becomes harder

- **Pool manager is no longer "dumb"** — it now has scheduling policy, which means more config, more testing, more edge cases.
- **Backward compatibility** — backends that don't send `tenant_id` get "untenanted" sandboxes that bypass quota checks. Must ensure all backends are updated together.

### What we'll need to revisit

- **Preemption policy** — the "reclaim from tenant with most idle sandboxes" heuristic may need tuning based on real usage patterns.
- **Cross-VM scheduling** — if AICT grows to multiple sandbox VMs, tenant quotas need to be global (aggregated across VMs). This ADR only covers the single-VM case.
- **Billing integration** — tenant-level sandbox usage data is a prerequisite for per-user billing.

## Migration Path

1. **Phase 1 — Data model only (`TENANT_MODE=off`).** Add `tenant_id` and `project_id` fields to `SandboxState`. Backend sends them on `session_start`. Pool manager stores them but does not enforce. Zero behavior change. Ship and observe.

2. **Phase 2 — Quota enforcement (`TENANT_MODE=quota`).** Enable per-tenant `max_sandboxes`. No preemption. If a user hits their limit, they get 429. This is the minimum viable multi-tenant mode.

3. **Phase 3 — Fair scheduling (`TENANT_MODE=fair`).** Enable idle preemption. This requires the health monitor to be aware of tenant ownership when evicting idle sandboxes.

## Action Items

1. [ ] Add `tenant_id`, `project_id`, `priority` to `SandboxState` dataclass
2. [ ] Add `_tenant_map` index to `PoolState` with `sandboxes_for_tenant()`, `tenant_count()`
3. [ ] Extend `SessionStartRequest` to accept `tenant_id` and `project_id`
4. [ ] Update `session_start` logic with tenant quota check (gated by `TENANT_MODE`)
5. [ ] Add `GET /api/tenants/{tenant_id}/sandboxes` and `GET /api/tenants/summary`
6. [ ] Update `PoolManagerClient.session_start()` in backend to pass tenant context
7. [ ] Update `SandboxService.ensure_running_sandbox()` to resolve and forward `tenant_id`
8. [ ] Add `TENANT_MODE`, `DEFAULT_TENANT_MAX_SANDBOXES`, `DEFAULT_TENANT_MAX_CONCURRENT` to config
9. [ ] Add preemption logic to `session_start` (gated by `PREEMPTION_ENABLED`)
10. [ ] Update health monitor to respect tenant ownership during TTL cleanup
11. [ ] Add tests for all three modes: off, quota, fair
