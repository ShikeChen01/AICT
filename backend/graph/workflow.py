"""
Main LangGraph workflow definition.

Returns an uncompiled StateGraph so callers can add a checkpointer.

NOTE: Engineers are no longer part of this synchronous workflow.
They execute in background workers via the EngineerWorker service.
The OM dispatches work to engineers using the dispatch_to_engineer tool.
"""

from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from backend.graph.state import AgentState
from backend.graph.utils import extract_text_content
from backend.graph.nodes.manager import manager_node
from backend.graph.nodes.om import om_node


def create_graph() -> StateGraph:
    """
    Constructs the Manager-OM workflow graph.
    
    Engineers work asynchronously via background workers (EngineerWorker).
    The OM dispatches tasks to engineers using dispatch_to_engineer tool.
    
    Flow: Manager -> [manager_tools] -> Manager -> OM -> [om_tools] -> OM -> Manager -> END
    
    Returns an uncompiled StateGraph. Caller should compile with checkpointer:
        graph = create_graph().compile(checkpointer=my_checkpointer)
    """
    # Import inside function to avoid circular import
    from backend.tools.registry import get_manager_tools, get_om_tools
    
    workflow = StateGraph(AgentState)
    
    # Define tools using helper functions.
    manager_tools = get_manager_tools()
    om_tools = get_om_tools()
    
    # Add Nodes (no engineer node - they run in background workers)
    workflow.add_node("manager", manager_node)
    workflow.add_node("om", om_node)
    workflow.add_node("manager_tools", ToolNode(manager_tools))
    workflow.add_node("om_tools", ToolNode(om_tools))
    
    # Entry Point
    workflow.set_entry_point("manager")
    
    # Conditional Edges for Manager
    def manager_router(state: AgentState):
        messages = state["messages"]
        last_message = messages[-1]
        
        # If Manager wants to use tools
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return "manager_tools"
        
        content = extract_text_content(last_message.content).lower()
        
        # If Manager explicitly hands off to OM
        if "om" in content or "operations manager" in content:
            return "om"
            
        # If Manager mentions assigning work to engineers, go to OM
        if "assign" in content and "engineer" in content:
            return "om"
        
        # If Manager mentions needing engineering work, go to OM
        if any(kw in content for kw in ["implement", "build", "develop", "code", "create"]):
            return "om"
            
        return END

    workflow.add_conditional_edges(
        "manager",
        manager_router,
        {
            "manager_tools": "manager_tools",
            "om": "om",
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

        # After OM finishes dispatching work, return to Manager for user response
        # OM should NOT route to engineer - engineers work asynchronously
        return "manager"

    workflow.add_conditional_edges(
        "om",
        om_router,
        {
            "om_tools": "om_tools",
            "manager": "manager",
        },
    )

    # Return from tools to OM
    workflow.add_edge("om_tools", "om")
    
    # Return uncompiled graph - caller adds checkpointer
    return workflow
