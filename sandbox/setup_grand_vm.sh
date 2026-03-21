#!/usr/bin/env bash
#
# setup_grand_vm.sh — Idempotent provisioning script for the AICT Grand-VM.
#
# Target: GCE n2-standard-2 (2 vCPU, 8 GB RAM, KVM nested virt) with 50 GB SSD.
# Sets up: Docker CE, QEMU/KVM, libvirt, bridge networking, base images,
#          pool manager service, and watchdog service.
#
# Usage:
#   sudo bash setup_grand_vm.sh
#
# The script is idempotent — safe to run multiple times.

set -euo pipefail

# ── Color output ─────────────────────────────────────────────────────────────

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'  # No color

log()  { echo -e "${GREEN}[setup]${NC} $*"; }
warn() { echo -e "${YELLOW}[setup]${NC} $*"; }
err()  { echo -e "${RED}[setup]${NC} $*" >&2; }

detect_external_host() {
    local host
    host="$(curl -fs -H 'Metadata-Flavor: Google' \
        'http://metadata.google.internal/computeMetadata/v1/instance/network-interfaces/0/access-configs/0/external-ip' \
        2>/dev/null || true)"
    if [[ -n "$host" ]]; then
        printf '%s' "$host"
        return
    fi
    hostname -I | awk '{print $1}'
}

docker_repo_os() {
    . /etc/os-release
    case "${ID:-}" in
        ubuntu|debian)
            printf '%s' "${ID}"
            ;;
        *)
            err "Unsupported distro for Docker repo: ${ID:-unknown}"
            exit 1
            ;;
    esac
}

docker_repo_codename() {
    . /etc/os-release
    if [[ -n "${VERSION_CODENAME:-}" ]]; then
        printf '%s' "${VERSION_CODENAME}"
        return
    fi
    lsb_release -cs
}

# ── Pre-flight checks ───────────────────────────────────────────────────────

if [[ $EUID -ne 0 ]]; then
    err "This script must be run as root (use sudo)"
    exit 1
fi

log "Starting AICT Grand-VM provisioning..."
log "Host: $(hostname)"
log "CPU: $(nproc) cores"
log "RAM: $(free -h | awk '/Mem:/ {print $2}')"

# ── 1. System packages ──────────────────────────────────────────────────────

log "Updating system packages..."
apt-get update -qq
apt-get install -y -qq \
    apt-transport-https \
    ca-certificates \
    curl \
    gnupg \
    lsb-release \
    software-properties-common \
    bridge-utils \
    iptables \
    rsync \
    jq \
    htop \
    tmux \
    unzip \
    python3 \
    python3-pip \
    python3-venv

# ── 2. Docker CE ─────────────────────────────────────────────────────────────

if ! command -v docker &>/dev/null; then
    log "Installing Docker CE..."
    rm -f /etc/apt/sources.list.d/docker.list
    DOCKER_REPO_OS="$(docker_repo_os)"
    DOCKER_REPO_CODENAME="$(docker_repo_codename)"

    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL "https://download.docker.com/linux/${DOCKER_REPO_OS}/gpg" \
        | gpg --dearmor --batch --yes -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg

    echo \
        "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
        https://download.docker.com/linux/${DOCKER_REPO_OS} \
        ${DOCKER_REPO_CODENAME} stable" \
        > /etc/apt/sources.list.d/docker.list

    apt-get update -qq
    apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin
else
    log "Docker already installed: $(docker --version)"
fi

# Configure Docker for sandbox isolation
mkdir -p /etc/docker
cat > /etc/docker/daemon.json <<'EOF'
{
    "storage-driver": "overlay2",
    "log-driver": "json-file",
    "log-opts": {
        "max-size": "10m",
        "max-file": "3"
    },
    "default-runtime": "runc",
    "default-shm-size": "64M",
    "no-new-privileges": true
}
EOF

systemctl enable docker
systemctl restart docker

# Create sandbox cgroup slice
if [[ ! -f /etc/systemd/system/sandbox.slice ]]; then
    cat > /etc/systemd/system/sandbox.slice <<'EOF'
[Unit]
Description=AICT Sandbox Container Slice
Before=slices.target

[Slice]
CPUAccounting=true
MemoryAccounting=true
IOAccounting=true
EOF
    systemctl daemon-reload
fi

# ── 3. QEMU/KVM + libvirt ───────────────────────────────────────────────────

