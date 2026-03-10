#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Build and push sandbox container images to Artifact Registry.
#
# Usage:
#   ./build-images.sh                    # Build + push all Linux images
#   ./build-images.sh ubuntu-22.04       # Build + push specific image
#   ./build-images.sh --orchestrator     # Build + push the orchestrator
#   ./build-images.sh --all              # Build everything (Linux + orchestrator)
#   ./build-images.sh --windows          # Build Windows image (requires Windows Docker)
#
# Prerequisites:
#   - Docker installed and running
#   - gcloud auth configure-docker us-central1-docker.pkg.dev
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

REGISTRY="us-central1-docker.pkg.dev/aict-487016/aict-dev"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Authenticate Docker with Artifact Registry
echo "[build] Configuring Docker auth for Artifact Registry..."
gcloud auth configure-docker us-central1-docker.pkg.dev --quiet 2>/dev/null || true

build_and_push() {
    local name="$1"
    local dockerfile="$2"
    local context="$3"
    local tag="${REGISTRY}/${name}:latest"

    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  Building: ${name}"
    echo "  Image:    ${tag}"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    docker build -f "$dockerfile" -t "$tag" "$context"

    echo "  Pushing ${tag}..."
    docker push "$tag"

    echo "  Done: ${name}"
}

build_linux_images() {
    # Ubuntu 22.04 (original Dockerfile at sandbox/Dockerfile)
    build_and_push \
        "sandbox-ubuntu-22.04" \
        "${SCRIPT_DIR}/Dockerfile" \
        "${SCRIPT_DIR}"

    # Ubuntu 24.04
    build_and_push \
        "sandbox-ubuntu-24.04" \
        "${SCRIPT_DIR}/images/ubuntu-24.04/Dockerfile" \
        "${SCRIPT_DIR}"

    # Debian 12
    build_and_push \
        "sandbox-debian-12" \
        "${SCRIPT_DIR}/images/debian-12/Dockerfile" \
        "${SCRIPT_DIR}"
}

build_orchestrator() {
    build_and_push \
        "sandbox-orchestrator" \
        "${SCRIPT_DIR}/k8s_orchestrator/Dockerfile" \
        "${SCRIPT_DIR}/k8s_orchestrator"
}

build_windows() {
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  Windows images must be built on a Windows Docker host."
    echo "  Build command:"
    echo "    docker build -f images/windows-server-2022/Dockerfile \\"
    echo "      -t ${REGISTRY}/sandbox-windows-2022:latest ."
    echo "    docker push ${REGISTRY}/sandbox-windows-2022:latest"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
}

# ── Main ─────────────────────────────────────────────────────────────────────

case "${1:-all-linux}" in
    ubuntu-22.04)
        build_and_push "sandbox-ubuntu-22.04" "${SCRIPT_DIR}/Dockerfile" "${SCRIPT_DIR}"
        ;;
    ubuntu-24.04)
        build_and_push "sandbox-ubuntu-24.04" "${SCRIPT_DIR}/images/ubuntu-24.04/Dockerfile" "${SCRIPT_DIR}"
        ;;
    debian-12)
        build_and_push "sandbox-debian-12" "${SCRIPT_DIR}/images/debian-12/Dockerfile" "${SCRIPT_DIR}"
        ;;
    --orchestrator)
        build_orchestrator
        ;;
    --windows)
        build_windows
        ;;
    --all)
        build_linux_images
        build_orchestrator
        build_windows
        ;;
    *)
        build_linux_images
        build_orchestrator
        ;;
esac

echo ""
echo "============================================"
echo "  Build complete."
echo "  Images available at: ${REGISTRY}/"
echo "============================================"
