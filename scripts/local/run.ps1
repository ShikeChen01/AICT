# Run backend locally.
# Uses .env.development when ENV=development (typically the shared dev VM DB).

param(
    [string]$Host = "0.0.0.0",
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $Root

$env:ENV = "development"
$env:PYTHONPATH = $Root

Write-Host "Starting backend at http://${Host}:${Port}"
Write-Host "Health: http://localhost:${Port}/api/v1/health"
uvicorn backend.main:app --host $Host --port $Port --reload
