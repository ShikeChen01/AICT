# Verify Cloud Run deployment for current stage.
# Checks service URL and health endpoints.

param(
    [string]$ServiceName = "aict-backend-dev",
    [string]$Region = "",
    [int]$TimeoutSec = 90
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $Root

# Load .env.development
if (Test-Path ".env.development") {
    Get-Content ".env.development" | ForEach-Object {
        if ($_ -match '^\s*([^#][^=]+)=(.*)$') {
            $key = $matches[1].Trim()
            $val = $matches[2].Trim().Trim('"').Trim("'")
            [Environment]::SetEnvironmentVariable($key, $val, "Process")
        }
    }
}

if (-not $Region) {
    $Region = $env:GCLOUD_REGION
    if (-not $Region) { $Region = "us-east1" }
}
$ProjectId = $env:GCLOUD_PROJECT_ID
if (-not $ProjectId -and $env:GCLOUD_ARTIFACT_REGISTRY_URL) {
    $ProjectId = ($env:GCLOUD_ARTIFACT_REGISTRY_URL -split "/")[1]
}

$url = ""
if ($ProjectId) {
    $url = gcloud run services describe $ServiceName --project $ProjectId --region $Region --format="value(status.url)"
} else {
    $url = gcloud run services describe $ServiceName --region $Region --format="value(status.url)"
}

if ($url) { $url = $url.Trim() }
if (-not $url -and $env:GCLOUD_BACKEND_URL) {
    # Fallback only when service describe cannot resolve URL.
    $url = $env:GCLOUD_BACKEND_URL.Trim()
}

if (-not $url) {
    Write-Error "Could not resolve Cloud Run URL. Set GCLOUD_BACKEND_URL or deploy service first."
    exit 1
}

$publicHealth = "$url/api/v1/health"
$internalHealth = "$url/internal/agent/health"

Write-Host "Checking cloud health endpoints..."
Write-Host " - $publicHealth"
Write-Host " - $internalHealth"

$deadline = (Get-Date).AddSeconds($TimeoutSec)
$ok = $false

while ((Get-Date) -lt $deadline) {
    try {
        $resp = Invoke-RestMethod -Uri $publicHealth -Method GET -TimeoutSec 8
        if ($resp.status -eq "ok") {
            $ok = $true
            break
        }
    } catch {
        Start-Sleep -Seconds 3
    }
}

if (-not $ok) {
    Write-Error "Public health check failed: $publicHealth"
    exit 1
}

try {
    $internal = Invoke-RestMethod -Uri $internalHealth -Method GET -TimeoutSec 8
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

$headers = @{
    "Authorization" = "Bearer $($env:API_TOKEN)"
    "Content-Type" = "application/json"
}

Write-Host "Running authenticated API smoke checks..."
$projectsUrl = "$url/api/v1/projects"
$projects = Invoke-RestMethod -Uri $projectsUrl -Method GET -Headers $headers -TimeoutSec 8
if (-not $projects -or $projects.Count -eq 0) {
    Write-Error "No projects returned from $projectsUrl"
    exit 1
}

$projectId = $projects[0].id
$agentsUrl = "$url/api/v1/agents?project_id=$projectId"
$null = Invoke-RestMethod -Uri $agentsUrl -Method GET -Headers $headers -TimeoutSec 8

$taskId = ""
try {
    $createTaskUrl = "$url/api/v1/tasks?project_id=$projectId"
    $taskPayload = @{
        title = "smoke-verify-task"
        description = "Created by scripts/cloud/verify.ps1"
    } | ConvertTo-Json
    $createdTask = Invoke-RestMethod -Uri $createTaskUrl -Method POST -Headers $headers -Body $taskPayload -TimeoutSec 8
    $taskId = $createdTask.id

    $statusUrl = "$url/api/v1/tasks/$taskId/status?status=specifying"
    $null = Invoke-RestMethod -Uri $statusUrl -Method PATCH -Headers $headers -TimeoutSec 8
}
finally {
    if ($taskId) {
        $deleteUrl = "$url/api/v1/tasks/$taskId"
        try {
            $null = Invoke-RestMethod -Uri $deleteUrl -Method DELETE -Headers $headers -TimeoutSec 8
        } catch {
            Write-Warning "Task cleanup failed for $taskId"
        }
    }
}

Write-Host "Cloud verification passed."
Write-Host "Service URL: $url"
exit 0
