"""
Engineer Node implementation.
"""

from langchain_core.messages import SystemMessage
from backend.graph.state import AgentState
from backend.graph.model_factory import get_model
from backend.tools.registry import get_engineer_tools


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
    model = get_model()
    
    # Bind tools available to the Engineer
    tools = get_engineer_tools()
    model_with_tools = model.bind_tools(tools)
    
    current_task = state.get("current_task", {})
    task_title = current_task.get("title", "Unknown Task")
    
    system_prompt = (
        "You are an expert Software Engineer Agent.\n"
        f"Your current assignment is: {task_title}\n"
        "Your workflow:\n"
        "1. Create a new git branch for the feature.\n"
        "2. Implement the solution by writing files and running commands in the sandbox.\n"
        "3. Verify your changes (run tests).\n"
        "4. Move task to in_review when implementation is ready.\n"
        "5. Commit your changes.\n"
        "6. Push the branch.\n"
        "7. Create a Pull Request.\n\n"
        "Use the provided tools to execute these steps. "
        "If you encounter errors, debug and retry. "
        "When finished, reply with 'Task completed and PR created for review'."
    )
    
    # Prepend system message
    messages = [SystemMessage(content=system_prompt)] + state["messages"]
    
    response = await model_with_tools.ainvoke(messages)
    
    return {"messages": [response]}
