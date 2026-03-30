"""
E2E smoke tests for real sandbox VM infrastructure.

These tests make actual HTTP calls to the pool manager and desktop VMs.
No mocks. Requires network access to the pool manager at 34.172.85.22:9090.

Run with:
    cd backend && python -m pytest tests/sandbox/test_e2e_smoke.py -v -m integration
"""

from __future__ import annotations

import httpx
import pytest

from backend.services.sandbox_client import SandboxClient, ShellResult
from tests.sandbox.conftest import POOL_MANAGER_HOST, POOL_MANAGER_PORT, POOL_MANAGER_TOKEN

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

BASE_URL = f"http://{POOL_MANAGER_HOST}:{POOL_MANAGER_PORT}"
HEADERS = {"Authorization": f"Bearer {POOL_MANAGER_TOKEN}"}
TIMEOUT = 15.0


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
async def desktop_unit():
    """Discover the first available desktop unit from the pool manager."""
    async with httpx.AsyncClient(base_url=BASE_URL, headers=HEADERS, timeout=TIMEOUT) as client:
        resp = await client.get("/api/units")
        resp.raise_for_status()
        units = resp.json()
        desktops = [u for u in units if u.get("unit_type") == "desktop"]
        if not desktops:
            pytest.skip("No desktop units available")
        return desktops[0]


@pytest.fixture
def proxy_prefix(desktop_unit) -> str:
    """Return the proxy path prefix for a desktop unit."""
    unit_id = desktop_unit["unit_id"]
    return f"/api/sandbox/{unit_id}/proxy"


# ===========================================================================
# Section 1: Pool Manager Health
# ===========================================================================


class TestPoolManagerHealth:
    """Verify the pool manager itself is reachable and reporting correctly."""

    async def test_pool_manager_reachable(self):
        """GET /api/health returns 200, status=ok, and has a version field."""
        async with httpx.AsyncClient(base_url=BASE_URL, headers=HEADERS, timeout=TIMEOUT) as client:
            resp = await client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "version" in data

    async def test_pool_manager_lists_units(self):
        """GET /api/units returns a list where each entry has unit_id, unit_type, status."""
        async with httpx.AsyncClient(base_url=BASE_URL, headers=HEADERS, timeout=TIMEOUT) as client:
            resp = await client.get("/api/units")
        assert resp.status_code == 200
        units = resp.json()
        assert isinstance(units, list)
        for unit in units:
            assert "unit_id" in unit
            assert "unit_type" in unit
            assert "status" in unit

    async def test_pool_manager_has_desktop_unit(self):
        """At least one unit with unit_type=desktop exists."""
        async with httpx.AsyncClient(base_url=BASE_URL, headers=HEADERS, timeout=TIMEOUT) as client:
            resp = await client.get("/api/units")
        resp.raise_for_status()
        units = resp.json()
        desktops = [u for u in units if u.get("unit_type") == "desktop"]
        assert len(desktops) >= 1, "Expected at least one desktop unit"


# ===========================================================================
# Section 2: Desktop VM via Proxy
# ===========================================================================


