#!/usr/bin/env bash
# deploy_to_vm.sh — Deploy sandbox code to the GCE VM and run setup_vm.sh
#
# Usage (from repo root):
#   bash sandbox/scripts/deploy_to_vm.sh
#
# Prerequisites:
#   - gcloud CLI authenticated
#   - VM accessible via gcloud compute ssh OR public SSH key installed
#   - Run from repository root

set -euo pipefail

VM_HOST="${EXTERNAL_IP:-34.9.162.152}"
VM_USER="${VM_USER:-$(whoami)}"
GCP_ZONE="${GCP_ZONE:-us-central1-c}"
GCP_INSTANCE="${GCP_INSTANCE_NAME:-aictsandboxv1}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

log() { echo "[deploy] $*"; }

# ── 0. Ensure remote directory exists (fixes pscp "unable to open" on Windows) ─

log "Ensuring remote directory /tmp/aict-sandbox exists..."
gcloud compute ssh "${VM_USER}@${GCP_INSTANCE}" \
    --zone="${GCP_ZONE}" \
    --command="mkdir -p /tmp/aict-sandbox"

# ── 1. Sync sandbox code to VM ──────────────────────────────────────────────

log "Syncing sandbox/ to VM ${GCP_INSTANCE}..."
gcloud compute scp --recurse \
    "${REPO_ROOT}/sandbox" \
    "${VM_USER}@${GCP_INSTANCE}:/tmp/aict-sandbox" \
    --zone="${GCP_ZONE}"

# ── 2. Run setup_vm.sh on VM ─────────────────────────────────────────────────

log "Running setup_vm.sh on VM..."
gcloud compute ssh "${VM_USER}@${GCP_INSTANCE}" \
    --zone="${GCP_ZONE}" \
    --command="sudo bash /tmp/aict-sandbox/sandbox/scripts/setup_vm.sh"

# ── 3. Verify pool manager ────────────────────────────────────────────────────

log "Verifying pool manager health..."
TOKEN=$(gcloud compute ssh "${VM_USER}@${GCP_INSTANCE}" \
    --zone="${GCP_ZONE}" \
    --command="sudo cat /etc/sandbox/auth_token")

HEALTH=$(gcloud compute ssh "${VM_USER}@${GCP_INSTANCE}" \
    --zone="${GCP_ZONE}" \
    --command="curl -sf -H 'Authorization: Bearer ${TOKEN}' http://localhost:9090/api/health")

log "Pool manager health: ${HEALTH}"

# ── 4. Print token for .env update ────────────────────────────────────────────

log ""
log "═══════════════════════════════════════════════"
log " Deployment complete!"
log ""
log " Add to .env.development:"
log "   SANDBOX_VM_ENABLED=true"
log "   SANDBOX_VM_HOST=${VM_HOST}"
log "   SANDBOX_VM_POOL_PORT=9090"
log "   SANDBOX_VM_MASTER_TOKEN=${TOKEN}"
log "═══════════════════════════════════════════════"
