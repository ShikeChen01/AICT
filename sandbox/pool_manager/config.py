"""Pool manager configuration."""

import os

# Auth
MASTER_TOKEN: str = os.environ.get("MASTER_TOKEN", "")

# Docker
DOCKER_IMAGE: str = os.environ.get("DOCKER_IMAGE", "sandbox-base")
CGROUP_PARENT: str = os.environ.get("CGROUP_PARENT", "sandbox.slice")
# CPU shares: relative weight used by the kernel scheduler when cores are
# contested.  Containers can burst above this when the host is idle
# (oversubscription).  Default 512 = half the normal Linux task weight,
# keeping the host responsive.  Does NOT hard-cap usage like nano_cpus did.
CONTAINER_CPU_SHARES: int = int(os.environ.get("CONTAINER_CPU_SHARES", "512"))
CONTAINER_MEMORY: str = os.environ.get("CONTAINER_MEMORY", "256m")

# Port allocation range for container port-mapping
PORT_RANGE_START: int = int(os.environ.get("PORT_RANGE_START", "30001"))
PORT_RANGE_END: int = int(os.environ.get("PORT_RANGE_END", "30100"))

# Capacity: explicit limit instead of a CPU-budget formula.
# Sandboxes share CPUs via the scheduler (oversubscription) so the pool size
# is bounded by port/memory/disk availability, not CPU count.
MAX_CONTAINERS: int = int(os.environ.get("MAX_CONTAINERS", "35"))

# Health monitor
HEALTH_CHECK_INTERVAL_SECONDS: int = int(os.environ.get("HEALTH_CHECK_INTERVAL", "30"))
HEALTH_CHECK_FAIL_THRESHOLD: int = 3   # consecutive failures before restart
IDLE_TTL_SECONDS: int = int(os.environ.get("IDLE_TTL_SECONDS", "1800"))  # 30 min
# Zombie-session guard: release sandboxes stuck in "assigned" longer than this.
# Covers cases where session_end failed silently (timeout, crash) on the backend.
ASSIGNED_TTL_SECONDS: int = int(os.environ.get("ASSIGNED_TTL_SECONDS", "3600"))  # 1 hour

# State persistence
STATE_FILE: str = os.environ.get("STATE_FILE", "/opt/sandbox/state.json")

# Server port for the pool manager itself
PORT: int = int(os.environ.get("PORT", "9090"))

# Container sandbox server port (inside container, always 8080)
CONTAINER_INTERNAL_PORT: int = 8080
