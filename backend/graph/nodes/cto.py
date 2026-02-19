"""
CTO (Chief Technology Officer) node implementation.
Advisory only: architecture, review, list_tasks/get_task_details. Does not assign or dispatch.
"""

from langchain_core.messages import SystemMessage

from backend.graph.model_factory import get_model
from backend.graph.state import AgentState
from backend.graph.events import emit_workflow_update, emit_agent_log


async def cto_node(state: AgentState):
    """
    CTO provides architectural advice when consulted by Manager (or engineers).
    Does NOT spawn, assign, or dispatch to engineers.
    """
    from backend.tools.registry import get_cto_tools

    project_id = state.get("project_id", "unknown")
    current_task = state.get("current_task", {})
    task_title = current_task.get("title", "unspecified")

    await emit_workflow_update(
        project_id=project_id,
        current_node="cto",
        node_status="started",
        previous_node="manager",
    )

    model = get_model(role="cto")
    tools = get_cto_tools()
    model_with_tools = model.bind_tools(tools)

    system_prompt = (
        "You are the CTO (Chief Technology Officer) of the project.\n"
        "You are an architecture advisor. You do NOT assign tasks or dispatch work to engineers.\n\n"
        f"Project ID: {project_id}\n"
        f"Current focus: {task_title}\n\n"
        "When consulted, you:\n"
        "- Provide architectural guidance and design recommendations\n"
        "- Review technical decisions and integration concerns\n"
        "- Answer questions about system design, patterns, or troubleshooting\n"
        "You can use list_tasks and get_task_details to understand context, then respond with advice.\n"
        "After responding, the flow returns to the Manager. Be concise and actionable."
    )

    await emit_agent_log(
        project_id=project_id,
        agent_role="cto",
        log_type="thought",
        content=f"Providing architectural advice. Focus: {task_title}",
    )

    messages = [SystemMessage(content=system_prompt)] + state["messages"]
    response = await model_with_tools.ainvoke(messages)

    response_content = response.content if hasattr(response, "content") else str(response)
    await emit_agent_log(
        project_id=project_id,
        agent_role="cto",
        log_type="message",
        content=response_content[:500] if len(response_content) > 500 else response_content,
    )

    if hasattr(response, "tool_calls") and response.tool_calls:
        for tc in response.tool_calls:
            await emit_agent_log(
                project_id=project_id,
                agent_role="cto",
                log_type="tool_call",
                content=f"Calling tool: {tc.get('name', 'unknown')}",
                tool_name=tc.get("name"),
                tool_input=tc.get("args"),
            )

    await emit_workflow_update(
        project_id=project_id,
        current_node="cto",
        node_status="completed",
    )

    return {
        "messages": [response],
    }
