"""
Main LangGraph workflow definition.

Returns an uncompiled StateGraph so callers can add a checkpointer.

Manager (GM) plans, assigns, and dispatches to engineers via manager_tools.
CTO is advisory only: Manager can route to CTO for architecture/design consultation.
Engineers run in background workers; Manager uses dispatch_to_engineer in manager_tools.
"""

from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from backend.graph.state import AgentState
from backend.graph.utils import extract_text_content
from backend.graph.nodes.manager import manager_node
from backend.graph.nodes.cto import cto_node


def create_graph() -> StateGraph:
    """
    Manager-CTO workflow. Manager has all orchestration tools (assign + dispatch).
    CTO node is for consultation only (architecture, design).
    Flow: Manager -> [manager_tools] | CTO -> [cto_tools] -> Manager | END
    """
    from backend.tools.registry import get_manager_tools, get_cto_tools

    workflow = StateGraph(AgentState)

    manager_tools = get_manager_tools()
    cto_tools = get_cto_tools()

    workflow.add_node("manager", manager_node)
    workflow.add_node("cto", cto_node)
    workflow.add_node("manager_tools", ToolNode(manager_tools))
    workflow.add_node("cto_tools", ToolNode(cto_tools))

    workflow.set_entry_point("manager")

    def manager_router(state: AgentState):
        messages = state["messages"]
        last_message = messages[-1]

        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return "manager_tools"

        content = extract_text_content(last_message.content).lower()

        # Route to CTO only for consultation (architecture, design), not for task assignment
        if any(kw in content for kw in ["consult cto", "architecture", "architectural", "design review", "cto"]):
            return "cto"

        return END

    workflow.add_conditional_edges(
        "manager",
        manager_router,
        {
            "manager_tools": "manager_tools",
            "cto": "cto",
            END: END,
        },
    )

    workflow.add_edge("manager_tools", "manager")

    def cto_router(state: AgentState):
        messages = state["messages"]
        last_message = messages[-1]
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return "cto_tools"
        return "manager"

    workflow.add_conditional_edges(
        "cto",
        cto_router,
        {
            "cto_tools": "cto_tools",
            "manager": "manager",
        },
    )

    workflow.add_edge("cto_tools", "cto")

    return workflow
