# Reset the dev database via Cloud Run Job.
# Drops everything, runs migrations, and re-seeds.
# Requires: gcloud. Loads values from .env.development.

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

$Registry = $env:GCLOUD_ARTIFACT_REGISTRY_URL
$ImageTag = "${Registry}/backend:latest"
$ProjectId = $env:GCLOUD_PROJECT_ID
if (-not $ProjectId) {
    $ProjectId = ($Registry -split "/")[1]
}

if (-not $Registry) {
    Write-Error "GCLOUD_ARTIFACT_REGISTRY_URL is required in .env.development"
    exit 1
}

# Postgres VM connection
$VmHost = $env:POSTGRES_VM_HOST
$VmPort = $env:POSTGRES_VM_PORT
$VmUser = $env:POSTGRES_VM_USER
$VmPassword = $env:POSTGRES_VM_PASSWORD
$VmDb = $env:POSTGRES_VM_DB
$VpcConnector = $env:VPC_CONNECTOR_NAME
$DbSslMode = $env:DB_SSL_MODE

if (-not $VmHost) { Write-Error "POSTGRES_VM_HOST is required."; exit 1 }
if (-not $VmPassword) { Write-Error "POSTGRES_VM_PASSWORD is required."; exit 1 }
if (-not $VpcConnector) { Write-Error "VPC_CONNECTOR_NAME is required."; exit 1 }
if (-not $VmPort) { $VmPort = "5432" }
if (-not $VmUser) { $VmUser = "aict" }
if (-not $VmDb) { $VmDb = "aict" }
if (-not $DbSslMode) { $DbSslMode = "require" }

$EncodedPassword = [uri]::EscapeDataString($VmPassword)
$DbUrl = "postgresql+asyncpg://${VmUser}:${EncodedPassword}@${VmHost}:${VmPort}/${VmDb}"

Write-Host ""
Write-Host "WARNING: This will DESTROY all data in ${VmDb} on ${VmHost}." -ForegroundColor Red
Write-Host "Press Ctrl+C to abort, or Enter to continue..." -ForegroundColor Yellow
Read-Host

$JobName = "aict-reset-db-dev"
$Region = $env:GCLOUD_REGION
if (-not $Region) { $Region = "us-central1" }

# Write env vars to temp YAML
$EnvFile = Join-Path $Root "tmp_env_vars_reset.yaml"
$yamlLines = @(
    "ENV: 'development'"
    "PYTHONPATH: '/app'"
    "DATABASE_URL: '$DbUrl'"
    "DB_SSL_MODE: '$DbSslMode'"
    "API_TOKEN: '$($env:API_TOKEN)'"
    "CLAUDE_API_KEY: '$($env:CLAUDE_API_KEY)'"
    "GEMINI_API_KEY: '$($env:GEMINI_API_KEY)'"
)
[System.IO.File]::WriteAllLines($EnvFile, $yamlLines)

try {
    $jobExists = $false
    try {
        gcloud run jobs describe $JobName --project $ProjectId --region $Region --format="value(metadata.name)" 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) { $jobExists = $true }
    } catch { }

    $ResetCmd = "python -m backend.scripts.reset_db"
    $ShArgs = "-c," + $ResetCmd
    if ($jobExists) {
        Write-Host "Updating existing job..."
        gcloud run jobs update $JobName `
            --project $ProjectId `
            --image $ImageTag `
            --region $Region `
            --command "/bin/sh" `
            --args="$ShArgs" `
            --vpc-connector $VpcConnector `
            --vpc-egress private-ranges-only `
            --env-vars-file $EnvFile `
            --max-retries 0 `
            --task-timeout 600s
    } else {
        Write-Host "Creating new job..."
        gcloud run jobs create $JobName `
            --project $ProjectId `
            --image $ImageTag `
            --region $Region `
            --command "/bin/sh" `
            --args="$ShArgs" `
            --vpc-connector $VpcConnector `
            --vpc-egress private-ranges-only `
            --env-vars-file $EnvFile `
            --max-retries 0 `
            --task-timeout 600s
    }

    if ($LASTEXITCODE -ne 0) {
        Write-Error "Job deploy failed."
        exit 1
    }

    Write-Host "Executing reset job..."
    gcloud run jobs execute $JobName --project $ProjectId --region $Region --wait

    if ($LASTEXITCODE -ne 0) {
        Write-Host ""
        Write-Host "--- Recent container logs ---" -ForegroundColor Yellow
        gcloud logging read "resource.type=cloud_run_job AND resource.labels.job_name=$JobName" `
            --project $ProjectId `
            --limit 50 `
            --format "value(timestamp,textPayload)" `
            --freshness 15m `
            2>$null
        Write-Host "---" -ForegroundColor Yellow
        Write-Error "Reset execution failed."
        exit 1
    }
}
finally {
    Remove-Item $EnvFile -Force -ErrorAction SilentlyContinue
}
Write-Host "Database reset completed successfully." -ForegroundColor Green