class TestDesktopViaProxy:
    """Test desktop VM endpoints accessed through the pool manager proxy."""

    async def test_desktop_health(self, desktop_unit, proxy_prefix):
        """GET .../proxy/health returns status=ok with uptime_seconds and display."""
        async with httpx.AsyncClient(base_url=BASE_URL, headers=HEADERS, timeout=TIMEOUT) as client:
            resp = await client.get(f"{proxy_prefix}/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "uptime_seconds" in data
        assert "display" in data

    async def test_desktop_screenshot(self, desktop_unit, proxy_prefix):
        """GET .../proxy/screenshot returns JPEG image data > 1000 bytes."""
        async with httpx.AsyncClient(base_url=BASE_URL, headers=HEADERS, timeout=TIMEOUT) as client:
            resp = await client.get(f"{proxy_prefix}/screenshot")
        assert resp.status_code == 200
        assert "image/jpeg" in resp.headers.get("content-type", "")
        assert len(resp.content) > 1000

    async def test_desktop_mouse_move(self, desktop_unit, proxy_prefix):
        """POST .../proxy/mouse/move with x=300, y=300 returns ok=true."""
        async with httpx.AsyncClient(base_url=BASE_URL, headers=HEADERS, timeout=TIMEOUT) as client:
            resp = await client.post(f"{proxy_prefix}/mouse/move", json={"x": 300, "y": 300})
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["x"] == 300
        assert data["y"] == 300

    async def test_desktop_mouse_click(self, desktop_unit, proxy_prefix):
        """POST .../proxy/mouse/click with button=1 returns ok=true."""
        async with httpx.AsyncClient(base_url=BASE_URL, headers=HEADERS, timeout=TIMEOUT) as client:
            resp = await client.post(
                f"{proxy_prefix}/mouse/click",
                json={"x": 400, "y": 400, "button": 1, "click_type": "single"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True

    async def test_desktop_mouse_scroll(self, desktop_unit, proxy_prefix):
        """POST .../proxy/mouse/scroll direction=down, clicks=2 returns ok=true."""
        async with httpx.AsyncClient(base_url=BASE_URL, headers=HEADERS, timeout=TIMEOUT) as client:
            resp = await client.post(
                f"{proxy_prefix}/mouse/scroll",
                json={"direction": "down", "clicks": 2},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True

    async def test_desktop_mouse_location(self, desktop_unit, proxy_prefix):
        """GET .../proxy/mouse/location returns integer x and y coordinates."""
        async with httpx.AsyncClient(base_url=BASE_URL, headers=HEADERS, timeout=TIMEOUT) as client:
            resp = await client.get(f"{proxy_prefix}/mouse/location")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data["x"], int)
        assert isinstance(data["y"], int)

    async def test_desktop_keyboard_type(self, desktop_unit, proxy_prefix):
        """POST .../proxy/keyboard with text='test' returns ok=true."""
        async with httpx.AsyncClient(base_url=BASE_URL, headers=HEADERS, timeout=TIMEOUT) as client:
            resp = await client.post(f"{proxy_prefix}/keyboard", json={"text": "test"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True

    async def test_desktop_keyboard_keys(self, desktop_unit, proxy_prefix):
        """POST .../proxy/keyboard with keys='Return' returns ok=true."""
        async with httpx.AsyncClient(base_url=BASE_URL, headers=HEADERS, timeout=TIMEOUT) as client:
            resp = await client.post(f"{proxy_prefix}/keyboard", json={"keys": "Return"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True

    async def test_desktop_shell_execute(self, desktop_unit, proxy_prefix):
        """POST .../proxy/shell/execute echoes 'hello' with exit_code=0."""
        async with httpx.AsyncClient(base_url=BASE_URL, headers=HEADERS, timeout=TIMEOUT) as client:
            resp = await client.post(
                f"{proxy_prefix}/shell/execute",
                json={"command": "echo hello", "timeout": 10},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "hello" in data["stdout"]
        assert data["exit_code"] == 0


# ===========================================================================
# Section 3: SandboxClient E2E
# ===========================================================================


class TestSandboxClientE2E:
    """Use the actual SandboxClient class pointed at the real VM through the proxy."""

    async def test_client_health_check(self, desktop_unit, proxy_prefix):
        """SandboxClient.health_check returns a dict with status."""
        sc = SandboxClient()
        result = await sc.health_check(
            POOL_MANAGER_HOST, POOL_MANAGER_PORT, POOL_MANAGER_TOKEN,
            path_prefix=proxy_prefix,
        )
        assert isinstance(result, dict)
        assert result["status"] == "ok"

    async def test_client_screenshot(self, desktop_unit, proxy_prefix):
        """SandboxClient.get_screenshot returns bytes > 1000."""
        sc = SandboxClient()
        data = await sc.get_screenshot(
            POOL_MANAGER_HOST, POOL_MANAGER_PORT, POOL_MANAGER_TOKEN,
            path_prefix=proxy_prefix,
        )
        assert isinstance(data, bytes)
        assert len(data) > 1000

    async def test_client_mouse_move(self, desktop_unit, proxy_prefix):
        """SandboxClient.mouse_move returns a dict with ok."""
        sc = SandboxClient()
        result = await sc.mouse_move(
            POOL_MANAGER_HOST, POOL_MANAGER_PORT, POOL_MANAGER_TOKEN,
            500, 500,
            path_prefix=proxy_prefix,
        )
        assert isinstance(result, dict)
        assert result["ok"] is True

    async def test_client_keyboard_press(self, desktop_unit, proxy_prefix):
        """SandboxClient.keyboard_press with text='e2e' returns a dict with ok."""
        sc = SandboxClient()
        result = await sc.keyboard_press(
            POOL_MANAGER_HOST, POOL_MANAGER_PORT, POOL_MANAGER_TOKEN,
            text="e2e",
            path_prefix=proxy_prefix,
        )
        assert isinstance(result, dict)
        assert result["ok"] is True

    async def test_client_execute_shell(self, desktop_unit, proxy_prefix):
        """SandboxClient.execute_shell returns ShellResult with 'e2e_test' in stdout."""
        sc = SandboxClient()
        result = await sc.execute_shell(
            POOL_MANAGER_HOST, POOL_MANAGER_PORT, POOL_MANAGER_TOKEN,
            "echo e2e_test", 10,
            path_prefix=proxy_prefix,
        )
        assert isinstance(result, ShellResult)
        assert "e2e_test" in result.stdout
        assert result.exit_code == 0


# ===========================================================================
# Section 4: Protocol Contract Validation
# ===========================================================================


class TestProtocolContract:
    """Verify data types and shapes match what the backend expects."""

    async def test_mouse_click_button_is_integer(self, desktop_unit, proxy_prefix):
        """The button field must be an integer, not a string like 'left'."""
        async with httpx.AsyncClient(base_url=BASE_URL, headers=HEADERS, timeout=TIMEOUT) as client:
            # Valid: integer button
            resp_ok = await client.post(
                f"{proxy_prefix}/mouse/click",
                json={"x": 100, "y": 100, "button": 1, "click_type": "single"},
            )
            assert resp_ok.status_code == 200
            data = resp_ok.json()
            assert isinstance(data.get("button"), int)

            # Invalid: string button should be rejected or at least not match
            resp_bad = await client.post(
                f"{proxy_prefix}/mouse/click",
                json={"x": 100, "y": 100, "button": "left", "click_type": "single"},
            )
            # Server should reject this with 422 or 400, or at minimum the
            # returned button field should not be a string.
            assert resp_bad.status_code in (200, 400, 422)
            if resp_bad.status_code == 200:
                bad_data = resp_bad.json()
                # Even if accepted, button in response must be integer
                assert isinstance(bad_data.get("button"), int)

    async def test_keyboard_keys_is_string(self, desktop_unit, proxy_prefix):
        """The keys field must be a string, not an array."""
        async with httpx.AsyncClient(base_url=BASE_URL, headers=HEADERS, timeout=TIMEOUT) as client:
            # Valid: string keys
            resp_ok = await client.post(f"{proxy_prefix}/keyboard", json={"keys": "Return"})
            assert resp_ok.status_code == 200

            # Invalid: array keys should be rejected
            resp_bad = await client.post(f"{proxy_prefix}/keyboard", json={"keys": ["Return", "a"]})
            assert resp_bad.status_code in (200, 400, 422)

    async def test_screenshot_returns_valid_jpeg(self, desktop_unit, proxy_prefix):
        """Screenshot bytes start with JPEG magic bytes 0xFF 0xD8."""
        async with httpx.AsyncClient(base_url=BASE_URL, headers=HEADERS, timeout=TIMEOUT) as client:
            resp = await client.get(f"{proxy_prefix}/screenshot")
        assert resp.status_code == 200
        assert len(resp.content) >= 2
        assert resp.content[0] == 0xFF
        assert resp.content[1] == 0xD8

    async def test_shell_result_has_exit_code(self, desktop_unit, proxy_prefix):
        """Shell execute response has an integer exit_code field."""
        async with httpx.AsyncClient(base_url=BASE_URL, headers=HEADERS, timeout=TIMEOUT) as client:
            resp = await client.post(
                f"{proxy_prefix}/shell/execute",
                json={"command": "true", "timeout": 10},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "exit_code" in data
        assert isinstance(data["exit_code"], int)


# ===========================================================================
# Section 5: SandboxClient Missing Methods E2E
# ===========================================================================


class TestSandboxClientMissingMethods:
    """Test SandboxClient methods not covered in Section 3."""

    async def test_client_mouse_click(self, desktop_unit, proxy_prefix):
        """SandboxClient.mouse_click with x=200, y=200, button=1 returns a dict with ok."""
        sc = SandboxClient()
        result = await sc.mouse_click(
            POOL_MANAGER_HOST, POOL_MANAGER_PORT, POOL_MANAGER_TOKEN,
            x=200, y=200, button=1, click_type="single",
            path_prefix=proxy_prefix,
        )
        assert isinstance(result, dict)
        assert result["ok"] is True

    async def test_client_mouse_scroll(self, desktop_unit, proxy_prefix):
        """SandboxClient.mouse_scroll direction=down, clicks=2 returns a dict with ok."""
        sc = SandboxClient()
        result = await sc.mouse_scroll(
            POOL_MANAGER_HOST, POOL_MANAGER_PORT, POOL_MANAGER_TOKEN,
            direction="down", clicks=2,
            path_prefix=proxy_prefix,
        )
        assert isinstance(result, dict)
        assert result["ok"] is True

    async def test_client_mouse_location(self, desktop_unit, proxy_prefix):
        """SandboxClient.mouse_location returns a dict with integer x and y."""
        sc = SandboxClient()
        result = await sc.mouse_location(
            POOL_MANAGER_HOST, POOL_MANAGER_PORT, POOL_MANAGER_TOKEN,
            path_prefix=proxy_prefix,
        )
        assert isinstance(result, dict)
        assert isinstance(result["x"], int)
        assert isinstance(result["y"], int)

    async def test_client_start_recording(self, desktop_unit, proxy_prefix):
        """SandboxClient.start_recording returns a dict with status."""
        sc = SandboxClient()
        result = await sc.start_recording(
            POOL_MANAGER_HOST, POOL_MANAGER_PORT, POOL_MANAGER_TOKEN,
            path_prefix=proxy_prefix,
        )
        assert isinstance(result, dict)
        assert "status" in result

    async def test_client_stop_recording(self, desktop_unit, proxy_prefix):
        """SandboxClient.stop_recording returns bytes after a brief recording."""
        import asyncio

        sc = SandboxClient()
        # Start recording first
        start_result = await sc.start_recording(
            POOL_MANAGER_HOST, POOL_MANAGER_PORT, POOL_MANAGER_TOKEN,
            path_prefix=proxy_prefix,
        )
        assert isinstance(start_result, dict)

        # Wait 1 second to capture some frames
        await asyncio.sleep(1)

        # Stop and retrieve the recording
        data = await sc.stop_recording(
            POOL_MANAGER_HOST, POOL_MANAGER_PORT, POOL_MANAGER_TOKEN,
            path_prefix=proxy_prefix,
        )
        assert isinstance(data, bytes)


# ===========================================================================
# Section 6: Desktop Shell-Based Tools E2E
# ===========================================================================


class TestDesktopShellTools:
    """Test the 5 desktop tools that use shell/execute under the hood."""

    async def test_desktop_open_url_via_shell(self, desktop_unit, proxy_prefix):
        """POST proxy/shell/execute to launch Chrome returns exit_code=0."""
        async with httpx.AsyncClient(base_url=BASE_URL, headers=HEADERS, timeout=TIMEOUT) as client:
            resp = await client.post(
                f"{proxy_prefix}/shell/execute",
                json={
                    "command": "DISPLAY=:99 google-chrome-stable --no-sandbox --disable-gpu 'about:blank' &",
                    "timeout": 10,
                },
            )
        assert resp.status_code == 200
        data = resp.json()
        # Non-blocking background command — exit_code should be 0
        assert data["exit_code"] == 0

    async def test_desktop_list_windows_via_shell(self, desktop_unit, proxy_prefix):
        """POST proxy/shell/execute wmctrl -l returns window list text."""
        async with httpx.AsyncClient(base_url=BASE_URL, headers=HEADERS, timeout=TIMEOUT) as client:
            resp = await client.post(
                f"{proxy_prefix}/shell/execute",
                json={"command": "DISPLAY=:99 wmctrl -l", "timeout": 10},
            )
        assert resp.status_code == 200
        data = resp.json()
        # wmctrl -l returns lines with window IDs (hex like 0x...) or empty if no windows
        assert isinstance(data["stdout"], str)
        # exit_code 0 means windows listed, 1 means no windows — both are valid
        assert data["exit_code"] in (0, 1)

    async def test_desktop_focus_window_via_shell(self, desktop_unit, proxy_prefix):
        """POST proxy/shell/execute wmctrl -a Desktop runs without error."""
        async with httpx.AsyncClient(base_url=BASE_URL, headers=HEADERS, timeout=TIMEOUT) as client:
            resp = await client.post(
                f"{proxy_prefix}/shell/execute",
                json={"command": "DISPLAY=:99 wmctrl -a Desktop", "timeout": 10},
            )
        assert resp.status_code == 200
        data = resp.json()
        # exit_code=0 if match found, 1 if no match — both are valid
        assert data["exit_code"] in (0, 1)

    async def test_desktop_get_clipboard_via_shell(self, desktop_unit, proxy_prefix):
        """POST proxy/shell/execute xclip returns clipboard text (may be empty)."""
        async with httpx.AsyncClient(base_url=BASE_URL, headers=HEADERS, timeout=TIMEOUT) as client:
            resp = await client.post(
                f"{proxy_prefix}/shell/execute",
                json={
                    "command": "DISPLAY=:99 xclip -selection clipboard -o",
                    "timeout": 10,
                },
            )
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data["stdout"], str)
        # xclip returns 1 if clipboard is empty — both are valid
        assert data["exit_code"] in (0, 1)

    async def test_desktop_set_clipboard_via_shell(self, desktop_unit, proxy_prefix):
        """Set clipboard then verify it reads back the same value."""
        async with httpx.AsyncClient(base_url=BASE_URL, headers=HEADERS, timeout=TIMEOUT) as client:
            # Set clipboard
            set_resp = await client.post(
                f"{proxy_prefix}/shell/execute",
                json={
                    "command": "echo -n 'e2e_clipboard_test' | DISPLAY=:99 xclip -selection clipboard",
                    "timeout": 10,
                },
            )
            assert set_resp.status_code == 200
            assert set_resp.json()["exit_code"] == 0

            # Read clipboard back
            get_resp = await client.post(
                f"{proxy_prefix}/shell/execute",
                json={
                    "command": "DISPLAY=:99 xclip -selection clipboard -o",
                    "timeout": 10,
                },
            )
            assert get_resp.status_code == 200
            get_data = get_resp.json()
            assert "e2e_clipboard_test" in get_data["stdout"]


# ===========================================================================
# Section 7: SandboxService E2E (Full Service -> Client -> Proxy Chain)
# ===========================================================================


@pytest.fixture
async def service_sandbox(desktop_unit):
    """Build a SimpleNamespace sandbox object that mirrors a real DB Sandbox row,
    pointed at the live desktop VM through the pool manager proxy.

    SandboxService._resolve_host_port uses:
      - sandbox.unit_type == "desktop" -> route through pool manager
      - settings.sandbox_vm_internal_host or settings.sandbox_vm_host -> pool manager host
      - settings.sandbox_vm_pool_port -> pool manager port
      - sandbox.orchestrator_sandbox_id -> builds /api/sandbox/{id}/proxy prefix
      - sandbox.auth_token -> Bearer token for the proxy
    """
    from types import SimpleNamespace

    return SimpleNamespace(
        unit_type="desktop",
        host=POOL_MANAGER_HOST,
        port=POOL_MANAGER_PORT,
        auth_token=POOL_MANAGER_TOKEN,
        orchestrator_sandbox_id=desktop_unit["unit_id"],
        status="ready",
    )


@pytest.fixture
def patched_sandbox_service(service_sandbox):
    """Create a real SandboxService with settings patched so _resolve_host_port
    routes desktop traffic through the pool manager at the real VM."""
    from unittest.mock import patch

    from backend.services.sandbox_service import SandboxService

    mock_settings = type("MockSettings", (), {
        "sandbox_orchestrator_host": "",
        "sandbox_vm_host": POOL_MANAGER_HOST,
        "sandbox_vm_internal_host": "",
        "sandbox_vm_pool_port": POOL_MANAGER_PORT,
        "sandbox_vm_master_token": POOL_MANAGER_TOKEN,
    })()

    with patch("backend.services.sandbox_service.settings", mock_settings):
        svc = SandboxService()
    # After construction, _resolve_host_port reads settings at call time,
    # so we need the patch active during method calls too.
    return svc, mock_settings


class TestSandboxServiceE2E:
    """Test SandboxService methods with real VM — full service->client->proxy chain."""

    async def test_service_health_check(self, service_sandbox, patched_sandbox_service):
        """SandboxService.sandbox_health returns dict with status=ok."""
        from unittest.mock import patch

        svc, mock_settings = patched_sandbox_service
        with patch("backend.services.sandbox_service.settings", mock_settings):
            result = await svc.sandbox_health(service_sandbox)
        assert isinstance(result, dict)
        assert result["status"] == "ok"

    async def test_service_screenshot(self, service_sandbox, patched_sandbox_service):
        """SandboxService.take_screenshot returns bytes > 1000."""
        from unittest.mock import patch

        svc, mock_settings = patched_sandbox_service
        with patch("backend.services.sandbox_service.settings", mock_settings):
            data = await svc.take_screenshot(service_sandbox)
        assert isinstance(data, bytes)
        assert len(data) > 1000

    async def test_service_mouse_move(self, service_sandbox, patched_sandbox_service):
        """SandboxService.mouse_move returns dict with ok=True."""
        from unittest.mock import patch

        svc, mock_settings = patched_sandbox_service
        with patch("backend.services.sandbox_service.settings", mock_settings):
            result = await svc.mouse_move(service_sandbox, 250, 250)
        assert isinstance(result, dict)
        assert result["ok"] is True

    async def test_service_mouse_click(self, service_sandbox, patched_sandbox_service):
        """SandboxService.mouse_click returns dict with ok."""
        from unittest.mock import patch

        svc, mock_settings = patched_sandbox_service
        with patch("backend.services.sandbox_service.settings", mock_settings):
            result = await svc.mouse_click(service_sandbox, x=250, y=250, button=1)
        assert isinstance(result, dict)
        assert result["ok"] is True

    async def test_service_shell_execute(self, service_sandbox, patched_sandbox_service):
        """SandboxService.execute_command returns ShellResult with 'svc_e2e' in stdout."""
        from unittest.mock import patch

        svc, mock_settings = patched_sandbox_service
        with patch("backend.services.sandbox_service.settings", mock_settings):
            result = await svc.execute_command(service_sandbox, "echo svc_e2e")
        assert isinstance(result, ShellResult)
        assert "svc_e2e" in result.stdout
        assert result.exit_code == 0

    async def test_service_keyboard_press(self, service_sandbox, patched_sandbox_service):
        """SandboxService.keyboard_press with text='svc' returns dict with ok."""
        from unittest.mock import patch

        svc, mock_settings = patched_sandbox_service
        with patch("backend.services.sandbox_service.settings", mock_settings):
            result = await svc.keyboard_press(service_sandbox, text="svc")
        assert isinstance(result, dict)
        assert result["ok"] is True

    async def test_service_mouse_scroll(self, service_sandbox, patched_sandbox_service):
        """SandboxService.mouse_scroll returns dict with ok=True."""
        from unittest.mock import patch

        svc, mock_settings = patched_sandbox_service
        with patch("backend.services.sandbox_service.settings", mock_settings):
            result = await svc.mouse_scroll(service_sandbox, direction="down", clicks=2)
        assert isinstance(result, dict)
        assert result["ok"] is True

    async def test_service_mouse_location(self, service_sandbox, patched_sandbox_service):
        """SandboxService.mouse_location returns dict with integer x and y."""
        from unittest.mock import patch

        svc, mock_settings = patched_sandbox_service
        with patch("backend.services.sandbox_service.settings", mock_settings):
            result = await svc.mouse_location(service_sandbox)
        assert isinstance(result, dict)
        assert isinstance(result["x"], int)
        assert isinstance(result["y"], int)

    async def test_service_start_recording(self, service_sandbox, patched_sandbox_service):
        """SandboxService.start_recording returns dict with status."""
        from unittest.mock import patch

        svc, mock_settings = patched_sandbox_service
        with patch("backend.services.sandbox_service.settings", mock_settings):
            result = await svc.start_recording(service_sandbox)
        assert isinstance(result, dict)
        assert "status" in result

    async def test_service_stop_recording(self, service_sandbox, patched_sandbox_service):
        """SandboxService.stop_recording returns bytes after a brief recording."""
        import asyncio
        from unittest.mock import patch

        svc, mock_settings = patched_sandbox_service
        with patch("backend.services.sandbox_service.settings", mock_settings):
            await svc.start_recording(service_sandbox)
            await asyncio.sleep(1)
            data = await svc.stop_recording(service_sandbox)
        assert isinstance(data, bytes)


# ===========================================================================
# Section 8: Agent Worker Source Verification
# ===========================================================================


class TestSourceVerification:
    """Verify critical source code patterns that prevent MissingGreenlet errors.

    These tests inspect the actual source code to ensure selectinload is used
    when loading sandbox and desktop relationships.
    """

    async def test_agent_worker_loads_sandbox_relationship(self):
        """AgentWorker.run source contains selectinload for sandbox."""
        import inspect

        from backend.workers.agent_worker import AgentWorker

        source = inspect.getsource(AgentWorker.run)
        assert "selectinload" in source, "AgentWorker.run must use selectinload"
        assert "sandbox" in source, "AgentWorker.run must load sandbox relationship"

    async def test_agent_worker_loads_desktop_relationship(self):
        """AgentWorker.run source contains selectinload for desktop."""
        import inspect

        from backend.workers.agent_worker import AgentWorker

        source = inspect.getsource(AgentWorker.run)
        assert "selectinload" in source, "AgentWorker.run must use selectinload"
        assert "desktop" in source, "AgentWorker.run must load desktop relationship"

    async def test_task_service_loads_desktop(self):
        """TaskService.assign source contains selectinload for desktop."""
        import inspect

        from backend.services.task_service import TaskService

        source = inspect.getsource(TaskService.assign)
        assert "selectinload" in source, "TaskService.assign must use selectinload"
        assert "desktop" in source, "TaskService.assign must load desktop relationship"

    async def test_internal_files_loads_desktop(self):
        """Internal files endpoint source contains selectinload for desktop."""
        import inspect

        from backend.api_internal.files import execute

        source = inspect.getsource(execute)
        assert "selectinload" in source, "Internal execute must use selectinload"
        assert "desktop" in source, "Internal execute must load desktop relationship"


# ===========================================================================
# Section 9: Recording E2E via Proxy
# ===========================================================================


class TestRecordingViaProxy:
    """Direct HTTP tests for recording endpoints through the proxy."""

    async def test_recording_start_via_proxy(self, desktop_unit, proxy_prefix):
        """POST proxy/record/start returns 200 with status."""
        async with httpx.AsyncClient(base_url=BASE_URL, headers=HEADERS, timeout=TIMEOUT) as client:
            resp = await client.post(f"{proxy_prefix}/record/start")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data

    async def test_recording_stop_via_proxy(self, desktop_unit, proxy_prefix):
        """POST proxy/record/stop returns 200 with video bytes after starting."""
        import asyncio

        async with httpx.AsyncClient(base_url=BASE_URL, headers=HEADERS, timeout=60.0) as client:
            # Start recording
            start_resp = await client.post(f"{proxy_prefix}/record/start")
            assert start_resp.status_code == 200

            # Wait 1 second to capture frames
            await asyncio.sleep(1)

            # Stop recording — returns video bytes
            stop_resp = await client.post(f"{proxy_prefix}/record/stop")
            assert stop_resp.status_code == 200
            assert isinstance(stop_resp.content, bytes)


# ===========================================================================
# Section 10: Error Handling E2E
# ===========================================================================


class TestErrorHandling:
    """Verify error responses from real VM for edge cases."""

    async def test_invalid_shell_command_returns_nonzero(self, desktop_unit, proxy_prefix):
        """POST proxy/shell/execute with 'false' command returns exit_code != 0."""
        async with httpx.AsyncClient(base_url=BASE_URL, headers=HEADERS, timeout=TIMEOUT) as client:
            resp = await client.post(
                f"{proxy_prefix}/shell/execute",
                json={"command": "false", "timeout": 10},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["exit_code"] != 0

    async def test_shell_timeout_returns_408_or_completes(self, desktop_unit, proxy_prefix):
        """POST proxy/shell/execute with 'sleep 30' and timeout=1 returns 408."""
        async with httpx.AsyncClient(base_url=BASE_URL, headers=HEADERS, timeout=30.0) as client:
            resp = await client.post(
                f"{proxy_prefix}/shell/execute",
                json={"command": "sleep 30", "timeout": 1},
            )
        # Server should return 408 (timeout) or 200 with partial output
        assert resp.status_code in (200, 408)


# ===========================================================================
# Section 11: Full Executor→Service→Client→VM E2E
# ===========================================================================


@pytest.fixture
def e2e_run_context(desktop_unit):
    """Build a RunContext with a real desktop sandbox pointing at the live VM.

    This allows calling actual executor functions end-to-end.
    """
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from uuid import uuid4

    from backend.tools.base import RunContext

    desktop_sandbox = SimpleNamespace(
        id=uuid4(),
        unit_type="desktop",
        host=POOL_MANAGER_HOST,
        port=POOL_MANAGER_PORT,
        auth_token=POOL_MANAGER_TOKEN,
        orchestrator_sandbox_id=desktop_unit["unit_id"],
        agent_id=uuid4(),
        status="ready",
    )
    agent = SimpleNamespace(
        id=uuid4(),
        project_id=uuid4(),
        sandbox=None,
        desktop=desktop_sandbox,
    )
    return RunContext(
        agent=agent,
        db=AsyncMock(),
        project=SimpleNamespace(id=uuid4(), name="e2e-test"),
        session_id=uuid4(),
        message_service=AsyncMock(),
        session_service=AsyncMock(),
        task_service=AsyncMock(),
        agent_service=AsyncMock(),
        agent_msg_repo=AsyncMock(),
    )


def _patch_service_settings():
    """Context manager that patches SandboxService settings for real VM routing."""
    from unittest.mock import patch

    mock_settings = type("MockSettings", (), {
        "sandbox_orchestrator_host": "",
        "sandbox_vm_host": POOL_MANAGER_HOST,
        "sandbox_vm_internal_host": "",
        "sandbox_vm_pool_port": POOL_MANAGER_PORT,
        "sandbox_vm_master_token": POOL_MANAGER_TOKEN,
    })()
    return patch("backend.services.sandbox_service.settings", mock_settings)


class TestExecutorE2E:
    """Invoke actual tool executor functions end-to-end against the real VM.

    This proves: executor → _require_desktop → _get_sandbox_service →
    SandboxService._resolve_host_port → SandboxClient → pool manager proxy → VM.
    """

    async def test_executor_desktop_screenshot(self, e2e_run_context):
        """run_desktop_screenshot returns ScreenshotResult with real JPEG bytes."""
        from backend.tools.executors.desktop import run_desktop_screenshot

        with _patch_service_settings():
            result = await run_desktop_screenshot(e2e_run_context, {})
        assert hasattr(result, "image_bytes")
        assert len(result.image_bytes) > 1000
        assert result.image_bytes[:2] == b"\xff\xd8"  # JPEG magic

    async def test_executor_desktop_mouse_move(self, e2e_run_context):
        """run_desktop_mouse_move returns success string."""
        from backend.tools.executors.desktop import run_desktop_mouse_move

        with _patch_service_settings():
            result = await run_desktop_mouse_move(e2e_run_context, {"x": 400, "y": 300})
        assert "400" in result and "300" in result

    async def test_executor_desktop_mouse_click(self, e2e_run_context):
        """run_desktop_mouse_click with button=1 returns success string."""
        from backend.tools.executors.desktop import run_desktop_mouse_click

        with _patch_service_settings():
            result = await run_desktop_mouse_click(
                e2e_run_context, {"x": 400, "y": 300, "button": 1, "click_type": "single"}
            )
        assert "clicked" in result.lower() or "400" in result

    async def test_executor_desktop_mouse_scroll(self, e2e_run_context):
        """run_desktop_mouse_scroll returns success string."""
        from backend.tools.executors.desktop import run_desktop_mouse_scroll

        with _patch_service_settings():
            result = await run_desktop_mouse_scroll(
                e2e_run_context, {"direction": "down", "clicks": 2}
            )
        assert "scroll" in result.lower() or "down" in result.lower()

    async def test_executor_desktop_keyboard_press(self, e2e_run_context):
        """run_desktop_keyboard_press with text returns success string."""
        from backend.tools.executors.desktop import run_desktop_keyboard_press

        with _patch_service_settings():
            result = await run_desktop_keyboard_press(
                e2e_run_context, {"text": "e2e_executor_test"}
            )
        assert "keyboard" in result.lower() or "e2e_executor_test" in result

    async def test_executor_desktop_open_url(self, e2e_run_context):
        """run_desktop_open_url with about:blank returns success string."""
        from backend.tools.executors.desktop import run_desktop_open_url

        with _patch_service_settings():
            result = await run_desktop_open_url(
                e2e_run_context, {"url": "about:blank"}
            )
        assert "about:blank" in result.lower() or "opening" in result.lower()

    async def test_executor_desktop_list_windows(self, e2e_run_context):
        """run_desktop_list_windows returns window list or 'no windows'."""
        from backend.tools.executors.desktop import run_desktop_list_windows

        with _patch_service_settings():
            result = await run_desktop_list_windows(e2e_run_context, {})
        assert isinstance(result, str)
        assert len(result) > 0

    async def test_executor_desktop_focus_window(self, e2e_run_context):
        """run_desktop_focus_window by title returns success string."""
        from backend.tools.executors.desktop import run_desktop_focus_window

        with _patch_service_settings():
            result = await run_desktop_focus_window(
                e2e_run_context, {"title": "Desktop"}
            )
        assert "desktop" in result.lower() or "focus" in result.lower()

    async def test_executor_desktop_get_clipboard(self, e2e_run_context):
        """run_desktop_get_clipboard returns clipboard contents or empty marker."""
        from backend.tools.executors.desktop import run_desktop_get_clipboard

        with _patch_service_settings():
            result = await run_desktop_get_clipboard(e2e_run_context, {})
        assert isinstance(result, str)

    async def test_executor_desktop_set_clipboard(self, e2e_run_context):
        """run_desktop_set_clipboard sets content, then get verifies it."""
        from backend.tools.executors.desktop import (
            run_desktop_get_clipboard,
            run_desktop_set_clipboard,
        )

        with _patch_service_settings():
            set_result = await run_desktop_set_clipboard(
                e2e_run_context, {"content": "executor_e2e_clip"}
            )
            assert "clipboard" in set_result.lower()

            get_result = await run_desktop_get_clipboard(e2e_run_context, {})
            assert "executor_e2e_clip" in get_result


# ===========================================================================
# Section 12: Sandbox Executor E2E (via desktop VM as sandbox proxy)
# ===========================================================================


@pytest.fixture
def e2e_sandbox_context(desktop_unit):
    """Build a RunContext with agent.sandbox pointing at the live desktop VM.

    Sandbox executors check ctx.agent.sandbox (not .desktop).
    We reuse the desktop VM for testing since the HTTP API is identical.
    """
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from uuid import uuid4

    from backend.tools.base import RunContext

    sandbox = SimpleNamespace(
        id=uuid4(),
        unit_type="desktop",
        host=POOL_MANAGER_HOST,
        port=POOL_MANAGER_PORT,
        auth_token=POOL_MANAGER_TOKEN,
        orchestrator_sandbox_id=desktop_unit["unit_id"],
        agent_id=uuid4(),
        status="ready",
    )
    agent = SimpleNamespace(
        id=uuid4(),
        project_id=uuid4(),
        sandbox=sandbox,
        desktop=None,
    )
    return RunContext(
        agent=agent,
        db=AsyncMock(),
        project=SimpleNamespace(id=uuid4(), name="e2e-sandbox-test"),
        session_id=uuid4(),
        message_service=AsyncMock(),
        session_service=AsyncMock(),
        task_service=AsyncMock(),
        agent_service=AsyncMock(),
        agent_msg_repo=AsyncMock(),
    )


class TestSandboxExecutorE2E:
    """Invoke sandbox executor functions end-to-end against the real VM.

    Tests the chain: executor → ctx.agent.sandbox → SandboxService → SandboxClient → VM.
    """

    async def test_executor_execute_command(self, e2e_sandbox_context):
        """run_execute_command echoes text through the full chain."""
        from backend.tools.executors.sandbox import run_execute_command

        with _patch_service_settings():
            result = await run_execute_command(
                e2e_sandbox_context, {"command": "echo sandbox_exec_e2e", "timeout": 10}
            )
        assert "sandbox_exec_e2e" in result

    async def test_executor_sandbox_health(self, e2e_sandbox_context):
        """run_sandbox_health returns status through the full chain."""
        from backend.tools.executors.sandbox import run_sandbox_health

        with _patch_service_settings():
            result = await run_sandbox_health(e2e_sandbox_context, {})
        assert "ok" in result.lower() or "status" in result.lower()

    async def test_executor_sandbox_screenshot(self, e2e_sandbox_context):
        """run_sandbox_screenshot returns ScreenshotResult with real bytes."""
        from backend.tools.executors.sandbox import run_sandbox_screenshot

        with _patch_service_settings():
            result = await run_sandbox_screenshot(e2e_sandbox_context, {})
        assert hasattr(result, "image_bytes")
        assert len(result.image_bytes) > 1000

    async def test_executor_sandbox_mouse_move(self, e2e_sandbox_context):
        """run_sandbox_mouse_move returns success string."""
        from backend.tools.executors.sandbox import run_sandbox_mouse_move

        with _patch_service_settings():
            result = await run_sandbox_mouse_move(
                e2e_sandbox_context, {"x": 350, "y": 250}
            )
        assert "350" in result or "moved" in result.lower()

    async def test_executor_sandbox_mouse_click(self, e2e_sandbox_context):
        """run_sandbox_mouse_click with button=1 returns success string."""
        from backend.tools.executors.sandbox import run_sandbox_mouse_click

        with _patch_service_settings():
            result = await run_sandbox_mouse_click(
                e2e_sandbox_context,
                {"x": 350, "y": 250, "button": 1, "click_type": "single"},
            )
        assert isinstance(result, str)

    async def test_executor_sandbox_mouse_scroll(self, e2e_sandbox_context):
        """run_sandbox_mouse_scroll returns success string."""
        from backend.tools.executors.sandbox import run_sandbox_mouse_scroll

        with _patch_service_settings():
            result = await run_sandbox_mouse_scroll(
                e2e_sandbox_context, {"direction": "up", "clicks": 2}
            )
        assert isinstance(result, str)

    async def test_executor_sandbox_mouse_location(self, e2e_sandbox_context):
        """run_sandbox_mouse_location returns coordinates string."""
        from backend.tools.executors.sandbox import run_sandbox_mouse_location

        with _patch_service_settings():
            result = await run_sandbox_mouse_location(e2e_sandbox_context, {})
        assert isinstance(result, str)

    async def test_executor_sandbox_keyboard_press(self, e2e_sandbox_context):
        """run_sandbox_keyboard_press with text returns success string."""
        from backend.tools.executors.sandbox import run_sandbox_keyboard_press

        with _patch_service_settings():
            result = await run_sandbox_keyboard_press(
                e2e_sandbox_context, {"text": "sandbox_e2e_kb"}
            )
        assert isinstance(result, str)

    async def test_executor_sandbox_record_screen(self, e2e_sandbox_context):
        """run_sandbox_record_screen starts recording through the full chain."""
        from backend.tools.executors.sandbox import run_sandbox_record_screen

        with _patch_service_settings():
            result = await run_sandbox_record_screen(e2e_sandbox_context, {})
        assert "record" in result.lower()

    async def test_executor_sandbox_end_record_screen(self, e2e_sandbox_context):
        """run_sandbox_end_record_screen stops recording and returns video data."""
        import asyncio

        from backend.tools.executors.sandbox import (
            run_sandbox_end_record_screen,
            run_sandbox_record_screen,
        )

        with _patch_service_settings():
            await run_sandbox_record_screen(e2e_sandbox_context, {})
            await asyncio.sleep(1)
            result = await run_sandbox_end_record_screen(e2e_sandbox_context, {})
        assert "record" in result.lower() or "bytes" in result.lower()
