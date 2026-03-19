#!/usr/bin/env bash
# Build the desktop base QCOW2 image for AICT QEMU desktop VMs.
#
# Prerequisites: libguestfs-tools, cloud-image-utils
# Usage: sudo ./build_desktop_image.sh [/path/to/base.qcow2]
#
# This script uses virt-customize to inject packages and the sandbox
# server into an Ubuntu cloud image WITHOUT booting it (no KVM needed).

set -euo pipefail

IMAGE="${1:-/data/images/ubuntu-desktop-base.qcow2}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SERVER_DIR="$REPO_ROOT/sandbox/server"
ENTRYPOINT="$REPO_ROOT/sandbox/entrypoint.sh"

if [ ! -f "$IMAGE" ]; then
    echo "Error: Base image not found: $IMAGE"
    echo "Download one first: wget -O $IMAGE https://cloud-images.ubuntu.com/jammy/current/jammy-server-cloudimg-amd64.img"
    exit 1
fi

echo "==> Building desktop base image: $IMAGE"
echo "==> Server code: $SERVER_DIR"
echo "==> Entrypoint: $ENTRYPOINT"

# Stage sandbox server files into a temp directory for copy-in
STAGING=$(mktemp -d)
trap 'rm -rf "$STAGING"' EXIT
cp "$SERVER_DIR"/*.py "$SERVER_DIR/requirements.txt" "$STAGING/"
cp "$ENTRYPOINT" "$STAGING/entrypoint.sh"
sed -i 's/\r$//' "$STAGING/entrypoint.sh"
chmod +x "$STAGING/entrypoint.sh"

# Create the systemd service file
cat > "$STAGING/sandbox.service" << 'EOF'
[Unit]
Description=AICT Sandbox Server
After=cloud-init.target network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/opt/sandbox-server
EnvironmentFile=-/etc/sandbox/env
ExecStart=/opt/sandbox-server/entrypoint.sh
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=sandbox-server

[Install]
WantedBy=multi-user.target
EOF

export LIBGUESTFS_BACKEND=direct

echo "==> Running virt-customize (this takes ~10 minutes)..."
virt-customize -a "$IMAGE" --memsize 2048 \
    --run-command 'apt-get update -qq' \
    \
    --install 'xvfb,xdotool,ffmpeg,x11-utils,x11-xserver-utils,x11vnc,openbox,dbus-x11,python3,python3-pip,python3-venv,curl,git,ca-certificates,gnupg,wget,net-tools,iputils-ping' \
    \
    --run-command 'curl -fsSL https://dl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /usr/share/keyrings/google-chrome.gpg' \
    --run-command 'echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] https://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list' \
    --run-command 'apt-get update -qq && apt-get install -y --no-install-recommends google-chrome-stable fonts-liberation fonts-noto-color-emoji libnss3 libatk-bridge2.0-0 libxss1' \
    \
    --mkdir /opt/sandbox-server \
    --mkdir /etc/sandbox \
    --copy-in "$STAGING/main.py:/opt/sandbox-server/" \
    --copy-in "$STAGING/auth.py:/opt/sandbox-server/" \
    --copy-in "$STAGING/config.py:/opt/sandbox-server/" \
    --copy-in "$STAGING/display_handler.py:/opt/sandbox-server/" \
    --copy-in "$STAGING/recording_handler.py:/opt/sandbox-server/" \
    --copy-in "$STAGING/shell_handler.py:/opt/sandbox-server/" \
    --copy-in "$STAGING/stream_handler.py:/opt/sandbox-server/" \
    --copy-in "$STAGING/vnc_handler.py:/opt/sandbox-server/" \
    --copy-in "$STAGING/requirements.txt:/opt/sandbox-server/" \
    --copy-in "$STAGING/entrypoint.sh:/opt/sandbox-server/" \
    \
    --run-command 'pip3 install --no-cache-dir --break-system-packages -r /opt/sandbox-server/requirements.txt' \
    \
    --copy-in "$STAGING/sandbox.service:/etc/systemd/system/" \
    --run-command 'systemctl enable sandbox.service' \
    \
    --write '/etc/sandbox/env:# Default env — overridden by cloud-init per-VM
AUTH_TOKEN=
DISPLAY=:99
PORT=8080
SCREEN_WIDTH=1024
SCREEN_HEIGHT=768
SCREEN_DEPTH=24
' \
    \
    --run-command 'apt-get clean && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*' \
    --run-command 'echo "==> Desktop image build complete"'

echo "==> Compacting image..."
virt-sparsify --in-place "$IMAGE" 2>/dev/null || echo "(sparsify skipped — may need more disk space)"

echo "==> Final image size:"
ls -lh "$IMAGE"

echo "==> Verifying key files..."
virt-ls -a "$IMAGE" /opt/sandbox-server/ 2>/dev/null || echo "(virt-ls skipped)"

echo "==> DONE"
