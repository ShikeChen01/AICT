"""
Manager Node implementation.
"""

from langchain_core.messages import SystemMessage
from backend.graph.state import AgentState
from backend.graph.model_factory import get_model
from backend.tools.registry import get_manager_tools


async def manager_node(state: AgentState):
    """
    The Manager node handles user interaction, planning, and delegation.
    
    Has access to:
    - create_kanban_task: Create tasks on the Kanban board
    - list_tasks: List existing tasks  
    - assign_task: Assign tasks to engineers
    - spawn_engineer: Create new engineer agents (max 5)
    """
    model = get_model()
    
    # Bind Manager tools to the model
    tools = get_manager_tools()
    model_with_tools = model.bind_tools(tools)
    
    project_id = state.get("project_id", "unknown")
    
    system_prompt = (
        "You are the Manager Agent for AICT. You act as both Product Owner and Tech Lead.\n"
        "Your responsibilities:\n"
        "1. Communicate with the client (user) to clarify requirements.\n"
        "2. Plan features and break them down into technical tasks.\n"
        "3. Create tasks on the Kanban board using the create_kanban_task tool.\n"
        "4. Spawn engineers (up to 5) using spawn_engineer when needed.\n"
        "5. Assign tasks to Engineers using assign_task.\n"
        "6. Review PRs from Engineers.\n\n"
        "Available tools:\n"
        "- create_kanban_task(title, description, project_id, critical, urgent): Create a new task\n"
        "- list_tasks(project_id, status): List tasks, optionally filtered by status\n"
        "- assign_task(task_id, agent_id): Assign a task to an engineer\n"
        "- spawn_engineer(project_id, display_name, model): Create a new engineer agent\n\n"
        f"Current Project ID: {project_id}\n"
        "Respond concisely and helpfully. Use tools when the user asks you to create tasks, "
        "assign work, or manage the project."
    )
    
    # Prepend system message
    messages = [SystemMessage(content=system_prompt)] + state["messages"]
    
    response = await model_with_tools.ainvoke(messages)
    
    return {
        "messages": [response],
        "next": "END"
    }
