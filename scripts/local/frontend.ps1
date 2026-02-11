# Run frontend locally.
# Connects to backend at localhost:8000

param(
    [int]$Port = 3000
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$FrontendDir = Join-Path $Root "frontend"

if (-not (Test-Path $FrontendDir)) {
    Write-Error "Frontend directory not found at: $FrontendDir"
    exit 1
}

Set-Location $FrontendDir

Write-Host "Starting frontend at http://localhost:${Port}"
Write-Host "Backend proxy: http://localhost:8000"
npm run dev -- --port $Port
