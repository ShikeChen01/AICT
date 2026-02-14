# Start full development environment (backend + frontend)
# Usage: .\start.ps1

param(
    [int]$BackendPort = 8000,
    [int]$FrontendPort = 3000
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$ScriptsDir = $PSScriptRoot

# Load .env.development so frontend gets matching API token.
$EnvFile = Join-Path $Root ".env.development"
if (Test-Path $EnvFile) {
    Get-Content $EnvFile | ForEach-Object {
        if ($_ -match '^\s*([^#][^=]+)=(.*)$') {
            $key = $matches[1].Trim()
            $val = $matches[2].Trim().Trim('"').Trim("'")
            [Environment]::SetEnvironmentVariable($key, $val, "Process")
        }
    }
}
if (-not $env:VITE_API_TOKEN -and $env:API_TOKEN) {
    $env:VITE_API_TOKEN = $env:API_TOKEN
}

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  AICT Development Environment" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Starting services..."
Write-Host "  Backend:  http://localhost:${BackendPort}"
Write-Host "  Frontend: http://localhost:${FrontendPort}"
Write-Host ""
Write-Host "Press Ctrl+C to stop all services."
Write-Host ""

# Start backend in background
$backendJob = Start-Job -ScriptBlock {
    param($Root, $Port)
    Set-Location $Root
    $env:ENV = "development"
    $env:PYTHONPATH = $Root
    uvicorn backend.main:app --host 0.0.0.0 --port $Port --reload
} -ArgumentList $Root, $BackendPort

# Start frontend in foreground
try {
    Set-Location (Join-Path $Root "frontend")
    npm run dev -- --port $FrontendPort
}
finally {
    # Cleanup on exit
    Write-Host "`nStopping services..."
    Stop-Job $backendJob -ErrorAction SilentlyContinue
    Remove-Job $backendJob -Force -ErrorAction SilentlyContinue
    Write-Host "Done."
}
