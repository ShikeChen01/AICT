# ADR-012: GKE-Based Sandbox Orchestration with Multi-OS Support

**Status:** Accepted
**Date:** 2026-03-09
**Deciders:** Engineering team
**Supersedes:** Portions of ADR-011 (pool manager moves from Docker to K8s; tenant scheduling concepts carry forward)

## Context

### Current Architecture

Sandboxes run as Docker containers on a single GCE VM (`aictsandboxv1`), managed by a custom pool manager that handles lifecycle, port allocation, health monitoring, and state persistence via a JSON file. This worked for prototyping but has fundamental limitations:

1. **Single-VM ceiling.** MAX_CONTAINERS=35 is a hard limit. Scaling means bigger VMs or manual sharding.
2. **No multi-OS support.** Everything runs Ubuntu 22.04. The implementation plan calls for Windows support; Docker on Linux cannot run Windows containers.
3. **Reinventing orchestration.** The pool manager reimplements health checks, restart policies, port allocation, and volume management — all things Kubernetes does natively.
4. **No auto-scaling.** Idle sandboxes consume VM resources even when nobody is using them. No scale-to-zero.

### Decision Driver

Phase 1 requires configurable sandboxes where users select an OS (Ubuntu, Debian, Windows Server) like provisioning a remote VM. Phase 2.6 specifies Kubernetes deployment. Rather than build Docker multi-OS support that gets thrown away, we migrate to GKE now and get both features in one move.

## Decision

**Replace the Docker-based pool manager with a Kubernetes sandbox orchestrator running on GKE Autopilot.**

The orchestrator is a FastAPI service deployed as a K8s Deployment inside the GKE cluster. It maintains the same REST API contract as the current pool manager, so the backend `SandboxService` and `PoolManagerClient` require minimal changes. Under the hood, it creates Pods, Services, and PersistentVolumeClaims via the Kubernetes API instead of Docker SDK calls.

### Architecture

```
Cloud Run (Backend)
  └── SandboxService → PoolManagerClient
        │
        ▼  (HTTP REST via VPC connector)
GKE Autopilot Cluster
  ├── sandbox-orchestrator (Deployment, ClusterIP Service)
  │     └── FastAPI app, same API as pool manager
  │     └── Uses K8s API (in-cluster ServiceAccount)
  │
  ├── sandbox-{id} Pods (one per agent sandbox)
  │     ├── Linux Pods → linux node pool (auto-provisioned)
  │     │     └── Images: ubuntu-22.04, ubuntu-24.04, debian-12
  │     └── Windows Pods → windows node pool (auto-provisioned)
  │           └── Images: windows-server-2022
  │
  ├── sandbox-{id} Services (ClusterIP, one per Pod)
  │     └── Routes traffic to sandbox Pod port 8080
  │
  └── sandbox-pvc-{id} PersistentVolumeClaims (optional, for persistent sandboxes)
        └── GCE Persistent Disk, 10Gi default
```

### Why GKE Autopilot

- **No node management.** Google auto-provisions nodes matching Pod resource requests. Linux Pods get Linux nodes; Windows Pods get Windows nodes automatically.
- **Scale to zero.** When no sandbox Pods are running, no compute nodes exist. Windows licensing cost is zero when no Windows sandboxes are active.
- **Built-in health checks.** K8s liveness/readiness probes replace our custom HealthMonitor.
- **Built-in networking.** ClusterIP Services replace our port allocator. No port range management.
- **Built-in persistence.** PVCs replace Docker named volumes.
- **Cost efficiency.** Pay per Pod-second, not for idle VMs.

### OS Image Catalog

The orchestrator maintains a catalog mapping user-facing OS names to container images and K8s scheduling constraints:

