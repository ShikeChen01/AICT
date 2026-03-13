# Run database migrations on Cloud Run (via Job).
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
if (-not $ProjectId) {
    Write-Error "Unable to determine GCP project. Set GCLOUD_PROJECT_ID in .env.development."
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
Write-Host "Database: ${VmDb} (user: ${VmUser}, host: ${VmHost}:${VmPort})"

$JobName = "aict-migrate-dev"
$Region = $env:GCLOUD_REGION
if (-not $Region) { $Region = "us-central1" }

Write-Host "Deploying migration job $JobName to Cloud Run (region: $Region)..."

# Write env vars to a temporary YAML file.
$EnvFile = Join-Path $Root "tmp_env_vars_migrate.yaml"
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
    } catch {
        # Ignore
    }

    $MigrateCmd = "python -m backend.scripts.upgrade_db"
    $ShArgs = "-c," + $MigrateCmd
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

    Write-Host "Executing migration job..."
    gcloud run jobs execute $JobName --project $ProjectId --region $Region --wait

    if ($LASTEXITCODE -ne 0) {
        Write-Host ""
        Write-Host "--- Recent container logs (to see the actual error) ---" -ForegroundColor Yellow
        gcloud logging read "resource.type=cloud_run_job AND resource.labels.job_name=$JobName" `
            --project $ProjectId `
            --limit 50 `
            --format "value(timestamp,textPayload)" `
            --freshness 15m `
            2>$null
        Write-Host "---" -ForegroundColor Yellow
        Write-Error "Migration execution failed."
        exit 1
    }
}
finally {
    Remove-Item $EnvFile -Force -ErrorAction SilentlyContinue
}
Write-Host "Migration completed successfully."

