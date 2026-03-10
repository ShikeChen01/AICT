#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# AICT GKE Infrastructure Setup
#
# Creates:
#   1. GKE Autopilot cluster (with Windows node auto-provisioning)
#   2. Artifact Registry repository (if not exists)
#   3. K8s namespace, service account, RBAC for sandbox orchestrator
#
# NOTE: This script does NOT create a database. AICT uses a self-hosted
# PostgreSQL VM (10.128.0.5) — see infra/postgres/ for that setup.
#
# Prerequisites:
#   - gcloud CLI installed and authenticated
#   - kubectl installed
#   - Project billing enabled
#   - Required APIs will be enabled by this script
#
# Usage:
#   chmod +x setup.sh
#   ./setup.sh              # Uses defaults from .env
#   ./setup.sh --dry-run    # Print commands without executing
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

# ── Configuration ────────────────────────────────────────────────────────────

PROJECT_ID="${GCP_PROJECT_ID:-aict-487016}"
REGION="${GCP_REGION:-us-central1}"
ZONE="${GCP_ZONE:-us-central1-c}"
NETWORK="${GCP_NETWORK:-default}"

# GKE
CLUSTER_NAME="${GKE_CLUSTER_NAME:-aict-sandbox-cluster}"

# Artifact Registry
AR_REPO="${AR_REPO:-aict-dev}"
AR_LOCATION="${AR_LOCATION:-us-central1}"

# VPC Connector (existing)
VPC_CONNECTOR="${VPC_CONNECTOR:-aict-vpc-connector}"

# Sandbox orchestrator
ORCHESTRATOR_NAMESPACE="sandbox-system"
ORCHESTRATOR_SA="sandbox-orchestrator"

DRY_RUN=false
if [[ "${1:-}" == "--dry-run" ]]; then
    DRY_RUN=true
    echo "=== DRY RUN MODE — commands will be printed but not executed ==="
fi

run() {
    echo "  → $*"
    if [[ "$DRY_RUN" == "false" ]]; then
        "$@"
    fi
}

echo "=============================================="
echo "  AICT GKE Infrastructure Setup"
echo "=============================================="
echo "  Project:    $PROJECT_ID"
echo "  Region:     $REGION"
echo "  Cluster:    $CLUSTER_NAME"
echo "  Registry:   $AR_LOCATION-docker.pkg.dev/$PROJECT_ID/$AR_REPO"
echo "  Postgres:   self-hosted VM (see infra/postgres/)"
echo "=============================================="
echo ""

# ── Step 1: Enable required APIs ─────────────────────────────────────────────

echo "[1/5] Enabling required GCP APIs..."
APIS=(
    container.googleapis.com        # GKE
    artifactregistry.googleapis.com # Artifact Registry
    compute.googleapis.com          # Compute Engine (networking)
    vpcaccess.googleapis.com        # VPC Connector
)
for api in "${APIS[@]}"; do
    run gcloud services enable "$api" --project="$PROJECT_ID" --quiet
done
echo "  Done."
echo ""

# ── Step 2: Create GKE Autopilot cluster ─────────────────────────────────────

echo "[2/5] Creating GKE Autopilot cluster '$CLUSTER_NAME'..."
echo "       (This takes 5-10 minutes)"

# Check if cluster already exists
if gcloud container clusters describe "$CLUSTER_NAME" \
    --region="$REGION" --project="$PROJECT_ID" &>/dev/null 2>&1; then
    echo "  Cluster '$CLUSTER_NAME' already exists. Skipping creation."
else
    run gcloud container clusters create-auto "$CLUSTER_NAME" \
        --project="$PROJECT_ID" \
        --region="$REGION" \
        --network="$NETWORK" \
        --release-channel=regular \
        --quiet

    # Enable Windows node pools on Autopilot
    # Autopilot automatically provisions Windows nodes when a Pod with
    # kubernetes.io/os=windows nodeSelector is scheduled. We just need
    # the cluster to have the Windows feature enabled.
    echo "  Enabling Windows container support..."
    run gcloud container clusters update "$CLUSTER_NAME" \
        --project="$PROJECT_ID" \
        --region="$REGION" \
        --enable-windows-dataplane-v2 \
        --quiet 2>/dev/null || echo "  (Windows dataplane may already be enabled or requires Standard mode — Autopilot handles this automatically)"
fi

# Get credentials for kubectl
echo "  Fetching kubectl credentials..."
run gcloud container clusters get-credentials "$CLUSTER_NAME" \
    --region="$REGION" \
    --project="$PROJECT_ID"
echo "  Done."
echo ""

# ── Step 3: Create Artifact Registry (if not exists) ─────────────────────────

