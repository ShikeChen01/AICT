"""Pool Manager v4 — Hybrid Docker + QEMU compute backend.

Unified API for headless (Docker) and desktop (QEMU/KVM) agent workloads.
Routes session_start by `requires_desktop` flag. Supports mid-session
promote/demote between tiers.

Backward compatible: all v3 /api/sandbox/* endpoints still work for
headless containers. New v4 endpoints added for desktop, promote/demote,
and capacity budget introspection.
"""

from __future__ import annotations

import asyncio
import secrets
from contextlib import asynccontextmanager
from typing import Optional

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

import config
from capacity_budget import CapacityBudget, ExhaustedError
from docker_manager import DockerManager

def _external_host() -> str:
    """Return the Grand-VM's external host for session responses."""
    if config.EXTERNAL_HOST:
        return config.EXTERNAL_HOST
    # Prefer the public NIC on GCE so Cloud Run can reach sandbox ports directly.
    import subprocess
    import urllib.request

    try:
        req = urllib.request.Request(
            "http://metadata.google.internal/computeMetadata/v1/instance/network-interfaces/0/access-configs/0/external-ip",
            headers={"Metadata-Flavor": "Google"},
        )
        with urllib.request.urlopen(req, timeout=2) as resp:
            ip = resp.read().decode().strip()
            if ip:
                return ip
    except Exception:
        pass

    # Fall back to auto-detect: hostname -I grabs the primary interface IP.
    try:
        result = subprocess.run(["hostname", "-I"], capture_output=True, text=True, timeout=2)
        if result.returncode == 0:
            ip = result.stdout.strip().split()[0]
            if ip:
                return ip
    except Exception:
        pass
    return "127.0.0.1"
from health_monitor import HealthMonitor
from models import PoolState, UnitState, UnitStatus, UnitType
from port_allocator import PortAllocator

# VMManager is optional — only available when libvirt is installed.
try:
    from vm_manager import VMManager

    _VM_AVAILABLE = True
except ImportError:
    VMManager = None  # type: ignore[assignment,misc]
    _VM_AVAILABLE = False

# ── Singletons ────────────────────────────────────────────────────────────────

_pool: PoolState
_docker: DockerManager
_vm: Optional["VMManager"]
_ports: PortAllocator
_budget: CapacityBudget
_monitor: HealthMonitor


# ── Startup / shutdown ────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _pool, _docker, _vm, _ports, _budget, _monitor

    _pool = PoolState(config.STATE_FILE)
    _docker = DockerManager()
    _vm = VMManager() if _VM_AVAILABLE else None
    _ports = PortAllocator()
    _budget = CapacityBudget()

    # ── Reconcile persisted state against reality ─────────────────────────
    stale_ids: list[str] = []
    for u in _pool.all():
        alive = False
        if u.is_headless:
            alive = _docker.is_running(u.unit_id)
        elif u.is_desktop and _vm is not None:
            alive = _vm.is_running(u.unit_id)

        if not alive:
            stale_ids.append(u.unit_id)

    for uid in stale_ids:
        u = _pool.get(uid)
        if not u:
            continue
        print(f"[pool-manager] Removing stale unit {uid} ({u.unit_type}) — not running")
        try:
            if u.is_headless:
                _docker.destroy_container(uid)
            elif u.is_desktop and _vm is not None:
                _vm.destroy_vm(uid, u.host_port)
        except Exception as exc:
            print(f"[pool-manager] Warning: cleanup error for {uid}: {exc}")
        _ports.release(u.host_port)
        _pool.remove(uid)

    # Destroy orphan Docker containers not in state
    known_ids = {u.unit_id for u in _pool.all()}
    for c in _docker.list_sandbox_containers():
        cname = c["name"].lstrip("/")
        if not cname.startswith("sandbox-"):
            continue
        sid = cname[len("sandbox-"):]
        if sid not in known_ids:
            print(f"[pool-manager] Destroying orphan container {cname}")
            try:
                _docker.destroy_container(sid)
            except Exception as exc:
                print(f"[pool-manager] Warning: orphan cleanup error {cname}: {exc}")

    # Reclaim ports and rebuild budget from surviving units
    used_ports = [u.host_port for u in _pool.all()]
    _ports.reclaim_from_pool(used_ports)
    _budget.rebuild_from_units(
        headless=_pool.headless_count(),
        desktop=_pool.desktop_count(),
    )

    _monitor = HealthMonitor(_pool, _docker, _vm, _ports, _budget)
    _monitor.start()

    snap = _budget.snapshot()
    print(
        f"[pool-manager] v4 started. "
        f"headless={snap.headless_count}/{snap.headless_max} "
        f"desktop={snap.desktop_count}/{snap.desktop_max} "
        f"(evicted {len(stale_ids)} stale)"
    )
    yield
    _monitor.stop()
    if _vm is not None:
        _vm.close()


# ── Auth ──────────────────────────────────────────────────────────────────────


