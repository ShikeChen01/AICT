#!/usr/bin/env bash
set -euo pipefail

DISPLAY_NUM="${DISPLAY:-:99}"
SCREEN_SPEC="${SCREEN_WIDTH:-1024}x${SCREEN_HEIGHT:-768}x${SCREEN_DEPTH:-24}"

echo "[sandbox] Starting Xvfb on ${DISPLAY_NUM} (${SCREEN_SPEC})..."
Xvfb "${DISPLAY_NUM}" -screen 0 "${SCREEN_SPEC}" -nolisten tcp &
XVFB_PID=$!

# Wait for Xvfb to be ready
for i in $(seq 1 20); do
    if xdpyinfo -display "${DISPLAY_NUM}" &>/dev/null; then
        echo "[sandbox] Xvfb ready."
        break
    fi
    sleep 0.3
done

export DISPLAY="${DISPLAY_NUM}"

# Start a minimal window manager so Chrome windows are properly composited
echo "[sandbox] Starting openbox window manager..."
openbox --sm-disable &

# Start x11vnc — VNC server attached to the Xvfb display for remote desktop
echo "[sandbox] Starting x11vnc on display ${DISPLAY_NUM}..."
x11vnc -display "${DISPLAY_NUM}" -forever -nopw -rfbport 5900 -shared -noxdamage -noxfixes &

echo "[sandbox] Starting sandbox server on port ${PORT:-8080}..."
exec python3 -m uvicorn main:app \
    --host 0.0.0.0 \
    --port "${PORT:-8080}" \
    --log-level info
