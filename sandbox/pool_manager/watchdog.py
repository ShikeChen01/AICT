"""Watchdog — standalone supervisor for the pool manager process.

Runs as a separate process (or systemd unit) that monitors the pool manager's
health endpoint and restarts it on failure.

Spec (from v4 architecture doc):
  - Check interval: Every 15 seconds, HTTP GET pool manager /api/health
  - Restart logic: 3 failures → SIGTERM → 5s wait → SIGKILL if alive → restart
  - Max 5 restart attempts in 10 minutes before alerting
  - Listens on port 9091 for its own health/status endpoint
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from collections import deque
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
from typing import Optional

# ── Configuration ────────────────────────────────────────────────────────────

CHECK_INTERVAL = int(os.environ.get("WATCHDOG_CHECK_INTERVAL", "15"))
FAIL_THRESHOLD = int(os.environ.get("WATCHDOG_FAIL_THRESHOLD", "3"))
SIGTERM_GRACE = int(os.environ.get("WATCHDOG_SIGTERM_GRACE", "5"))
MAX_RESTARTS = int(os.environ.get("WATCHDOG_MAX_RESTARTS", "5"))
RESTART_WINDOW = int(os.environ.get("WATCHDOG_RESTART_WINDOW", "600"))  # 10 min
WATCHDOG_PORT = int(os.environ.get("WATCHDOG_PORT", "9091"))

POOL_MANAGER_HOST = os.environ.get("POOL_MANAGER_HOST", "127.0.0.1")
POOL_MANAGER_PORT = int(os.environ.get("PORT", "9090"))
POOL_MANAGER_CMD = os.environ.get(
    "POOL_MANAGER_CMD",
    f"{sys.executable} -m uvicorn main:app --host 0.0.0.0 --port {POOL_MANAGER_PORT}",
)
POOL_MANAGER_CWD = os.environ.get(
    "POOL_MANAGER_CWD",
    os.path.dirname(os.path.abspath(__file__)),
)
MASTER_TOKEN = os.environ.get("MASTER_TOKEN", "")

# ── Utilities ────────────────────────────────────────────────────────────────


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    print(f"[watchdog {ts}] {msg}", flush=True)


# ── Global state ─────────────────────────────────────────────────────────────


class WatchdogState:
    """Mutable singleton holding watchdog runtime state."""

    def __init__(self) -> None:
        self.process: Optional[subprocess.Popen] = None
        self.consecutive_failures: int = 0
        self.total_restarts: int = 0
        self.restart_timestamps: deque[float] = deque()
        self.started_at: str = _now_iso()
        self.last_check_at: Optional[str] = None
        self.last_healthy_at: Optional[str] = None
        self.last_restart_at: Optional[str] = None
        self.status: str = "starting"  # starting | healthy | degraded | alert
        self.alert_active: bool = False

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "pool_manager_pid": self.process.pid if self.process else None,
            "pool_manager_alive": self.process is not None and self.process.poll() is None,
            "consecutive_failures": self.consecutive_failures,
            "total_restarts": self.total_restarts,
            "alert_active": self.alert_active,
            "started_at": self.started_at,
            "last_check_at": self.last_check_at,
            "last_healthy_at": self.last_healthy_at,
            "last_restart_at": self.last_restart_at,
        }


_state = WatchdogState()


# ── Health check ─────────────────────────────────────────────────────────────


def _check_health() -> bool:
    """HTTP GET the pool manager's health endpoint."""
    import urllib.request
    import urllib.error

    url = f"http://{POOL_MANAGER_HOST}:{POOL_MANAGER_PORT}/api/health"
    req = urllib.request.Request(url, method="GET")
    if MASTER_TOKEN:
        req.add_header("Authorization", f"Bearer {MASTER_TOKEN}")

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception:
        return False


# ── Process management ───────────────────────────────────────────────────────