async def require_master_token(request: Request) -> None:
    if not config.MASTER_TOKEN:
        return
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token")
    token = auth.removeprefix("Bearer ").strip()
    if token != config.MASTER_TOKEN:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(title="AICT Pool Manager v4", version="4.0.0", lifespan=lifespan)


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _wait_for_ready(
    host_port: int,
    auth_token: str,
    timeout: float = 30.0,
    poll_interval: float = 1.0,
    vm_ip: str | None = None,
) -> bool:
    # For desktop VMs, poll the bridge IP directly (iptables OUTPUT DNAT
    # is unreliable when Docker's FORWARD policy is DROP).
    if vm_ip:
        url = f"http://{vm_ip}:{config.CONTAINER_INTERNAL_PORT}/health"
    else:
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


async def _create_headless(unit_id: str, auth_token: str, persistent: bool = False) -> UnitState:
    """Create a headless Docker container. Raises on failure."""
    _budget.reserve("headless")
    host_port = _ports.allocate("headless")
    if host_port is None:
        _budget.release("headless")
        raise HTTPException(status_code=503, detail="No headless ports available")

    volume_name = f"sandbox-vol-{unit_id}"
    loop = asyncio.get_event_loop()
    try:
        await loop.run_in_executor(None, _docker.ensure_volume, volume_name)
        container_id = await loop.run_in_executor(
            None, _docker.create_container, unit_id, host_port, auth_token, volume_name,
        )
    except Exception as exc:
        _ports.release(host_port)
        _budget.release("headless")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    u = UnitState(
        unit_id=unit_id,
        unit_type=UnitType.HEADLESS.value,
        host_port=host_port,
        auth_token=auth_token,
        status=UnitStatus.IDLE.value,
        persistent=persistent,
        container_id=container_id,
        volume_name=volume_name,
    )
    _pool.add(u)
    return u


async def _create_desktop(unit_id: str, auth_token: str, persistent: bool = False) -> UnitState:
    """Create a desktop QEMU/KVM sub-VM. Raises on failure."""
    if _vm is None:
        raise HTTPException(
            status_code=501,
            detail="Desktop sub-VMs unavailable: libvirt not installed on this host",
        )

    _budget.reserve("desktop")
    host_port = _ports.allocate("desktop")
    if host_port is None:
        _budget.release("desktop")
        raise HTTPException(status_code=503, detail="No desktop ports available")

    loop = asyncio.get_event_loop()
    try:
        domain_name = await loop.run_in_executor(
            None, _vm.create_vm, unit_id, host_port, auth_token,
        )
    except Exception as exc:
        _ports.release(host_port)
        _budget.release("desktop")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    vm_ip = VMManager._static_ip_for_port(host_port) if VMManager else ""

    u = UnitState(
        unit_id=unit_id,
        unit_type=UnitType.DESKTOP.value,
        host_port=host_port,
        auth_token=auth_token,
        status=UnitStatus.IDLE.value,
        persistent=persistent,
        domain_name=domain_name,
        vm_ip=vm_ip,
    )
    _pool.add(u)
    return u


async def _run_setup_script(host_port: int, auth_token: str, script: str, timeout: float = 300.0) -> dict:
    if not script or not script.strip():
        return {"ok": True, "stdout": "", "exit_code": 0, "skipped": True}
    url = f"http://127.0.0.1:{host_port}/shell/execute"
    headers = {"Authorization": f"Bearer {auth_token}"}
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json={"command": script, "timeout": int(timeout)}, headers=headers)
            if resp.status_code == 200:
                return {"ok": True, **resp.json()}
            return {"ok": False, "stdout": resp.text, "exit_code": None}
    except Exception as exc:
        return {"ok": False, "stdout": str(exc), "exit_code": None}


async def _destroy_unit(u: UnitState) -> list[str]:
    """Destroy a unit and free all resources. Returns list of non-fatal errors."""
    errors: list[str] = []
    loop = asyncio.get_event_loop()

    try:
        if u.is_headless:
            await loop.run_in_executor(None, _docker.destroy_container, u.unit_id)
        elif u.is_desktop and _vm is not None:
            await loop.run_in_executor(None, _vm.destroy_vm, u.unit_id, u.host_port)
    except Exception as exc:
        errors.append(f"destroy: {exc}")

    if u.is_headless and u.volume_name:
        try:
            await loop.run_in_executor(None, _docker.remove_volume, u.volume_name)
        except Exception as exc:
            errors.append(f"volume: {exc}")

    _ports.release(u.host_port)
    _pool.remove(u.unit_id)
    _budget.release(u.unit_type)
    return errors


# ── Health ────────────────────────────────────────────────────────────────────


@app.get("/api/health")
async def health(_: None = Depends(require_master_token)) -> JSONResponse:
    snap = _budget.snapshot()
    return JSONResponse({
        "status": "ok",
        "version": "4.0",
        **snap.to_dict(),
    })


# ── Status (v4) ──────────────────────────────────────────────────────────────


@app.get("/api/status")
async def budget_status(_: None = Depends(require_master_token)) -> JSONResponse:
    snap = _budget.snapshot()
    units = [u.to_dict() for u in _pool.all()]
    return JSONResponse({"budget": snap.to_dict(), "units": units})


# ── List units (v4, replaces /api/sandbox/list) ──────────────────────────────


