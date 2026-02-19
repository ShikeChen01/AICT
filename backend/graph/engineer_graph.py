"""
Engineer LangGraph workflow.

Each engineer runs in its own graph with thread_id = engineer-{agent_id}-{task_id},
enabling parallel execution and interrupt (human-in-the-loop) support.
"""

from typing import TypedDict, Annotated, List, Dict, Any
import operator
from langchain_core.messages import BaseMessage
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode


class EngineerState(TypedDict):
    """State for a single engineer's graph run."""

    messages: Annotated[List[BaseMessage], operator.add]
    project_id: str
    agent_id: str
    task_id: str
    current_task: Dict[str, Any]
    pending_message_id: str  # message ID when waiting for user, empty string otherwise
    abort_reason: str  # set when aborting, empty string otherwise


def create_engineer_graph() -> StateGraph:
    """
    Build the engineer StateGraph: engineer -> engineer_tools -> engineer (or END).
    Caller compiles with checkpointer for interrupt/resume support.
    """
    from backend.tools.registry import get_engineer_tools
    from backend.graph.nodes.engineer import engineer_node

    tools = get_engineer_tools()
    workflow = StateGraph(EngineerState)

    workflow.add_node("engineer", engineer_node)
    workflow.add_node("engineer_tools", ToolNode(tools))
    workflow.set_entry_point("engineer")

    def router(state: EngineerState) -> str:
        messages = state["messages"]
        if not messages:
            return END
        last = messages[-1]
        if hasattr(last, "tool_calls") and last.tool_calls:
            return "engineer_tools"
        return END

    workflow.add_conditional_edges(
        "engineer",
        router,
        {
            "engineer_tools": "engineer_tools",
            END: END,
        },
    )
    workflow.add_edge("engineer_tools", "engineer")

    return workflow
