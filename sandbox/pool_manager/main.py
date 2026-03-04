"""Pool Manager — FastAPI service running on the VM host."""

from __future__ import annotations

import asyncio
import secrets
from contextlib import asynccontextmanager
from typing import Optional

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

import config
from docker_manager import DockerManager
from health_monitor import HealthMonitor
from models import PoolState, SandboxState
from port_allocator import PortAllocator

# ── Singletons ───────────────────────────────────────────────────────────────

_pool: PoolState
_docker: DockerManager
_ports: PortAllocator
_monitor: HealthMonitor


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _pool, _docker, _ports, _monitor

    _pool = PoolState(config.STATE_FILE)
    _docker = DockerManager()
    _ports = PortAllocator()

    # Reconcile persisted state against Docker reality.
    # Any sandbox whose container is not running is evicted: we destroy the
    # Docker container (stopped containers still hold their port binding in the
    # kernel, causing "port is already allocated" on the next create) and drop
    # it from state so the pool doesn't hand out dead sandbox IDs.
    stale = [s for s in _pool.all() if not _docker.is_running(s.sandbox_id)]
    for s in stale:
        print(f"[pool-manager] Removing stale sandbox {s.sandbox_id} (container not running) — destroying")
        try:
            _docker.destroy_container(s.sandbox_id)
        except Exception as exc:
            print(f"[pool-manager] Warning: could not destroy stale container {s.sandbox_id}: {exc}")
        _ports.release(s.host_port)
        _pool.remove(s.sandbox_id)

    # Also destroy any Docker-level sandbox-* containers that are NOT in state
    # (orphans from crashes / manual intervention that would block port reuse).
    known_ids = {s.sandbox_id for s in _pool.all()}
    for c in _docker.list_sandbox_containers():
        # container name is "sandbox-<sandbox_id>"
        cname = c["name"].lstrip("/")
        if not cname.startswith("sandbox-"):
            continue
        sid = cname[len("sandbox-"):]
        if sid not in known_ids:
            print(f"[pool-manager] Destroying orphan Docker container {cname} (not in state)")
            try:
                _docker.destroy_container(sid)
            except Exception as exc:
                print(f"[pool-manager] Warning: could not destroy orphan {cname}: {exc}")

    # Reclaim ports still in use from surviving state entries
    used_ports = [s.host_port for s in _pool.all()]
    _ports.reclaim_from_pool(used_ports)

    _monitor = HealthMonitor(_pool, _docker, _ports)
    _monitor.start()

    print(f"[pool-manager] Started. max_containers={config.MAX_CONTAINERS} (evicted {len(stale)} stale)")
    yield
    _monitor.stop()


# ── Auth ─────────────────────────────────────────────────────────────────────


async def require_master_token(request: Request) -> None:
    if not config.MASTER_TOKEN:
        return  # open in dev mode
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token")
    token = auth.removeprefix("Bearer ").strip()
    if token != config.MASTER_TOKEN:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(title="AICT Sandbox Pool Manager", lifespan=lifespan)


# ── Readiness probe ───────────────────────────────────────────────────────────


async def _wait_for_container_ready(
    host_port: int,
    auth_token: str,
    timeout: float = 30.0,
    poll_interval: float = 1.0,
) -> bool:
    """
    Poll the container's /health endpoint until it responds 200 or timeout.
    Called after docker.create_container so that session_start only returns
    once the sandbox server is actually accepting requests.
    """
    url = f"http://127.0.0.1:{host_port}/health"
    headers = {"Authorization": f"Bearer {auth_token}"}
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                resp = await client.get(url, headers=headers)
                if resp.status_code == 200:
                    return True
        except Exception:
            pass
        await asyncio.sleep(poll_interval)
    return False


# ── Health ────────────────────────────────────────────────────────────────────


@app.get("/api/health")
async def health(_: None = Depends(require_master_token)) -> JSONResponse:
    sandboxes = _pool.all()
    return JSONResponse({
        "status": "ok",
        "total": len(sandboxes),
        "idle": sum(1 for s in sandboxes if s.status == "idle"),
        "assigned": sum(1 for s in sandboxes if s.status == "assigned"),
        "resetting": sum(1 for s in sandboxes if s.status == "resetting"),
        "unhealthy": sum(1 for s in sandboxes if s.status == "unhealthy"),
        "max_containers": config.MAX_CONTAINERS,
        "can_create": _pool.active_count() < config.MAX_CONTAINERS,
    })