@app.get("/api/units")
async def list_units(_: None = Depends(require_master_token)) -> JSONResponse:
    return JSONResponse([u.to_dict() for u in _pool.all()])


# ── Backward compat: /api/sandbox/list ────────────────────────────────────────


@app.get("/api/sandbox/list")
async def list_sandboxes(_: None = Depends(require_master_token)) -> JSONResponse:
    return JSONResponse([u.to_dict() for u in _pool.all()])


# ── Get unit ──────────────────────────────────────────────────────────────────


@app.get("/api/sandbox/{unit_id}")
async def get_unit(unit_id: str, _: None = Depends(require_master_token)) -> JSONResponse:
    u = _pool.get(unit_id)
    if not u:
        raise HTTPException(status_code=404, detail="Unit not found")
    return JSONResponse(u.to_dict())


# ── Session start (v4: dual-backend routing) ─────────────────────────────────


class SessionStartRequest(BaseModel):
    agent_id: str | None = None  # Optional: backend may create sandbox before agent assignment
    persistent: bool = False
    requires_desktop: bool = False
    setup_script: str | None = None
    os_image: str | None = None
    project_id: str | None = None


@app.post("/api/sandbox/session/start")
async def session_start(
    body: SessionStartRequest,
    _: None = Depends(require_master_token),
) -> JSONResponse:
    """Get-or-create a compute unit for an agent.

    Routes by `requires_desktop`:
      - false → Docker headless container
      - true  → QEMU/KVM desktop sub-VM
    """
    unit_type = UnitType.DESKTOP.value if body.requires_desktop else UnitType.HEADLESS.value
    timeout = 180.0 if body.requires_desktop else 30.0

    host = _external_host()

    # 1. Agent already has a unit
    if body.agent_id:
        existing = _pool.get_by_agent(body.agent_id)
        if existing and existing.status in (UnitStatus.ASSIGNED.value, UnitStatus.IDLE.value):
            if existing.status == UnitStatus.IDLE.value:
                _pool.assign(existing.unit_id, body.agent_id)
            ready = await _wait_for_ready(existing.host_port, existing.auth_token, timeout=5.0, poll_interval=0.5, vm_ip=existing.vm_ip)
            return JSONResponse({
                "sandbox_id": existing.unit_id,
                "host": host,
                "host_port": existing.host_port,
                "auth_token": existing.auth_token,
                "unit_type": existing.unit_type,
                "created": False,
                "ready": ready,
            })

    # 2. Take an idle unit of the requested type
    idle_units = _pool.idle(unit_type)
    if idle_units:
        u = idle_units[0]
        if body.agent_id:
            _pool.assign(u.unit_id, body.agent_id)
        ready = await _wait_for_ready(u.host_port, u.auth_token, timeout=5.0, poll_interval=0.5, vm_ip=u.vm_ip)
        return JSONResponse({
            "sandbox_id": u.unit_id,
            "host": host,
            "host_port": u.host_port,
            "auth_token": u.auth_token,
            "unit_type": u.unit_type,
            "created": False,
            "ready": ready,
        })

    # 3. Create new unit
    unit_id = secrets.token_hex(8)
    auth_token = secrets.token_hex(24)

    try:
        if body.requires_desktop:
            u = await _create_desktop(unit_id, auth_token, persistent=True)  # desktops are always persistent
        else:
            u = await _create_headless(unit_id, auth_token, body.persistent)
    except ExhaustedError as exc:
        return JSONResponse(exc.to_dict(), status_code=503)

    if body.agent_id:
        _pool.assign(u.unit_id, body.agent_id)

    ready = await _wait_for_ready(u.host_port, u.auth_token, timeout=timeout, vm_ip=u.vm_ip)
    if not ready:
        print(f"[pool-manager] WARNING: unit {u.unit_id} did not become ready in {timeout}s")

    setup_result = None
    if body.setup_script and ready:
        setup_result = await _run_setup_script(u.host_port, u.auth_token, body.setup_script)
        if not setup_result.get("ok"):
            print(f"[pool-manager] WARNING: setup script failed for {u.unit_id}: {setup_result}")

    return JSONResponse(
        {
            "sandbox_id": u.unit_id,
            "host": host,
            "host_port": u.host_port,
            "auth_token": u.auth_token,
            "unit_type": u.unit_type,
            "created": True,
            "ready": ready,
            "setup_result": setup_result,
        },
        status_code=201,
    )


# ── Session end ───────────────────────────────────────────────────────────────


class SessionEndRequest(BaseModel):
    agent_id: str


@app.post("/api/sandbox/session/end")
async def session_end(
    body: SessionEndRequest,
    _: None = Depends(require_master_token),
) -> JSONResponse:
    u = _pool.get_by_agent(body.agent_id)
    if not u:
        return JSONResponse({"ok": True, "message": "No unit assigned to this agent"})

    if u.persistent:
        _pool.release(u.unit_id)
        return JSONResponse({"ok": True, "sandbox_id": u.unit_id, "persistent": True})

    if u.is_headless:
        _pool.mark_resetting(u.unit_id)
        asyncio.create_task(_background_reset_headless(u.unit_id))
    else:
        # Desktop sub-VMs: destroy entirely for temp units (reclaim resources)
        await _destroy_unit(u)

    return JSONResponse({"ok": True, "sandbox_id": u.unit_id})


