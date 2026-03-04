"""First-class Agent abstraction package.

An Agent encapsulates identity, prompt assembly, tool registry, LLM interaction,
and the wake-to-END loop. All agents are instances of the same class; behavior
differs by role via prompt blocks and tool configuration (DB-driven).
"""

from backend.agents.agent import (
    Agent,
    AgentServices,
    BudgetPolicy,
    EmitCallbacks,
    SessionState,
)

__all__ = [
    "Agent",
    "AgentServices",
    "BudgetPolicy",
    "EmitCallbacks",
    "SessionState",
]
