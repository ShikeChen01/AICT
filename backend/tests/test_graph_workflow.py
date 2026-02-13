"""
Tests for the LangGraph workflow and tool registry.
"""

import pytest
from langgraph.graph import StateGraph

from backend.graph.workflow import create_graph
from backend.tools.registry import get_manager_tools, get_engineer_tools


def test_create_graph_returns_state_graph():
    """Test that create_graph returns an uncompiled StateGraph."""
    graph = create_graph()
    assert isinstance(graph, StateGraph)


def test_create_graph_can_be_compiled():
    """Test that the returned StateGraph can be compiled."""
    graph = create_graph()
    compiled = graph.compile()
    assert compiled is not None


def test_manager_tools_returns_list():
    """Test that get_manager_tools returns a non-empty list."""
    tools = get_manager_tools()
    assert isinstance(tools, list)
    assert len(tools) > 0


def test_engineer_tools_returns_list():
    """Test that get_engineer_tools returns a non-empty list."""
    tools = get_engineer_tools()
    assert isinstance(tools, list)
    assert len(tools) > 0


def test_manager_tools_contains_expected_tools():
    """Test that manager tools include expected capabilities."""
    tools = get_manager_tools()
    tool_names = [t.name for t in tools]
    
    assert "create_kanban_task" in tool_names
    assert "list_tasks" in tool_names
    assert "assign_task" in tool_names
    assert "spawn_engineer" in tool_names


def test_engineer_tools_contains_expected_tools():
    """Test that engineer tools include expected capabilities."""
    tools = get_engineer_tools()
    tool_names = [t.name for t in tools]
    
    # Git tools
    assert "create_branch" in tool_names
    assert "commit_changes" in tool_names
    assert "push_changes" in tool_names
    assert "create_pull_request" in tool_names
    
    # Sandbox tools
    assert "execute_in_sandbox" in tool_names
    
    # File tools
    assert "read_file" in tool_names
    assert "write_file" in tool_names
    assert "list_directory" in tool_names
    
    # Task tools
    assert "update_task_status" in tool_names


def test_manager_and_engineer_tools_differ():
    """Test that manager and engineer have different tool sets."""
    manager_tools = get_manager_tools()
    engineer_tools = get_engineer_tools()
    
    manager_names = set(t.name for t in manager_tools)
    engineer_names = set(t.name for t in engineer_tools)
    
    # Some tools should only be for manager
    assert "spawn_engineer" in manager_names
    assert "spawn_engineer" not in engineer_names
    
    # Some tools should only be for engineer
    assert "create_branch" in engineer_names
    assert "create_branch" not in manager_names