# ── List sandboxes ────────────────────────────────────────────────────────────


@app.get("/api/sandbox/list")
async def list_sandboxes(_: None = Depends(require_master_token)) -> JSONResponse:
    return JSONResponse([s.to_dict() for s in _pool.all()])


# ── Get sandbox ───────────────────────────────────────────────────────────────


@app.get("/api/sandbox/{sandbox_id}")
async def get_sandbox(
    sandbox_id: str,
    _: None = Depends(require_master_token),
) -> JSONResponse:
    s = _pool.get(sandbox_id)
    if not s:
        raise HTTPException(status_code=404, detail="Sandbox not found")
    return JSONResponse(s.to_dict())


# ── Create sandbox ────────────────────────────────────────────────────────────


@app.post("/api/sandbox/create")
async def create_sandbox(_: None = Depends(require_master_token)) -> JSONResponse:
    if _pool.active_count() >= config.MAX_CONTAINERS:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Pool at capacity ({config.MAX_CONTAINERS} containers)",
        )

    sandbox_id = secrets.token_hex(8)
    auth_token = secrets.token_hex(24)
    volume_name = f"sandbox-vol-{sandbox_id}"
    host_port = _ports.allocate()
    if host_port is None:
        raise HTTPException(status_code=503, detail="No ports available")

    loop = asyncio.get_event_loop()
    try:
        await loop.run_in_executor(None, _docker.ensure_volume, volume_name)
        container_id = await loop.run_in_executor(
            None,
            _docker.create_container,
            sandbox_id,
            host_port,
            auth_token,
            volume_name,
        )
    except Exception as exc:
        _ports.release(host_port)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    s = SandboxState(
        sandbox_id=sandbox_id,
        container_id=container_id,
        host_port=host_port,
        volume_name=volume_name,
        auth_token=auth_token,
        status="idle",
    )
    _pool.add(s)

    return JSONResponse({
        "sandbox_id": sandbox_id,
        "host_port": host_port,
        "auth_token": auth_token,
        "container_id": container_id,
        "status": "idle",
    }, status_code=201)


# ── Assign sandbox ────────────────────────────────────────────────────────────


class AssignRequest(BaseModel):
    agent_id: str


@app.post("/api/sandbox/{sandbox_id}/assign")
async def assign_sandbox(
    sandbox_id: str,
    body: AssignRequest,
    _: None = Depends(require_master_token),
) -> JSONResponse:
    s = _pool.get(sandbox_id)
    if not s:
        raise HTTPException(status_code=404, detail="Sandbox not found")
    if s.status == "assigned":
        raise HTTPException(status_code=409, detail="Sandbox already assigned")
    _pool.assign(sandbox_id, body.agent_id)
    return JSONResponse({"ok": True, "sandbox_id": sandbox_id, "agent_id": body.agent_id})


# ── Background reset helper ───────────────────────────────────────────────────


async def _background_reset_and_idle(sandbox_id: str) -> None:
    """
    Destroy and recreate the container for *sandbox_id*, wait until it is
    ready, then mark the slot as "idle".

    Called as a fire-and-forget asyncio task by both ``session_end`` and
    ``release_sandbox``.  The sandbox is already in "resetting" state when
    this coroutine runs, so it will not be handed out by ``session_start``
    until the reset finishes.  If the reset fails the slot is marked
    "unhealthy" so the health monitor can clean it up.
    """
    s = _pool.get(sandbox_id)
    if not s:
        return

    loop = asyncio.get_event_loop()
    try:
        new_container_id = await loop.run_in_executor(
            None,
            _docker.reset_container,
            sandbox_id,
            s.host_port,
            s.auth_token,
            s.volume_name,
        )
        s.container_id = new_container_id
        _pool.update(s)

        # Wait for the freshly created container to accept requests before
        # advertising it as idle.  Without this, the next session_start that
        # picks up the idle slot would hand a still-booting container to the
        # agent (the original "sandbox not ready" race condition).
        ready = await _wait_for_container_ready(s.host_port, s.auth_token, timeout=30.0)
        if not ready:
            print(
                f"[pool-manager] WARNING: sandbox {sandbox_id} did not become ready "
                "after reset in 30s — marking unhealthy"
            )
            s.status = "unhealthy"
            _pool.update(s)
            return

        _pool.release(sandbox_id)  # status → "idle"
    except Exception as exc:
        print(f"[pool-manager] Background reset failed for {sandbox_id}: {exc} — marking unhealthy")
        s2 = _pool.get(sandbox_id)
        if s2:
            s2.status = "unhealthy"
            _pool.update(s2)


