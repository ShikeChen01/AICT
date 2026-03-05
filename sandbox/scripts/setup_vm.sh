#!/usr/bin/env bash
# setup_vm.sh — Idempotent provisioning script for the AICT sandbox VM
# Tested on Ubuntu 22.04 LTS. Run as root.
#
# What this does:
#   1. Installs Docker CE
#   2. Installs Python 3.10 + pip
#   3. Creates the sandbox.slice cgroup (CPUQuota=380%)
#   4. Generates a master auth token
#   5. Opens firewall ports (ufw)
#   6. Creates directory structure
#   7. Copies server + pool_manager code
#   8. Builds the Docker sandbox base image
#   9. Installs + enables the pool manager systemd service

set -euo pipefail

SANDBOX_DIR="/opt/sandbox"
SERVER_DIR="${SANDBOX_DIR}/server"
PM_DIR="${SANDBOX_DIR}/pool_manager"
TOKEN_FILE="/etc/sandbox/auth_token"
STATE_FILE="${SANDBOX_DIR}/state.json"
DOCKER_IMAGE="sandbox-base"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
SANDBOX_REPO_DIR="${REPO_ROOT}/sandbox"

log() { echo "[setup_vm] $*"; }

# ── 1. Docker CE ────────────────────────────────────────────────────────────

if ! command -v docker &>/dev/null; then
    log "Installing Docker CE..."
    apt-get update -q
    apt-get install -y -q ca-certificates curl gnupg lsb-release

    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
        | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg

    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
      https://download.docker.com/linux/ubuntu \
      $(lsb_release -cs) stable" \
      > /etc/apt/sources.list.d/docker.list

    apt-get update -q
    apt-get install -y -q docker-ce docker-ce-cli containerd.io docker-buildx-plugin
    systemctl enable --now docker
    log "Docker installed."
else
    log "Docker already installed: $(docker --version)"
fi

# ── 2. Python 3.10 + pip ────────────────────────────────────────────────────

apt-get install -y -q python3 python3-pip python3-venv
log "Python: $(python3 --version)"

# ── 3. cgroup sandbox.slice ─────────────────────────────────────────────────

SLICE_FILE="/etc/systemd/system/sandbox.slice"
if [ ! -f "${SLICE_FILE}" ]; then
    log "Creating sandbox.slice..."
    cat > "${SLICE_FILE}" <<'EOF'
[Slice]
CPUQuota=380%
EOF
    systemctl daemon-reload
    systemctl start sandbox.slice
    log "sandbox.slice created and started."
else
    log "sandbox.slice already exists."
fi

# ── 4. Auth token ────────────────────────────────────────────────────────────

mkdir -p /etc/sandbox
if [ ! -f "${TOKEN_FILE}" ]; then
    log "Generating master auth token..."
    python3 -c "import secrets; print(secrets.token_hex(32))" > "${TOKEN_FILE}"
    chmod 600 "${TOKEN_FILE}"
    log "Token written to ${TOKEN_FILE}"
else
    log "Auth token already exists."
fi

MASTER_TOKEN="$(cat "${TOKEN_FILE}")"

# ── 5. Firewall ──────────────────────────────────────────────────────────────

if command -v ufw &>/dev/null; then
    log "Configuring ufw..."
    ufw allow 9090/tcp comment "sandbox pool manager"
    ufw allow 30001:30100/tcp comment "sandbox container ports"
    log "ufw rules applied."
else
    log "ufw not found — skipping firewall config (use GCE firewall rules instead)."
fi

# ── 6. Directories ───────────────────────────────────────────────────────────

log "Creating directories..."
mkdir -p "${SERVER_DIR}" "${PM_DIR}"
chown -R root:root "${SANDBOX_DIR}"

# ── 7. Copy code ─────────────────────────────────────────────────────────────

log "Copying sandbox server code..."
cp -r "${SANDBOX_REPO_DIR}/server/"* "${SERVER_DIR}/"

log "Copying pool manager code..."
cp -r "${SANDBOX_REPO_DIR}/pool_manager/"* "${PM_DIR}/"

# ── 8. Build Docker base image ───────────────────────────────────────────────

log "Building Docker image '${DOCKER_IMAGE}'..."
docker build -t "${DOCKER_IMAGE}" "${SANDBOX_REPO_DIR}"
log "Docker image built."

# ── 9. Pool manager virtualenv + systemd ────────────────────────────────────

log "Setting up pool manager virtualenv..."
python3 -m venv "${PM_DIR}/venv"
"${PM_DIR}/venv/bin/pip" install --quiet -r "${PM_DIR}/requirements.txt"

log "Installing pool manager systemd service..."
cp "${SANDBOX_REPO_DIR}/pool_manager.service" /etc/systemd/system/pool_manager.service

# Inject token into service environment
sed -i "s|MASTER_TOKEN_PLACEHOLDER|${MASTER_TOKEN}|g" \
    /etc/systemd/system/pool_manager.service

systemctl daemon-reload
systemctl enable pool_manager
systemctl restart pool_manager

log "Pool manager service started."

# ── Done ─────────────────────────────────────────────────────────────────────

log ""
log "═══════════════════════════════════════════════"
log " Setup complete!"
log " Pool manager: http://$(hostname -I | awk '{print $1}'):9090"
log " Master token: ${MASTER_TOKEN}"
log " Token file:   ${TOKEN_FILE}"
log "═══════════════════════════════════════════════"
log ""
log " Verify with:"
log "   curl -H 'Authorization: Bearer ${MASTER_TOKEN}' \\"
log "        http://localhost:9090/api/health"