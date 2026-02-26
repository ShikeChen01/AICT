# ADR-002: Universal Agent Execution Loop

## Status

Accepted

## Context

AICT has three agent roles: Manager, CTO, and Engineer. Each role has different responsibilities, tools, and prompts. The question is whether each role should have its own execution loop implementation or share a single loop.

Options considered:
1. **Per-role loop implementations** — `manager_loop.py`, `cto_loop.py`, `engineer_loop.py`. Maximum flexibility, maximum duplication.
2. **Base loop + role overrides** — inheritance/composition pattern. Moderate flexibility, some duplication.
3. **Single universal loop** — one `run_inner_loop()` for all roles. Role-specific behavior driven entirely by prompts and tool registries.

## Decision

**All agents run the exact same `run_inner_loop()`.** Agent-specific behavior is driven by:
- **Prompt blocks** — different Identity blocks per role, same Rules/Thinking/Memory blocks
- **Tool registries** — `get_handlers_for_role(role)` returns the tools available to that role
- **Model selection** — `model_resolver` maps role + seniority to a default model string

The loop itself has zero role-specific branching. It does not check `if role == "manager"`.

## Consequences

**Positive:**
- One loop to maintain, test, and debug. Bug fixes apply to all agents simultaneously.
- Adding a new agent role requires only new prompt blocks and a tool registry entry — no loop code changes.
- Easier reasoning about system behavior — all agents follow the same lifecycle (wake → read messages → LLM → tools → END).
- Testing is simplified: test the loop once, test role-specific behavior via prompt/tool tests.

**Negative:**
- Role-specific execution quirks (e.g., Manager needs to consult CTO before spawning engineers) must be handled via prompts rather than code, which is less deterministic.
- Performance optimizations for a specific role require either loop-level flags or per-role configuration, not per-role code.

**Trade-off accepted:**
- Prompt engineering carries more weight than in a code-driven approach. The trade-off is acceptable because prompt-driven behavior is the core value proposition of the platform.
