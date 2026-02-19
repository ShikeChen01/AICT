"""
Unit tests for the engineer LangGraph workflow.
"""

from backend.graph.engineer_graph import EngineerState, create_engineer_graph


class TestEngineerState:
    """EngineerState is a TypedDict with expected keys."""

    def test_state_has_required_keys(self):
        assert "messages" in EngineerState.__annotations__
        assert "project_id" in EngineerState.__annotations__
        assert "agent_id" in EngineerState.__annotations__
        assert "task_id" in EngineerState.__annotations__
        assert "current_task" in EngineerState.__annotations__
        assert "pending_message_id" in EngineerState.__annotations__
        assert "abort_reason" in EngineerState.__annotations__


class TestCreateEngineerGraph:
    """create_engineer_graph returns a StateGraph with expected structure."""

    def test_returns_state_graph(self):
        graph = create_engineer_graph()
        from langgraph.graph import StateGraph

        assert isinstance(graph, StateGraph)

    def test_compiles_and_has_invoke(self):
        graph = create_engineer_graph()
        compiled = graph.compile()
        assert hasattr(compiled, "ainvoke") or hasattr(compiled, "invoke")
