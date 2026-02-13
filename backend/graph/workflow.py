"""
Main LangGraph workflow definition.

Returns an uncompiled StateGraph so callers can add a checkpointer.
"""

from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from backend.graph.state import AgentState
from backend.graph.nodes.manager import manager_node
from backend.graph.nodes.om import om_node
from backend.graph.nodes.engineer import engineer_node
from backend.tools.registry import get_manager_tools, get_om_tools, get_engineer_tools


def create_graph() -> StateGraph:
    """
    Constructs the Manager-OM-Engineer graph.
    
    Returns an uncompiled StateGraph. Caller should compile with checkpointer:
        graph = create_graph().compile(checkpointer=my_checkpointer)
    """
    workflow = StateGraph(AgentState)
    
    # Define tools using helper functions.
    manager_tools = get_manager_tools()
    om_tools = get_om_tools()
    engineer_tools = get_engineer_tools()
    
    # Add Nodes
    workflow.add_node("manager", manager_node)
    workflow.add_node("om", om_node)
    workflow.add_node("engineer", engineer_node)
    workflow.add_node("manager_tools", ToolNode(manager_tools))
    workflow.add_node("om_tools", ToolNode(om_tools))
    workflow.add_node("engineer_tools", ToolNode(engineer_tools))
    
    # Entry Point
    workflow.set_entry_point("manager")
    
    # Conditional Edges for Manager
    def manager_router(state: AgentState):
        messages = state["messages"]
        last_message = messages[-1]
        
        # If Manager wants to use tools
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return "manager_tools"
            
        # If Manager explicitly hands off to OM.
        if "om" in last_message.content.lower() or "operations manager" in last_message.content.lower():
            return "om"

        # If Manager explicitly hands off directly to Engineer.
        if "assign" in last_message.content.lower() and "engineer" in last_message.content.lower():
            return "engineer"
            
        return END

    workflow.add_conditional_edges(
        "manager",
        manager_router,
        {
            "manager_tools": "manager_tools",
            "om": "om",
            "engineer": "engineer",
            END: END
        }
    )
    
    # Return from tools to Manager
    workflow.add_edge("manager_tools", "manager")

    # Conditional edges for OM
    def om_router(state: AgentState):
        messages = state["messages"]
        last_message = messages[-1]

        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return "om_tools"

        # Handoff to engineer when implementation work is requested.
        content = last_message.content.lower()
        if "engineer" in content and (
            "implement" in content
            or "code" in content
            or "build" in content
            or "fix" in content
        ):
            return "engineer"

        # Otherwise loop back to manager for user-facing coordination.
        return "manager"

    workflow.add_conditional_edges(
        "om",
        om_router,
        {
            "om_tools": "om_tools",
            "engineer": "engineer",
            "manager": "manager",
        },
    )

    # Return from tools to OM.
    workflow.add_edge("om_tools", "om")
    
    # Conditional Edges for Engineer
    def engineer_router(state: AgentState):
        messages = state["messages"]
        last_message = messages[-1]
        
        # If Engineer wants to use tools
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return "engineer_tools"
            
        # Engineer normally returns to OM for review/handoff.
        return "om"

    workflow.add_conditional_edges(
        "engineer",
        engineer_router,
        {
            "engineer_tools": "engineer_tools",
            "om": "om"
        }
    )
    
    # Return from tools to Engineer
    workflow.add_edge("engineer_tools", "engineer")
    
    # Return uncompiled graph - caller adds checkpointer
    return workflow