# ── Release sandbox ───────────────────────────────────────────────────────────


@app.post("/api/sandbox/{sandbox_id}/release")
async def release_sandbox(
    sandbox_id: str,
    _: None = Depends(require_master_token),
) -> JSONResponse:
    s = _pool.get(sandbox_id)
    if not s:
        raise HTTPException(status_code=404, detail="Sandbox not found")

    # Mark as "resetting" immediately (removes agent assignment, stays in
    # active_count so the slot is still guarded) and kick off the Docker
    # destroy+recreate in the background so this HTTP call returns fast.
    _pool.mark_resetting(sandbox_id)
    asyncio.create_task(_background_reset_and_idle(sandbox_id))

    return JSONResponse({"ok": True, "sandbox_id": sandbox_id, "status": "resetting"})


# ── Destroy sandbox ───────────────────────────────────────────────────────────


@app.delete("/api/sandbox/{sandbox_id}")
async def destroy_sandbox(
    sandbox_id: str,
    _: None = Depends(require_master_token),
) -> JSONResponse:
    s = _pool.get(sandbox_id)
    if not s:
        raise HTTPException(status_code=404, detail="Sandbox not found")

    loop = asyncio.get_event_loop()
    errors: list[str] = []
    try:
        await loop.run_in_executor(None, _docker.destroy_container, sandbox_id)
    except Exception as exc:
        errors.append(f"container destroy: {exc}")
    try:
        await loop.run_in_executor(None, _docker.remove_volume, s.volume_name)
    except Exception as exc:
        errors.append(f"volume remove: {exc}")
    finally:
        _ports.release(s.host_port)
        _pool.remove(sandbox_id)

    if errors:
        print(f"[pool-manager] destroy_sandbox {sandbox_id} completed with errors: {errors}")
    return JSONResponse({"ok": True, "sandbox_id": sandbox_id})


# ── Restart sandbox (preserves volume) ────────────────────────────────────────


@app.post("/api/sandbox/{sandbox_id}/restart")
async def restart_sandbox(
    sandbox_id: str,
    _: None = Depends(require_master_token),
) -> JSONResponse:
    """Restart a sandbox container but keep its volume (installed apps persist)."""
    s = _pool.get(sandbox_id)
    if not s:
        raise HTTPException(status_code=404, detail="Sandbox not found")

    prev_agent = s.assigned_agent_id
    _pool.mark_resetting(sandbox_id)

    loop = asyncio.get_event_loop()
    try:
        new_container_id = await loop.run_in_executor(
            None,
            _docker.reset_container,
            sandbox_id,
            s.host_port,
            s.auth_token,
            s.volume_name,
        )
        s2 = _pool.get(sandbox_id)
        if s2:
            s2.container_id = new_container_id
            _pool.update(s2)

        ready = await _wait_for_container_ready(s.host_port, s.auth_token, timeout=30.0)
        if not ready:
            if s2:
                s2.status = "unhealthy"
                _pool.update(s2)
            return JSONResponse({"ok": False, "sandbox_id": sandbox_id, "status": "unhealthy"})

        _pool.release(sandbox_id)
        # Re-assign to the previous agent if it had one
        if prev_agent:
            _pool.assign(sandbox_id, prev_agent)

        return JSONResponse({"ok": True, "sandbox_id": sandbox_id, "status": "running"})
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Restart failed: {exc}") from exc


# ── Toggle persistence ───────────────────────────────────────────────────────


class PersistentRequest(BaseModel):
    persistent: bool


@app.post("/api/sandbox/{sandbox_id}/persistent")
async def set_persistent(
    sandbox_id: str,
    body: PersistentRequest,
    _: None = Depends(require_master_token),
) -> JSONResponse:
    """Toggle the persistent flag on a sandbox."""
    s = _pool.get(sandbox_id)
    if not s:
        raise HTTPException(status_code=404, detail="Sandbox not found")
    s.persistent = body.persistent
    _pool.update(s)
    return JSONResponse({"ok": True, "sandbox_id": sandbox_id, "persistent": s.persistent})


