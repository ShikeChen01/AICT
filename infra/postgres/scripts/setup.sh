#!/usr/bin/env bash
# setup.sh — Idempotent provisioning for the AICT Postgres VM.
# Tested on Ubuntu 22.04 LTS. Run as root.
#
# What this does:
#   1. Installs Docker CE
#   2. Detects and mounts the attached data disk (if present)
#   3. Creates directory structure
#   4. Generates a self-signed SSL certificate
#   5. Writes a .env file for docker-compose
#   6. Copies config files and starts Postgres via docker compose

set -euo pipefail

POSTGRES_DIR="/opt/postgres"
DATA_DIR="${POSTGRES_DIR}/data"
SSL_DIR="${POSTGRES_DIR}/ssl"
BACKUP_DIR="${POSTGRES_DIR}/backups"
COMPOSE_DIR="${POSTGRES_DIR}/compose"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_INFRA_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

log() { echo "[setup] $*"; }

# ── 1. Docker CE ──────────────────────────────────────────────────────

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
    apt-get install -y -q docker-ce docker-ce-cli containerd.io docker-compose-plugin
    systemctl enable --now docker
    log "Docker installed."
else
    log "Docker already installed: $(docker --version)"
fi

# ── 2. Data disk ─────────────────────────────────────────────────────
# GCE attaches additional disks as /dev/sdb (or /dev/disk/by-id/...).
# If an unformatted/unmounted disk exists, format and mount it.

DATA_DISK="/dev/sdb"
MOUNT_POINT="/mnt/pgdata"

if [ -b "${DATA_DISK}" ]; then
    if ! mount | grep -q "${MOUNT_POINT}"; then
        log "Detected data disk ${DATA_DISK}."

        # Format only if no filesystem exists
        if ! blkid "${DATA_DISK}" | grep -q 'TYPE='; then
            log "Formatting ${DATA_DISK} as ext4..."
            mkfs.ext4 -m 0 -F -E lazy_itable_init=0,lazy_journal_init=0 "${DATA_DISK}"
        fi

        mkdir -p "${MOUNT_POINT}"
        mount -o discard,defaults "${DATA_DISK}" "${MOUNT_POINT}"

        # Persist in fstab
        if ! grep -q "${MOUNT_POINT}" /etc/fstab; then
            DISK_UUID=$(blkid -s UUID -o value "${DATA_DISK}")
            echo "UUID=${DISK_UUID} ${MOUNT_POINT} ext4 discard,defaults,nofail 0 2" >> /etc/fstab
            log "Added ${DATA_DISK} to /etc/fstab."
        fi

        DATA_DIR="${MOUNT_POINT}/data"
        BACKUP_DIR="${MOUNT_POINT}/backups"
        log "Data disk mounted at ${MOUNT_POINT}."
    else
        DATA_DIR="${MOUNT_POINT}/data"
        BACKUP_DIR="${MOUNT_POINT}/backups"
        log "Data disk already mounted at ${MOUNT_POINT}."
    fi
else
    log "No data disk at ${DATA_DISK}. Using boot disk at ${DATA_DIR}."
fi

# ── 3. Directories ───────────────────────────────────────────────────

log "Creating directories..."
mkdir -p "${DATA_DIR}" "${SSL_DIR}" "${BACKUP_DIR}" "${COMPOSE_DIR}"
chown -R root:root "${POSTGRES_DIR}"

# ── 4. SSL certificate ──────────────────────────────────────────────

if [ ! -f "${SSL_DIR}/server.crt" ]; then
    log "Generating self-signed SSL certificate..."
    openssl req -new -x509 -days 3650 -nodes \
        -subj "/CN=aict-postgres" \
        -keyout "${SSL_DIR}/server.key" \
        -out "${SSL_DIR}/server.crt"
    # Postgres requires key to be readable only by owner
    chmod 600 "${SSL_DIR}/server.key"
    chmod 644 "${SSL_DIR}/server.crt"
    # Postgres runs as uid 999 (postgres user in the alpine image)
    chown 999:999 "${SSL_DIR}/server.key" "${SSL_DIR}/server.crt"
    log "SSL certificate generated (valid 10 years)."
