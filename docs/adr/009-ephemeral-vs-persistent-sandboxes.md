# ADR-009: Ephemeral vs. Persistent Sandboxes

## Status

Accepted

## Context

Agents execute code in isolated sandbox containers. Different agent roles have different sandbox lifecycle needs:

- **Engineers** work on discrete tasks with clear start/end boundaries. Each task typically involves a fresh branch.
- **Manager** inspects code, reviews diffs, and reads files across the project's lifetime.
- **CTO** performs architectural analysis and troubleshooting on demand.

Options:
1. **All sandboxes ephemeral** — created per session, destroyed after. Simple lifecycle, but Manager/CTO lose filesystem state between sessions.
2. **All sandboxes persistent** — survive across sessions. Simpler mental model, but wastes resources for engineers who don't reuse state.
3. **Role-based policy** — ephemeral for engineers, persistent for Manager/CTO. More complex lifecycle management, but optimized resource usage.

## Decision

**Sandboxes are ephemeral for Engineers and persistent for Manager/CTO.**

| Role | Sandbox lifecycle | `sandbox_persist` | Rationale |
|------|------------------|--------------------|-----------|
| Manager | Persistent | `true` | Needs long-lived filesystem access to review code, inspect diffs, run diagnostic commands across sessions. |
| CTO | Persistent | `true` | Needs to analyze architecture, review code across sessions. Sandbox created on-demand (first `execute_command` call). |
| Engineer | Ephemeral | `false` | Works on isolated tasks. Sandbox created at session start, destroyed at session end. Clean environment prevents state leakage between tasks. |

The `agents.sandbox_persist` flag controls the lifecycle. The `SandboxService` coordinates with the `PoolManagerClient` to acquire/release sandboxes based on this flag.

## Consequences

**Positive:**
- Engineers always start with a clean environment — no leftover files, broken dependencies, or stale branches from previous tasks.
- Manager and CTO maintain continuity — they can inspect the same working directory across sessions without re-cloning.
- Resource-efficient: sandbox containers are released when not needed (engineers return containers to the pool after each session).

**Negative:**
- Two lifecycle policies to maintain and test.
- Persistent sandboxes can accumulate state drift (stale files, broken packages) over time. May need periodic cleanup.
- Container restarts clear all sandboxes (ephemeral and persistent). Persistent sandboxes must be re-provisioned from the git remote.

**Configuration:**
- `project_settings.persistent_sandbox_count` — how many persistent sandbox slots are available per project. Currently stored but not fully enforced.
