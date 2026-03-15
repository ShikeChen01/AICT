# Run everything locally: SQL (Docker Postgres) + migrations + backend + frontend.
# Usage: .\scripts\local\run-all.ps1
#
# Prerequisites: Docker (for Postgres), Python with deps, Node/npm for frontend.
# Optional: .env.development for API_TOKEN and other keys (DATABASE_URL is overridden for local DB).

param(
    [int]$BackendPort = 8000,
    [int]$FrontendPort = 3000
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$ScriptsDir = Join-Path $Root "scripts\local"
Set-Location $Root

$LocalDbUrl = "postgresql+asyncpg://aict:aict@localhost:5432/aict"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  AICT Local Full Stack (SQL + API + UI)" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 1. Start local PostgreSQL
Write-Host "[1/4] Starting local PostgreSQL (Docker)..." -ForegroundColor Yellow
& "$ScriptsDir\db.up.ps1"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host ""

# 2. Run migrations against local DB
Write-Host "[2/4] Running database migrations..." -ForegroundColor Yellow
$env:DATABASE_URL = $LocalDbUrl
& "$ScriptsDir\migrate.ps1" -UseLocalDb
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host ""

# 3. Load .env.development for API_TOKEN etc. (DATABASE_URL stays local)
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
$env:DATABASE_URL = $LocalDbUrl
if (-not $env:VITE_API_TOKEN -and $env:API_TOKEN) {
    $env:VITE_API_TOKEN = $env:API_TOKEN
}

Write-Host "[3/4] Starting backend at http://localhost:${BackendPort} ..." -ForegroundColor Yellow
$backendJob = Start-Job -ScriptBlock {
    param($RootDir, $Port, $DbUrl)
    Set-Location $RootDir
    $env:ENV = "development"
    $env:PYTHONPATH = $RootDir
    $env:DATABASE_URL = $DbUrl
    uvicorn backend.main:app --host 0.0.0.0 --port $Port --reload
} -ArgumentList $Root, $BackendPort, $LocalDbUrl

Write-Host "[4/4] Starting frontend at http://localhost:${FrontendPort} ..." -ForegroundColor Yellow
Write-Host ""
Write-Host "  Backend:  http://localhost:${BackendPort}  (health: /api/v1/health)" -ForegroundColor Green
Write-Host "  Frontend: http://localhost:${FrontendPort}" -ForegroundColor Green
Write-Host ""
Write-Host "Press Ctrl+C to stop all services." -ForegroundColor Gray
Write-Host ""

try {
    Set-Location (Join-Path $Root "frontend")
    npm run dev -- --port $FrontendPort
}
finally {
    Write-Host "`nStopping backend..."
    Stop-Job $backendJob -ErrorAction SilentlyContinue
    Remove-Job $backendJob -Force -ErrorAction SilentlyContinue
    Write-Host "Done."
}