if ! command -v virsh &>/dev/null; then
    log "Installing QEMU/KVM and libvirt..."
    apt-get install -y -qq \
        qemu-system-x86 \
        qemu-utils \
        libvirt-daemon-system \
        libvirt-clients \
        virtinst \
        ovmf
else
    log "libvirt already installed: $(virsh --version)"
fi

systemctl enable libvirtd
systemctl start libvirtd

# Verify KVM support
if [[ -e /dev/kvm ]]; then
    log "KVM acceleration available"
else
    warn "KVM acceleration NOT available — VMs will be slow (TCG fallback)"
fi

# ── 4. Bridge networking ─────────────────────────────────────────────────────

BRIDGE_NAME="br0"
BRIDGE_IP="192.168.100.1"
BRIDGE_SUBNET="192.168.100.0/24"

if ! ip link show "$BRIDGE_NAME" &>/dev/null; then
    log "Creating bridge network $BRIDGE_NAME ($BRIDGE_SUBNET)..."

    # Create netplan config for the bridge
    cat > /etc/netplan/60-aict-bridge.yaml <<EOF
network:
  version: 2
  bridges:
    ${BRIDGE_NAME}:
      addresses:
        - ${BRIDGE_IP}/24
      dhcp4: false
      parameters:
        stp: false
        forward-delay: 0
EOF
    netplan apply 2>/dev/null || true

    # Fallback: manual bridge creation if netplan isn't available
    if ! ip link show "$BRIDGE_NAME" &>/dev/null; then
        ip link add name "$BRIDGE_NAME" type bridge
        ip addr add "${BRIDGE_IP}/24" dev "$BRIDGE_NAME"
        ip link set "$BRIDGE_NAME" up
    fi
else
    log "Bridge $BRIDGE_NAME already exists"
fi

# Enable IP forwarding
sysctl -w net.ipv4.ip_forward=1
grep -q "net.ipv4.ip_forward=1" /etc/sysctl.conf || \
    echo "net.ipv4.ip_forward=1" >> /etc/sysctl.conf

# NAT masquerade for VM internet access
if ! iptables -t nat -C POSTROUTING -s "$BRIDGE_SUBNET" ! -d "$BRIDGE_SUBNET" -j MASQUERADE 2>/dev/null; then
    iptables -t nat -A POSTROUTING -s "$BRIDGE_SUBNET" ! -d "$BRIDGE_SUBNET" -j MASQUERADE
fi

# ── 5. Directory structure ───────────────────────────────────────────────────

log "Creating directory structure..."
mkdir -p /opt/sandbox
mkdir -p /data/images    # Base QCOW2 images
mkdir -p /data/vms       # Per-VM overlay images
mkdir -p /data/volumes   # Docker volume data
mkdir -p /var/log/aict

# ── 6. Python environment for pool manager ───────────────────────────────────

VENV_DIR="/opt/sandbox/venv"
if [[ ! -d "$VENV_DIR" ]]; then
    log "Creating Python virtual environment..."
    python3 -m venv "$VENV_DIR"
fi

log "Installing Python dependencies..."
"$VENV_DIR/bin/pip" install -q --upgrade pip
"$VENV_DIR/bin/pip" install -q \
    fastapi \
    uvicorn[standard] \
    httpx \
    docker \
    libvirt-python \
    pydantic

# ── 7. Copy pool manager code ───────────────────────────────────────────────

POOL_DIR="/opt/sandbox/pool_manager"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ -d "$SCRIPT_DIR/pool_manager" ]]; then
    log "Deploying pool manager code..."
    rsync -a --delete "$SCRIPT_DIR/pool_manager/" "$POOL_DIR/"
else
    warn "Pool manager source not found at $SCRIPT_DIR/pool_manager — skipping deploy"
fi

# ── 8. Environment file ─────────────────────────────────────────────────────

ENV_FILE="/opt/sandbox/.env"
if [[ ! -f "$ENV_FILE" ]]; then
    log "Generating environment file..."
    MASTER_TOKEN=$(openssl rand -hex 32)
    EXTERNAL_HOST=$(detect_external_host)
    cat > "$ENV_FILE" <<EOF
# AICT Grand-VM pool manager configuration
MASTER_TOKEN=${MASTER_TOKEN}
EXTERNAL_HOST=${EXTERNAL_HOST}
PORT=9090
STATE_FILE=/opt/sandbox/state.json