async def _background_reset_headless(unit_id: str) -> None:
    """Destroy and recreate a headless container for reuse."""
    u = _pool.get(unit_id)
    if not u:
        return
    loop = asyncio.get_event_loop()
    try:
        new_container_id = await loop.run_in_executor(
            None, _docker.reset_container, unit_id, u.host_port, u.auth_token, u.volume_name,
        )
        u2 = _pool.get(unit_id)
        if u2:
            u2.container_id = new_container_id
            _pool.update(u2)

        if await _wait_for_ready(u.host_port, u.auth_token, timeout=30.0):
            _pool.release(unit_id)
        else:
            print(f"[pool-manager] WARNING: {unit_id} not ready after reset — marking unhealthy")
            u3 = _pool.get(unit_id)
            if u3:
                u3.status = UnitStatus.UNHEALTHY.value
                _pool.update(u3)
    except Exception as exc:
        print(f"[pool-manager] Background reset failed for {unit_id}: {exc}")
        u4 = _pool.get(unit_id)
        if u4:
            u4.status = UnitStatus.UNHEALTHY.value
            _pool.update(u4)


# ── Promote (headless → desktop) ─────────────────────────────────────────────


class PromoteRequest(BaseModel):
    agent_id: str | None = None


@app.post("/api/session/promote/{unit_id}")
async def promote_unit(
    unit_id: str,
    body: PromoteRequest,
    _: None = Depends(require_master_token),
) -> JSONResponse:
    """Promote a headless container to a desktop sub-VM mid-session."""
    u = _pool.get(unit_id)
    if not u:
        raise HTTPException(status_code=404, detail="Unit not found")
    if u.unit_type != UnitType.HEADLESS.value:
        raise HTTPException(status_code=409, detail="Unit is already a desktop")
    if _vm is None:
        raise HTTPException(status_code=501, detail="Desktop sub-VMs unavailable")

    try:
        _budget.promote()
    except ExhaustedError as exc:
        return JSONResponse(exc.to_dict(), status_code=503)

    prev_agent = u.assigned_agent_id
    u.status = UnitStatus.PROMOTING.value
    _pool.update(u)

    # Create desktop VM
    new_id = secrets.token_hex(8)
    desktop_port = _ports.allocate("desktop")
    if desktop_port is None:
        _budget.demote()
        u.status = UnitStatus.ASSIGNED.value if prev_agent else UnitStatus.IDLE.value
        _pool.update(u)
        raise HTTPException(status_code=503, detail="No desktop ports available")

    loop = asyncio.get_event_loop()
    try:
        domain_name = await loop.run_in_executor(
            None, _vm.create_vm, new_id, desktop_port, u.auth_token,
        )
    except Exception as exc:
        _ports.release(desktop_port)
        _budget.demote()
        u.status = UnitStatus.ASSIGNED.value if prev_agent else UnitStatus.IDLE.value
        _pool.update(u)
        raise HTTPException(status_code=500, detail=f"VM creation failed: {exc}") from exc

    # Wait for VM to be ready
    desktop_vm_ip = VMManager._static_ip_for_port(desktop_port) if VMManager else None
    ready = await _wait_for_ready(desktop_port, u.auth_token, timeout=60.0, vm_ip=desktop_vm_ip)

    # Migrate files from Docker volume to VM
    if ready and u.volume_name:
        vm_ip = desktop_vm_ip or VMManager._static_ip_for_port(desktop_port)
        await loop.run_in_executor(
            None, VMManager.migrate_files_to_vm,
            u.volume_name, new_id, vm_ip, u.auth_token,
        )

    # Destroy old headless container
    try:
        await loop.run_in_executor(None, _docker.destroy_container, u.unit_id)
        if u.volume_name:
            await loop.run_in_executor(None, _docker.remove_volume, u.volume_name)
    except Exception:
        pass
    _ports.release(u.host_port)
    _pool.remove(u.unit_id)

    # Register new desktop unit
    vm_ip = VMManager._static_ip_for_port(desktop_port) if VMManager else ""
    new_unit = UnitState(
        unit_id=new_id,
        unit_type=UnitType.DESKTOP.value,
        host_port=desktop_port,
        auth_token=u.auth_token,
        status=UnitStatus.IDLE.value,
        persistent=False,  # promoted desktops are temporary
        domain_name=domain_name,
        vm_ip=vm_ip,
    )
    _pool.add(new_unit)
    if prev_agent:
        _pool.assign(new_id, prev_agent)

    return JSONResponse({
        "ok": True,
        "old_unit_id": unit_id,
        "new_unit_id": new_id,
        "unit_type": "desktop",
        "host": _external_host(),
        "host_port": desktop_port,
        "auth_token": u.auth_token,
        "ready": ready,
    })


# ── Demote (desktop → headless) ──────────────────────────────────────────────


