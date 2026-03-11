# ADR-013: v3 Declarative Agent Cluster Control

**Date:** 2026-03-10  
**Status:** Accepted  
**Authors:** AICT v3 Architecture Team

---

## Context

AICT v2 provides a powerful agent orchestration runtime but requires imperative API calls
to create, configure, and manage agents. As clusters grow beyond 2–4 agents, managing
replicas, drift, and lifecycle imperatively becomes fragile and error-prone.

The v3 Cluster Control Proposal identifies the core market insight:
> "The intelligent agent infrastructure market lacks what Kubernetes brought to containers."

The existing codebase already contains 70% of the required primitives:
- `Reconciler` → self-healing controller
- `WorkerManager` → scheduler
- `ChannelMessage + MessageRouter` → service mesh
- `LLMUsageEvent + BudgetPolicy` → cost control

The missing 30% is: a declarative spec layer on top of these primitives.

---

## Decision

Introduce a **declarative ClusterSpec** YAML format and a reconciler-based control loop
that converges live cluster state to match the spec.

**Key design choices:**

1. **Kubernetes-style manifest syntax** (`apiVersion`, `kind`, `metadata`, `spec`) —
   lowers the learning curve and enables future kubectl-style CLI tooling.

2. **Spec-level primitives stay in backend** — `ClusterSpec` is a backend Python class
   (`backend/cluster/spec.py`) that the CLI and API both use. No separate spec server.

3. **Reconciler extends to 8 drift categories** — the existing 4-category reconciler
   is extended with cluster drift, dead-letter retry, budget breach, and zombie sandbox
   detection.

4. **MessageRouter gains topology-aware routing** — `route_to_cluster()` selects the
   least-loaded member of a named cluster, enabling basic work-stealing without a
   separate scheduler.

5. **Cluster membership tracked in agent.memory** — agents store `cluster_name` and
   `cluster_labels` in their JSON memory blob. This avoids a new join table while
   allowing the reconciler and router to identify cluster members.

6. **Budget enforcement is a hard gate, not advisory** — `BudgetService.check_llm_budget()`
   raises `BudgetExceededError` before the LLM call is made. Sandbox pod-second metering
   is recorded in `sandbox_usage_events` for aggregate enforcement.

---

## API Surface

```
POST   /api/v1/clusters/apply          Apply a ClusterSpec (create/update/delete agents)
POST   /api/v1/clusters/diff           Dry-run preview
GET    /api/v1/clusters/{project_id}   Describe live cluster state
GET    /metrics                        Prometheus scrape endpoint
GET    /api/v1/budget/{project_id}     Budget utilization summary
POST   /api/v1/budget/{project_id}/sandbox-usage  Record sandbox compute
```

---

## Consequences

**Positive:**
- Operators can declaratively manage agent clusters with a single YAML file.
- The reconciler automatically heals drift every 30 seconds.
- Budget enforcement prevents runaway costs across both LLM and sandbox compute.
- Topology-aware routing enables basic load-balancing without a separate orchestrator.
- MessageRouter dead-letter queue ensures message delivery is observable, not silent.

**Negative / Trade-offs:**
- Cluster membership is stored in `agent.memory` (JSON blob) rather than a dedicated
  column. This is a pragmatic choice to avoid another migration; a dedicated
  `agent_cluster_id` column would be cleaner for querying.
- The diff algorithm uses a display_name prefix convention to match agents to specs.
  This is fragile if agents are renamed. A stable `spec_name` column would be better.
- Circular imports in the tool registry (pre-existing tech debt) prevent some tests
  from running in isolation.

**Migration:**
- `026_v3_cluster_control.py` adds `cluster_specs`, `dead_letter_messages`, and
  `sandbox_usage_events` tables.
- All new tables are optional/graceful — existing code falls back safely if the
  migration has not yet run (pre-migration behavior preserved).

---

## Alternatives Considered

| Alternative | Rejected Because |
|-------------|-----------------|
| Separate spec server | Unnecessary complexity; backend already has the primitives |
| CRD-style Kubernetes extension | Overkill; requires running full K8s control plane in AICT |
| Event-sourced spec ledger | Premature optimization for the current scale |
| Agent-level spec YAML in DB | Cluster is a higher-level concept than a single agent |
