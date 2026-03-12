"""
K8s Sandbox Orchestrator — FastAPI service managing sandbox Pods on GKE.

Replaces the Docker-based pool manager. Maintains the same REST API contract
so the backend SandboxService/PoolManagerClient requires minimal changes.

Runs as a Deployment inside the GKE cluster with in-cluster K8s API access.
"""

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
from k8s_manager import (
    K8sManager,
    LABEL_AGENT_ID,
    LABEL_OS_IMAGE,
    LABEL_PERSISTENT,
    LABEL_SANDBOX_ID,
    LABEL_TENANT_ID,
    LABEL_PROJECT_ID,
    ANNOTATION_AUTH_TOKEN,
)

# Additional model classes for new endpoints
class ClaimRequest(BaseModel):
    agent_id: str
    project_id: str | None = None
    tenant_id: str | None = None
    setup_script: str | None = None

class SnapshotRequest(BaseModel):
    label: str = ""

class RestoreRequest(BaseModel):
    snapshot_name: str

# ── In-memory state ─────────────────────────────────────────────────────────
# Lightweight cache for fast lookups. The K8s cluster is the source of truth —
# this cache is rebuilt from K8s on startup and kept in sync by API operations.

_sandbox_cache: dict[str, dict] = {}  # sandbox_id → metadata
_agent_map: dict[str, str] = {}  # agent_id → sandbox_id
_k8s: K8sManager


def _rebuild_cache() -> None:
    """Reconstruct in-memory cache from K8s Pod state."""
    global _sandbox_cache, _agent_map
    _sandbox_cache = {}
    _agent_map = {}

    pods = _k8s.list_sandbox_pods()
    for pod in pods:
        labels = pod.metadata.labels or {}
        annotations = pod.metadata.annotations or {}
        sandbox_id = labels.get(LABEL_SANDBOX_ID, "")
        if not sandbox_id:
            continue

        agent_id = labels.get(LABEL_AGENT_ID)
        pod_status = _k8s.get_pod_status(sandbox_id)

        entry = {
            "sandbox_id": sandbox_id,
            "agent_id": agent_id,
            "os_image": labels.get(LABEL_OS_IMAGE, config.DEFAULT_OS_IMAGE),
            "persistent": labels.get(LABEL_PERSISTENT, "false") == "true",
            "tenant_id": labels.get(LABEL_TENANT_ID),
            "project_id": labels.get(LABEL_PROJECT_ID),
            "auth_token": annotations.get(ANNOTATION_AUTH_TOKEN, ""),
            "status": "assigned" if agent_id else ("idle" if pod_status == "running" else pod_status),
            "host": _k8s.get_service_host(sandbox_id),
            "port": config.CONTAINER_INTERNAL_PORT,
        }
        _sandbox_cache[sandbox_id] = entry
        if agent_id:
            _agent_map[agent_id] = sandbox_id


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _k8s
    _k8s = K8sManager()
    _rebuild_cache()
    print(f"[orchestrator] Started. {len(_sandbox_cache)} existing sandboxes found.")
    yield


# ── Auth ─────────────────────────────────────────────────────────────────────


async def require_master_token(request: Request) -> None:
    if not config.MASTER_TOKEN:
        return
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token")
    token = auth.removeprefix("Bearer ").strip()
    if token != config.MASTER_TOKEN:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


# ── App ──────────────────────────────────────────────────────────────────────

app = FastAPI(title="AICT Sandbox Orchestrator (GKE)", lifespan=lifespan)


# ── Readiness probe ──────────────────────────────────────────────────────────


async def _wait_for_pod_ready(
    sandbox_id: str,
    auth_token: str,
    timeout: float = 120.0,
    poll_interval: float = 2.0,
) -> bool:
    """
    Wait until the sandbox Pod is running and its /health endpoint responds.
    Longer default timeout than Docker (120s) because Autopilot may need to
    provision a new node (especially for Windows — can take 2-5 min).
    """
    host = _k8s.get_service_host(sandbox_id)
    if not host:
        return False

    url = f"http://{host}:{config.CONTAINER_INTERNAL_PORT}/health"
    headers = {"Authorization": f"Bearer {auth_token}"}
    deadline = asyncio.get_event_loop().time() + timeout

    while asyncio.get_event_loop().time() < deadline:
        # First check K8s pod status
        pod_status = _k8s.get_pod_status(sandbox_id)
        if pod_status in ("unhealthy", "stopped", "not_found"):
            return False

        # Then try HTTP health check
        if pod_status == "running":
            try:
                async with httpx.AsyncClient(timeout=3.0) as client:
                    resp = await client.get(url, headers=headers)
                    if resp.status_code == 200:
                        return True
            except Exception:
                pass

        await asyncio.sleep(poll_interval)

    return False


