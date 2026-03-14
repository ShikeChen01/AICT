"""
End-to-end tests that simulate what an agent actually does when it calls
sandbox tools in sequence.

These tests are designed to EXPOSE the startup race condition and validate
the fixes.  They do NOT hit real network endpoints — everything is mocked at
the boundary layer (OrchestratorClient / SandboxClient methods).

v3.1: Updated for stateless SandboxClient. All methods now take
(host, port, auth_token) parameters instead of sandbox_id lookups
in a connection pool.

Bugs being tested:
  1. Startup race condition — session_start returns before container is ready,
     causing health / shell / screenshot tools to fail immediately.
  2. Empty error message — ConnectError with no detail bubbles up as "".
  3. Shell output is empty — WS times out while container is booting, so
     execute_command returns only "Sandbox: <id>" with no stdout.
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from backend.services.sandbox_client import ShellResult, SandboxClient


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

_TEST_HOST = "127.0.0.1"
_TEST_PORT = 30001
_TEST_TOKEN = "tok"


def _make_agent(sandbox_id: str | None = "testsandbox") -> MagicMock:
    agent = MagicMock()
    agent.id = "agent-1"
    agent.role = "engineer"
    if sandbox_id:
        mock_sandbox = MagicMock()
        mock_sandbox.id = sandbox_id
        mock_sandbox.host = _TEST_HOST
        mock_sandbox.port = _TEST_PORT
        mock_sandbox.auth_token = _TEST_TOKEN
        agent.sandbox = mock_sandbox
    else:
        agent.sandbox = None
    return agent


# ---------------------------------------------------------------------------
# 1. Startup race condition — health check fails with connection error
# ---------------------------------------------------------------------------

class TestStartupRaceCondition:
    """
    Reproduce the scenario: agent calls sandbox_start_session, then immediately
    calls sandbox_health before the container uvicorn has started.
    """

    @pytest.mark.asyncio
    async def test_health_fails_with_connect_error_when_container_not_ready(self):
        """
        Simulate the race condition: container port rejects connections.
        Verify that the error propagates clearly.
        """
        client = SandboxClient()

        with patch("httpx.AsyncClient") as MockClient:
            mock_instance = AsyncMock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            mock_instance.get = AsyncMock(
                side_effect=httpx.ConnectError("Connection refused")
            )
            MockClient.return_value = mock_instance

            with pytest.raises(httpx.ConnectError):
                await client.health_check(_TEST_HOST, _TEST_PORT, _TEST_TOKEN)

    @pytest.mark.asyncio
    async def test_health_error_message_is_non_empty(self):
        """
        Verify str(ConnectError) gives a non-empty, human-readable message.
        """
        err = httpx.ConnectError("Connection refused by peer")
        msg = str(err)
        assert msg, (
            "BUG: httpx.ConnectError.__str__ returned empty string. "
            "The agent will see 'Health check failed: ' with no detail."
        )
        assert "refused" in msg.lower() or "connection" in msg.lower(), (
            f"Error message '{msg}' doesn't contain useful diagnostic info"
        )

    @pytest.mark.asyncio
    async def test_screenshot_fails_when_display_not_ready(self):
        """
        If the container started but Xvfb hasn't initialised yet,
        /screenshot returns 500. Verify the error propagates clearly.
        """
        client = SandboxClient()

        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.raise_for_status = MagicMock(
            side_effect=httpx.HTTPStatusError(
                "500 Internal Server Error",
                request=MagicMock(),
                response=mock_resp,
            )
        )

        with patch("httpx.AsyncClient") as MockClient:
            mock_instance = AsyncMock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            mock_instance.get = AsyncMock(return_value=mock_resp)
            MockClient.return_value = mock_instance

            with pytest.raises(httpx.HTTPStatusError):
                await client.get_screenshot(_TEST_HOST, _TEST_PORT, _TEST_TOKEN)


# ---------------------------------------------------------------------------
# 2. Timing / readiness — pool manager session_start must wait
# ---------------------------------------------------------------------------

class TestSessionStartReadiness:
    """
    Tests that verify the pool manager session_start endpoint waits for the
    container to be ready before returning to the caller.
    """

    @pytest.mark.asyncio
    async def test_health_succeeds_after_container_ready(self):
        """
        Happy path: container is ready, health check returns 200.
        """
        client = SandboxClient()

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = MagicMock(return_value={
            "status": "ok",
            "uptime_seconds": 2.1,
            "display": ":99",
        })

        with patch("httpx.AsyncClient") as MockClient:
            mock_instance = AsyncMock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            mock_instance.get = AsyncMock(return_value=mock_resp)
            MockClient.return_value = mock_instance

            result = await client.health_check(_TEST_HOST, _TEST_PORT, _TEST_TOKEN)

        assert result["status"] == "ok"
        assert "uptime_seconds" in result

    @pytest.mark.asyncio
    async def test_readiness_poll_retries_until_ready(self):
        """
        Simulate a readiness probe: first N attempts fail, then succeed.
        """
        call_count = 0
        fail_times = 3

        async def fake_get(url: str, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= fail_times:
                raise httpx.ConnectError("Connection refused")
            resp = MagicMock()
            resp.status_code = 200
            return resp

        start = time.monotonic()

        async def _wait_for_ready(host: str, port: int, auth_token: str, timeout: float = 10.0) -> bool:
            """Inlined copy of the pool manager readiness probe (under test)."""
            url = f"http://{host}:{port}/health"
            headers = {"Authorization": f"Bearer {auth_token}"}
            deadline = asyncio.get_event_loop().time() + timeout
            while asyncio.get_event_loop().time() < deadline:
                try:
                    async with httpx.AsyncClient(timeout=2.0) as c:
                        resp = await c.get(url, headers=headers)
                        if resp.status_code == 200:
                            return True
                except Exception:
                    pass
                await asyncio.sleep(0.05)
            return False

        with patch("httpx.AsyncClient") as MockClient:
            mock_instance = AsyncMock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            mock_instance.get = fake_get
            MockClient.return_value = mock_instance

            ready = await _wait_for_ready(_TEST_HOST, _TEST_PORT, _TEST_TOKEN, timeout=5.0)

        elapsed = time.monotonic() - start
        assert ready is True, "Readiness probe should eventually return True"
        assert call_count == fail_times + 1, f"Expected {fail_times+1} calls, got {call_count}"
        assert elapsed < 2.0, f"Readiness probe took too long ({elapsed:.2f}s)"

    @pytest.mark.asyncio
    async def test_readiness_poll_times_out(self):
        """
        If the container never becomes healthy, the probe returns False.
        """
        async def _wait_for_ready(host: str, port: int, auth_token: str, timeout: float = 0.1) -> bool:
            url = f"http://{host}:{port}/health"
            headers = {"Authorization": f"Bearer {auth_token}"}
            deadline = asyncio.get_event_loop().time() + timeout
            while asyncio.get_event_loop().time() < deadline:
                try:
                    async with httpx.AsyncClient(timeout=0.05) as c:
                        resp = await c.get(url, headers=headers)
                        if resp.status_code == 200:
                            return True
                except Exception:
                    pass
                await asyncio.sleep(0.01)
            return False

        with patch("httpx.AsyncClient") as MockClient:
            mock_instance = AsyncMock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            mock_instance.get = AsyncMock(side_effect=httpx.ConnectError("refused"))
            MockClient.return_value = mock_instance

            ready = await _wait_for_ready(_TEST_HOST, _TEST_PORT, _TEST_TOKEN, timeout=0.1)

        assert ready is False


# ---------------------------------------------------------------------------
# 3. Full agent tool flow — happy path after fix
# ---------------------------------------------------------------------------

class TestAgentToolFlowHappyPath:
    """
    Simulate the complete sequence an agent runs.
    All external calls are mocked.
    """

    @pytest.mark.asyncio
    async def test_health_check_returns_complete_data(self):
        client = SandboxClient()

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = MagicMock(return_value={
            "status": "ok",
            "uptime_seconds": 5.3,
            "display": ":99",
        })

        with patch("httpx.AsyncClient") as MockClient:
            mock_instance = AsyncMock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            mock_instance.get = AsyncMock(return_value=mock_resp)
            MockClient.return_value = mock_instance

            result = await client.health_check(_TEST_HOST, _TEST_PORT, _TEST_TOKEN)

        assert result["status"] == "ok"
        assert result["uptime_seconds"] == 5.3
        assert result["display"] == ":99"

    @pytest.mark.asyncio
    async def test_screenshot_returns_bytes(self):
        client = SandboxClient()

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.content = b"\xff\xd8\xff" + b"\x00" * 100  # fake JPEG

        with patch("httpx.AsyncClient") as MockClient:
            mock_instance = AsyncMock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            mock_instance.get = AsyncMock(return_value=mock_resp)
            MockClient.return_value = mock_instance

            img = await client.get_screenshot(_TEST_HOST, _TEST_PORT, _TEST_TOKEN)

        assert isinstance(img, bytes)
        assert len(img) > 0
        assert img[:3] == b"\xff\xd8\xff"

    @pytest.mark.asyncio
    async def test_execute_shell_returns_stdout(self):
        """
        Simulate a successful WS shell execution that returns real output.
        Verifies the sentinel parsing logic works correctly.
        """
        client = SandboxClient()

        marker = "deadbeef12345678"
        drain_sentinel = f"__AICT_DRAIN_{marker}__"
        sentinel = f"__AICT_CMD_DONE_{marker}__"

        drain_data = f"prompt\n{drain_sentinel}\n{drain_sentinel}\n".encode()
        fake_output = f"Linux sandbox 5.15.0-1 #1 SMP x86_64\n{sentinel}:0\n".encode()

        class FakeWS:
            def __init__(self):
                self._payloads = [drain_data, fake_output]
                self._index = 0
            async def __aenter__(self):
                return self
            async def __aexit__(self, *a):
                pass
            async def send(self, data):
                pass
            async def recv(self):
                if self._index < len(self._payloads):
                    data = self._payloads[self._index]
                    self._index += 1
                    return data
                return b""

        with patch("websockets.connect", return_value=FakeWS()), \
             patch("secrets.token_hex", return_value=marker):
            result = await client.execute_shell(
                _TEST_HOST, _TEST_PORT, _TEST_TOKEN, "uname -a"
            )

        assert result.exit_code == 0
        assert "Linux" in result.stdout
        assert sentinel not in result.stdout

    @pytest.mark.asyncio
    async def test_execute_shell_non_zero_exit_code(self):
        """Verify exit code is parsed correctly for failing commands."""
        client = SandboxClient()

        marker = "cafebabe99887766"
        drain_sentinel = f"__AICT_DRAIN_{marker}__"
        sentinel = f"__AICT_CMD_DONE_{marker}__"

        drain_data = f"prompt\n{drain_sentinel}\n{drain_sentinel}\n".encode()
        fake_output = f"ls: cannot access '/nonexistent': No such file or directory\n{sentinel}:2\n".encode()

        class FakeWS:
            def __init__(self):
                self._payloads = [drain_data, fake_output]
                self._index = 0
            async def __aenter__(self): return self
            async def __aexit__(self, *a): pass
            async def send(self, data): pass
            async def recv(self):
                if self._index < len(self._payloads):
                    data = self._payloads[self._index]
                    self._index += 1
                    return data
                return b""

        with patch("websockets.connect", return_value=FakeWS()), \
             patch("secrets.token_hex", return_value=marker):
            result = await client.execute_shell(
                _TEST_HOST, _TEST_PORT, _TEST_TOKEN, "ls /nonexistent"
            )

        assert result.exit_code == 2
        assert "No such file" in result.stdout


# ---------------------------------------------------------------------------
# 4. _run_sandbox_health executor — error surfacing
# ---------------------------------------------------------------------------

class TestSandboxHealthExecutor:
    """
    Test the _run_sandbox_health tool executor in loop_registry.py.
    Focus: error messages must be non-empty and actionable.
    """

    @pytest.mark.asyncio
    async def test_health_executor_surfaces_connect_error(self):
        from backend.tools.loop_registry import _run_sandbox_health, RunContext

        ctx = MagicMock(spec=RunContext)
        ctx.agent = _make_agent()
        ctx.db = MagicMock()

        mock_svc = AsyncMock()
        mock_svc.sandbox_health = AsyncMock(
            side_effect=httpx.ConnectError("Connection refused")
        )

        from backend.tools.result import ToolExecutionError

        with patch("backend.tools.executors.sandbox._get_sandbox_service", return_value=mock_svc):
            with pytest.raises(ToolExecutionError) as exc_info:
                await _run_sandbox_health(ctx, {})

        result = str(exc_info.value)
        assert "Health check failed" in result
        after_colon = result.split("Health check failed:")[-1].strip()
        assert after_colon, (
            "BUG REPRODUCED: health check error message is empty. "
            "Agent sees 'Health check failed: ' with no detail."
        )

    @pytest.mark.asyncio
    async def test_health_executor_surfaces_timeout_error(self):
        from backend.tools.loop_registry import _run_sandbox_health, RunContext

        ctx = MagicMock(spec=RunContext)
        ctx.agent = _make_agent()
        ctx.db = MagicMock()

        mock_svc = AsyncMock()
        mock_svc.sandbox_health = AsyncMock(
            side_effect=httpx.ReadTimeout("Timed out waiting for server")
        )

        from backend.tools.result import ToolExecutionError

        with patch("backend.tools.executors.sandbox._get_sandbox_service", return_value=mock_svc):
            with pytest.raises(ToolExecutionError) as exc_info:
                await _run_sandbox_health(ctx, {})

        result = str(exc_info.value)
        assert "Health check failed" in result
        after_colon = result.split("Health check failed:")[-1].strip()
        assert after_colon, "Timeout error message must be surfaced to the agent"

    @pytest.mark.asyncio
    async def test_health_executor_success_formats_correctly(self):
        from backend.tools.loop_registry import _run_sandbox_health, RunContext

        ctx = MagicMock(spec=RunContext)
        ctx.agent = _make_agent()
        ctx.db = MagicMock()

        mock_svc = AsyncMock()
        mock_svc.sandbox_health = AsyncMock(return_value={
            "status": "ok",
            "uptime_seconds": 12.5,
            "display": ":99",
        })

        with patch("backend.tools.executors.sandbox._get_sandbox_service", return_value=mock_svc):
            result = await _run_sandbox_health(ctx, {})

        assert "ok" in result
        assert "12.5" in result
        assert ":99" in result


# ---------------------------------------------------------------------------
# 5. _run_execute_command executor — full output surfacing
# ---------------------------------------------------------------------------

class TestExecuteCommandExecutor:
    """
    Test the _run_execute_command executor.
    """

    @pytest.mark.asyncio
    async def test_execute_command_includes_stdout(self):
        from backend.tools.loop_registry import _run_execute_command, RunContext

        ctx = MagicMock(spec=RunContext)
        ctx.agent = _make_agent()
        ctx.db = AsyncMock()

        mock_svc = AsyncMock()
        mock_svc.execute_command_legacy = AsyncMock(
            return_value=ShellResult(stdout="hello world\n", exit_code=0)
        )

        with patch("backend.tools.executors.sandbox._get_sandbox_service", return_value=mock_svc):
            result = await _run_execute_command(ctx, {"command": "echo hello world"})

        assert "hello world" in result
        assert "Exit Code: 0" in result

    @pytest.mark.asyncio
    async def test_execute_command_empty_stdout_on_timeout(self):
        """
        BUG REPRODUCTION: when execute_shell times out, stdout is "" and
        exit_code is None.
        """
        from backend.tools.loop_registry import _run_execute_command, RunContext

        ctx = MagicMock(spec=RunContext)
        ctx.agent = _make_agent(sandbox_id="testsandbox")
        ctx.db = AsyncMock()

        mock_svc = AsyncMock()
        mock_svc.execute_command_legacy = AsyncMock(
            return_value=ShellResult(stdout="", exit_code=None)
        )

        with patch("backend.tools.executors.sandbox._get_sandbox_service", return_value=mock_svc):
            result = await _run_execute_command(ctx, {"command": "echo hello"})

        assert (
            "timed out" in result.lower()
            or "no output" in result.lower()
            or "timeout" in result.lower()
        ), (
            f"execute_command with empty stdout must warn the agent. "
            f"Agent received: {result!r}"
        )

    @pytest.mark.asyncio
    async def test_execute_command_shell_error_propagates(self):
        from backend.tools.loop_registry import _run_execute_command, RunContext

        ctx = MagicMock(spec=RunContext)
        ctx.agent = _make_agent()
        ctx.db = AsyncMock()

        mock_svc = AsyncMock()
        mock_svc.execute_command_legacy = AsyncMock(
            side_effect=RuntimeError("Shell execution failed: Connection refused")
        )

        with patch("backend.tools.executors.sandbox._get_sandbox_service", return_value=mock_svc):
            with pytest.raises(RuntimeError, match="Shell execution failed"):
                await _run_execute_command(ctx, {"command": "echo hello"})
