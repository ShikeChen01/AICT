"""
Tool registry for LangGraph agents.

Centralizes tool definitions to avoid circular imports between
workflow.py and node implementations.
"""

from backend.tools.git import commit_changes, create_branch, create_github_project, create_issue, create_pull_request, push_changes
from backend.tools.tasks import (
    assign_task,
    create_kanban_task,
    get_task_details,
    list_tasks,
    update_task_status,
)
from backend.tools.agents import list_engineers, spawn_engineer
from backend.tools.sandbox_vm import (
    sandbox_end_record_screen,
    sandbox_end_session,
    sandbox_execute_command,
    sandbox_health,
    sandbox_keyboard_press,
    sandbox_mouse_location,
    sandbox_mouse_move,
    sandbox_record_screen,
    sandbox_screenshot,
    sandbox_start_session,
)


def get_manager_tools():
    """Tools available to the Manager (GM) agent."""
    return [
        create_kanban_task,
        list_tasks,
        assign_task,
        update_task_status,
        get_task_details,
        spawn_engineer,
        list_engineers,
        create_issue,
        create_github_project,
        sandbox_start_session,
    ]


def get_cto_tools():
    """Tools available to the CTO (advisory only)."""
    return [
        list_tasks,
        get_task_details,
        create_issue,
        create_github_project,
        sandbox_start_session,
    ]


def get_engineer_tools():
    """Tools available to Engineer agents."""
    return [
        create_branch,
        commit_changes,
        push_changes,
        create_pull_request,
        create_issue,
        update_task_status,
        get_task_details,
        sandbox_start_session,
        sandbox_end_session,
        sandbox_execute_command,
        sandbox_health,
        sandbox_screenshot,
        sandbox_mouse_move,
        sandbox_mouse_location,
        sandbox_keyboard_press,
        sandbox_record_screen,
        sandbox_end_record_screen,
    ]