# Grand-VM resource budget (n2-standard-2: 2 vCPU, 8 GB)
GRAND_VM_TOTAL_CPU=2
GRAND_VM_TOTAL_RAM_GB=8
RESERVED_CPU=0.5
RESERVED_RAM_GB=1.0
BUDGET_CPU=1.5
BUDGET_RAM_GB=7.0
BUDGET_DISK_GB=40

# Docker headless
DOCKER_IMAGE=sandbox-base
CGROUP_PARENT=sandbox.slice
MAX_HEADLESS=5

# Desktop sub-VMs (KVM accelerated on N2)
MAX_DESKTOP=1
DESKTOP_BASE_IMAGE=/data/images/ubuntu-desktop-base.qcow2
DESKTOP_IMAGE_DIR=/data/vms
VM_BRIDGE=br0
VM_SUBNET=192.168.100.0/24
VM_GATEWAY=192.168.100.1

# Watchdog
WATCHDOG_PORT=9091
WATCHDOG_CHECK_INTERVAL=15
WATCHDOG_FAIL_THRESHOLD=3
WATCHDOG_MAX_RESTARTS=5
WATCHDOG_RESTART_WINDOW=600
EOF
    chmod 600 "$ENV_FILE"
    log "Master token generated and saved to $ENV_FILE"
else
    log "Environment file already exists at $ENV_FILE"
fi

# ── 9. Systemd services ─────────────────────────────────────────────────────

# Pool manager service (managed by watchdog, but also available standalone)
cat > /etc/systemd/system/aict-pool-manager.service <<'EOF'
[Unit]
Description=AICT Pool Manager
After=docker.service libvirtd.service
Requires=docker.service
Wants=libvirtd.service

[Service]
Type=simple
User=root
WorkingDirectory=/opt/sandbox/pool_manager
EnvironmentFile=/opt/sandbox/.env
ExecStart=/opt/sandbox/venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 9090
Restart=no
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# Watchdog service (supervises pool manager)
cat > /etc/systemd/system/aict-watchdog.service <<'EOF'
[Unit]
Description=AICT Pool Manager Watchdog
After=docker.service libvirtd.service
Requires=docker.service
Wants=libvirtd.service

[Service]
Type=simple
User=root
WorkingDirectory=/opt/sandbox/pool_manager
EnvironmentFile=/opt/sandbox/.env
Environment="POOL_MANAGER_CMD=/opt/sandbox/venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 9090"
Environment="POOL_MANAGER_CWD=/opt/sandbox/pool_manager"
ExecStart=/opt/sandbox/venv/bin/python watchdog.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload

# ── 10. Logrotate ────────────────────────────────────────────────────────────

cat > /etc/logrotate.d/aict <<'EOF'
/var/log/aict/*.log {
    daily
    rotate 14
    compress
    delaycompress
    missingok
    notifempty
    create 0640 root root
}
EOF

# ── 11. Firewall rules (if ufw is active) ───────────────────────────────────

if command -v ufw &>/dev/null && ufw status | grep -q "active"; then
    log "Configuring firewall..."
    ufw allow 9090/tcp comment "AICT pool manager"
    ufw allow 9091/tcp comment "AICT watchdog"
    # Port range for sandbox units
    ufw allow 30001:30100/tcp comment "AICT sandbox units"
fi

# ── 12. Final checks ────────────────────────────────────────────────────────

log ""
log "============================================"
log "  AICT Grand-VM provisioning complete!"
log "============================================"
log ""
log "Services:"
log "  Pool manager: port 9090 (managed by watchdog)"
log "  Watchdog:     port 9091"
log ""
log "Next steps:"
log "  1. Build the sandbox-base Docker image:"
log "     cd /opt/sandbox && docker build -t sandbox-base ."
log ""
log "  2. Create the desktop base QCOW2 image:"
log "     (See docs/v4/AICT_v4_GrandVM_Architecture.md for image specs)"
log ""
log "  3. Start the watchdog (which starts pool manager):"
log "     systemctl enable --now aict-watchdog"
log ""
log "  4. Verify health:"
log "     curl http://localhost:9090/api/health"
log "     curl http://localhost:9091/health"
log ""
log "Master token: $(grep MASTER_TOKEN /opt/sandbox/.env | cut -d= -f2)"
log ""
