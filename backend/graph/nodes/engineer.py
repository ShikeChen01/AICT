"""
Engineer Node implementation.
"""

from langchain_core.messages import SystemMessage
from backend.graph.state import AgentState
from backend.graph.model_factory import get_model
from backend.graph.events import emit_workflow_update, emit_agent_log


async def engineer_node(state: AgentState):
    """
    The Engineer node handles implementation tasks.
    It receives a task, writes code, tests, and creates PRs.
    
    Has access to:
    - create_branch: Create a git branch
    - commit_changes: Commit files
    - push_changes: Push to remote
    - create_pull_request: Open a PR
    - execute_in_sandbox: Run commands in E2B sandbox
    - update_task_status: Update task status in Kanban
    """
    # Import inside function to avoid circular import
    from backend.tools.registry import get_engineer_tools
    
    project_id = state.get("project_id", "unknown")
    current_task = state.get("current_task", {})
    task_title = current_task.get("title", "Unknown Task")
    task_description = current_task.get("description", "")
    task_id = current_task.get("id", "")
    
    # Emit workflow start event
    await emit_workflow_update(
        project_id=project_id,
        current_node="engineer",
        node_status="started",
        previous_node="om",
        metadata={"task_id": task_id, "task_title": task_title},
    )
    
    model = get_model()
    
    # Bind tools available to the Engineer
    tools = get_engineer_tools()
    model_with_tools = model.bind_tools(tools)
    
    system_prompt = (
        "You are an expert Software Engineer Agent.\n"
        f"Your current assignment is: {task_title}\n"
        f"Task description: {task_description}\n\n"
        f"Project ID: {project_id}\n"
        f"Task ID: {task_id}\n\n"
        "Your workflow:\n"
        "1. Create a new git branch for the feature (e.g., feat/{task-name}).\n"
        "2. Implement the solution by writing files and running commands in the sandbox.\n"
        "3. Verify your changes (run tests if applicable).\n"
        "4. Update task status to 'in_review' when implementation is ready.\n"
        "5. Commit your changes with a descriptive message.\n"
        "6. Push the branch to remote.\n"
        "7. Create a Pull Request.\n\n"
        "Use the provided tools to execute these steps. "
        "If you encounter errors, debug and retry. "
        "When finished, reply with 'Task completed and PR created for review'.\n\n"
        "IMPORTANT: You must provide your agent_id when using sandbox/file tools. "
        "Ask the OM for your agent_id if you don't have it."
    )
    
    # Emit agent thinking log
    await emit_agent_log(
        project_id=project_id,
        agent_role="engineer",
        log_type="thought",
        content=f"Starting implementation of: {task_title}",
    )
    
    # Prepend system message
    messages = [SystemMessage(content=system_prompt)] + state["messages"]
    
    response = await model_with_tools.ainvoke(messages)
    
    # Log the response
    response_content = response.content if hasattr(response, "content") else str(response)
    await emit_agent_log(
        project_id=project_id,
        agent_role="engineer",
        log_type="message",
        content=response_content[:500] if len(response_content) > 500 else response_content,
    )
    
    # Check if there are tool calls to log
    if hasattr(response, "tool_calls") and response.tool_calls:
        for tc in response.tool_calls:
            await emit_agent_log(
                project_id=project_id,
                agent_role="engineer",
                log_type="tool_call",
                content=f"Calling tool: {tc.get('name', 'unknown')}",
                tool_name=tc.get("name"),
                tool_input=tc.get("args"),
            )
    
    # Emit workflow completion event
    await emit_workflow_update(
        project_id=project_id,
        current_node="engineer",
        node_status="completed",
    )
    
    return {"messages": [response]}