@app.post("/api/session/demote/{unit_id}")
async def demote_unit(
    unit_id: str,
    body: PromoteRequest,
    _: None = Depends(require_master_token),
) -> JSONResponse:
    """Demote a desktop sub-VM back to a headless container."""
    u = _pool.get(unit_id)
    if not u:
        raise HTTPException(status_code=404, detail="Unit not found")
    if u.unit_type != UnitType.DESKTOP.value:
        raise HTTPException(status_code=409, detail="Unit is already headless")

    prev_agent = u.assigned_agent_id
    u.status = UnitStatus.DEMOTING.value
    _pool.update(u)

    _budget.demote()

    # Create new headless container
    new_id = secrets.token_hex(8)
    auth_token = u.auth_token
    headless_port = _ports.allocate("headless")
    if headless_port is None:
        _budget.promote()  # rollback
        u.status = UnitStatus.ASSIGNED.value if prev_agent else UnitStatus.IDLE.value
        _pool.update(u)
        raise HTTPException(status_code=503, detail="No headless ports available")

    volume_name = f"sandbox-vol-{new_id}"
    loop = asyncio.get_event_loop()
    try:
        await loop.run_in_executor(None, _docker.ensure_volume, volume_name)
        container_id = await loop.run_in_executor(
            None, _docker.create_container, new_id, headless_port, auth_token, volume_name,
        )
    except Exception as exc:
        _ports.release(headless_port)
        _budget.promote()  # rollback
        u.status = UnitStatus.ASSIGNED.value if prev_agent else UnitStatus.IDLE.value
        _pool.update(u)
        raise HTTPException(status_code=500, detail=f"Container creation failed: {exc}") from exc

    ready = await _wait_for_ready(headless_port, auth_token, timeout=30.0)

    # Migrate files from VM to Docker volume
    if ready and u.vm_ip:
        await loop.run_in_executor(
            None, VMManager.migrate_files_from_vm, u.vm_ip, volume_name,
        )

    # Destroy old desktop VM
    if _vm is not None:
        try:
            await loop.run_in_executor(None, _vm.destroy_vm, u.unit_id, u.host_port)
        except Exception:
            pass
    _ports.release(u.host_port)
    _pool.remove(u.unit_id)

    new_unit = UnitState(
        unit_id=new_id,
        unit_type=UnitType.HEADLESS.value,
        host_port=headless_port,
        auth_token=auth_token,
        status=UnitStatus.IDLE.value,
        persistent=False,
        container_id=container_id,
        volume_name=volume_name,
    )
    _pool.add(new_unit)
    if prev_agent:
        _pool.assign(new_id, prev_agent)

    return JSONResponse({
        "ok": True,
        "old_unit_id": unit_id,
        "new_unit_id": new_id,
        "unit_type": "headless",
        "host": _external_host(),
        "host_port": headless_port,
        "auth_token": auth_token,
        "ready": ready,
    })


# ── Destroy unit ──────────────────────────────────────────────────────────────


@app.delete("/api/unit/{unit_id}")
async def destroy_unit_endpoint(
    unit_id: str,
    _: None = Depends(require_master_token),
) -> JSONResponse:
    u = _pool.get(unit_id)
    if not u:
        raise HTTPException(status_code=404, detail="Unit not found")
    errors = await _destroy_unit(u)
    if errors:
        print(f"[pool-manager] destroy {unit_id} completed with errors: {errors}")
    return JSONResponse({"ok": True, "sandbox_id": unit_id})


# Backward compat
@app.delete("/api/sandbox/{unit_id}")
async def destroy_sandbox(unit_id: str, _: None = Depends(require_master_token)) -> JSONResponse:
    return await destroy_unit_endpoint(unit_id, _)


# ── Assign / release / restart ────────────────────────────────────────────────


class AssignRequest(BaseModel):
    agent_id: str


@app.post("/api/sandbox/{unit_id}/assign")
async def assign_unit(
    unit_id: str,
    body: AssignRequest,
    _: None = Depends(require_master_token),
) -> JSONResponse:
    u = _pool.get(unit_id)
    if not u:
        raise HTTPException(status_code=404, detail="Unit not found")
    if u.status == UnitStatus.ASSIGNED.value:
        raise HTTPException(status_code=409, detail="Unit already assigned")
    _pool.assign(unit_id, body.agent_id)
    return JSONResponse({"ok": True, "sandbox_id": unit_id, "agent_id": body.agent_id})


@app.post("/api/sandbox/{unit_id}/release")
async def release_unit(
    unit_id: str,
    _: None = Depends(require_master_token),
) -> JSONResponse:
    u = _pool.get(unit_id)
    if not u:
        raise HTTPException(status_code=404, detail="Unit not found")

    if u.is_headless:
        _pool.mark_resetting(unit_id)
        asyncio.create_task(_background_reset_headless(unit_id))
    else:
        _pool.release(unit_id)

    return JSONResponse({"ok": True, "sandbox_id": unit_id, "status": "resetting" if u.is_headless else "idle"})


