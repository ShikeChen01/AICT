"""
Operations Manager (OM) node implementation.
"""

from langchain_core.messages import SystemMessage

from backend.graph.model_factory import get_model
from backend.graph.state import AgentState
from backend.tools.agents import spawn_engineer
from backend.tools.tasks import assign_task, create_kanban_task, list_tasks, update_task_status


async def om_node(state: AgentState):
    """
    OM receives a project-management handoff from Manager and coordinates execution.

    Expected responsibilities:
    - break work into concrete tasks
    - assign tasks to engineers
    - keep task statuses moving through kanban states
    - hand off to engineer when implementation is required
    """
    model = get_model()

    tools = [create_kanban_task, list_tasks, assign_task, update_task_status, spawn_engineer]
    model_with_tools = model.bind_tools(tools)

    project_id = state.get("project_id", "unknown")
    current_task = state.get("current_task", {})
    task_title = current_task.get("title", "unspecified")

    system_prompt = (
        "You are the OM (Operations Manager) agent.\n"
        "You convert plans into executable, assigned kanban tasks.\n\n"
        f"Project ID: {project_id}\n"
        f"Current focus task: {task_title}\n\n"
        "Workflow:\n"
        "1. Break down requested work into tasks when needed.\n"
        "2. Ensure there is an engineer available (spawn one if needed).\n"
        "3. Assign tasks to engineers.\n"
        "4. Update task statuses as work progresses.\n"
        "5. Hand off to engineer when coding should begin.\n\n"
        "Use tools for any task mutation. Be explicit and concise."
    )

    messages = [SystemMessage(content=system_prompt)] + state["messages"]
    response = await model_with_tools.ainvoke(messages)

    return {
        "messages": [response],
    }
