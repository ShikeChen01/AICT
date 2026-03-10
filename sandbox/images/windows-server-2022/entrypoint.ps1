# ─────────────────────────────────────────────────────────────────────────────
# Windows Sandbox Entrypoint
#
# Starts TightVNC server and the sandbox FastAPI server.
# Equivalent to the Linux entrypoint.sh but for Windows Server Core.
# ─────────────────────────────────────────────────────────────────────────────

$ErrorActionPreference = "Stop"

Write-Host "[sandbox] Starting TightVNC server..."

# Start TightVNC in service mode (no auth for now — auth handled by sandbox server)
Start-Process -FilePath "C:\Program Files\TightVNC\tvnserver.exe" `
    -ArgumentList "-run" -NoNewWindow

# Give VNC a moment to start
Start-Sleep -Seconds 3

Write-Host "[sandbox] Starting sandbox server on port $($env:PORT ?? '8080')..."

$port = if ($env:PORT) { $env:PORT } else { "8080" }

# Start the sandbox FastAPI server
python -m uvicorn main:app `
    --host 0.0.0.0 `
    --port $port `
    --log-level info
