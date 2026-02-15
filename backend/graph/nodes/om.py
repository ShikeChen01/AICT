"""
Operations Manager (OM) node implementation.
"""

from langchain_core.messages import SystemMessage

from backend.graph.model_factory import get_model
from backend.graph.state import AgentState
from backend.graph.events import emit_workflow_update, emit_agent_log


async def om_node(state: AgentState):
    """
    OM receives a project-management handoff from Manager and coordinates execution.

    Expected responsibilities:
    - break work into concrete tasks
    - assign tasks to engineers
    - keep task statuses moving through kanban states
    - hand off to engineer when implementation is required
    """
    # Import inside function to avoid circular import
    from backend.tools.registry import get_om_tools
    
    project_id = state.get("project_id", "unknown")
    current_task = state.get("current_task", {})
    task_title = current_task.get("title", "unspecified")
    
    # Emit workflow start event
    await emit_workflow_update(
        project_id=project_id,
        current_node="om",
        node_status="started",
        previous_node="manager",
    )
    
    model = get_model()

    tools = get_om_tools()
    model_with_tools = model.bind_tools(tools)

    system_prompt = (
        "You are the OM (Operations Manager) agent.\n"
        "You convert plans into executable, assigned kanban tasks.\n\n"
        f"Project ID: {project_id}\n"
        f"Current focus task: {task_title}\n\n"
        "Workflow:\n"
        "1. Break down requested work into tasks (use create_kanban_task).\n"
        "2. List available engineers (use list_engineers). Spawn one if needed (use spawn_engineer).\n"
        "3. Assign tasks to engineers (use assign_task).\n"
        "4. DISPATCH the work to the engineer (use dispatch_to_engineer with task_id and agent_id).\n"
        "   This queues the work for background execution - the engineer works asynchronously.\n"
        "5. After dispatching, report back that work has been dispatched.\n\n"
        "IMPORTANT: You must use dispatch_to_engineer after assigning a task to actually "
        "start the engineer working on it. Without dispatch, the engineer won't do anything.\n\n"
        "Example flow:\n"
        "1. create_kanban_task(title='Implement login', ...)\n"
        "2. list_engineers(project_id=...) -> Engineer-1 available\n"
        "3. assign_task(task_id=..., agent_id=<engineer-id>)\n"
        "4. dispatch_to_engineer(task_id=..., agent_id=<engineer-id>)\n"
        "5. Report: 'I have dispatched the login task to Engineer-1. They will work on it in the background.'\n\n"
        "Use tools for any task mutation. Be explicit and concise."
    )
    
    # Emit agent thinking log
    await emit_agent_log(
        project_id=project_id,
        agent_role="om",
        log_type="thought",
        content=f"Coordinating task execution. Current focus: {task_title}",
    )

    messages = [SystemMessage(content=system_prompt)] + state["messages"]
    response = await model_with_tools.ainvoke(messages)
    
    # Log the response
    response_content = response.content if hasattr(response, "content") else str(response)
    await emit_agent_log(
        project_id=project_id,
        agent_role="om",
        log_type="message",
        content=response_content[:500] if len(response_content) > 500 else response_content,
    )
    
    # Check if there are tool calls to log
    if hasattr(response, "tool_calls") and response.tool_calls:
        for tc in response.tool_calls:
            await emit_agent_log(
                project_id=project_id,
                agent_role="om",
                log_type="tool_call",
                content=f"Calling tool: {tc.get('name', 'unknown')}",
                tool_name=tc.get("name"),
                tool_input=tc.get("args"),
            )
    
    # Emit workflow completion event
    await emit_workflow_update(
        project_id=project_id,
        current_node="om",
        node_status="completed",
    )

    return {
        "messages": [response],
    }