# ── Health ───────────────────────────────────────────────────────────────────


@app.get("/api/health")
async def health(_: None = Depends(require_master_token)) -> JSONResponse:
    sandboxes = list(_sandbox_cache.values())
    return JSONResponse({
        "status": "ok",
        "total": len(sandboxes),
        "idle": sum(1 for s in sandboxes if s["status"] == "idle"),
        "assigned": sum(1 for s in sandboxes if s["status"] == "assigned"),
        "starting": sum(1 for s in sandboxes if s["status"] == "starting"),
        "unhealthy": sum(1 for s in sandboxes if s["status"] == "unhealthy"),
        "max_sandboxes": config.MAX_SANDBOXES,
        "can_create": len(sandboxes) < config.MAX_SANDBOXES,
        "backend": "gke-autopilot",
    })


# ── List sandboxes ───────────────────────────────────────────────────────────


@app.get("/api/sandbox/list")
async def list_sandboxes(_: None = Depends(require_master_token)) -> JSONResponse:
    return JSONResponse(list(_sandbox_cache.values()))


# ── Get sandbox ──────────────────────────────────────────────────────────────


@app.get("/api/sandbox/{sandbox_id}")
async def get_sandbox(
    sandbox_id: str,
    _: None = Depends(require_master_token),
) -> JSONResponse:
    entry = _sandbox_cache.get(sandbox_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Sandbox not found")
    return JSONResponse(entry)


# ── OS image catalog ─────────────────────────────────────────────────────────


@app.get("/api/images")
async def list_images(_: None = Depends(require_master_token)) -> JSONResponse:
    """Return the OS image catalog for frontend display."""
    catalog = []
    for slug, entry in config.OS_CATALOG.items():
        catalog.append({
            "slug": slug,
            "display_name": entry.get("display_name", slug),
            "os_family": entry["os_family"],
            "default": entry.get("default", False),
            "resources": entry["resources"],
        })
    return JSONResponse(catalog)


# ── Warm pool provisioning ───────────────────────────────────────────────

@app.post("/api/pool/provision")
async def provision_warm(
    _: None = Depends(require_master_token),
    os_image: str = config.DEFAULT_OS_IMAGE,
) -> JSONResponse:
    """Create a sandbox in the warm pool with no agent assignment."""
    if len(_sandbox_cache) >= config.MAX_SANDBOXES:
        raise HTTPException(status_code=503, detail=f"At capacity ({config.MAX_SANDBOXES})")

    sandbox_id = secrets.token_hex(8)
    auth_token = secrets.token_hex(24)

    try:
        pod = _k8s.create_sandbox_pod(
            sandbox_id=sandbox_id, auth_token=auth_token, os_image=os_image,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    host = _k8s.get_service_host(sandbox_id)
    entry = {
        "sandbox_id": sandbox_id, "agent_id": None, "os_image": os_image,
        "persistent": False, "tenant_id": None, "project_id": None,
        "auth_token": auth_token, "status": "idle", "host": host,
        "port": config.CONTAINER_INTERNAL_PORT,
    }
    _sandbox_cache[sandbox_id] = entry

    # Wait for readiness
    catalog_entry = config.OS_CATALOG.get(os_image, {})
    timeout = 300.0 if catalog_entry.get("os_family") == "windows" else 120.0
    ready = await _wait_for_pod_ready(sandbox_id, auth_token, timeout=timeout)
    if ready:
        entry["status"] = "idle"
    else:
        entry["status"] = "unhealthy"

    return JSONResponse(entry, status_code=201)


# ── Create sandbox ───────────────────────────────────────────────────────────


@app.post("/api/sandbox/create")
async def create_sandbox(
    _: None = Depends(require_master_token),
    os_image: str = config.DEFAULT_OS_IMAGE,
) -> JSONResponse:
    if len(_sandbox_cache) >= config.MAX_SANDBOXES:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"At capacity ({config.MAX_SANDBOXES} sandboxes)",
        )

    sandbox_id = secrets.token_hex(8)
    auth_token = secrets.token_hex(24)

    try:
        pod = _k8s.create_sandbox_pod(
            sandbox_id=sandbox_id,
            auth_token=auth_token,
            os_image=os_image,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    host = _k8s.get_service_host(sandbox_id)
    entry = {
        "sandbox_id": sandbox_id,
        "agent_id": None,
        "os_image": os_image,
        "persistent": False,
        "tenant_id": None,
        "project_id": None,
        "auth_token": auth_token,
        "status": "starting",
        "host": host,
        "port": config.CONTAINER_INTERNAL_PORT,
    }
    _sandbox_cache[sandbox_id] = entry

    return JSONResponse({
        "sandbox_id": sandbox_id,
        "host": host,
        "host_port": config.CONTAINER_INTERNAL_PORT,
        "auth_token": auth_token,
        "status": "starting",
        "os_image": os_image,
    }, status_code=201)


# ── Session start (main entry point for backend) ────────────────────────────


class SessionStartRequest(BaseModel):
    agent_id: str
    persistent: bool = False
    setup_script: str | None = None
    os_image: str | None = None
    tenant_id: str | None = None
    project_id: str | None = None


@app.post("/api/sandbox/session/start")
async def session_start(
    body: SessionStartRequest,
    _: None = Depends(require_master_token),
) -> JSONResponse:
    """
    Get-or-create a sandbox for an agent.
    1. Agent already has sandbox → return it
    2. Idle sandbox with matching OS available → assign it
    3. Capacity allows → create new, assign
    4. At capacity → 503
    """
    os_image = body.os_image or config.DEFAULT_OS_IMAGE
    if os_image not in config.OS_CATALOG:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown OS image '{os_image}'. Available: {list(config.OS_CATALOG.keys())}",
        )

    # 1. Already assigned
    existing_id = _agent_map.get(body.agent_id)
    if existing_id and existing_id in _sandbox_cache:
        entry = _sandbox_cache[existing_id]
        if entry["status"] in ("assigned", "idle", "running", "starting"):
            # Quick health check
            ready = await _wait_for_pod_ready(
                existing_id, entry["auth_token"], timeout=10.0, poll_interval=1.0,
            )
            return JSONResponse({
                "sandbox_id": existing_id,
                "host": entry["host"],
                "host_port": entry["port"],
                "auth_token": entry["auth_token"],
                "created": False,
                "ready": ready,
                "os_image": entry["os_image"],
            })

    # 2. Take an idle sandbox with matching OS
    for sid, entry in _sandbox_cache.items():
        if (
            entry["status"] == "idle"
            and entry["os_image"] == os_image
            and entry["agent_id"] is None
        ):
            # Assign it
            entry["agent_id"] = body.agent_id
            entry["status"] = "assigned"
            if body.tenant_id:
                entry["tenant_id"] = body.tenant_id
            if body.project_id:
                entry["project_id"] = body.project_id
            _agent_map[body.agent_id] = sid

            # Update K8s labels
            _k8s.update_pod_labels(sid, {
                LABEL_AGENT_ID: body.agent_id,
                **({LABEL_TENANT_ID: body.tenant_id} if body.tenant_id else {}),
                **({LABEL_PROJECT_ID: body.project_id} if body.project_id else {}),
            })

            ready = await _wait_for_pod_ready(
                sid, entry["auth_token"], timeout=10.0, poll_interval=1.0,
            )

            return JSONResponse({
                "sandbox_id": sid,
                "host": entry["host"],
                "host_port": entry["port"],
                "auth_token": entry["auth_token"],
                "created": False,
                "ready": ready,
                "os_image": entry["os_image"],
            })

    # 3. Create new
    if len(_sandbox_cache) >= config.MAX_SANDBOXES:
        raise HTTPException(
            status_code=503,
            detail=f"At capacity ({config.MAX_SANDBOXES}). Try again later.",
        )

    sandbox_id = secrets.token_hex(8)
    auth_token = secrets.token_hex(24)

    try:
        pod = _k8s.create_sandbox_pod(
            sandbox_id=sandbox_id,
            auth_token=auth_token,
            os_image=os_image,
            persistent=body.persistent,
            tenant_id=body.tenant_id,
            project_id=body.project_id,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    host = _k8s.get_service_host(sandbox_id)
    entry = {
        "sandbox_id": sandbox_id,
        "agent_id": body.agent_id,
        "os_image": os_image,
        "persistent": body.persistent,
        "tenant_id": body.tenant_id,
        "project_id": body.project_id,
        "auth_token": auth_token,
        "status": "assigned",
        "host": host,
        "port": config.CONTAINER_INTERNAL_PORT,
    }
    _sandbox_cache[sandbox_id] = entry
    _agent_map[body.agent_id] = sandbox_id

    # Update Pod labels with agent assignment
    _k8s.update_pod_labels(sandbox_id, {LABEL_AGENT_ID: body.agent_id})

    # Wait for readiness (may take longer for Windows — Autopilot node provisioning)
    catalog_entry = config.OS_CATALOG[os_image]
    timeout = 300.0 if catalog_entry["os_family"] == "windows" else 120.0
    ready = await _wait_for_pod_ready(sandbox_id, auth_token, timeout=timeout)

    if not ready:
        print(f"[orchestrator] WARNING: sandbox {sandbox_id} did not become ready in {timeout}s")

    # Run setup script if provided
    setup_result = None
    if body.setup_script and ready:
        setup_result = await _run_setup_script(host, auth_token, body.setup_script)
        if not setup_result.get("ok"):
            print(f"[orchestrator] WARNING: setup script failed for {sandbox_id}: {setup_result}")

    return JSONResponse({
        "sandbox_id": sandbox_id,
        "host": host,
        "host_port": config.CONTAINER_INTERNAL_PORT,
        "auth_token": auth_token,
        "created": True,
        "ready": ready,
        "os_image": os_image,
        "setup_result": setup_result,
    }, status_code=201)


# ── Session end ──────────────────────────────────────────────────────────────


class SessionEndRequest(BaseModel):
    agent_id: str


@app.post("/api/sandbox/session/end")
async def session_end(
    body: SessionEndRequest,
    _: None = Depends(require_master_token),
) -> JSONResponse:
    sandbox_id = _agent_map.pop(body.agent_id, None)
    if not sandbox_id or sandbox_id not in _sandbox_cache:
        return JSONResponse({"ok": True, "message": "No sandbox assigned to this agent"})

    entry = _sandbox_cache[sandbox_id]

    if entry["persistent"]:
        # Keep Pod alive, just release agent assignment
        entry["agent_id"] = None
        entry["status"] = "idle"
        _k8s.update_pod_labels(sandbox_id, {LABEL_AGENT_ID: ""})
        return JSONResponse({"ok": True, "sandbox_id": sandbox_id, "persistent": True})

    # Ephemeral: destroy Pod (K8s handles cleanup)
    _k8s.destroy_sandbox(sandbox_id)
    del _sandbox_cache[sandbox_id]

    return JSONResponse({"ok": True, "sandbox_id": sandbox_id})


# ── Warm pool claim/release ──────────────────────────────────────────────

@app.post("/api/sandbox/{sandbox_id}/claim")
async def claim_sandbox(
    sandbox_id: str,
    body: ClaimRequest,
    _: None = Depends(require_master_token),
) -> JSONResponse:
    entry = _sandbox_cache.get(sandbox_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Sandbox not found")
    if entry["status"] != "idle" or entry["agent_id"] is not None:
        raise HTTPException(status_code=409, detail=f"Sandbox is {entry['status']}, not idle")

    entry["agent_id"] = body.agent_id
    entry["status"] = "assigned"
    if body.project_id:
        entry["project_id"] = body.project_id
    if body.tenant_id:
        entry["tenant_id"] = body.tenant_id
    _agent_map[body.agent_id] = sandbox_id

    _k8s.update_pod_labels(sandbox_id, {
        LABEL_AGENT_ID: body.agent_id,
        **({LABEL_PROJECT_ID: body.project_id} if body.project_id else {}),
        **({LABEL_TENANT_ID: body.tenant_id} if body.tenant_id else {}),
    })

    setup_result = None
    if body.setup_script:
        setup_result = await _run_setup_script(entry["host"], entry["auth_token"], body.setup_script)

    return JSONResponse({
        "sandbox_id": sandbox_id,
        "host": entry["host"],
        "host_port": entry["port"],
        "auth_token": entry["auth_token"],
        "agent_id": body.agent_id,
        "status": "assigned",
        "setup_result": setup_result,
    })


@app.post("/api/sandbox/{sandbox_id}/release")
async def release_sandbox(
    sandbox_id: str,
    _: None = Depends(require_master_token),
) -> JSONResponse:
    entry = _sandbox_cache.get(sandbox_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Sandbox not found")

    # Remove agent assignment
    if entry["agent_id"]:
        _agent_map.pop(entry["agent_id"], None)

    if not entry["persistent"]:
        # Wipe user data for ephemeral sandboxes
        try:
            await _run_setup_script(entry["host"], entry["auth_token"], "rm -rf /workspace/* /workspace/.[!.]* 2>/dev/null || true")
        except Exception:
            pass  # Best effort cleanup

    entry["agent_id"] = None
    entry["status"] = "idle"
    _k8s.update_pod_labels(sandbox_id, {LABEL_AGENT_ID: ""})

    return JSONResponse({"ok": True, "sandbox_id": sandbox_id, "status": "idle"})


# ── Destroy sandbox ──────────────────────────────────────────────────────────


@app.delete("/api/sandbox/{sandbox_id}")
async def destroy_sandbox(
    sandbox_id: str,
    _: None = Depends(require_master_token),
) -> JSONResponse:
    entry = _sandbox_cache.get(sandbox_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Sandbox not found")

    # Remove from agent map
    if entry["agent_id"]:
        _agent_map.pop(entry["agent_id"], None)

    # Destroy K8s resources
    _k8s.destroy_sandbox(sandbox_id)
    del _sandbox_cache[sandbox_id]

    return JSONResponse({"ok": True, "sandbox_id": sandbox_id})


# ── Restart sandbox ──────────────────────────────────────────────────────────


@app.post("/api/sandbox/{sandbox_id}/restart")
async def restart_sandbox(
    sandbox_id: str,
    _: None = Depends(require_master_token),
) -> JSONResponse:
    entry = _sandbox_cache.get(sandbox_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Sandbox not found")

    prev_agent = entry["agent_id"]

    # Delete and recreate Pod (run sync K8s calls in a thread to avoid
    # blocking the async event loop)
    new_pod = await asyncio.to_thread(_k8s.restart_sandbox, sandbox_id)
    if not new_pod:
        raise HTTPException(status_code=500, detail="Failed to restart sandbox")

    # Wait for readiness
    ready = await _wait_for_pod_ready(sandbox_id, entry["auth_token"], timeout=120.0)

    entry["status"] = "assigned" if prev_agent else "idle"
    if not ready:
        entry["status"] = "unhealthy"

    return JSONResponse({
        "ok": ready,
        "sandbox_id": sandbox_id,
        "status": entry["status"],
    })


# ── Pool metrics ─────────────────────────────────────────────────────────

@app.get("/api/pool/metrics")
async def pool_metrics(_: None = Depends(require_master_token)) -> JSONResponse:
    sandboxes = list(_sandbox_cache.values())

    metrics = {}
    for os_family in ["linux", "windows"]:
        family_sandboxes = [
            s for s in sandboxes
            if config.OS_CATALOG.get(s.get("os_image", ""), {}).get("os_family") == os_family
        ]
        total = len(family_sandboxes)
        idle = sum(1 for s in family_sandboxes if s["status"] == "idle")
        metrics[os_family] = {
            "total": total,
            "idle": idle,
            "assigned": total - idle,
            "idle_ratio": idle / total if total > 0 else 1.0,
        }

    return JSONResponse(metrics)


# ── Snapshots ───────────────────────────────────────────────────────────

@app.post("/api/sandbox/{sandbox_id}/snapshot")
async def create_snapshot(
    sandbox_id: str,
    body: SnapshotRequest,
    _: None = Depends(require_master_token),
) -> JSONResponse:
    entry = _sandbox_cache.get(sandbox_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Sandbox not found")

    snapshot_name = f"snap-{sandbox_id}-{secrets.token_hex(4)}"
    try:
        result = await asyncio.to_thread(
            _k8s.create_volume_snapshot, sandbox_id, snapshot_name
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return JSONResponse({
        "snapshot_name": snapshot_name,
        "sandbox_id": sandbox_id,
        "label": body.label,
        **result,
    }, status_code=201)


@app.post("/api/sandbox/{sandbox_id}/restore")
async def restore_snapshot(
    sandbox_id: str,
    body: RestoreRequest,
    _: None = Depends(require_master_token),
) -> JSONResponse:
    entry = _sandbox_cache.get(sandbox_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Sandbox not found")

    prev_status = entry["status"]
    entry["status"] = "restoring"

    try:
        await asyncio.to_thread(
            _k8s.restore_from_snapshot, sandbox_id, body.snapshot_name
        )
    except Exception as exc:
        entry["status"] = prev_status
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    # Wait for pod to come back
    ready = await _wait_for_pod_ready(sandbox_id, entry["auth_token"], timeout=120.0)
    entry["status"] = "assigned" if entry["agent_id"] else "idle"
    if not ready:
        entry["status"] = "unhealthy"

    return JSONResponse({"ok": ready, "sandbox_id": sandbox_id, "status": entry["status"]})


@app.get("/api/sandbox/{sandbox_id}/snapshots")
async def list_snapshots(
    sandbox_id: str,
    _: None = Depends(require_master_token),
) -> JSONResponse:
    if sandbox_id not in _sandbox_cache:
        raise HTTPException(status_code=404, detail="Sandbox not found")

    snapshots = await asyncio.to_thread(_k8s.list_snapshots, sandbox_id)
    return JSONResponse(snapshots)


# ── Toggle persistence ───────────────────────────────────────────────────────


class PersistentRequest(BaseModel):
    persistent: bool


@app.post("/api/sandbox/{sandbox_id}/persistent")
async def set_persistent(
    sandbox_id: str,
    body: PersistentRequest,
    _: None = Depends(require_master_token),
) -> JSONResponse:
    entry = _sandbox_cache.get(sandbox_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Sandbox not found")

    entry["persistent"] = body.persistent
    _k8s.update_pod_labels(sandbox_id, {LABEL_PERSISTENT: str(body.persistent).lower()})

    # If switching to persistent and no PVC exists, we'd need to recreate
    # the Pod with a PVC. For now, persistence only takes effect on next restart.

    return JSONResponse({
        "ok": True,
        "sandbox_id": sandbox_id,
        "persistent": body.persistent,
    })


# ── Setup script execution ───────────────────────────────────────────────────


async def _run_setup_script(
    host: str | None,
    auth_token: str,
    script: str,
    timeout: float = 300.0,
) -> dict:
    if not script or not script.strip() or not host:
        return {"ok": True, "stdout": "", "exit_code": 0, "skipped": True}

    url = f"http://{host}:{config.CONTAINER_INTERNAL_PORT}/shell/execute"
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
    entry = _sandbox_cache.get(sandbox_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Sandbox not found")
    if entry["status"] not in ("assigned", "idle", "running"):
        raise HTTPException(status_code=409, detail=f"Sandbox is {entry['status']}, cannot run setup")

    result = await _run_setup_script(entry["host"], entry["auth_token"], body.setup_script)
    return JSONResponse(result)


# ── Debug / observability ────────────────────────────────────────────────────


@app.get("/pool/debug")
async def pool_debug(_: None = Depends(require_master_token)) -> JSONResponse:
    """Detailed pool state for ops visibility."""
    # Refresh from K8s for accurate data
    _rebuild_cache()
    sandboxes = list(_sandbox_cache.values())

    by_os: dict[str, int] = {}
    for s in sandboxes:
        os_img = s.get("os_image", "unknown")
        by_os[os_img] = by_os.get(os_img, 0) + 1

    return JSONResponse({
        "max_sandboxes": config.MAX_SANDBOXES,
        "sandbox_count": len(sandboxes),
        "assigned": sum(1 for s in sandboxes if s["status"] == "assigned"),
        "idle": sum(1 for s in sandboxes if s["status"] == "idle"),
        "starting": sum(1 for s in sandboxes if s["status"] == "starting"),
        "unhealthy": sum(1 for s in sandboxes if s["status"] == "unhealthy"),
        "by_os_image": by_os,
        "backend": "gke-autopilot",
        "namespace": config.SANDBOX_NAMESPACE,
        "sandboxes": {s["sandbox_id"]: s for s in sandboxes},
    })
