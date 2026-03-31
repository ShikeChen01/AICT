"""Unit tests for SandboxService — orchestration layer above SandboxClient."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from backend.services.sandbox_client import ShellResult
from backend.tests.sandbox.conftest import make_sandbox


# ── Constants ────────────────────────────────────────────────────────────────

PM_HOST = "10.200.0.5"
PM_PORT = 9090


# ── Helpers ──────────────────────────────────────────────────────────────────

def _fake_settings(**overrides):
    """Return a SimpleNamespace that looks like backend.config.settings.

    Includes all attributes accessed during SandboxService.__init__
    (which creates an OrchestratorClient that reads settings).
    """
    defaults = dict(
        ENV="production",
        sandbox_vm_host="34.172.85.22",
        sandbox_vm_internal_host=PM_HOST,
        sandbox_vm_pool_port=PM_PORT,
        sandbox_vm_master_token="test-master-token",
        # OrchestratorClient checks this to decide GKE vs VM path
        sandbox_orchestrator_host="",
        sandbox_orchestrator_port=8080,
        sandbox_orchestrator_token="",
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _make_service(settings_overrides=None):
    """Create a SandboxService with mocked settings."""
    fake = _fake_settings(**(settings_overrides or {}))
    with patch("backend.services.sandbox_service.settings", fake), \
         patch("backend.services.sandbox_client.settings", fake, create=True):
        from backend.services.sandbox_service import SandboxService
        return SandboxService()


# ── 1. _resolve_host_port — headless ────────────────────────────────────────

class TestResolveHeadless:
    @pytest.mark.asyncio
    async def test_headless_returns_sandbox_host_port(self):
        """Headless sandboxes connect directly — no pool manager proxy."""
        sandbox = make_sandbox(unit_type="headless", host="10.0.0.1", port=8080)

        with patch("backend.services.sandbox_service.settings", _fake_settings()), \
             patch.dict("os.environ", {"ENV": "production", "K_SERVICE": "true"}, clear=False):
            from backend.services.sandbox_service import SandboxService
            svc = SandboxService()
            host, port, prefix, token = await svc._resolve_host_port(sandbox)

        assert host == "10.0.0.1"
        assert port == 8080
        assert prefix == ""
        assert token == sandbox.auth_token

    @pytest.mark.asyncio
    async def test_headless_ignores_pool_manager_settings(self):
        sandbox = make_sandbox(unit_type="headless", host="172.16.0.5", port=7777)

        with patch("backend.services.sandbox_service.settings", _fake_settings()), \
             patch.dict("os.environ", {"ENV": "production", "K_SERVICE": "true"}, clear=False):
            from backend.services.sandbox_service import SandboxService
            svc = SandboxService()
            host, port, prefix, token = await svc._resolve_host_port(sandbox)

        assert host == "172.16.0.5"
        assert port == 7777
        assert prefix == ""
        assert token == sandbox.auth_token


# ── 2. _resolve_host_port — desktop ─────────────────────────────────────────

class TestResolveDesktop:
    @pytest.mark.asyncio
    async def test_desktop_routes_through_pool_manager(self):
        """Desktop sandboxes are proxied via the pool manager."""
        sandbox = make_sandbox(
            unit_type="desktop",
            orchestrator_sandbox_id="desk-abc123",
        )

        with patch("backend.services.sandbox_service.settings", _fake_settings()), \
             patch.dict("os.environ", {"ENV": "production", "K_SERVICE": "true"}, clear=False):
            from backend.services.sandbox_service import SandboxService
            svc = SandboxService()
            host, port, prefix, token = await svc._resolve_host_port(sandbox)

        assert host == PM_HOST
        assert port == PM_PORT
        assert prefix == "/api/sandbox/desk-abc123/proxy"
        assert token == "test-master-token"

    @pytest.mark.asyncio
    async def test_desktop_uses_internal_host_when_available(self):
        sandbox = make_sandbox(unit_type="desktop", orchestrator_sandbox_id="d-999")

        settings = _fake_settings(
            sandbox_vm_internal_host="internal.host.local",
            sandbox_vm_host="external.host.com",
        )
        with patch("backend.services.sandbox_service.settings", settings), \
             patch.dict("os.environ", {"ENV": "production", "K_SERVICE": "true"}, clear=False):
            from backend.services.sandbox_service import SandboxService
            svc = SandboxService()
            host, port, prefix, token = await svc._resolve_host_port(sandbox)

        # Internal host takes precedence
        assert host == "internal.host.local"
        assert token == "test-master-token"

    @pytest.mark.asyncio
    async def test_desktop_falls_back_to_public_host(self):
        sandbox = make_sandbox(unit_type="desktop", orchestrator_sandbox_id="d-111")

        settings = _fake_settings(
            sandbox_vm_internal_host="",  # empty -> fall back
            sandbox_vm_host="public.host.com",
        )
        with patch("backend.services.sandbox_service.settings", settings), \
             patch.dict("os.environ", {"ENV": "production", "K_SERVICE": "true"}, clear=False):
            from backend.services.sandbox_service import SandboxService
            svc = SandboxService()
            host, port, prefix, token = await svc._resolve_host_port(sandbox)

        assert host == "public.host.com"
        assert token == "test-master-token"


# ── 3. Service methods delegate to client ────────────────────────────────────

class TestDelegation:
    """Each service method should call the corresponding SandboxClient method
    with the resolved (host, port, prefix) and the sandbox auth_token."""

    @pytest.fixture
    def sandbox(self):
        return make_sandbox(
            unit_type="headless",
            host="10.0.0.1",
            port=8080,
            auth_token="tok-delegate",
        )

    @pytest.fixture
    def svc_and_client(self):
        """Yield a SandboxService with its _client fully mocked."""
        fake = _fake_settings()
        with patch("backend.services.sandbox_service.settings", fake), \
             patch.dict("os.environ", {"ENV": "production", "K_SERVICE": "true"}, clear=False):
            from backend.services.sandbox_service import SandboxService
            svc = SandboxService()

            mock_client = AsyncMock()
            mock_client.execute_shell = AsyncMock(
                return_value=ShellResult(stdout="ok", exit_code=0),
            )
            mock_client.health_check = AsyncMock(return_value={"status": "ok"})
            mock_client.get_screenshot = AsyncMock(return_value=b"\x89PNG")
            mock_client.mouse_move = AsyncMock(return_value={"ok": True})
            mock_client.mouse_click = AsyncMock(return_value={"ok": True})
            mock_client.mouse_scroll = AsyncMock(return_value={"ok": True})
            mock_client.mouse_location = AsyncMock(return_value={"x": 0, "y": 0})
            mock_client.keyboard_press = AsyncMock(return_value={"ok": True})
            mock_client.start_recording = AsyncMock(return_value={"status": "recording"})
            mock_client.stop_recording = AsyncMock(return_value=b"\x00vid")

            svc._client = mock_client
            yield svc, mock_client

    @pytest.mark.asyncio
    async def test_execute_command(self, svc_and_client, sandbox):
        svc, client = svc_and_client
        result = await svc.execute_command(sandbox, "ls -la", timeout=60)

        client.execute_shell.assert_awaited_once_with(
            "10.0.0.1", 8080, "tok-delegate", "ls -la", 60,
            path_prefix="",
        )
        assert isinstance(result, ShellResult)

    @pytest.mark.asyncio
    async def test_take_screenshot(self, svc_and_client, sandbox):
        svc, client = svc_and_client
        result = await svc.take_screenshot(sandbox)

        client.get_screenshot.assert_awaited_once_with(
            "10.0.0.1", 8080, "tok-delegate", path_prefix="",
        )
        assert result == b"\x89PNG"

    @pytest.mark.asyncio
    async def test_mouse_move(self, svc_and_client, sandbox):
        svc, client = svc_and_client
        await svc.mouse_move(sandbox, 100, 200)

        client.mouse_move.assert_awaited_once_with(
            "10.0.0.1", 8080, "tok-delegate", 100, 200, path_prefix="",
        )

    @pytest.mark.asyncio
    async def test_mouse_click(self, svc_and_client, sandbox):
        svc, client = svc_and_client
        await svc.mouse_click(sandbox, x=50, y=75, button=2, click_type="double")

        client.mouse_click.assert_awaited_once_with(
            "10.0.0.1", 8080, "tok-delegate",
            x=50, y=75, button=2, click_type="double",
            path_prefix="",
        )

    @pytest.mark.asyncio
    async def test_mouse_scroll(self, svc_and_client, sandbox):
        svc, client = svc_and_client
        await svc.mouse_scroll(sandbox, direction="up", clicks=5)

        client.mouse_scroll.assert_awaited_once_with(
            "10.0.0.1", 8080, "tok-delegate",
            x=None, y=None, direction="up", clicks=5,
            path_prefix="",
        )

    @pytest.mark.asyncio
    async def test_mouse_location(self, svc_and_client, sandbox):
        svc, client = svc_and_client
        result = await svc.mouse_location(sandbox)

        client.mouse_location.assert_awaited_once_with(
            "10.0.0.1", 8080, "tok-delegate", path_prefix="",
        )
        assert result == {"x": 0, "y": 0}

    @pytest.mark.asyncio
    async def test_keyboard_press(self, svc_and_client, sandbox):
        svc, client = svc_and_client
        await svc.keyboard_press(sandbox, keys="ctrl+s")

        client.keyboard_press.assert_awaited_once_with(
            "10.0.0.1", 8080, "tok-delegate",
            keys="ctrl+s", text=None,
            path_prefix="",
        )

    @pytest.mark.asyncio
    async def test_sandbox_health(self, svc_and_client, sandbox):
        svc, client = svc_and_client
        result = await svc.sandbox_health(sandbox)

        client.health_check.assert_awaited_once_with(
            "10.0.0.1", 8080, "tok-delegate", path_prefix="",
        )
        assert result == {"status": "ok"}

    @pytest.mark.asyncio
    async def test_start_recording(self, svc_and_client, sandbox):
        svc, client = svc_and_client
        result = await svc.start_recording(sandbox)

        client.start_recording.assert_awaited_once_with(
            "10.0.0.1", 8080, "tok-delegate", path_prefix="",
        )
        assert result == {"status": "recording"}

    @pytest.mark.asyncio
    async def test_stop_recording(self, svc_and_client, sandbox):
        svc, client = svc_and_client
        result = await svc.stop_recording(sandbox)

        client.stop_recording.assert_awaited_once_with(
            "10.0.0.1", 8080, "tok-delegate", path_prefix="",
        )
        assert result == b"\x00vid"


# ── 4. Auth token forwarding ────────────────────────────────────────────────

class TestAuthTokenForwarding:
    """Service must pass sandbox.auth_token to every client call."""

    @pytest.mark.asyncio
    async def test_auth_token_passed_to_client(self):
        sandbox = make_sandbox(auth_token="secret-token-xyz")

        fake = _fake_settings()
        with patch("backend.services.sandbox_service.settings", fake), \
             patch.dict("os.environ", {"ENV": "production", "K_SERVICE": "true"}, clear=False):
            from backend.services.sandbox_service import SandboxService
            svc = SandboxService()

            mock_client = AsyncMock()
            mock_client.get_screenshot = AsyncMock(return_value=b"img")
            svc._client = mock_client

            await svc.take_screenshot(sandbox)

            call = mock_client.get_screenshot.call_args
            # auth_token is the 3rd positional arg: (host, port, auth_token, ...)
            assert call[0][2] == "secret-token-xyz"

    @pytest.mark.asyncio
    async def test_auth_token_forwarded_for_shell(self):
        sandbox = make_sandbox(auth_token="shell-tok-42")

        fake = _fake_settings()
        with patch("backend.services.sandbox_service.settings", fake), \
             patch.dict("os.environ", {"ENV": "production", "K_SERVICE": "true"}, clear=False):
            from backend.services.sandbox_service import SandboxService
            svc = SandboxService()

            mock_client = AsyncMock()
            mock_client.execute_shell = AsyncMock(
                return_value=ShellResult(stdout="", exit_code=0),
            )
            svc._client = mock_client

            await svc.execute_command(sandbox, "whoami")

            call = mock_client.execute_shell.call_args
            assert call[0][2] == "shell-tok-42"

    @pytest.mark.asyncio
    async def test_desktop_uses_master_token(self):
        """Desktop sandboxes use the pool manager master token, not the
        sandbox's individual auth_token. The pool manager's require_master_token
        validates this before forwarding to the sandbox VM."""
        sandbox = make_sandbox(
            unit_type="desktop",
            auth_token="desktop-tok",
            orchestrator_sandbox_id="desk-proxy-1",
        )

        fake = _fake_settings()
        with patch("backend.services.sandbox_service.settings", fake), \
             patch.dict("os.environ", {"ENV": "production", "K_SERVICE": "true"}, clear=False):
            from backend.services.sandbox_service import SandboxService
            svc = SandboxService()

            mock_client = AsyncMock()
            mock_client.health_check = AsyncMock(return_value={"status": "ok"})
            svc._client = mock_client

            await svc.sandbox_health(sandbox)

            call = mock_client.health_check.call_args
            # Desktop uses master token, NOT sandbox.auth_token
            assert call[0][2] == "test-master-token"
            # And path_prefix routes through pool manager
            assert call[1]["path_prefix"] == "/api/sandbox/desk-proxy-1/proxy"