@app.post("/api/sandbox/{unit_id}/restart")
async def restart_unit(
    unit_id: str,
    _: None = Depends(require_master_token),
) -> JSONResponse:
    u = _pool.get(unit_id)
    if not u:
        raise HTTPException(status_code=404, detail="Unit not found")

    prev_agent = u.assigned_agent_id
    _pool.mark_resetting(unit_id)

    loop = asyncio.get_event_loop()
    if u.is_headless:
        try:
            new_id = await loop.run_in_executor(
                None, _docker.reset_container, unit_id, u.host_port, u.auth_token, u.volume_name,
            )
            u2 = _pool.get(unit_id)
            if u2:
                u2.container_id = new_id
                _pool.update(u2)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Restart failed: {exc}") from exc
    elif u.is_desktop and _vm is not None:
        try:
            await loop.run_in_executor(None, _vm.stop_vm, unit_id)
            await asyncio.sleep(2)
            await loop.run_in_executor(None, _vm.start_vm, unit_id)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"VM restart failed: {exc}") from exc

    timeout = 60.0 if u.is_desktop else 30.0
    ready = await _wait_for_ready(u.host_port, u.auth_token, timeout=timeout, vm_ip=u.vm_ip)

    if not ready:
        u3 = _pool.get(unit_id)
        if u3:
            u3.status = UnitStatus.UNHEALTHY.value
            _pool.update(u3)
        return JSONResponse({"ok": False, "sandbox_id": unit_id, "status": "unhealthy"})

    _pool.release(unit_id)
    if prev_agent:
        _pool.assign(unit_id, prev_agent)

    return JSONResponse({"ok": True, "sandbox_id": unit_id, "status": "running"})


# ── Persistent toggle ─────────────────────────────────────────────────────────


class PersistentRequest(BaseModel):
    persistent: bool


@app.post("/api/sandbox/{unit_id}/persistent")
async def set_persistent(
    unit_id: str,
    body: PersistentRequest,
    _: None = Depends(require_master_token),
) -> JSONResponse:
    u = _pool.get(unit_id)
    if not u:
        raise HTTPException(status_code=404, detail="Unit not found")
    u.persistent = body.persistent
    _pool.update(u)
    return JSONResponse({"ok": True, "sandbox_id": unit_id, "persistent": u.persistent})


# ── Setup script execution ────────────────────────────────────────────────────


class RunSetupRequest(BaseModel):
    setup_script: str


@app.post("/api/sandbox/{unit_id}/run-setup")
async def run_setup(
    unit_id: str,
    body: RunSetupRequest,
    _: None = Depends(require_master_token),
) -> JSONResponse:
    u = _pool.get(unit_id)
    if not u:
        raise HTTPException(status_code=404, detail="Unit not found")
    if u.status not in (UnitStatus.ASSIGNED.value, UnitStatus.IDLE.value):
        raise HTTPException(status_code=409, detail=f"Unit is {u.status}, cannot run setup")
    result = await _run_setup_script(u.host_port, u.auth_token, body.setup_script)
    return JSONResponse(result)


# ── Command timestamp tracking ────────────────────────────────────────────────


@app.post("/api/sandbox/{unit_id}/touch")
async def touch_command(
    unit_id: str,
    _: None = Depends(require_master_token),
) -> JSONResponse:
    """Record that a command was routed to this unit (updates idle timer)."""
    u = _pool.get(unit_id)
    if not u:
        raise HTTPException(status_code=404, detail="Unit not found")
    u.touch_command()
    _pool.update(u)
    return JSONResponse({"ok": True})


# ── Snapshot / restore (unified) ───────────────────────────────────────────────
#
# For headless containers: docker commit → tagged image
# For desktop sub-VMs: libvirt snapshot
# The backend calls /api/sandbox/{id}/snapshot for all unit types.


class SnapshotCreateRequest(BaseModel):
    label: str = ""


@app.post("/api/sandbox/{unit_id}/snapshot")
async def create_snapshot(
    unit_id: str,
    body: SnapshotCreateRequest,
    _: None = Depends(require_master_token),
) -> JSONResponse:
    """Create a snapshot of a unit (Docker commit or VM snapshot)."""
    u = _pool.get(unit_id)
    if not u:
        raise HTTPException(status_code=404, detail="Unit not found")

    loop = asyncio.get_event_loop()
    label = body.label or f"snap-{unit_id[:8]}"

    if u.is_headless:
        # Docker commit to a tagged image
        snapshot_name = f"sandbox-snap-{unit_id}-{label}"
        try:
            await loop.run_in_executor(
                None, _docker.commit_container, unit_id, snapshot_name,
            )
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Snapshot failed: {exc}") from exc
    elif u.is_desktop and _vm is not None:
        snapshot_name = await loop.run_in_executor(None, _vm.create_snapshot, unit_id, label)
    else:
        raise HTTPException(status_code=501, detail="Snapshots unavailable for this unit type")

    return JSONResponse({"ok": True, "snapshot_name": snapshot_name, "unit_id": unit_id})


# ── VNC WebSocket proxy ──────────────────────────────────────────────────────


