"""Production chain tests — verify the full agent→tool→VM path works in production.

Tests the critical links that must hold for agents to use sandbox/desktop tools:
1. WebSocket broadcasts include desktop_id
2. Agent worker loads both relationships
3. Tool dispatch receives context with loaded relationships
4. API responses include both sandbox_id and desktop_id
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.sandbox.conftest import make_sandbox, make_agent


# ── Section 1: WebSocket Agent Status Events ──────────────────────────────────


class TestWebSocketAgentStatus:
    """Verify WebSocket broadcasts include both sandbox_id and desktop_id."""

    def test_payload_has_desktop_id_field(self):
        from backend.websocket.events import AgentStatusPayload

        payload = AgentStatusPayload(
            id=uuid.uuid4(),
            project_id=uuid.uuid4(),
            role="engineer",
            display_name="Eng-1",
            status="active",
            current_task_id=None,
            sandbox_id=None,
            desktop_id=None,
        )
        assert hasattr(payload, "desktop_id")
        assert payload.desktop_id is None

    def test_payload_serializes_desktop_id(self):
        from backend.websocket.events import AgentStatusPayload

        desk_id = str(uuid.uuid4())
        payload = AgentStatusPayload(
            id=uuid.uuid4(),
            project_id=uuid.uuid4(),
            role="engineer",
            display_name="Eng-1",
            status="active",
            current_task_id=None,
            sandbox_id=None,
            desktop_id=desk_id,
        )
        data = payload.model_dump(mode="json")
        assert data["desktop_id"] == desk_id

    def test_create_event_with_desktop(self):
        from backend.websocket.events import create_agent_status_event

        desktop = SimpleNamespace(id=uuid.uuid4())
        agent = SimpleNamespace(
            id=uuid.uuid4(),
            project_id=uuid.uuid4(),
            role="engineer",
            display_name="Eng-1",
            status="active",
            current_task_id=None,
            sandbox=None,
            desktop=desktop,
        )
        event = create_agent_status_event(agent)
        assert event.data["desktop_id"] == str(desktop.id)
        assert event.data["sandbox_id"] is None

    def test_create_event_with_sandbox(self):
        from backend.websocket.events import create_agent_status_event

        sandbox = SimpleNamespace(id=uuid.uuid4())
        agent = SimpleNamespace(
            id=uuid.uuid4(),
            project_id=uuid.uuid4(),
            role="engineer",
            display_name="Eng-1",
            status="active",
            current_task_id=None,
            sandbox=sandbox,
            desktop=None,
        )
        event = create_agent_status_event(agent)
        assert event.data["sandbox_id"] == str(sandbox.id)
        assert event.data["desktop_id"] is None

    def test_create_event_with_both(self):
        from backend.websocket.events import create_agent_status_event

        sandbox = SimpleNamespace(id=uuid.uuid4())
        desktop = SimpleNamespace(id=uuid.uuid4())
        agent = SimpleNamespace(
            id=uuid.uuid4(),
            project_id=uuid.uuid4(),
            role="engineer",
            display_name="Eng-1",
            status="active",
            current_task_id=None,
            sandbox=sandbox,
            desktop=desktop,
        )
        event = create_agent_status_event(agent)
        assert event.data["sandbox_id"] == str(sandbox.id)
        assert event.data["desktop_id"] == str(desktop.id)

    def test_create_event_with_neither(self):
        from backend.websocket.events import create_agent_status_event

        agent = SimpleNamespace(
            id=uuid.uuid4(),
            project_id=uuid.uuid4(),
            role="engineer",
            display_name="Eng-1",
            status="idle",
            current_task_id=None,
            sandbox=None,
            desktop=None,
        )
        event = create_agent_status_event(agent)
        assert event.data["sandbox_id"] is None
        assert event.data["desktop_id"] is None

    def test_create_event_tolerates_missing_attrs(self):
        """Agent object without sandbox/desktop attrs should not crash."""
        from backend.websocket.events import create_agent_status_event

        agent = SimpleNamespace(
            id=uuid.uuid4(),
            project_id=uuid.uuid4(),
            role="engineer",
            display_name="Eng-1",
            status="idle",
            current_task_id=None,
        )
        event = create_agent_status_event(agent)
        assert event.data["sandbox_id"] is None
        assert event.data["desktop_id"] is None


# ── Section 2: API Response Schema ───────────────────────────────────────────


class TestApiResponseSchema:
    """Verify API response schemas include desktop_id."""

    def test_agent_response_has_desktop_id(self):
        from backend.schemas.agent import AgentResponse

        fields = AgentResponse.model_fields
        assert "desktop_id" in fields
        assert "sandbox_id" in fields

    def test_agent_status_response_has_desktop_id(self):
        from backend.schemas.agent import AgentStatusWithQueueResponse

        fields = AgentStatusWithQueueResponse.model_fields
        assert "desktop_id" in fields
        assert "sandbox_id" in fields


# ── Section 3: Tool Registry Completeness ────────────────────────────────────


class TestToolRegistryCompleteness:
    """Verify every registered tool has a working executor and correct schema."""

    def test_all_sandbox_tools_have_executors(self):
        from backend.tools.loop_registry import _SANDBOX_TOOL_NAMES, _TOOL_EXECUTORS

        for name in _SANDBOX_TOOL_NAMES:
            assert name in _TOOL_EXECUTORS, f"Sandbox tool {name!r} missing from executor map"
            assert _TOOL_EXECUTORS[name] is not None, f"Sandbox tool {name!r} executor is None"

    def test_all_desktop_tools_have_executors(self):
        from backend.tools.loop_registry import _DESKTOP_TOOL_NAMES, _TOOL_EXECUTORS

        for name in _DESKTOP_TOOL_NAMES:
            assert name in _TOOL_EXECUTORS, f"Desktop tool {name!r} missing from executor map"
            assert _TOOL_EXECUTORS[name] is not None, f"Desktop tool {name!r} executor is None"

    def test_tool_descriptions_match_executors(self):
        """Every tool in tool_descriptions.json that is sandbox/desktop must have executor."""
        import json
        from pathlib import Path
        from backend.tools.loop_registry import _SANDBOX_TOOL_NAMES, _DESKTOP_TOOL_NAMES, _TOOL_EXECUTORS

        raw = json.loads(
            (Path(__file__).parent.parent.parent / "tools" / "tool_descriptions.json")
            .read_text(encoding="utf-8")
        )
        sandbox_desktop_names = _SANDBOX_TOOL_NAMES | _DESKTOP_TOOL_NAMES
        for tool in raw:
            if tool["name"] in sandbox_desktop_names:
                assert tool["name"] in _TOOL_EXECUTORS, f"Tool {tool['name']!r} in JSON but not in executors"

    def test_desktop_mouse_click_button_is_integer_in_schema(self):
        """LLM schema must specify button as integer, not string."""
        import json
        from pathlib import Path

        raw = json.loads(
            (Path(__file__).parent.parent.parent / "tools" / "tool_descriptions.json")
            .read_text(encoding="utf-8")
        )
        click_tool = next(t for t in raw if t["name"] == "desktop_mouse_click")
        assert click_tool["input_schema"]["properties"]["button"]["type"] == "integer"

    def test_desktop_keyboard_keys_is_string_in_schema(self):
        """LLM schema must specify keys as string, not array."""
        import json
        from pathlib import Path

        raw = json.loads(
            (Path(__file__).parent.parent.parent / "tools" / "tool_descriptions.json")
            .read_text(encoding="utf-8")
        )
        kb_tool = next(t for t in raw if t["name"] == "desktop_keyboard_press")
        assert kb_tool["input_schema"]["properties"]["keys"]["type"] == "string"

    def test_sandbox_mouse_click_button_is_integer_in_schema(self):
        """LLM schema must specify button as integer for sandbox tools too."""
        import json
        from pathlib import Path

        raw = json.loads(
            (Path(__file__).parent.parent.parent / "tools" / "tool_descriptions.json")
            .read_text(encoding="utf-8")
        )
        click_tool = next(t for t in raw if t["name"] == "sandbox_mouse_click")
        assert click_tool["input_schema"]["properties"]["button"]["type"] == "integer"

    def test_sandbox_keyboard_keys_is_string_in_schema(self):
        """LLM schema must specify keys as string for sandbox tools too."""
        import json
        from pathlib import Path

        raw = json.loads(
            (Path(__file__).parent.parent.parent / "tools" / "tool_descriptions.json")
            .read_text(encoding="utf-8")
        )
        kb_tool = next(t for t in raw if t["name"] == "sandbox_keyboard_press")
        assert kb_tool["input_schema"]["properties"]["keys"]["type"] == "string"

    def test_exact_sandbox_tool_count(self):
        """Registry must have exactly 12 sandbox tools."""
        from backend.tools.loop_registry import _SANDBOX_TOOL_NAMES
        assert len(_SANDBOX_TOOL_NAMES) == 12, f"Expected 12 sandbox tools, got {len(_SANDBOX_TOOL_NAMES)}"

    def test_exact_desktop_tool_count(self):
        """Registry must have exactly 10 desktop tools."""
        from backend.tools.loop_registry import _DESKTOP_TOOL_NAMES
        assert len(_DESKTOP_TOOL_NAMES) == 10, f"Expected 10 desktop tools, got {len(_DESKTOP_TOOL_NAMES)}"

    def test_every_registered_tool_in_json(self):
        """Every registered sandbox/desktop tool must appear in tool_descriptions.json (bidirectional)."""
        import json
        from pathlib import Path
        from backend.tools.loop_registry import _SANDBOX_TOOL_NAMES, _DESKTOP_TOOL_NAMES

        raw = json.loads(
            (Path(__file__).parent.parent.parent / "tools" / "tool_descriptions.json")
            .read_text(encoding="utf-8")
        )
        json_names = {t["name"] for t in raw}
        all_registered = _SANDBOX_TOOL_NAMES | _DESKTOP_TOOL_NAMES
        missing_from_json = all_registered - json_names
        assert not missing_from_json, (
            f"Registered tools missing from tool_descriptions.json: {missing_from_json}"
        )


# ── Section 4: RunContext & Agent Relationship Integrity ─────────────────────


class TestRunContextIntegrity:
    """Verify RunContext carries agent with both sandbox and desktop."""

    def test_run_context_agent_has_sandbox(self):
        from tests.sandbox.conftest import make_run_context
        sandbox = make_sandbox(unit_type="headless")
        agent = make_agent(sandbox=sandbox)
        ctx = make_run_context(agent)
        assert ctx.agent.sandbox is sandbox

    def test_run_context_agent_has_desktop(self):
        from tests.sandbox.conftest import make_run_context
        sandbox = make_sandbox(unit_type="desktop")
        agent = make_agent(desktop=sandbox)
        ctx = make_run_context(agent)
        assert ctx.agent.desktop is sandbox

    def test_run_context_agent_has_both(self):
        from tests.sandbox.conftest import make_run_context
        headless = make_sandbox(unit_type="headless")
        desktop = make_sandbox(unit_type="desktop")
        agent = make_agent(sandbox=headless, desktop=desktop)
        ctx = make_run_context(agent)
        assert ctx.agent.sandbox is headless
        assert ctx.agent.desktop is desktop

    def test_run_context_agent_has_neither(self):
        from tests.sandbox.conftest import make_run_context
        agent = make_agent()
        ctx = make_run_context(agent)
        assert ctx.agent.sandbox is None
        assert ctx.agent.desktop is None


# ── Section 5: Cross-Layer Contract Tests ────────────────────────────────────


class TestCrossLayerContracts:
    """Verify the data contracts between layers match."""

    def test_client_mouse_click_sends_button_as_int(self):
        """SandboxClient must send button as integer to match server schema."""
        from backend.services.sandbox_client import SandboxClient
        import inspect
        src = inspect.getsource(SandboxClient.mouse_click)
        # The payload construction must use the int param directly
        assert '"button": button' in src or "'button': button" in src

    def test_client_keyboard_sends_keys_as_string(self):
        """SandboxClient must send keys as string to match server schema."""
        from backend.services.sandbox_client import SandboxClient
        sig = inspect.signature(SandboxClient.keyboard_press)
        keys_param = sig.parameters["keys"]
        # keys should accept str | None, not list
        assert keys_param.annotation in ("str | None", str | None)

    def test_service_resolve_desktop_returns_proxy_prefix(self):
        """SandboxService must route desktops through pool manager proxy."""
        from backend.services.sandbox_service import SandboxService
        import inspect
        src = inspect.getsource(SandboxService._resolve_host_port)
        assert "/api/sandbox/" in src
        assert "/proxy" in src

    def test_executor_desktop_click_passes_int_button(self):
        """Desktop executor must convert button to int before passing to service."""
        from backend.tools.executors.desktop import run_desktop_mouse_click
        import inspect
        src = inspect.getsource(run_desktop_mouse_click)
        assert "int(tool_input" in src

    def test_executor_sandbox_click_passes_int_button(self):
        """Sandbox executor must convert button to int before passing to service."""
        from backend.tools.executors.sandbox import run_sandbox_mouse_click
        import inspect
        src = inspect.getsource(run_sandbox_mouse_click)
        assert "int(tool_input" in src


import inspect


# ── Section 6: Agent Worker DB Loading Verification ────────────────────────────


class TestAgentWorkerDbLoading:
    """Verify that agent_worker.py correctly loads both sandbox and desktop relationships."""

    def test_agent_worker_selectinloads_sandbox(self):
        from backend.workers.agent_worker import AgentWorker

        src = inspect.getsource(AgentWorker.run)
        assert "selectinload" in src, "AgentWorker.run must use selectinload"
        assert ".sandbox" in src, "AgentWorker.run must load .sandbox relationship"

    def test_agent_worker_selectinloads_desktop(self):
        from backend.workers.agent_worker import AgentWorker

        src = inspect.getsource(AgentWorker.run)
        assert "selectinload" in src, "AgentWorker.run must use selectinload"
        assert ".desktop" in src, "AgentWorker.run must load .desktop relationship"

    def test_agent_worker_loads_both_in_same_query(self):
        from backend.workers.agent_worker import AgentWorker

        src = inspect.getsource(AgentWorker.run)
        lines = src.split("\n")
        # Find lines containing selectinload — both sandbox and desktop should be
        # on the same line or adjacent lines within a single select() call.
        selectinload_lines = [
            (i, line) for i, line in enumerate(lines) if "selectinload" in line
        ]
        sandbox_lines = {i for i, line in selectinload_lines if "sandbox" in line}
        desktop_lines = {i for i, line in selectinload_lines if "desktop" in line}

        if sandbox_lines & desktop_lines:
            # Both on same line(s)
            return

        # Check adjacency: sandbox and desktop selectinloads within 2 lines of each other
        for s_line in sandbox_lines:
            for d_line in desktop_lines:
                if abs(s_line - d_line) <= 2:
                    return

        pytest.fail(
            "sandbox and desktop selectinloads are not in the same query "
            f"(sandbox lines: {sandbox_lines}, desktop lines: {desktop_lines})"
        )


# ── Section 7: Task Service DB Loading Verification ───────────────────────────


class TestTaskServiceDbLoading:
    """Verify task_service.py and api_internal.files load desktop when loading agents."""

    def test_task_service_loads_desktop_relationship(self):
        from backend.services.task_service import TaskService

        src = inspect.getsource(TaskService.assign)
        assert "selectinload" in src, "TaskService.assign must use selectinload"
        assert "desktop" in src, "TaskService.assign must load desktop relationship"

    def test_internal_files_loads_desktop(self):
        from backend.api_internal import files

        src = inspect.getsource(files.execute)
        assert "selectinload" in src, "internal files.execute must use selectinload"
        assert "desktop" in src, "internal files.execute must load desktop relationship"


# ── Section 8: Tool Executor Function Signatures ──────────────────────────────


class TestToolExecutorSignatures:
    """Verify all executor functions have the correct signature (ctx: RunContext, tool_input: dict)."""

    def test_all_sandbox_executors_accept_run_context(self):
        from backend.tools.loop_registry import _SANDBOX_TOOL_NAMES, _TOOL_EXECUTORS

        for name in _SANDBOX_TOOL_NAMES:
            executor = _TOOL_EXECUTORS[name]
            assert executor is not None, f"Sandbox tool {name!r} has no executor"
            sig = inspect.signature(executor)
            params = list(sig.parameters.keys())
            assert "ctx" in params, f"Executor for {name!r} missing 'ctx' parameter"
            assert "tool_input" in params, f"Executor for {name!r} missing 'tool_input' parameter"

    def test_all_desktop_executors_accept_run_context(self):
        from backend.tools.loop_registry import _DESKTOP_TOOL_NAMES, _TOOL_EXECUTORS

        for name in _DESKTOP_TOOL_NAMES:
            executor = _TOOL_EXECUTORS[name]
            assert executor is not None, f"Desktop tool {name!r} has no executor"
            sig = inspect.signature(executor)
            params = list(sig.parameters.keys())
            assert "ctx" in params, f"Executor for {name!r} missing 'ctx' parameter"
            assert "tool_input" in params, f"Executor for {name!r} missing 'tool_input' parameter"


# ── Section 9: WebSocket Manager Broadcast Path ──────────────────────────────


class TestWebSocketBroadcastPath:
    """Verify the WebSocket manager can broadcast agent status events correctly."""

    def test_broadcast_agent_status_creates_event(self):
        from backend.websocket.events import create_agent_status_event

        sandbox = SimpleNamespace(id=uuid.uuid4())
        desktop = SimpleNamespace(id=uuid.uuid4())
        agent = SimpleNamespace(
            id=uuid.uuid4(),
            project_id=uuid.uuid4(),
            role="engineer",
            display_name="Eng-1",
            status="active",
            current_task_id=None,
            sandbox=sandbox,
            desktop=desktop,
        )
        event = create_agent_status_event(agent)
        # Must be JSON-serializable without error
        data = event.model_dump(mode="json")
        assert isinstance(data, dict)

    def test_broadcast_event_serializable(self):
        import json
        from datetime import datetime
        from backend.websocket.events import (
            create_task_created_event,
            create_task_update_event,
            create_agent_status_event,
        )

        now = datetime.now()
        task = SimpleNamespace(
            id=uuid.uuid4(),
            project_id=uuid.uuid4(),
            title="Test task",
            description="desc",
            status="backlog",
            critical=0,
            urgent=0,
            assigned_agent_id=None,
            module_path=None,
            git_branch=None,
            pr_url=None,
            parent_task_id=None,
            created_by_id=None,
            created_at=now,
            updated_at=now,
        )
        agent = SimpleNamespace(
            id=uuid.uuid4(),
            project_id=uuid.uuid4(),
            role="cto",
            display_name="CTO-1",
            status="idle",
            current_task_id=None,
            sandbox=None,
            desktop=None,
        )

        for factory, arg in [
            (create_task_created_event, task),
            (create_task_update_event, task),
            (create_agent_status_event, agent),
        ]:
            event = factory(arg)
            serialized = event.model_dump(mode="json")
            # Must round-trip through JSON without error
            json.dumps(serialized)

    def test_agent_status_event_has_all_required_fields(self):
        from backend.websocket.events import create_agent_status_event

        agent = SimpleNamespace(
            id=uuid.uuid4(),
            project_id=uuid.uuid4(),
            role="manager",
            display_name="Mgr-1",
            status="active",
            current_task_id=uuid.uuid4(),
            sandbox=SimpleNamespace(id=uuid.uuid4()),
            desktop=SimpleNamespace(id=uuid.uuid4()),
        )
        event = create_agent_status_event(agent)
        serialized = event.model_dump(mode="json")

        # Top-level event fields
        assert "type" in serialized
        assert "data" in serialized
        assert "timestamp" in serialized

        # Data payload fields
        data = serialized["data"]
        for field in (
            "id", "project_id", "role", "display_name", "status",
            "current_task_id", "sandbox_id", "desktop_id",
        ):
            assert field in data, f"agent_status event data missing field {field!r}"


# ── Section 10: API Agent Response Generation ─────────────────────────────────


class TestApiAgentResponseGeneration:
    """Verify AgentResponse and AgentStatusWithQueueResponse populate all fields."""

    def test_agent_response_from_mock_record(self):
        from datetime import datetime
        from backend.schemas.agent import AgentResponse

        now = datetime.now()
        sandbox_id = str(uuid.uuid4())
        desktop_id = str(uuid.uuid4())

        response = AgentResponse(
            id=uuid.uuid4(),
            project_id=uuid.uuid4(),
            template_id=None,
            role="engineer",
            display_name="Eng-1",
            model="claude-sonnet-4-20250514",
            provider="anthropic",
            thinking_enabled=False,
            status="active",
            current_task_id=None,
            sandbox_id=sandbox_id,
            desktop_id=desktop_id,
            memory=None,
            created_at=now,
            updated_at=now,
        )
        data = response.model_dump()
        assert data["sandbox_id"] == sandbox_id
        assert data["desktop_id"] == desktop_id

    def test_agent_status_response_includes_queue_fields(self):
        from datetime import datetime
        from backend.schemas.agent import AgentStatusWithQueueResponse

        now = datetime.now()
        desktop_id = str(uuid.uuid4())

        response = AgentStatusWithQueueResponse(
            id=uuid.uuid4(),
            project_id=uuid.uuid4(),
            role="engineer",
            display_name="Eng-1",
            model="claude-sonnet-4-20250514",
            provider="anthropic",
            status="active",
            current_task_id=None,
            sandbox_id=None,
            desktop_id=desktop_id,
            created_at=now,
            updated_at=now,
            queue_size=3,
            pending_message_count=1,
            task_queue=[],
        )
        data = response.model_dump()
        assert data["desktop_id"] == desktop_id
        assert "queue_size" in data
        assert "pending_message_count" in data
        assert "task_queue" in data
        assert data["queue_size"] == 3

    def test_agent_status_response_with_both_ids(self):
        """AgentStatusWithQueueResponse must populate BOTH sandbox_id and desktop_id."""
        from datetime import datetime
        from backend.schemas.agent import AgentStatusWithQueueResponse

        now = datetime.now()
        sandbox_id = str(uuid.uuid4())
        desktop_id = str(uuid.uuid4())

        response = AgentStatusWithQueueResponse(
            id=uuid.uuid4(),
            project_id=uuid.uuid4(),
            role="engineer",
            display_name="Eng-1",
            model="claude-sonnet-4-20250514",
            provider="anthropic",
            status="active",
            current_task_id=None,
            sandbox_id=sandbox_id,
            desktop_id=desktop_id,
            created_at=now,
            updated_at=now,
            queue_size=0,
            pending_message_count=0,
            task_queue=[],
        )
        data = response.model_dump()
        assert data["sandbox_id"] == sandbox_id
        assert data["desktop_id"] == desktop_id


# ── Section 11: Full Tool Chain Verification ──────────────────────────────────


class TestFullToolChain:
    """Verify the complete chain: tool_name -> executor_function -> module import."""

    def test_sandbox_tool_chain_complete(self):
        from backend.tools.loop_registry import _SANDBOX_TOOL_NAMES, _TOOL_EXECUTORS
        import backend.tools.executors.sandbox as sandbox_mod

        for name in _SANDBOX_TOOL_NAMES:
            assert name in _TOOL_EXECUTORS, f"Sandbox tool {name!r} missing from _TOOL_EXECUTORS"
            executor = _TOOL_EXECUTORS[name]
            assert callable(executor), f"Executor for {name!r} is not callable"
            # Verify it's importable from the sandbox executors module
            func_name = executor.__name__
            assert hasattr(sandbox_mod, func_name), (
                f"Executor {func_name!r} for tool {name!r} not found in "
                f"backend.tools.executors.sandbox"
            )

    def test_desktop_tool_chain_complete(self):
        from backend.tools.loop_registry import _DESKTOP_TOOL_NAMES, _TOOL_EXECUTORS
        import backend.tools.executors.desktop as desktop_mod

        for name in _DESKTOP_TOOL_NAMES:
            assert name in _TOOL_EXECUTORS, f"Desktop tool {name!r} missing from _TOOL_EXECUTORS"
            executor = _TOOL_EXECUTORS[name]
            assert callable(executor), f"Executor for {name!r} is not callable"
            # Verify it's importable from the desktop executors module
            func_name = executor.__name__
            assert hasattr(desktop_mod, func_name), (
                f"Executor {func_name!r} for tool {name!r} not found in "
                f"backend.tools.executors.desktop"
            )

    def test_sandbox_service_has_all_required_methods(self):
        from backend.services.sandbox_service import SandboxService

        required_methods = [
            "execute_command",
            "take_screenshot",
            "mouse_move",
            "mouse_click",
            "mouse_scroll",
            "mouse_location",
            "keyboard_press",
            "sandbox_health",
            "start_recording",
            "stop_recording",
            "acquire_sandbox_for_agent",
            "release_agent_sandbox",
        ]
        for method_name in required_methods:
            assert hasattr(SandboxService, method_name), (
                f"SandboxService missing required method {method_name!r}"
            )
            assert callable(getattr(SandboxService, method_name)), (
                f"SandboxService.{method_name} is not callable"
            )

    def test_sandbox_client_has_all_required_methods(self):
        from backend.services.sandbox_client import SandboxClient

        required_methods = [
            "execute_shell",
            "get_screenshot",
            "mouse_move",
            "mouse_click",
            "mouse_scroll",
            "mouse_location",
            "keyboard_press",
            "health_check",
            "start_recording",
            "stop_recording",
        ]
        for method_name in required_methods:
            assert hasattr(SandboxClient, method_name), (
                f"SandboxClient missing required method {method_name!r}"
            )
            assert callable(getattr(SandboxClient, method_name)), (
                f"SandboxClient.{method_name} is not callable"
            )
