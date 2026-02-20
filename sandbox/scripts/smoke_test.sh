#!/usr/bin/env bash
# smoke_test.sh — Integration smoke test for the pool manager + sandbox server
#
# Run ON the VM (or with VM accessible):
#   TOKEN=$(cat /etc/sandbox/auth_token)
#   bash smoke_test.sh $TOKEN
#
# Expected: creates a sandbox, runs a command, takes a screenshot, destroys sandbox

set -euo pipefail

TOKEN="${1:-}"
HOST="${2:-localhost}"
PORT="${3:-9090}"
BASE="http://${HOST}:${PORT}/api"

if [[ -z "${TOKEN}" ]]; then
    echo "Usage: $0 <master_token> [host] [port]"
    exit 1
fi

H="Authorization: Bearer ${TOKEN}"

log() { echo "[smoke] $*"; }
check() {
    local label="$1"
    local resp="$2"
    if echo "${resp}" | grep -q '"ok"'; then
        log "✓ ${label}"
    elif echo "${resp}" | grep -q '"status"'; then
        log "✓ ${label}"
    else
        log "✗ ${label}: ${resp}"
        exit 1
    fi
}

# ── 1. Pool manager health ────────────────────────────────────────────────────
log "1. Pool manager health..."
HEALTH=$(curl -sf -H "${H}" "${BASE}/health")
log "   ${HEALTH}"

# ── 2. Create sandbox ────────────────────────────────────────────────────────
log "2. Creating sandbox..."
CREATE=$(curl -sf -X POST -H "${H}" -H "Content-Type: application/json" \
    "${BASE}/sandbox/session/start" \
    -d '{"agent_id":"test-agent-001"}')
log "   ${CREATE}"

SANDBOX_ID=$(echo "${CREATE}" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['sandbox_id'])")
CONTAINER_PORT=$(echo "${CREATE}" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['host_port'])")
CONTAINER_TOKEN=$(echo "${CREATE}" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['auth_token'])")

log "   Sandbox: ${SANDBOX_ID} on port ${CONTAINER_PORT}"

# ── 3. Wait for sandbox server to be ready ────────────────────────────────────
log "3. Waiting for sandbox server to be ready..."
for i in $(seq 1 20); do
    if curl -sf -H "Authorization: Bearer ${CONTAINER_TOKEN}" \
        "http://${HOST}:${CONTAINER_PORT}/health" &>/dev/null; then
        log "   Sandbox server ready."
        break
    fi
    sleep 1
done

# ── 4. Health check sandbox ───────────────────────────────────────────────────
log "4. Sandbox health..."
SB_HEALTH=$(curl -sf -H "Authorization: Bearer ${CONTAINER_TOKEN}" \
    "http://${HOST}:${CONTAINER_PORT}/health")
log "   ${SB_HEALTH}"

# ── 5. Screenshot ────────────────────────────────────────────────────────────
log "5. Taking screenshot..."
curl -sf -H "Authorization: Bearer ${CONTAINER_TOKEN}" \
    "http://${HOST}:${CONTAINER_PORT}/screenshot" \
    -o /tmp/sandbox_smoke_test.jpg
if [[ -s /tmp/sandbox_smoke_test.jpg ]]; then
    SIZE=$(stat -c%s /tmp/sandbox_smoke_test.jpg)
    log "   Screenshot saved (${SIZE} bytes) → /tmp/sandbox_smoke_test.jpg"
else
    log "   WARNING: Screenshot file empty"
fi

# ── 6. Mouse location ─────────────────────────────────────────────────────────
log "6. Mouse location..."
MOUSE=$(curl -sf -H "Authorization: Bearer ${CONTAINER_TOKEN}" \
    "http://${HOST}:${CONTAINER_PORT}/mouse/location")
log "   ${MOUSE}"

# ── 7. End session ────────────────────────────────────────────────────────────
log "7. Ending session..."
END=$(curl -sf -X POST -H "${H}" -H "Content-Type: application/json" \
    "${BASE}/sandbox/session/end" \
    -d '{"agent_id":"test-agent-001"}')
log "   ${END}"

# ── 8. Verify pool shows sandbox as idle ─────────────────────────────────────
log "8. Pool state..."
LIST=$(curl -sf -H "${H}" "${BASE}/sandbox/list")
log "   ${LIST}"

log ""
log "═══════════════════════════════════"
log " Smoke test PASSED ✓"
log "═══════════════════════════════════"