@app.websocket("/ws/vnc/{unit_id}")
async def vnc_proxy_ws(ws: WebSocket, unit_id: str):
    """Proxy VNC WebSocket from external clients to the sub-VM's sandbox server.

    The backend (Cloud Run) connects here instead of going through iptables DNAT
    on the desktop port, since VPC→DNAT→bridge routing is unreliable.
    """
    import websockets

    u = _pool.get(unit_id)
    if u is None:
        await ws.close(code=4004, reason="Unit not found")
        return
    if not u.is_desktop or not u.vm_ip:
        await ws.close(code=4005, reason="Not a desktop unit")
        return

    # Verify auth token from query params
    token = ws.query_params.get("token", "")
    if token != u.auth_token:
        await ws.close(code=4001, reason="Invalid token")
        return

    await ws.accept(subprotocol="binary")

    upstream_url = f"ws://{u.vm_ip}:{config.CONTAINER_INTERNAL_PORT}/ws/vnc?token={u.auth_token}"
    try:
        upstream = await asyncio.wait_for(
            websockets.connect(
                upstream_url,
                open_timeout=6,
                max_size=2**22,
                subprotocols=[websockets.Subprotocol("binary")],
                ping_interval=30,
                ping_timeout=10,
            ).__aenter__(),
            timeout=8,
        )
    except Exception as exc:
        print(f"[vnc-proxy] Failed to connect upstream for {unit_id}: {exc}")
        await ws.close(code=1011, reason=f"VNC upstream unreachable: {type(exc).__name__}")
        return

    # Keepalive: the pool manager owns the idle timer for VNC sessions.
    # Touch the unit every 2 min while the VNC proxy is alive so the
    # idle reaper never kills a desktop with an active viewer.
    async def _vnc_keepalive():
        try:
            while True:
                await asyncio.sleep(120)
                u2 = _pool.get(unit_id)
                if u2:
                    u2.touch_command()
                    _pool.update(u2)
        except asyncio.CancelledError:
            pass

    touch_task = asyncio.create_task(_vnc_keepalive())

    try:
        async def frontend_to_sandbox():
            while True:
                data = await ws.receive_bytes()
                await upstream.send(data)

        async def sandbox_to_frontend():
            async for msg in upstream:
                if isinstance(msg, bytes):
                    await ws.send_bytes(msg)
                else:
                    await ws.send_text(msg)

        f2s = asyncio.create_task(frontend_to_sandbox())
        s2f = asyncio.create_task(sandbox_to_frontend())
        done, pending = await asyncio.wait({f2s, s2f}, return_when=asyncio.FIRST_COMPLETED)
        for t in pending:
            t.cancel()
    except Exception:
        pass
    finally:
        touch_task.cancel()
        try:
            await upstream.close()
        except Exception:
            pass


class SnapshotRestoreRequest(BaseModel):
    snapshot_name: str


@app.post("/api/sandbox/{unit_id}/restore")
async def restore_snapshot(
    unit_id: str,
    body: SnapshotRestoreRequest,
    _: None = Depends(require_master_token),
) -> JSONResponse:
    """Restore a unit from a snapshot."""
    u = _pool.get(unit_id)
    if not u:
        raise HTTPException(status_code=404, detail="Unit not found")

    loop = asyncio.get_event_loop()

    if u.is_headless:
        # For Docker: stop, remove, re-create from snapshot image
        try:
            await loop.run_in_executor(
                None, _docker.restore_from_snapshot, unit_id, body.snapshot_name,
                u.host_port, u.auth_token, u.volume_name,
            )
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Restore failed: {exc}") from exc
    elif u.is_desktop and _vm is not None:
        await loop.run_in_executor(None, _vm.restore_snapshot, unit_id, body.snapshot_name)
    else:
        raise HTTPException(status_code=501, detail="Restore unavailable for this unit type")

    return JSONResponse({"ok": True, "restored": body.snapshot_name, "unit_id": unit_id})


@app.get("/api/sandbox/{unit_id}/snapshots")
async def list_snapshots(
    unit_id: str,
    _: None = Depends(require_master_token),
) -> JSONResponse:
    """List snapshots for a unit."""
    u = _pool.get(unit_id)
    if not u:
        raise HTTPException(status_code=404, detail="Unit not found")

    loop = asyncio.get_event_loop()

    if u.is_headless:
        try:
            snapshots = await loop.run_in_executor(
                None, _docker.list_snapshots, unit_id,
            )
        except Exception:
            snapshots = []
    elif u.is_desktop and _vm is not None:
        try:
            snapshots = await loop.run_in_executor(None, _vm.list_snapshots, unit_id)
        except Exception:
            snapshots = []
    else:
        snapshots = []

    return JSONResponse(snapshots)


# ── VM snapshot / restore (v4 legacy path, desktop only) ──────────────────────


class SnapshotRequest(BaseModel):
    label: str = ""


@app.post("/api/vm/{unit_id}/snapshot")
async def vm_snapshot(
    unit_id: str,
    body: SnapshotRequest,
    _: None = Depends(require_master_token),
) -> JSONResponse:
    u = _pool.get(unit_id)
    if not u:
        raise HTTPException(status_code=404, detail="Unit not found")
    if u.unit_type != UnitType.DESKTOP.value:
        raise HTTPException(status_code=409, detail="Snapshots only available for desktop sub-VMs")
    if _vm is None:
        raise HTTPException(status_code=501, detail="VMManager unavailable")

    loop = asyncio.get_event_loop()
    snap_name = await loop.run_in_executor(None, _vm.create_snapshot, unit_id, body.label)
    return JSONResponse({"ok": True, "snapshot": snap_name})


