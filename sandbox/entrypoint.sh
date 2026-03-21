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
sleep 0.3

# ── Desktop environment (non-fatal — failures here must not kill the server) ──
xsetroot -solid "#1e293b" 2>/dev/null || true

# ── Openbox right-click menu ──
mkdir -p /root/.config/openbox 2>/dev/null || true
cat > /root/.config/openbox/menu.xml <<'MENUXML'
<?xml version="1.0" encoding="utf-8"?>
<openbox_menu xmlns="http://openbox.org/3.4/menu">
  <menu id="root-menu" label="Desktop">
    <item label="Terminal">
      <action name="Execute"><execute>xterm -fa 'Monospace' -fs 11 -bg '#1e293b' -fg '#e2e8f0' -title Terminal</execute></action>
    </item>
    <item label="Chrome Browser">
      <action name="Execute"><execute>google-chrome-stable --no-sandbox --disable-gpu --disable-dev-shm-usage --no-first-run --no-default-browser-check</execute></action>
    </item>
    <separator/>
    <item label="File Manager">
      <action name="Execute"><execute>xterm -fa 'Monospace' -fs 11 -bg '#1e293b' -fg '#e2e8f0' -title Files -e bash -c 'cd /workspace; ls -la; exec bash'</execute></action>
    </item>
  </menu>
</openbox_menu>
MENUXML
openbox --reconfigure 2>/dev/null || true

# ── Tint2 taskbar (if available) ──
if command -v tint2 &>/dev/null; then
    mkdir -p /root/.config/tint2 2>/dev/null || true
    cat > /root/.config/tint2/tint2rc <<'TINT2RC'
panel_position = bottom center horizontal
panel_size = 100% 32
panel_margin = 0 0
panel_padding = 4 2 4
panel_background_id = 1
taskbar_mode = single_desktop
taskbar_padding = 2 2 2

# Background
rounded = 0
border_width = 0
border_sides = T
background_color = #1e293b 90
border_color = #475569 60

# Task buttons
task_font = sans 9
task_font_color = #e2e8f0 100
task_active_font_color = #ffffff 100
task_background_id = 0
task_active_background_id = 2
task_padding = 6 2 6
task_centered = 1
task_maximum_size = 200 0

# Active task background
rounded = 4
border_width = 0
background_color = #3b82f6 60

# Launcher
launcher_padding = 4 2 4
launcher_item_app = /usr/share/applications/google-chrome.desktop
TINT2RC
    tint2 &>/dev/null &
fi

# ── Open Chrome with welcome page ──
cat > /tmp/welcome.html <<'WELCOME'
<!DOCTYPE html>
<html>
<head>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    font-family: system-ui, -apple-system, sans-serif;
    background: linear-gradient(135deg, #0f172a 0%, #1e293b 50%, #334155 100%);
    color: #e2e8f0;
  }
  .card {
    text-align: center;
    padding: 3rem 4rem;
    background: rgba(255,255,255,0.05);
    border: 1px solid rgba(255,255,255,0.1);
    border-radius: 16px;
    backdrop-filter: blur(8px);
  }
  h1 { font-size: 1.5rem; font-weight: 600; margin-bottom: 0.5rem; }
  p  { font-size: 0.9rem; color: #94a3b8; }
  .dot { display: inline-block; width: 8px; height: 8px;
         background: #22c55e; border-radius: 50%; margin-right: 8px; }
  .hint { font-size: 0.8rem; color: #64748b; margin-top: 1rem; }
</style>
</head>
<body>
  <div class="card">
    <h1><span class="dot"></span>Sandbox Ready</h1>
    <p>Your environment is running.</p>
    <p class="hint">Right-click the desktop to open Terminal or Chrome.</p>
  </div>
</body>
</html>
WELCOME

google-chrome-stable \
    --no-sandbox --disable-gpu --disable-dev-shm-usage \
    --no-first-run --no-default-browser-check --disable-translate \
    --window-size="${SCREEN_WIDTH:-1024},$((${SCREEN_HEIGHT:-768} - 32))" \
    --window-position=0,0 \
    --app="file:///tmp/welcome.html" \
    &>/dev/null &

# Start x11vnc — VNC server attached to the Xvfb display for remote desktop
echo "[sandbox] Starting x11vnc on display ${DISPLAY_NUM}..."
x11vnc -display "${DISPLAY_NUM}" -forever -nopw -rfbport 5900 -shared -noxdamage -noxfixes &

echo "[sandbox] Starting sandbox server on port ${PORT:-8080}..."
exec python3 -m uvicorn main:app \
    --host 0.0.0.0 \
    --port "${PORT:-8080}" \
    --log-level info
