"""
Tool registry for LangGraph agents.

Centralizes tool definitions to avoid circular imports between
workflow.py and node implementations.
"""

from backend.tools.git import create_branch, commit_changes, push_changes, create_pull_request
from backend.tools.e2b import execute_in_sandbox
from backend.tools.tasks import create_kanban_task, list_tasks, assign_task, update_task_status
from backend.tools.agents import spawn_engineer
from backend.tools.files import read_file, write_file, list_directory, delete_file


def get_manager_tools():
    """Return tools available to the Manager agent."""
    return [create_kanban_task, list_tasks, assign_task, update_task_status, spawn_engineer]


def get_om_tools():
    """Return tools available to the OM agent."""
    return [create_kanban_task, list_tasks, assign_task, update_task_status, spawn_engineer]


def get_engineer_tools():
    """
    Return tools available to Engineer agents.
    
    Engineers can:
    - Git: create_branch, commit_changes, push_changes, create_pull_request
    - Sandbox: execute_in_sandbox (run commands)
    - Files: read_file, write_file, list_directory, delete_file
    - Tasks: update_task_status
    """
    return [
        # Git operations
        create_branch,
        commit_changes,
        push_changes,
        create_pull_request,
        # Sandbox execution
        execute_in_sandbox,
        # File operations
        read_file,
        write_file,
        list_directory,
        delete_file,
        # Task management
        update_task_status,
    ]
