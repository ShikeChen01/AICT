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


# ── Release sandbox ───────────────────────────────────────────────────────────


@app.post("/api/sandbox/{sandbox_id}/release")
async def release_sandbox(
    sandbox_id: str,
    _: None = Depends(require_master_token),
) -> JSONResponse:
    s = _pool.get(sandbox_id)
    if not s:
        raise HTTPException(status_code=404, detail="Sandbox not found")

    # Reset the container filesystem (keeps the volume)
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
        _pool.release(sandbox_id)
        _pool.update(s)
    except Exception as exc:
        # If reset fails, mark unhealthy instead of crashing
        s.status = "unhealthy"
        _pool.update(s)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return JSONResponse({"ok": True, "sandbox_id": sandbox_id, "status": "idle"})


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
        "unhealthy": sum(1 for s in sandboxes if s.status == "unhealthy"),
        "ports_used": len([s for s in sandboxes]),
        "port_range": f"{config.PORT_RANGE_START}-{config.PORT_RANGE_END}",
        "containers": container_stats,
    })


# ── Session helpers (main entry point for backend) ────────────────────────────


class SessionStartRequest(BaseModel):
    agent_id: str


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
    )
    _pool.add(s)
    _pool.assign(sandbox_id, body.agent_id)

    # Wait for the container's uvicorn + Xvfb to be ready before returning.
    # Without this, the very first tool call from the agent hits a container
    # that is still booting (startup race condition).
    ready = await _wait_for_container_ready(host_port, auth_token, timeout=30.0)
    if not ready:
        print(f"[pool-manager] WARNING: sandbox {sandbox_id} did not become ready in 30s")

    return JSONResponse({
        "sandbox_id": sandbox_id,
        "host_port": host_port,
        "auth_token": auth_token,
        "created": True,
        "ready": ready,
    }, status_code=201)


class SessionEndRequest(BaseModel):
    agent_id: str


@app.post("/api/sandbox/session/end")
async def session_end(
    body: SessionEndRequest,
    _: None = Depends(require_master_token),
) -> JSONResponse:
    """Release the sandbox assigned to an agent and reset it for reuse."""
    s = _pool.get_by_agent(body.agent_id)
    if not s:
        return JSONResponse({"ok": True, "message": "No sandbox assigned to this agent"})

    loop = asyncio.get_event_loop()
    try:
        new_container_id = await loop.run_in_executor(
            None,
            _docker.reset_container,
            s.sandbox_id,
            s.host_port,
            s.auth_token,
            s.volume_name,
        )
        s.container_id = new_container_id
        _pool.release(s.sandbox_id)
        _pool.update(s)
    except Exception as exc:
        s.status = "unhealthy"
        _pool.update(s)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return JSONResponse({"ok": True, "sandbox_id": s.sandbox_id})