class RestoreRequest(BaseModel):
    snapshot: str


@app.post("/api/vm/{unit_id}/restore")
async def vm_restore(
    unit_id: str,
    body: RestoreRequest,
    _: None = Depends(require_master_token),
) -> JSONResponse:
    u = _pool.get(unit_id)
    if not u:
        raise HTTPException(status_code=404, detail="Unit not found")
    if u.unit_type != UnitType.DESKTOP.value:
        raise HTTPException(status_code=409, detail="Restore only available for desktop sub-VMs")
    if _vm is None:
        raise HTTPException(status_code=501, detail="VMManager unavailable")

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _vm.restore_snapshot, unit_id, body.snapshot)
    return JSONResponse({"ok": True, "restored": body.snapshot})


# ── REST proxy for desktop sub-VMs ────────────────────────────────────────────
#
# Cloud Run cannot reach desktop sub-VMs directly (iptables DNAT through
# Docker's FORWARD chain is unreliable). This proxy forwards REST requests
# to the sub-VM's bridge IP, same pattern as the VNC WebSocket proxy above.
# Headless containers use normal Docker port mapping and don't need this.


@app.api_route(
    "/api/sandbox/{unit_id}/proxy/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE"],
)
async def proxy_to_sandbox(
    unit_id: str,
    path: str,
    request: Request,
    _: None = Depends(require_master_token),
):
    """Forward any REST request to a unit's sandbox server.

    Routes:
      - Desktop VMs: via bridge IP (192.168.100.x:8080)
      - Headless containers: via localhost:{host_port}
    """
    u = _pool.get(unit_id)
    if u is None:
        raise HTTPException(status_code=404, detail="Unit not found")

    if u.is_desktop and u.vm_ip:
        base = f"http://{u.vm_ip}:{config.CONTAINER_INTERNAL_PORT}"
    else:
        base = f"http://127.0.0.1:{u.host_port}"

    url = f"{base}/{path}"
    headers = {"Authorization": f"Bearer {u.auth_token}"}

    # Touch idle timer on every proxied command
    u.touch_command()
    _pool.update(u)

    body = await request.body()
    timeout = httpx.Timeout(
        read=180.0,  # long-running shell commands
        connect=10.0,
        write=10.0,
        pool=10.0,
    )

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.request(
                method=request.method,
                url=url,
                headers=headers,
                content=body if body else None,
                params=dict(request.query_params),
            )
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail=f"Sandbox timeout: {exc}")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Sandbox unreachable: {exc}")

    # Forward response — handle binary (screenshots) and JSON
    content_type = resp.headers.get("content-type", "")
    if "image/" in content_type or "octet-stream" in content_type:
        from fastapi.responses import Response
        return Response(
            content=resp.content,
            status_code=resp.status_code,
            media_type=content_type,
        )
    return JSONResponse(content=resp.json() if resp.content else {}, status_code=resp.status_code)


# ── Debug / observability ─────────────────────────────────────────────────────


@app.get("/pool/debug")
async def pool_debug(_: None = Depends(require_master_token)) -> JSONResponse:
    units = _pool.all()
    loop = asyncio.get_event_loop()
    snap = _budget.snapshot()

    unit_details = {}
    for u in units:
        try:
            if u.is_headless:
                mem_mb = await loop.run_in_executor(None, _docker.get_container_memory_mb, u.unit_id)
            else:
                mem_mb = config.DESKTOP_RAM_GB * 1024  # approximate
            unit_details[u.unit_id] = {
                "unit_type": u.unit_type,
                "status": u.status,
                "host_port": u.host_port,
                "assigned_agent_id": u.assigned_agent_id,
                "persistent": u.persistent,
                "memory_mb": mem_mb,
                "idle_seconds": round(u.idle_seconds(), 1),
                "command_idle_seconds": round(u.command_idle_seconds(), 1),
                "health_failures": u.health_failures,
            }
        except Exception as exc:
            unit_details[u.unit_id] = {"error": str(exc)}

    return JSONResponse({
        "budget": snap.to_dict(),
        "units": unit_details,
    })


# ── Sandbox create (backward compat) ─────────────────────────────────────────


@app.post("/api/sandbox/create")
async def create_sandbox(_: None = Depends(require_master_token)) -> JSONResponse:
    """v3 compat: create an idle headless container."""
    unit_id = secrets.token_hex(8)
    auth_token = secrets.token_hex(24)
    try:
        u = await _create_headless(unit_id, auth_token)
    except ExhaustedError as exc:
        return JSONResponse(exc.to_dict(), status_code=503)

    return JSONResponse(
        {
            "sandbox_id": u.unit_id,
            "host_port": u.host_port,
            "auth_token": u.auth_token,
            "container_id": u.container_id,
            "status": u.status,
            "unit_type": u.unit_type,
        },
        status_code=201,
    )
