"""Pool manager configuration."""

import os

# Auth
MASTER_TOKEN: str = os.environ.get("MASTER_TOKEN", "")

# Docker
DOCKER_IMAGE: str = os.environ.get("DOCKER_IMAGE", "sandbox-base")
CGROUP_PARENT: str = os.environ.get("CGROUP_PARENT", "sandbox.slice")
CONTAINER_CPU: float = float(os.environ.get("CONTAINER_CPU", "0.5"))
CONTAINER_MEMORY: str = os.environ.get("CONTAINER_MEMORY", "256m")

# Port allocation range for container port-mapping
PORT_RANGE_START: int = int(os.environ.get("PORT_RANGE_START", "30001"))
PORT_RANGE_END: int = int(os.environ.get("PORT_RANGE_END", "30100"))

# Capacity
SYSTEM_CPU_TOTAL: float = float(os.environ.get("SYSTEM_CPU_TOTAL", "4.0"))
SYSTEM_CPU_RESERVE: float = float(os.environ.get("SYSTEM_CPU_RESERVE", "0.2"))  # 5%
MAX_CONTAINERS: int = int(
    (SYSTEM_CPU_TOTAL - SYSTEM_CPU_RESERVE) // CONTAINER_CPU
)

# Health monitor
HEALTH_CHECK_INTERVAL_SECONDS: int = int(os.environ.get("HEALTH_CHECK_INTERVAL", "30"))
HEALTH_CHECK_FAIL_THRESHOLD: int = 3   # consecutive failures before restart
IDLE_TTL_SECONDS: int = int(os.environ.get("IDLE_TTL_SECONDS", "1800"))  # 30 min

# State persistence
STATE_FILE: str = os.environ.get("STATE_FILE", "/opt/sandbox/state.json")

# Server port for the pool manager itself
PORT: int = int(os.environ.get("PORT", "9090"))

# Container sandbox server port (inside container, always 8080)
CONTAINER_INTERNAL_PORT: int = 8080