# ── Debug / observability ─────────────────────────────────────────────────────


@app.get("/pool/debug")
async def pool_debug(_: None = Depends(require_master_token)) -> JSONResponse:
    """Return pool state + per-container memory snapshot for ops visibility."""
    sandboxes = _pool.all()
    loop = asyncio.get_event_loop()

    container_stats = {}
    for s in sandboxes:
        try:
            mem_mb = await loop.run_in_executor(None, _docker.get_container_memory_mb, s.sandbox_id)
            container_stats[s.sandbox_id] = {
                "status": s.status,
                "host_port": s.host_port,
                "assigned_agent_id": s.assigned_agent_id,
                "memory_mb": mem_mb,
                "idle_seconds": round(s.idle_seconds(), 1),
                "health_failures": s.health_failures,
            }
        except Exception as exc:
            container_stats[s.sandbox_id] = {"error": str(exc)}

    return JSONResponse({
        "max_containers": config.MAX_CONTAINERS,
        "container_count": len(sandboxes),
        "assigned": sum(1 for s in sandboxes if s.status == "assigned"),
        "idle": sum(1 for s in sandboxes if s.status == "idle"),
        "resetting": sum(1 for s in sandboxes if s.status == "resetting"),
        "unhealthy": sum(1 for s in sandboxes if s.status == "unhealthy"),
        "ports_used": len([s for s in sandboxes]),
        "port_range": f"{config.PORT_RANGE_START}-{config.PORT_RANGE_END}",
        "containers": container_stats,
    })


# ── Setup script execution ────────────────────────────────────────────────────


async def _run_setup_script(
    host_port: int,
    auth_token: str,
    script: str,
    timeout: float = 300.0,
) -> dict:
    """
    Execute a setup script inside a running sandbox container.

    Uses the sandbox server's shell execute endpoint (POST /shell/execute)
    to run the setup script as a bash command.  The script is wrapped in
    bash -c so multi-line scripts work correctly.

    Returns {"ok": bool, "stdout": str, "exit_code": int|None}.
    """
    if not script or not script.strip():
        return {"ok": True, "stdout": "", "exit_code": 0, "skipped": True}

    url = f"http://127.0.0.1:{host_port}/shell/execute"
    headers = {"Authorization": f"Bearer {auth_token}"}

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                url,
                json={"command": script, "timeout": int(timeout)},
                headers=headers,
            )
            if resp.status_code == 200:
                data = resp.json()
                return {"ok": True, **data}
            return {"ok": False, "stdout": resp.text, "exit_code": None}
    except Exception as exc:
        return {"ok": False, "stdout": str(exc), "exit_code": None}


class RunSetupRequest(BaseModel):
    setup_script: str


@app.post("/api/sandbox/{sandbox_id}/run-setup")
async def run_setup(
    sandbox_id: str,
    body: RunSetupRequest,
    _: None = Depends(require_master_token),
) -> JSONResponse:
    """Run a setup script inside a sandbox container."""
    s = _pool.get(sandbox_id)
    if not s:
        raise HTTPException(status_code=404, detail="Sandbox not found")
    if s.status not in ("assigned", "idle"):
        raise HTTPException(status_code=409, detail=f"Sandbox is {s.status}, cannot run setup")

    result = await _run_setup_script(s.host_port, s.auth_token, body.setup_script)
    return JSONResponse(result)


# ── Session helpers (main entry point for backend) ────────────────────────────


class SessionStartRequest(BaseModel):
    agent_id: str
    persistent: bool = False
    setup_script: str | None = None  # Shell commands to run after container is ready


