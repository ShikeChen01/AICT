"""
Tests for WebSocket events and manager.
"""

import uuid
from datetime import datetime

import pytest

from backend.websocket.events import (
    EventType,
    WebSocketEvent,
    GMStatusPayload,
    TaskPayload,
    AgentStatusPayload,
    create_gm_status_event,
    create_task_created_event,
    create_task_update_event,
    create_agent_status_event,
)
from backend.websocket.manager import Channel, ConnectionInfo, WebSocketManager


class MockWebSocket:
    """Mock WebSocket for testing."""

    def __init__(self):
        self.sent_messages = []
        self.client_state = type("State", (), {"CONNECTED": "connected"})()
        self.client_state = type("State", (), {"value": "connected"})()

    async def accept(self):
        pass

    async def send_json(self, data):
        self.sent_messages.append(data)

    async def receive_json(self):
        return {"type": "ping"}

    async def close(self, code=None, reason=None):
        pass


class TestEventTypes:
    """Test WebSocket event types and payloads."""

    def test_event_type_values(self):
        assert EventType.GM_STATUS.value == "gm_status"
        assert EventType.TASK_CREATED.value == "task_created"
        assert EventType.TASK_UPDATE.value == "task_update"
        assert EventType.AGENT_STATUS.value == "agent_status"

    def test_websocket_event_structure(self):
        event = WebSocketEvent(
            type=EventType.GM_STATUS,
            data={"test": "value"},
        )
        assert event.type == EventType.GM_STATUS
        assert event.data == {"test": "value"}
        assert event.timestamp is not None

    def test_gm_status_payload(self):
        payload = GMStatusPayload(
            project_id=uuid.uuid4(),
            status="busy",
        )
        assert payload.status == "busy"

    def test_task_payload(self):
        payload = TaskPayload(
            id=uuid.uuid4(),
            project_id=uuid.uuid4(),
            title="Test Task",
            description="Description",
            status="backlog",
            critical=5,
            urgent=5,
            assigned_agent_id=None,
            module_path=None,
            git_branch=None,
            pr_url=None,
            parent_task_id=None,
            created_by_id=None,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        assert payload.title == "Test Task"
        assert payload.status == "backlog"

    def test_agent_status_payload(self):
        payload = AgentStatusPayload(
            id=uuid.uuid4(),
            project_id=uuid.uuid4(),
            role="engineer",
            display_name="Engineer-1",
            status="active",
            current_task_id=None,
        )
        assert payload.role == "engineer"
        assert payload.status == "active"


class TestEventFactories:
    """Test event factory functions."""

    def test_create_gm_status_event(self):
        project_id = uuid.uuid4()
        event = create_gm_status_event(project_id, "busy")

        assert event.type == EventType.GM_STATUS
        assert event.data["status"] == "busy"

    def test_create_task_created_event(self):
        task = type("Task", (), {
            "id": uuid.uuid4(),
            "project_id": uuid.uuid4(),
            "title": "New Task",
            "description": "Desc",
            "status": "backlog",
            "critical": 5,
            "urgent": 5,
            "assigned_agent_id": None,
            "module_path": None,
            "git_branch": None,
            "pr_url": None,
            "parent_task_id": None,
            "created_by_id": None,
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
        })()

        event = create_task_created_event(task)
        assert event.type == EventType.TASK_CREATED
        assert event.data["title"] == "New Task"

    def test_create_task_update_event(self):
        task = type("Task", (), {
            "id": uuid.uuid4(),
            "project_id": uuid.uuid4(),
            "title": "Updated Task",
            "description": "Desc",
            "status": "in_progress",
            "critical": 3,
            "urgent": 2,
            "assigned_agent_id": uuid.uuid4(),
            "module_path": "backend/api",
            "git_branch": "feature/test",
            "pr_url": None,
            "parent_task_id": None,
            "created_by_id": None,
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
        })()

        event = create_task_update_event(task)
        assert event.type == EventType.TASK_UPDATE
        assert event.data["status"] == "in_progress"

    def test_create_agent_status_event(self):
        agent = type("Agent", (), {
            "id": uuid.uuid4(),
            "project_id": uuid.uuid4(),
            "role": "cto",
            "display_name": "CTO",
            "status": "busy",
            "current_task_id": uuid.uuid4(),
        })()

        event = create_agent_status_event(agent)
        assert event.type == EventType.AGENT_STATUS
        assert event.data["role"] == "cto"
        assert event.data["status"] == "busy"


class TestConnectionInfo:
    """Test ConnectionInfo class (docs channels: agent_stream, messages, kanban, agents, activity)."""

    def test_subscribe(self):
        ws = MockWebSocket()
        conn = ConnectionInfo(ws, uuid.uuid4())

        conn.subscribe(Channel.MESSAGES)
        assert Channel.MESSAGES in conn.channels

    def test_subscribe_all(self):
        ws = MockWebSocket()
        conn = ConnectionInfo(ws, uuid.uuid4())

        conn.subscribe(Channel.ALL)
        assert Channel.MESSAGES in conn.channels
        assert Channel.KANBAN in conn.channels
        assert Channel.AGENT_STREAM in conn.channels

    def test_unsubscribe(self):
        ws = MockWebSocket()
        conn = ConnectionInfo(ws, uuid.uuid4())

        conn.subscribe(Channel.MESSAGES)
        conn.unsubscribe(Channel.MESSAGES)
        assert Channel.MESSAGES not in conn.channels

    def test_is_subscribed(self):
        ws = MockWebSocket()
        conn = ConnectionInfo(ws, uuid.uuid4())

        conn.subscribe(Channel.KANBAN)
        assert conn.is_subscribed(Channel.KANBAN) is True
        assert conn.is_subscribed(Channel.MESSAGES) is False


class TestWebSocketManager:
    """Test WebSocketManager class."""

    @pytest.fixture
    def manager(self):
        return WebSocketManager()

    async def test_connect(self, manager):
        ws = MockWebSocket()
        project_id = uuid.uuid4()

        conn_id = await manager.connect(ws, project_id)

        assert conn_id is not None
        assert manager.active_connections == 1

    async def test_disconnect(self, manager):
        ws = MockWebSocket()
        project_id = uuid.uuid4()

        await manager.connect(ws, project_id)
        await manager.disconnect(ws)

        assert manager.active_connections == 0

    async def test_subscribe_after_connect(self, manager):
        ws = MockWebSocket()
        project_id = uuid.uuid4()

        await manager.connect(ws, project_id, [Channel.MESSAGES])
        await manager.subscribe(ws, Channel.KANBAN)

        conn_id = manager._connection_id(ws)
        assert Channel.KANBAN in manager._connections[conn_id].channels

    async def test_unsubscribe(self, manager):
        ws = MockWebSocket()
        project_id = uuid.uuid4()

        await manager.connect(ws, project_id)
        await manager.unsubscribe(ws, Channel.MESSAGES)

        conn_id = manager._connection_id(ws)
        assert Channel.MESSAGES not in manager._connections[conn_id].channels

    async def test_active_connections_count(self, manager):
        ws1 = MockWebSocket()
        ws2 = MockWebSocket()
        project_id = uuid.uuid4()

        await manager.connect(ws1, project_id)
        await manager.connect(ws2, project_id)

        assert manager.active_connections == 2

        await manager.disconnect(ws1)
        assert manager.active_connections == 1