else
    log "SSL certificate already exists."
fi

# ── 5. Environment file ─────────────────────────────────────────────

ENV_FILE="${COMPOSE_DIR}/.env"
if [ ! -f "${ENV_FILE}" ]; then
    log "Generating .env file..."
    # Generate a strong random password if not provided
    PG_PASSWORD="${POSTGRES_PASSWORD:-$(openssl rand -base64 24 | tr -dc 'A-Za-z0-9' | head -c 32)}"
    cat > "${ENV_FILE}" <<EOF
POSTGRES_USER=aict
POSTGRES_PASSWORD=${PG_PASSWORD}
POSTGRES_DB=aict
PGDATA_DIR=${DATA_DIR}
EOF
    chmod 600 "${ENV_FILE}"
    log ".env written to ${ENV_FILE}"
    log "Password: ${PG_PASSWORD}"
    log "IMPORTANT: Save this password and add it as POSTGRES_VM_PASSWORD in your local .env.development"
else
    log ".env already exists at ${ENV_FILE}. Skipping."
fi

# ── 6. Copy configs and start ────────────────────────────────────────

log "Copying configuration files..."
cp "${REPO_INFRA_DIR}/docker-compose.yml" "${COMPOSE_DIR}/docker-compose.yml"
cp "${REPO_INFRA_DIR}/postgresql.conf" "${COMPOSE_DIR}/postgresql.conf"
cp "${REPO_INFRA_DIR}/pg_hba.conf" "${COMPOSE_DIR}/pg_hba.conf"

log "Starting Postgres container..."
cd "${COMPOSE_DIR}"
docker compose up -d

log "Waiting for Postgres to be ready..."
MAX_ATTEMPTS=30
ATTEMPT=0
while [ $ATTEMPT -lt $MAX_ATTEMPTS ]; do
    if docker exec aict-postgres pg_isready -U aict -d aict &>/dev/null; then
        break
    fi
    sleep 2
    ATTEMPT=$((ATTEMPT + 1))
done

if [ $ATTEMPT -ge $MAX_ATTEMPTS ]; then
    log "ERROR: Postgres did not become ready in time."
    docker logs aict-postgres --tail 50
    exit 1
fi

# ── Done ─────────────────────────────────────────────────────────────

INTERNAL_IP=$(hostname -I | awk '{print $1}')
PG_USER=$(grep POSTGRES_USER "${ENV_FILE}" | cut -d= -f2)
PG_DB=$(grep POSTGRES_DB "${ENV_FILE}" | cut -d= -f2)
PG_PASS=$(grep POSTGRES_PASSWORD "${ENV_FILE}" | cut -d= -f2)

log ""
log "═══════════════════════════════════════════════"
log " Postgres setup complete!"
log " Host:     ${INTERNAL_IP}:5432 (SSL enabled)"
log " User:     ${PG_USER}"
log " Database: ${PG_DB}"
log " Data dir: ${DATA_DIR}"
log " Backups:  ${BACKUP_DIR}"
log "═══════════════════════════════════════════════"
log ""
log " Add to your .env.development:"
log "   POSTGRES_VM_HOST=${INTERNAL_IP}"
log "   POSTGRES_VM_PORT=5432"
log "   POSTGRES_VM_USER=${PG_USER}"
log "   POSTGRES_VM_PASSWORD=${PG_PASS}"
log "   POSTGRES_VM_DB=${PG_DB}"
log "   DB_SSL_MODE=require"
log "   VPC_CONNECTOR_NAME=aict-vpc-connector"
log ""
log " Test with:"
log "   psql \"sslmode=require host=${INTERNAL_IP} port=5432 dbname=${PG_DB} user=${PG_USER}\""