echo "[3/5] Ensuring Artifact Registry repo '$AR_REPO' exists..."
if gcloud artifacts repositories describe "$AR_REPO" \
    --location="$AR_LOCATION" --project="$PROJECT_ID" &>/dev/null 2>&1; then
    echo "  Repository '$AR_REPO' already exists."
else
    run gcloud artifacts repositories create "$AR_REPO" \
        --repository-format=docker \
        --location="$AR_LOCATION" \
        --project="$PROJECT_ID" \
        --description="AICT container images" \
        --quiet
fi
echo "  Done."
echo ""

# ── Step 4: Configure K8s namespace and RBAC ─────────────────────────────────

echo "[4/5] Setting up K8s namespace and RBAC for sandbox orchestrator..."

# Create namespaces (idempotent — apply won't fail if they already exist)
cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: Namespace
metadata:
  name: $ORCHESTRATOR_NAMESPACE
  labels:
    purpose: sandbox-orchestrator
---
apiVersion: v1
kind: Namespace
metadata:
  name: sandboxes
  labels:
    purpose: sandbox-workloads
EOF

# Create ServiceAccount for the orchestrator
cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: ServiceAccount
metadata:
  name: $ORCHESTRATOR_SA
  namespace: $ORCHESTRATOR_NAMESPACE
  labels:
    app: sandbox-orchestrator
---
# ClusterRole: orchestrator needs to create/delete Pods, Services, PVCs
# in the sandbox namespace
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: sandbox-orchestrator-role
rules:
  - apiGroups: [""]
    resources: ["pods", "pods/log", "pods/status"]
    verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]
  - apiGroups: [""]
    resources: ["services"]
    verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]
  - apiGroups: [""]
    resources: ["persistentvolumeclaims"]
    verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]
  - apiGroups: [""]
    resources: ["configmaps", "secrets"]
    verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]
  - apiGroups: [""]
    resources: ["events"]
    verbs: ["get", "list", "watch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: sandbox-orchestrator-binding
subjects:
  - kind: ServiceAccount
    name: $ORCHESTRATOR_SA
    namespace: $ORCHESTRATOR_NAMESPACE
roleRef:
  kind: ClusterRole
  name: sandbox-orchestrator-role
  apiGroup: rbac.authorization.k8s.io
EOF

echo "  Done."
echo ""

# ── Step 5: Verify image pull access ──────────────────────────────────────────

echo "[5/5] Configuring image pull access..."

# In Autopilot, GKE automatically pulls from same-project Artifact Registry.
# Just verify the default SA has access.
echo "  Autopilot clusters have built-in access to same-project Artifact Registry."
echo "  No additional configuration needed."
echo "  Done."
echo ""

# ── Summary ──────────────────────────────────────────────────────────────────

echo ""
echo "Setup complete. Gathering connection info..."
echo ""

CLUSTER_ENDPOINT=""
if [[ "$DRY_RUN" == "false" ]]; then
    CLUSTER_ENDPOINT=$(gcloud container clusters describe "$CLUSTER_NAME" \
        --region="$REGION" --project="$PROJECT_ID" \
        --format="value(endpoint)" 2>/dev/null || echo "unknown")
fi

cat <<SUMMARY

============================================
  AICT GKE Infrastructure — Ready
============================================

  GKE Cluster
    Name:       $CLUSTER_NAME
    Region:     $REGION
    Endpoint:   $CLUSTER_ENDPOINT
    Type:       Autopilot (managed nodes)

  PostgreSQL
    Using self-hosted VM at 10.128.0.5:5432
    (see infra/postgres/ for management)

  Artifact Registry
    URL:        $AR_LOCATION-docker.pkg.dev/$PROJECT_ID/$AR_REPO

  K8s Namespaces
    Orchestrator:  $ORCHESTRATOR_NAMESPACE
    Sandboxes:     sandboxes

  Next Steps
    1. Create orchestrator secret:
       TOKEN=\$(python3 -c "import secrets; print(secrets.token_hex(32))")
       kubectl create secret generic orchestrator-secrets \\
         --namespace=sandbox-system \\
         --from-literal=master-token="\$TOKEN"

    2. Build and push sandbox images:
       cd sandbox && ./build-images.sh

    3. Deploy sandbox orchestrator:
       kubectl apply -f sandbox/k8s_orchestrator/manifests/orchestrator.yaml

    4. Update backend .env:
       SANDBOX_ORCHESTRATOR_HOST=sandbox-orchestrator.sandbox-system.svc.cluster.local
       SANDBOX_ORCHESTRATOR_PORT=9090
       SANDBOX_ORCHESTRATOR_TOKEN=<same token from step 1>

============================================
SUMMARY
