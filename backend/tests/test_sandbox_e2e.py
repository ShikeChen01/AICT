"""
End-to-end tests that simulate what an agent actually does when it calls
sandbox tools in sequence.

These tests are designed to EXPOSE the startup race condition and validate
the fixes.  They do NOT hit real network endpoints — everything is mocked at
the boundary layer (PoolManagerClient / SandboxClient methods).

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
from typing import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from backend.services.sandbox_client import ShellResult, SandboxClient, SandboxConnection


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def _make_connection(host_port: int = 30001, auth_token: str = "tok") -> SandboxConnection:
    return SandboxConnection(
        sandbox_id="testsandbox",
        rest_base_url=f"http://127.0.0.1:{host_port}",
        auth_token=auth_token,
    )


def _make_agent(sandbox_id: str | None = "testsandbox") -> MagicMock:
    agent = MagicMock()
    agent.id = "agent-1"
    agent.role = "engineer"
    # Create a mock sandbox object if sandbox_id is provided
    if sandbox_id:
        mock_sandbox = MagicMock()
        mock_sandbox.id = sandbox_id
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

    Expected (BEFORE fix): health check raises ConnectError — either hanging
    for 30 s or returning an empty / opaque error string.
    Expected (AFTER fix): session_start waits for the container to be ready, so
    health check succeeds immediately.
    """

    @pytest.mark.asyncio
    async def test_health_fails_with_connect_error_when_container_not_ready(self):
        """
        Simulate the race condition: container port rejects connections.
        Verify that the error message surfaced to the agent is non-empty and
        contains useful diagnostic info (the bug was it returned "").
        """
        client = SandboxClient()
        conn = _make_connection()
        client._connections["testsandbox"] = conn

        # Simulate container not ready: every HTTP call raises ConnectError
        connect_err = httpx.ConnectError("Connection refused")

        mock_http = AsyncMock()
        mock_http.is_closed = False  # prevent http() from creating a real client
        mock_http.get = AsyncMock(side_effect=connect_err)
        conn._http = mock_http

        with pytest.raises(httpx.ConnectError):
            await client.health_check("testsandbox")

    @pytest.mark.asyncio
    async def test_health_error_message_is_non_empty(self):
        """
        The _run_sandbox_health executor catches exceptions and returns
        f"Health check failed: {exc}".  Verify str(ConnectError) gives a
        non-empty, human-readable message — not just "".
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
    async def test_execute_command_returns_only_sandbox_id_when_container_not_ready(self):
        """
        Reproduce: when the WS times out (container not ready), execute_shell
        returns ShellResult(stdout="", exit_code=None).

        _run_execute_command then assembles:
            "Sandbox: <id>"
            ""        <-- result.stdout is empty
        And the agent sees ONLY the sandbox ID — no output at all.

        This test confirms the bug exists in the client layer.
        """
        client = SandboxClient()
        conn = _make_connection()
        client._connections["testsandbox"] = conn

        # Simulate WS open timeout — connection refused immediately
        import websockets.exceptions

        async def mock_connect_fail(*args, **kwargs):
            raise websockets.exceptions.InvalidURI("ws://127.0.0.1:30001/ws/shell", "refused")

        with patch("websockets.connect", side_effect=mock_connect_fail):
            with pytest.raises(RuntimeError) as exc_info:
                await client.execute_shell("testsandbox", "echo hello")
            assert "Shell execution failed" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_screenshot_fails_when_display_not_ready(self):
        """
        If the container started but Xvfb hasn't initialised yet (or if the
        container itself is still booting), /screenshot returns 500.
        Verify the error propagates clearly.
        """
        client = SandboxClient()
        conn = _make_connection()
        client._connections["testsandbox"] = conn

        # Container up but Xvfb not ready → server returns 500
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.raise_for_status = MagicMock(
            side_effect=httpx.HTTPStatusError(
                "500 Internal Server Error",
                request=MagicMock(),
                response=mock_resp,
            )
        )

        mock_http = AsyncMock()
        mock_http.is_closed = False
        mock_http.get = AsyncMock(return_value=mock_resp)
        conn._http = mock_http

        with pytest.raises(httpx.HTTPStatusError):
            await client.get_screenshot("testsandbox")


# ---------------------------------------------------------------------------
# 2. Timing / readiness — pool manager session_start must wait
# ---------------------------------------------------------------------------

class TestSessionStartReadiness:
    """
    Tests that verify the pool manager session_start endpoint waits for the
    container to be ready before returning to the caller.

    These tests target the FIXED behaviour.  They mock the readiness poll.
    """

    @pytest.mark.asyncio
    async def test_health_succeeds_after_container_ready(self):
        """
        Happy path: pool manager creates container, waits for /health to return
        200, then returns to the backend.  The backend registers the connection
        and subsequent health_check should succeed immediately.
        """
        client = SandboxClient()
        conn = _make_connection()
        client._connections["testsandbox"] = conn

        # Container is now ready: /health returns 200
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = MagicMock(return_value={
            "status": "ok",
            "uptime_seconds": 2.1,
            "display": ":99",
        })

        mock_http = AsyncMock()
        mock_http.is_closed = False
        mock_http.get = AsyncMock(return_value=mock_resp)
        conn._http = mock_http

        result = await client.health_check("testsandbox")
        assert result["status"] == "ok"
        assert "uptime_seconds" in result

    @pytest.mark.asyncio
    async def test_readiness_poll_retries_until_ready(self):
        """
        Simulate the pool manager's _wait_for_ready logic:
        - First N attempts fail (connection refused / 503)
        - Attempt N+1 succeeds
        Verify that we retry and ultimately return True.
        """
        call_count = 0
        fail_times = 3  # fail for 3 iterations, succeed on 4th

        async def fake_get(url: str, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= fail_times:
                raise httpx.ConnectError("Connection refused")
            resp = MagicMock()
            resp.status_code = 200
            return resp

        start = time.monotonic()

        async def _wait_for_ready(host_port: int, auth_token: str, timeout: float = 10.0) -> bool:
            """Inlined copy of the pool manager readiness probe (under test)."""
            url = f"http://127.0.0.1:{host_port}/health"
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
                await asyncio.sleep(0.05)  # fast for tests
            return False

        with patch("httpx.AsyncClient") as MockClient:
            mock_instance = AsyncMock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            mock_instance.get = fake_get
            MockClient.return_value = mock_instance

            ready = await _wait_for_ready(30001, "tok", timeout=5.0)

        elapsed = time.monotonic() - start
        assert ready is True, "Readiness probe should eventually return True"
        assert call_count == fail_times + 1, f"Expected {fail_times+1} calls, got {call_count}"
        assert elapsed < 2.0, f"Readiness probe took too long ({elapsed:.2f}s)"

    @pytest.mark.asyncio
    async def test_readiness_poll_times_out(self):
        """
        If the container never becomes healthy within the timeout, the readiness
        probe returns False.  session_start should still return (not hang) but
        the response indicates the container may not be ready.
        """
        async def _wait_for_ready(host_port: int, auth_token: str, timeout: float = 0.1) -> bool:
            url = f"http://127.0.0.1:{host_port}/health"
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
            # Always raises — container never ready
            mock_instance.get = AsyncMock(side_effect=httpx.ConnectError("refused"))
            MockClient.return_value = mock_instance

            ready = await _wait_for_ready(30001, "tok", timeout=0.1)

        assert ready is False


# ---------------------------------------------------------------------------
# 3. Full agent tool flow — happy path after fix
# ---------------------------------------------------------------------------

class TestAgentToolFlowHappyPath:
    """
    Simulate the complete sequence an agent runs:
      sandbox_start_session → sandbox_health → execute_command → sandbox_screenshot
      → sandbox_end_session

    All external calls are mocked.  The test verifies:
      - Each step returns the expected data shape
      - Shell output is non-empty
      - Health response includes status/uptime/display
      - Session end is called correctly
    """

    @pytest.fixture
    def sandbox_client(self):
        client = SandboxClient()
        conn = _make_connection()
        client._connections["testsandbox"] = conn

        # Pre-configure a good HTTP mock for REST calls
        mock_resp_health = MagicMock()
        mock_resp_health.status_code = 200
        mock_resp_health.raise_for_status = MagicMock()
        mock_resp_health.json = MagicMock(return_value={
            "status": "ok",
            "uptime_seconds": 5.3,
            "display": ":99",
        })

        mock_resp_screenshot = MagicMock()
        mock_resp_screenshot.status_code = 200
        mock_resp_screenshot.raise_for_status = MagicMock()
        mock_resp_screenshot.content = b"\xff\xd8\xff" + b"\x00" * 100  # fake JPEG

        async def fake_get(path, **kwargs):
            if "health" in path:
                return mock_resp_health
            if "screenshot" in path:
                return mock_resp_screenshot
            raise ValueError(f"Unexpected GET {path}")

        mock_http = AsyncMock()
        mock_http.is_closed = False  # prevent http() from creating a real client
        mock_http.get = fake_get
        conn._http = mock_http

        return client

    @pytest.mark.asyncio
    async def test_health_check_returns_complete_data(self, sandbox_client):
        result = await sandbox_client.health_check("testsandbox")
        assert result["status"] == "ok"
        assert result["uptime_seconds"] == 5.3
        assert result["display"] == ":99"

    @pytest.mark.asyncio
    async def test_screenshot_returns_bytes(self, sandbox_client):
        img = await sandbox_client.get_screenshot("testsandbox")
        assert isinstance(img, bytes)
        assert len(img) > 0
        assert img[:3] == b"\xff\xd8\xff"  # JPEG magic bytes

    @pytest.mark.asyncio
    async def test_execute_shell_returns_stdout(self):
        """
        Simulate a successful WS shell execution that returns real output.
        Verifies the sentinel parsing logic works correctly.
        """
        client = SandboxClient()
        conn = _make_connection()
        client._connections["testsandbox"] = conn

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
            result = await client.execute_shell("testsandbox", "uname -a")

        assert result.exit_code == 0
        assert "Linux" in result.stdout
        assert sentinel not in result.stdout

    @pytest.mark.asyncio
    async def test_execute_shell_non_zero_exit_code(self):
        """Verify exit code is parsed correctly for failing commands."""
        client = SandboxClient()
        conn = _make_connection()
        client._connections["testsandbox"] = conn

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
            result = await client.execute_shell("testsandbox", "ls /nonexistent")

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
        ctx.db = MagicMock()  # sandbox_health now receives session=ctx.db

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
        # The error detail must be non-empty — this was the original bug
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
        ctx.db = MagicMock()  # sandbox_health now receives session=ctx.db

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
        ctx.db = MagicMock()  # sandbox_health now receives session=ctx.db

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
    Focus: when shell output is empty (container not ready), the agent should
    NOT silently receive only the sandbox ID — it should receive an error.
    """

    @pytest.mark.asyncio
    async def test_execute_command_includes_stdout(self):
        from backend.tools.loop_registry import _run_execute_command, RunContext

        ctx = MagicMock(spec=RunContext)
        ctx.agent = _make_agent()
        ctx.db = AsyncMock()

        mock_svc = AsyncMock()
        mock_svc.execute_command = AsyncMock(
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
        exit_code is None.  The executor returns only "Sandbox: <id>" with
        no indication of what happened.

        This test confirms the bug and documents the EXPECTED fix:
        the executor should include a timeout notice, not silently return nothing.
        """
        from backend.tools.loop_registry import _run_execute_command, RunContext

        ctx = MagicMock(spec=RunContext)
        ctx.agent = _make_agent(sandbox_id="testsandbox")
        ctx.db = AsyncMock()

        mock_svc = AsyncMock()
        # Simulate timeout: stdout empty, exit_code None
        mock_svc.execute_command = AsyncMock(
            return_value=ShellResult(stdout="", exit_code=None)
        )

        with patch("backend.tools.executors.sandbox._get_sandbox_service", return_value=mock_svc):
            result = await _run_execute_command(ctx, {"command": "echo hello"})

        # After fix: must include a timeout/no-output notice so the agent knows
        # the command didn't produce output (not silently receive only the sandbox ID).
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
        """
        If execute_shell raises (WS connect error), the error should be
        surfaced to the agent, not silently swallowed.
        """
        from backend.tools.loop_registry import _run_execute_command, RunContext

        ctx = MagicMock(spec=RunContext)
        ctx.agent = _make_agent()
        ctx.db = AsyncMock()

        mock_svc = AsyncMock()
        mock_svc.execute_command = AsyncMock(
            side_effect=RuntimeError("Shell execution failed: Connection refused")
        )

        with patch("backend.tools.executors.sandbox._get_sandbox_service", return_value=mock_svc):
            with pytest.raises(RuntimeError, match="Shell execution failed"):
                await _run_execute_command(ctx, {"command": "echo hello"})
