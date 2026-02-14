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

# Load .env.development for API token and related local settings
if (Test-Path ".env.development") {
    Get-Content ".env.development" | ForEach-Object {
        if ($_ -match '^\s*([^#][^=]+)=(.*)$') {
            $key = $matches[1].Trim()
            $val = $matches[2].Trim().Trim('"').Trim("'")
            [Environment]::SetEnvironmentVariable($key, $val, "Process")
        }
    }
}

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

if (-not $env:API_TOKEN) {
    Write-Error "API_TOKEN is required for authenticated verification checks."
    exit 1
}

$baseUrl = "http://${Host}:${Port}"
$headers = @{
    "Authorization" = "Bearer $($env:API_TOKEN)"
    "Content-Type" = "application/json"
}

Write-Host "Running authenticated API smoke checks..."
$projectsUrl = "$baseUrl/api/v1/projects"
$projects = Invoke-RestMethod -Uri $projectsUrl -Method GET -Headers $headers -TimeoutSec 8
if (-not $projects -or $projects.Count -eq 0) {
    Write-Error "No projects returned from $projectsUrl"
    exit 1
}

$projectId = $projects[0].id
$agentsUrl = "$baseUrl/api/v1/agents?project_id=$projectId"
$null = Invoke-RestMethod -Uri $agentsUrl -Method GET -Headers $headers -TimeoutSec 8

$taskId = ""
try {
    $createTaskUrl = "$baseUrl/api/v1/tasks?project_id=$projectId"
    $taskPayload = @{
        title = "smoke-verify-task"
        description = "Created by scripts/local/verify.ps1"
    } | ConvertTo-Json

    $createdTask = Invoke-RestMethod -Uri $createTaskUrl -Method POST -Headers $headers -Body $taskPayload -TimeoutSec 8
    $taskId = $createdTask.id

    $statusUrl = "$baseUrl/api/v1/tasks/$taskId/status?status=specifying"
    $null = Invoke-RestMethod -Uri $statusUrl -Method PATCH -Headers $headers -TimeoutSec 8
}
finally {
    if ($taskId) {
        $deleteUrl = "$baseUrl/api/v1/tasks/$taskId"
        try {
            $null = Invoke-RestMethod -Uri $deleteUrl -Method DELETE -Headers $headers -TimeoutSec 8
        } catch {
            Write-Warning "Task cleanup failed for $taskId"
        }
    }
}

Write-Host "Local verification passed."
exit 0