```python
OS_CATALOG = {
    "ubuntu-22.04": {
        "display_name": "Ubuntu 22.04 LTS",
        "image": "us-central1-docker.pkg.dev/aict-487016/aict-dev/sandbox-ubuntu-22.04:latest",
        "os_family": "linux",
        "node_selector": {"kubernetes.io/os": "linux"},
        "default_resources": {"cpu": "500m", "memory": "512Mi"},
        "default": True,
    },
    "ubuntu-24.04": {
        "image": "us-central1-docker.pkg.dev/aict-487016/aict-dev/sandbox-ubuntu-24.04:latest",
        "os_family": "linux",
        ...
    },
    "debian-12": {
        "image": "us-central1-docker.pkg.dev/aict-487016/aict-dev/sandbox-debian-12:latest",
        "os_family": "linux",
        ...
    },
    "windows-server-2022": {
        "display_name": "Windows Server 2022",
        "image": "us-central1-docker.pkg.dev/aict-487016/aict-dev/sandbox-windows-2022:latest",
        "os_family": "windows",
        "node_selector": {"kubernetes.io/os": "windows"},
        "tolerations": [{"key": "node.kubernetes.io/os", "value": "windows", "effect": "NoSchedule"}],
        "default_resources": {"cpu": "1000m", "memory": "2Gi"},
    },
}
```

### API Contract (unchanged surface, extended parameters)

```
POST /api/sandbox/session/start
  body: {agent_id, persistent, setup_script, os_image?, tenant_id?, project_id?}
  → {sandbox_id, host, port, auth_token, created, ready, os_image}

POST /api/sandbox/session/end
DELETE /api/sandbox/{sandbox_id}
POST /api/sandbox/{sandbox_id}/restart
POST /api/sandbox/{sandbox_id}/persistent
POST /api/sandbox/{sandbox_id}/run-setup
GET  /api/sandbox/list
GET  /api/sandbox/{sandbox_id}
GET  /api/health
GET  /api/images              ← NEW: returns OS_CATALOG for frontend
```

The key addition is `os_image` on `session/start`. If omitted, defaults to `ubuntu-22.04`. The orchestrator selects the right image, node selector, and resource limits from the catalog.

### What Changes

| Component | Before | After |
|-----------|--------|-------|
| Pool manager | Docker SDK, runs on GCE VM | K8s API, runs as Deployment in GKE |
| Container creation | `docker.containers.run()` | `kubectl create pod` (K8s Python client) |
| Port allocation | Custom PortAllocator (30001-30100) | K8s ClusterIP Service (automatic) |
| Health monitoring | Custom HealthMonitor polling /health | K8s liveness/readiness probes |
| Volume management | Docker named volumes | PersistentVolumeClaims |
| State persistence | JSON file on disk | K8s resources ARE the state (Pods, Services, PVCs) |
| Networking | VM host:port → container | ClusterIP service → Pod |
| Backend connectivity | VPC connector → VM private IP:9090 | VPC connector → orchestrator ClusterIP |
| OS support | Ubuntu 22.04 only | Ubuntu, Debian, Windows Server |
| Scaling | Manual (MAX_CONTAINERS=35) | Autopilot auto-provisions nodes |

### What Stays the Same

- **Sandbox server** inside each container (main.py, VNC, shell, streaming) — identical
- **Sandbox Dockerfile** — same base, just pushed to Artifact Registry
- **Backend SandboxService** — same PoolManagerClient interface, just updated URL
- **Backend SandboxClient** (connection multiplexer) — same WebSocket/HTTP routing
- **Frontend VNC/shell/streaming** — unchanged

### State Management

The current pool manager persists state to a JSON file and reconciles against Docker on startup. With Kubernetes, **the cluster IS the state**:

- `kubectl get pods -l app=sandbox` = list of sandboxes
- Pod labels store metadata: `sandbox-id`, `agent-id`, `tenant-id`, `os-image`, `persistent`
- Pod annotations store: `auth-token`, `created-at`
- Pod status = sandbox status (Running, Pending, Failed)

The orchestrator keeps a lightweight in-memory cache for fast lookups but can always reconstruct state from K8s. No JSON file, no reconciliation logic.

### Networking

Cloud Run backend → VPC connector → GKE cluster (same VPC):

1. Orchestrator exposed as ClusterIP Service `sandbox-orchestrator:9090`
2. Each sandbox Pod exposed as ClusterIP Service `sandbox-{id}:8080`
3. Backend reaches orchestrator via internal DNS or IP
4. Orchestrator returns sandbox service hostname to backend
5. Backend SandboxClient connects to sandbox service for shell/VNC/streaming

For VNC from the browser (frontend → sandbox), we need an Ingress or the existing pattern of proxying through the backend WebSocket. The current architecture already proxies VNC through the backend, so this continues to work.

## Options Considered

### Option A: GKE Autopilot orchestrator (this decision)