def _start_pool_manager() -> subprocess.Popen:
    """Start the pool manager as a child process."""
    _log(f"Starting pool manager: {POOL_MANAGER_CMD}")
    env = os.environ.copy()
    proc = subprocess.Popen(
        POOL_MANAGER_CMD.split(),
        cwd=POOL_MANAGER_CWD,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    _log(f"Pool manager started with PID {proc.pid}")
    return proc


def _stream_output(proc: subprocess.Popen) -> None:
    """Stream child stdout/stderr to watchdog's stdout in a background thread."""
    if proc.stdout is None:
        return
    try:
        for line in iter(proc.stdout.readline, b""):
            sys.stdout.buffer.write(line)
            sys.stdout.buffer.flush()
    except (ValueError, OSError):
        pass  # Process closed


def _kill_process(proc: subprocess.Popen) -> None:
    """SIGTERM → wait → SIGKILL if still alive."""
    if proc.poll() is not None:
        return  # Already dead

    _log(f"Sending SIGTERM to PID {proc.pid}")
    try:
        os.kill(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        return

    try:
        proc.wait(timeout=SIGTERM_GRACE)
        _log(f"PID {proc.pid} exited after SIGTERM")
        return
    except subprocess.TimeoutExpired:
        pass

    _log(f"PID {proc.pid} did not exit, sending SIGKILL")
    try:
        os.kill(proc.pid, signal.SIGKILL)
        proc.wait(timeout=5)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        pass


def _restart_pool_manager() -> None:
    """Kill existing process and start a new one."""
    now = time.time()
    _state.restart_timestamps.append(now)

    # Prune timestamps outside the window
    cutoff = now - RESTART_WINDOW
    while _state.restart_timestamps and _state.restart_timestamps[0] < cutoff:
        _state.restart_timestamps.popleft()

    # Check restart rate limit
    if len(_state.restart_timestamps) > MAX_RESTARTS:
        _state.status = "alert"
        _state.alert_active = True
        _log(
            f"ALERT: {MAX_RESTARTS} restarts in {RESTART_WINDOW}s window — "
            f"backing off. Manual intervention required."
        )
        return

    # Kill existing
    if _state.process:
        _kill_process(_state.process)

    # Start new
    _state.process = _start_pool_manager()
    _state.total_restarts += 1
    _state.last_restart_at = _now_iso()
    _state.consecutive_failures = 0
    _state.status = "degraded"

    # Stream output in background
    Thread(target=_stream_output, args=(_state.process,), daemon=True).start()


# ── Watchdog HTTP server ────────────────────────────────────────────────────


class WatchdogHandler(BaseHTTPRequestHandler):
    """Minimal HTTP handler for watchdog status queries."""

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self._respond(200, {"status": "ok", "service": "watchdog"})
        elif self.path == "/status":
            self._respond(200, _state.to_dict())
        else:
            self._respond(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path == "/restart":
            _log("Manual restart requested via API")
            _state.alert_active = False  # Clear alert on manual restart
            _restart_pool_manager()
            self._respond(200, {"ok": True, "message": "Restart initiated"})
        elif self.path == "/clear-alert":
            _state.alert_active = False
            _state.status = "degraded"
            _state.restart_timestamps.clear()
            _log("Alert cleared via API")
            self._respond(200, {"ok": True, "message": "Alert cleared"})
        else:
            self._respond(404, {"error": "not found"})

    def _respond(self, code: int, body: dict) -> None:
        payload = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args) -> None:
        """Suppress default HTTP request logging."""
        pass


def _start_http_server() -> None:
    """Start the watchdog's own status HTTP server in a background thread."""
    server = HTTPServer(("0.0.0.0", WATCHDOG_PORT), WatchdogHandler)
    _log(f"Watchdog HTTP server listening on :{WATCHDOG_PORT}")
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()


# ── Main loop ────────────────────────────────────────────────────────────────


def main() -> None:
    _log("Watchdog starting")
    _log(f"  Pool manager: {POOL_MANAGER_HOST}:{POOL_MANAGER_PORT}")
    _log(f"  Check interval: {CHECK_INTERVAL}s")
    _log(f"  Fail threshold: {FAIL_THRESHOLD}")
    _log(f"  Max restarts: {MAX_RESTARTS} in {RESTART_WINDOW}s")

    # Start HTTP status server
    _start_http_server()

    # Initial start of pool manager
    _state.process = _start_pool_manager()
    Thread(target=_stream_output, args=(_state.process,), daemon=True).start()

    # Give it time to boot before first health check
    _log(f"Waiting {CHECK_INTERVAL}s for initial startup...")
    time.sleep(CHECK_INTERVAL)

    while True:
        _state.last_check_at = _now_iso()

        # Check if process exited unexpectedly
        if _state.process and _state.process.poll() is not None:
            exit_code = _state.process.returncode
            _log(f"Pool manager exited unexpectedly with code {exit_code}")
            _state.consecutive_failures = FAIL_THRESHOLD  # Force restart
        else:
            # HTTP health check
            healthy = _check_health()

            if healthy:
                if _state.consecutive_failures > 0:
                    _log("Pool manager recovered")
                _state.consecutive_failures = 0
                _state.last_healthy_at = _now_iso()
                if not _state.alert_active:
                    _state.status = "healthy"
            else:
                _state.consecutive_failures += 1
                _log(
                    f"Health check failed ({_state.consecutive_failures}/{FAIL_THRESHOLD})"
                )

        # Restart if threshold reached
        if _state.consecutive_failures >= FAIL_THRESHOLD:
            if _state.alert_active:
                _log("Alert active — skipping restart (manual intervention required)")
            else:
                _log("Threshold reached — restarting pool manager")
                _restart_pool_manager()

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        _log("Shutting down")
        if _state.process:
            _kill_process(_state.process)
        sys.exit(0)
