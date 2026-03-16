"""Pool manager configuration — v4 hybrid (Docker headless + QEMU desktop)."""

import os

# ── Auth ──────────────────────────────────────────────────────────────────────
MASTER_TOKEN: str = os.environ.get("MASTER_TOKEN", "")

# ── Grand-VM specification ────────────────────────────────────────────────────
GRAND_VM_TOTAL_CPU: float = float(os.environ.get("GRAND_VM_TOTAL_CPU", "8"))
GRAND_VM_TOTAL_RAM_GB: float = float(os.environ.get("GRAND_VM_TOTAL_RAM_GB", "16"))

# Host reservation (OS, pool manager, watchdog)
RESERVED_CPU: float = float(os.environ.get("RESERVED_CPU", "1.5"))
RESERVED_RAM_GB: float = float(os.environ.get("RESERVED_RAM_GB", "2.0"))

# Allocable budget
BUDGET_CPU: float = float(os.environ.get("BUDGET_CPU", "6.5"))
BUDGET_RAM_GB: float = float(os.environ.get("BUDGET_RAM_GB", "14.0"))
BUDGET_DISK_GB: float = float(os.environ.get("BUDGET_DISK_GB", "400"))

# ── Docker headless containers ────────────────────────────────────────────────
DOCKER_IMAGE: str = os.environ.get("DOCKER_IMAGE", "sandbox-base")
CGROUP_PARENT: str = os.environ.get("CGROUP_PARENT", "sandbox.slice")

HEADLESS_CPU_SHARES: int = int(os.environ.get("HEADLESS_CPU_SHARES", "102"))
HEADLESS_MEMORY: str = os.environ.get("HEADLESS_MEMORY", "256m")
HEADLESS_CPU_BUDGET: float = float(os.environ.get("HEADLESS_CPU_BUDGET", "0.1"))
HEADLESS_RAM_BUDGET_GB: float = float(os.environ.get("HEADLESS_RAM_BUDGET_GB", "0.256"))
HEADLESS_DISK_QUOTA_GB: float = float(os.environ.get("HEADLESS_DISK_QUOTA_GB", "5"))
HEADLESS_PORT_START: int = int(os.environ.get("HEADLESS_PORT_START", "30001"))
HEADLESS_PORT_END: int = int(os.environ.get("HEADLESS_PORT_END", "30050"))
MAX_HEADLESS: int = int(os.environ.get("MAX_HEADLESS", "35"))

# ── QEMU/KVM desktop sub-VMs ─────────────────────────────────────────────────
DESKTOP_VCPUS: int = int(os.environ.get("DESKTOP_VCPUS", "1"))
DESKTOP_RAM_GB: float = float(os.environ.get("DESKTOP_RAM_GB", "1.5"))
DESKTOP_DISK_QUOTA_GB: float = float(os.environ.get("DESKTOP_DISK_QUOTA_GB", "10"))
DESKTOP_CPU_BUDGET: float = float(os.environ.get("DESKTOP_CPU_BUDGET", "1.0"))
DESKTOP_PORT_START: int = int(os.environ.get("DESKTOP_PORT_START", "30051"))
DESKTOP_PORT_END: int = int(os.environ.get("DESKTOP_PORT_END", "30100"))
MAX_DESKTOP: int = int(os.environ.get("MAX_DESKTOP", "3"))

# Base QCOW2 image for desktop sub-VMs
DESKTOP_BASE_IMAGE: str = os.environ.get(
    "DESKTOP_BASE_IMAGE", "/data/images/ubuntu-desktop-base.qcow2"
)
# Directory for per-VM overlay/cloned QCOW2 images
DESKTOP_IMAGE_DIR: str = os.environ.get("DESKTOP_IMAGE_DIR", "/data/vms")

# Bridge network for sub-VMs
VM_BRIDGE: str = os.environ.get("VM_BRIDGE", "br0")
VM_SUBNET: str = os.environ.get("VM_SUBNET", "192.168.100.0/24")
VM_GATEWAY: str = os.environ.get("VM_GATEWAY", "192.168.100.1")
VM_IP_START: int = int(os.environ.get("VM_IP_START", "10"))  # 192.168.100.10

# ── Combined limits ───────────────────────────────────────────────────────────
MAX_TOTAL_UNITS: int = int(os.environ.get("MAX_TOTAL_UNITS", "38"))

# Container sandbox server port (inside container/VM, always 8080)
CONTAINER_INTERNAL_PORT: int = 8080

# ── Idle reaping ──────────────────────────────────────────────────────────────
SWEEP_INTERVAL_SECONDS: int = int(os.environ.get("SWEEP_INTERVAL_SECONDS", "600"))
IDLE_THRESHOLD_SECONDS: int = int(os.environ.get("IDLE_THRESHOLD_SECONDS", "300"))

# ── Health monitor ────────────────────────────────────────────────────────────
HEALTH_CHECK_INTERVAL_SECONDS: int = int(os.environ.get("HEALTH_CHECK_INTERVAL", "30"))
HEALTH_CHECK_FAIL_THRESHOLD: int = 3

# Legacy compat: these map to IDLE_THRESHOLD_SECONDS and a longer TTL
IDLE_TTL_SECONDS: int = int(os.environ.get("IDLE_TTL_SECONDS", "1800"))
ASSIGNED_TTL_SECONDS: int = int(os.environ.get("ASSIGNED_TTL_SECONDS", "3600"))

# ── State persistence ─────────────────────────────────────────────────────────
STATE_FILE: str = os.environ.get("STATE_FILE", "/opt/sandbox/state.json")

# ── Server port for the pool manager itself ───────────────────────────────────
PORT: int = int(os.environ.get("PORT", "9090"))

# ── External host address ────────────────────────────────────────────────────
# The Grand-VM's external IP or hostname. Backend uses this to reach sandboxes.
# Auto-detected if not set; used in session_start and promote/demote responses.
EXTERNAL_HOST: str = os.environ.get("EXTERNAL_HOST", "")

# ── Backward compatibility aliases ────────────────────────────────────────────
# v3 code used these names; keep them pointing to headless defaults.
CONTAINER_CPU_SHARES: int = HEADLESS_CPU_SHARES
CONTAINER_MEMORY: str = HEADLESS_MEMORY
PORT_RANGE_START: int = HEADLESS_PORT_START
PORT_RANGE_END: int = HEADLESS_PORT_END
MAX_CONTAINERS: int = MAX_HEADLESS