**Pros:** Auto-scaling, multi-OS, managed nodes, pay-per-pod, K8s-native health/networking
**Cons:** GKE cluster cost (~$74/mo for Autopilot management fee), K8s learning curve, cold-start latency for first Windows Pod (~2-5 min node provisioning)

### Option B: Keep Docker pool manager, add multi-image support

**Pros:** No new infrastructure, fast to implement
**Cons:** No Windows support (Docker on Linux), no auto-scaling, no path to Phase 2.6 K8s, throws away work when K8s arrives

### Option C: GKE Standard (manual node pools)

**Pros:** More control over node types, no Autopilot management fee
**Cons:** Must manage node pools, auto-scaler config, OS-specific node pools manually. More ops burden.

### Option D: Fly.io / Railway / other PaaS

**Pros:** Simpler than K8s for container orchestration
**Cons:** No Windows support, vendor lock-in, less control, harder VNC networking

**Decision: Option A.** Autopilot eliminates node management, auto-handles Windows node provisioning, and aligns with the Phase 2.6 K8s target.

## Consequences

### What becomes easier

- **Multi-OS sandboxes** — users pick an OS, orchestrator creates the right Pod
- **Scaling** — Autopilot handles node provisioning/deprovisioning
- **Windows support** — Windows node pools auto-provision when Windows Pods are scheduled
- **Reliability** — K8s restart policies, liveness probes, self-healing
- **Cost** — scale-to-zero for idle periods; Windows nodes only exist when needed

### What becomes harder

- **Cold starts** — first Pod on a new node type takes 1-5 minutes (node provisioning). Subsequent Pods on existing nodes are fast (~10-30s).
- **Debugging** — K8s adds abstraction layers. `kubectl logs` instead of `docker logs`.
- **Local development** — developers need minikube/kind or skip sandbox features locally

### What we'll need to revisit

- **Tenant-aware scheduling (ADR-011)** — concepts carry forward but implementation changes from Docker-level to K8s-level (ResourceQuotas, LimitRanges per namespace)
- **VNC networking** — if we want direct browser→sandbox VNC (bypassing backend proxy), we'll need an Ingress controller with WebSocket support
- **Persistent volumes** — PVC lifecycle (create, attach, detach, delete) needs careful handling for sandbox reset/destroy

## Infrastructure Requirements

### GKE Cluster

- **Type:** Autopilot
- **Region:** us-central1 (same as existing infra)
- **Network:** Default VPC (same as Cloud Run + VPC connector)
- **Features:** Workload Identity (for Artifact Registry pull), Windows node auto-provisioning

### Artifact Registry

- **Existing:** `us-central1-docker.pkg.dev/aict-487016/aict-dev`
- **New images to push:** sandbox-ubuntu-22.04, sandbox-ubuntu-24.04, sandbox-debian-12, sandbox-windows-2022, sandbox-orchestrator

### Database Connectivity

- **Current database:** self-hosted PostgreSQL on the GCE Postgres VM
- **Network path:** same VPC for private IP access from both Cloud Run and GKE
- **Constraint:** sandbox orchestration migration should not require a separate Cloud SQL adoption

### Networking

- VPC connector `aict-vpc-connector` already exists
- GKE Autopilot cluster in same VPC = automatic connectivity
- Cloud Run → VPC connector → GKE ClusterIP (orchestrator)
- Cloud Run → VPC connector → GKE ClusterIP (individual sandbox services)

## Migration Path

1. Create GKE Autopilot cluster (infra script)
2. Build and push sandbox images to Artifact Registry
3. Deploy sandbox-orchestrator to GKE
4. Update backend env vars to point at GKE orchestrator instead of VM pool manager
5. Verify end-to-end: backend → orchestrator → sandbox Pod → VNC/shell
6. Decommission old GCE sandbox VM

## Action Items

1. [x] Write this ADR
2. [ ] Create GKE infrastructure setup script
3. [ ] Build K8s sandbox orchestrator (FastAPI + kubernetes Python client)
4. [ ] Create multi-OS sandbox Dockerfiles
5. [ ] Build OS image catalog
6. [ ] Update backend PoolManagerClient for GKE networking
7. [ ] Add OS selector to frontend sandbox config
8. [ ] Push images to Artifact Registry
9. [ ] Deploy and test end-to-end
10. [ ] Update implementation plan checkout
