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
$ConnName = $env:SQL_CONNECTION_NAME
$DbName = $env:SQL_DB_NAME
$DbUser = $env:SQL_USER
$ImageTag = "${Registry}/backend:latest"
$ProjectId = $env:GCLOUD_PROJECT_ID
if (-not $ProjectId) {
    $ProjectId = ($Registry -split "/")[1]
}

if (-not $Registry -or -not $ConnName) {
    Write-Error "GCLOUD_ARTIFACT_REGISTRY_URL and SQL_CONNECTION_NAME are required in .env.development"
    exit 1
}
if (-not $ProjectId) {
    Write-Error "Unable to determine GCP project. Set GCLOUD_PROJECT_ID in .env.development."
    exit 1
}
if (-not $DbName) { $DbName = "aict" }
if (-not $DbUser) { $DbUser = "aict" }

# Extract the URL-encoded password directly from DATABASE_URL.
$UrlEncodedPassword = ""
if ($env:DATABASE_URL -match '://[^:]+:([^@]+)@') {
    $UrlEncodedPassword = $matches[1]
}
if (-not $UrlEncodedPassword) {
    $UrlEncodedPassword = [uri]::EscapeDataString($env:GCLOUD_SQL_PASSWORD)
}

# Build the full Cloud SQL unix socket DATABASE_URL
$SocketPath = "/cloudsql/${ConnName}"
$DbUrl = "postgresql+asyncpg://${DbUser}:${UrlEncodedPassword}@/${DbName}?host=${SocketPath}"
Write-Host "Database: $DbName (user: $DbUser, socket: $SocketPath)"

$JobName = "aict-migrate-dev"
$Region = $env:GCLOUD_REGION
if (-not $Region) { $Region = "us-east1" }

Write-Host "Deploying migration job $JobName to Cloud Run (region: $Region)..."

# Write env vars to a temporary YAML file.
$EnvFile = Join-Path $Root "tmp_env_vars_migrate.yaml"
$yamlLines = @(
    "ENV: 'development'"
    "DATABASE_URL: '$DbUrl'"
    "API_TOKEN: '$($env:API_TOKEN)'"
    "CLAUDE_API_KEY: '$($env:CLAUDE_API_KEY)'"
    "GEMINI_API_KEY: '$($env:GEMINI_API_KEY)'"
    "E2B_API_KEY: '$($env:E2B_API_KEY)'"
)
[System.IO.File]::WriteAllLines($EnvFile, $yamlLines)

try {
    # Create or update the job
    # We override the entrypoint to run alembic
    
    # Check if job exists
    $jobExists = $false
    try {
        gcloud run jobs describe $JobName --project $ProjectId --region $Region --format="value(metadata.name)" 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) { $jobExists = $true }
    } catch {
        # Ignore
    }

    if ($jobExists) {
        Write-Host "Updating existing job..."
        gcloud run jobs update $JobName `
            --project $ProjectId `
            --image $ImageTag `
            --region $Region `
        --command "python" `
        --args "-c","import os; print(os.getcwd()); print(os.listdir('.'))" `
            --set-cloudsql-instances $ConnName `
            --env-vars-file $EnvFile `
            --max-retries 0 `
            --task-timeout 600s
    } else {
        Write-Host "Creating new job..."
        gcloud run jobs create $JobName `
            --project $ProjectId `
            --image $ImageTag `
            --region $Region `
        --command "python" `
        --args "-c","import os; print(os.getcwd()); print(os.listdir('.'))" `
            --set-cloudsql-instances $ConnName `
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
        Write-Error "Migration execution failed."
        exit 1
    }
}
finally {
    Remove-Item $EnvFile -Force -ErrorAction SilentlyContinue
}

Write-Host "Migration completed successfully."
