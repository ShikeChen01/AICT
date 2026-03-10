"""K8s Sandbox Orchestrator — configuration."""

import os

# Auth
MASTER_TOKEN: str = os.environ.get("MASTER_TOKEN", "")

# K8s namespace where sandbox Pods are created
SANDBOX_NAMESPACE: str = os.environ.get("SANDBOX_NAMESPACE", "sandboxes")

# Artifact Registry base URL
REGISTRY_BASE: str = os.environ.get(
    "REGISTRY_BASE",
    "us-central1-docker.pkg.dev/aict-487016/aict-dev",
)

# Capacity
MAX_SANDBOXES: int = int(os.environ.get("MAX_SANDBOXES", "50"))

# Health & TTL
HEALTH_CHECK_INTERVAL_SECONDS: int = int(os.environ.get("HEALTH_CHECK_INTERVAL", "30"))
IDLE_TTL_SECONDS: int = int(os.environ.get("IDLE_TTL_SECONDS", "1800"))  # 30 min
ASSIGNED_TTL_SECONDS: int = int(os.environ.get("ASSIGNED_TTL_SECONDS", "3600"))  # 1 hour

# Server port for the orchestrator itself
PORT: int = int(os.environ.get("PORT", "9090"))

# Container sandbox server port (inside pod, always 8080)
CONTAINER_INTERNAL_PORT: int = 8080

# Default PVC size for persistent sandboxes
DEFAULT_PVC_SIZE: str = os.environ.get("DEFAULT_PVC_SIZE", "10Gi")

# ── OS Image Catalog ─────────────────────────────────────────────────────────
# Maps user-facing OS slug → container image + K8s scheduling config.
# The orchestrator selects from this catalog when creating sandbox Pods.

OS_CATALOG: dict[str, dict] = {
    "ubuntu-22.04": {
        "display_name": "Ubuntu 22.04 LTS",
        "image": f"{REGISTRY_BASE}/sandbox-ubuntu-22.04:latest",
        "os_family": "linux",
        "node_selector": {"kubernetes.io/os": "linux"},
        "tolerations": [],
        "resources": {
            "requests": {"cpu": "250m", "memory": "256Mi"},
            "limits": {"cpu": "1000m", "memory": "1Gi"},
        },
        "default": True,
    },
    "ubuntu-24.04": {
        "display_name": "Ubuntu 24.04 LTS",
        "image": f"{REGISTRY_BASE}/sandbox-ubuntu-24.04:latest",
        "os_family": "linux",
        "node_selector": {"kubernetes.io/os": "linux"},
        "tolerations": [],
        "resources": {
            "requests": {"cpu": "250m", "memory": "256Mi"},
            "limits": {"cpu": "1000m", "memory": "1Gi"},
        },
    },
    "debian-12": {
        "display_name": "Debian 12 (Bookworm)",
        "image": f"{REGISTRY_BASE}/sandbox-debian-12:latest",
        "os_family": "linux",
        "node_selector": {"kubernetes.io/os": "linux"},
        "tolerations": [],
        "resources": {
            "requests": {"cpu": "250m", "memory": "256Mi"},
            "limits": {"cpu": "1000m", "memory": "1Gi"},
        },
    },
    "windows-server-2022": {
        "display_name": "Windows Server 2022",
        "image": f"{REGISTRY_BASE}/sandbox-windows-2022:latest",
        "os_family": "windows",
        "node_selector": {"kubernetes.io/os": "windows"},
        "tolerations": [
            {
                "key": "node.kubernetes.io/os",
                "operator": "Equal",
                "value": "windows",
                "effect": "NoSchedule",
            },
        ],
        "resources": {
            "requests": {"cpu": "500m", "memory": "2Gi"},
            "limits": {"cpu": "2000m", "memory": "4Gi"},
        },
    },
}

DEFAULT_OS_IMAGE: str = os.environ.get("DEFAULT_OS_IMAGE", "ubuntu-22.04")
