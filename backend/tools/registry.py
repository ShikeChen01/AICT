"""
Tool registry for LangGraph agents.

Centralizes tool definitions to avoid circular imports between
workflow.py and node implementations.
"""

from backend.tools.git import create_branch, commit_changes, push_changes, create_pull_request
from backend.tools.e2b import execute_in_sandbox
from backend.tools.tasks import create_kanban_task, list_tasks, assign_task, update_task_status, get_task_details
from backend.tools.agents import spawn_engineer, list_engineers


def get_manager_tools():
    """Return tools available to the Manager (GM) agent. Manager plans, assigns, and dispatches to engineers."""
    return [
        create_kanban_task,
        list_tasks,
        assign_task,
        update_task_status,
        get_task_details,
        spawn_engineer,
        list_engineers,
    ]


def get_cto_tools():
    """
    Return tools available to the CTO (advisory only).
    CTO can: list tasks, get task details. No create/assign/spawn/dispatch.
    """
    return [
        list_tasks,
        get_task_details,
    ]


def get_engineer_tools():
    """
    Return tools available to Engineer agents.
    Engineers: Git, sandbox execute, task status/details. File ops via execute_command.
    """
    return [
        create_branch,
        commit_changes,
        push_changes,
        create_pull_request,
        execute_in_sandbox,
        update_task_status,
        get_task_details,
    ]