@app.post("/api/sandbox/session/start")
async def session_start(
    body: SessionStartRequest,
    _: None = Depends(require_master_token),
) -> JSONResponse:
    """
    Get-or-create a sandbox for an agent.
    1. Agent already has sandbox → return it
    2. Idle sandbox available → assign it
    3. Capacity allows → create new, assign
    4. At capacity → 503
    """
    # 1. Already assigned
    existing = _pool.get_by_agent(body.agent_id)
    if existing and existing.status in ("assigned", "idle"):
        if existing.status == "idle":
            _pool.assign(existing.sandbox_id, body.agent_id)
        return JSONResponse({
            "sandbox_id": existing.sandbox_id,
            "host_port": existing.host_port,
            "auth_token": existing.auth_token,
            "created": False,
        })

    # 2. Take an idle sandbox
    idle = _pool.idle()
    if idle:
        s = idle[0]
        _pool.assign(s.sandbox_id, body.agent_id)
        return JSONResponse({
            "sandbox_id": s.sandbox_id,
            "host_port": s.host_port,
            "auth_token": s.auth_token,
            "created": False,
        })

    # 3. Create new
    if _pool.active_count() >= config.MAX_CONTAINERS:
        raise HTTPException(
            status_code=503,
            detail=f"Pool at capacity ({config.MAX_CONTAINERS}). Try again later.",
        )

    sandbox_id = secrets.token_hex(8)
    auth_token = secrets.token_hex(24)
    volume_name = f"sandbox-vol-{sandbox_id}"
    host_port = _ports.allocate()
    if host_port is None:
        raise HTTPException(status_code=503, detail="No ports available")

    loop = asyncio.get_event_loop()
    try:
        await loop.run_in_executor(None, _docker.ensure_volume, volume_name)
        container_id = await loop.run_in_executor(
            None,
            _docker.create_container,
            sandbox_id,
            host_port,
            auth_token,
            volume_name,
        )
    except Exception as exc:
        _ports.release(host_port)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    s = SandboxState(
        sandbox_id=sandbox_id,
        container_id=container_id,
        host_port=host_port,
        volume_name=volume_name,
        auth_token=auth_token,
        status="idle",
        persistent=body.persistent,
    )
    _pool.add(s)
    _pool.assign(sandbox_id, body.agent_id)

    # Wait for the container's uvicorn + Xvfb to be ready before returning.
    # Without this, the very first tool call from the agent hits a container
    # that is still booting (startup race condition).
    ready = await _wait_for_container_ready(host_port, auth_token, timeout=30.0)
    if not ready:
        print(f"[pool-manager] WARNING: sandbox {sandbox_id} did not become ready in 30s")

    # Run setup script if provided (non-blocking — errors are logged but don't
    # prevent the sandbox from being returned)
    setup_result = None
    if body.setup_script and ready:
        setup_result = await _run_setup_script(host_port, auth_token, body.setup_script)
        if not setup_result.get("ok"):
            print(f"[pool-manager] WARNING: setup script failed for {sandbox_id}: {setup_result}")

    return JSONResponse({
        "sandbox_id": sandbox_id,
        "host_port": host_port,
        "auth_token": auth_token,
        "created": True,
        "ready": ready,
        "setup_result": setup_result,
    }, status_code=201)


class SessionEndRequest(BaseModel):
    agent_id: str


@app.post("/api/sandbox/session/end")
async def session_end(
    body: SessionEndRequest,
    _: None = Depends(require_master_token),
) -> JSONResponse:
    """
    Release the sandbox assigned to an agent and schedule a reset for reuse.

    The Docker destroy+recreate is intentionally non-blocking: we immediately
    transition the slot to "resetting" (so it is no longer assigned to the
    agent and cannot be handed out as idle) and return success to the caller.
    The background task completes the reset and marks the slot as "idle" once
    the new container is healthy.  This prevents the previous bug where a
    slow Docker reset caused the 30 s HTTP timeout on the backend client,
    leaving the slot permanently stuck in "assigned" state.
    """
    s = _pool.get_by_agent(body.agent_id)
    if not s:
        return JSONResponse({"ok": True, "message": "No sandbox assigned to this agent"})

    sandbox_id = s.sandbox_id

    if s.persistent:
        # Persistent sandboxes keep running — just release the agent assignment.
        # Container stays alive, volume intact, apps installed by the agent persist.
        _pool.release(sandbox_id)
        return JSONResponse({"ok": True, "sandbox_id": sandbox_id, "persistent": True})

    _pool.mark_resetting(sandbox_id)
    asyncio.create_task(_background_reset_and_idle(sandbox_id))

    return JSONResponse({"ok": True, "sandbox_id": sandbox_id})
