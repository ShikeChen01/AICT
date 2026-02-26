# ADR-006: Platform, Not Workflow

## Status

Accepted

## Context

Multi-agent systems typically come in two flavors:

1. **Workflow systems** — a fixed orchestration graph defines which agent talks to which, in what order. Examples: CrewAI, AutoGen with predefined flows. The graph is the product.
2. **Platform systems** — infrastructure provides agent primitives (execution, messaging, sandboxes, memory, tasks). Users compose their own workflows. The primitives are the product.

AICT originally had a fixed workflow: User → Manager → CTO (consultation) → Engineer (execution) → Manager (review) → User. The CTO was a mandatory consultation step. The Manager-CTO flow was hardcoded in a LangGraph `StateGraph`.

Problems with the workflow approach:
- Users couldn't message engineers directly — everything went through the Manager.
- The CTO consultation was mandatory even when unnecessary, adding latency and cost.
- Adding a new agent role required modifying the orchestration graph.
- The system felt rigid: users observed a fixed pipeline, not a team they could direct.

## Decision

**AICT is a platform, not a workflow.** The system provides primitives; it does not prescribe orchestration.

Key design shifts:
- **Users can message any agent.** Talking to the Manager is the same mechanism as talking to an Engineer. No fixed entry point.
- **Agents are peers in the messaging system.** Any agent can message any other agent. The Manager has management tools (spawn, assign), but communication is symmetric.
- **No hardcoded consultation steps.** The Manager can consult the CTO via prompt guidance, but there is no code-level enforcement of the consultation flow.
- **The CTO role becomes optional.** Users can interact with whichever agents they choose. The CTO exists as an available resource, not a required pipeline stage.
- **New agent roles can be added** by defining new prompt blocks and tool registries — no orchestration graph changes needed.

## Consequences

**Positive:**
- Users have full control over which agents they interact with and how.
- Adding new agent roles (e.g., QA Engineer, Designer) requires only prompt blocks and tool registries.
- The system is more natural: it models a team where people can talk to anyone, not a pipeline.
- Removing the hardcoded CTO consultation reduces latency for simple tasks.
- The platform is more general-purpose: it can support coding workflows, design workflows, or any agent composition the user desires.

**Negative:**
- Without a prescribed workflow, new users may not know who to talk to. Mitigated by: Manager is the default target, and prompts guide the Manager to delegate appropriately.
- Agents can create chaotic communication patterns (e.g., two engineers sending conflicting messages to the Manager simultaneously). Mitigated by: the queue-based wake-up model serializes message processing per agent.
- The "platform" positioning is harder to market than a simple "AI coding team" pitch. The platform value becomes clear at scale when users want custom workflows.

**Migration path:**
- The LangGraph Manager-CTO graph can be fully removed. The Manager's prompt already includes guidance to consult the CTO when needed — the graph just enforced it in code.
