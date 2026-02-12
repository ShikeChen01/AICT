# Verify local backend for current stage.
# Checks health endpoints and optionally runs migration first.

param(
    [string]$Host = "localhost",
    [int]$Port = 8000,
    [int]$TimeoutSec = 60,
    [switch]$RunMigration,
    [switch]$UseLocalDb
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $Root

if ($RunMigration) {
    if ($UseLocalDb) {
        .\scripts\local\migrate.ps1 -UseLocalDb
    } else {
        .\scripts\local\migrate.ps1
    }
}

$publicHealth = "http://${Host}:${Port}/api/v1/health"
$internalHealth = "http://${Host}:${Port}/internal/agent/health"

Write-Host "Checking local health endpoints..."
Write-Host " - $publicHealth"
Write-Host " - $internalHealth"

$deadline = (Get-Date).AddSeconds($TimeoutSec)
$ok = $false

while ((Get-Date) -lt $deadline) {
    try {
        $resp = Invoke-RestMethod -Uri $publicHealth -Method GET -TimeoutSec 5
        if ($resp.status -eq "ok") {
            $ok = $true
            break
        }
    } catch {
        Start-Sleep -Seconds 2
    }
}

if (-not $ok) {
    Write-Error "Public health check failed: $publicHealth"
    exit 1
}

try {
    $internal = Invoke-RestMethod -Uri $internalHealth -Method GET -TimeoutSec 5
    if ($internal.status -ne "ok") {
        Write-Error "Internal health returned unexpected payload."
        exit 1
    }
} catch {
    Write-Error "Internal health check failed: $internalHealth"
    exit 1
}

Write-Host "Local verification passed."
exit 0
