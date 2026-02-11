# Deploy backend to Cloud Run with Cloud SQL.
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
$Password = $env:GCLOUD_SQL_PASSWORD
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

# DATABASE_URL for Cloud SQL via Unix socket (Cloud Run)
$DbUrl = "postgresql+asyncpg://aict:$([uri]::EscapeDataString($Password))@/aict?host=/cloudsql/${ConnName}"

$ServiceName = "aict-backend-dev"
$Region = $env:GCLOUD_REGION
if (-not $Region) { $Region = "us-east1" }

Write-Host "Deploying $ServiceName to Cloud Run (region: $Region)..."

gcloud run deploy $ServiceName `
    --project $ProjectId `
    --image $ImageTag `
    --region $Region `
    --platform managed `
    --allow-unauthenticated `
    --add-cloudsql-instances $ConnName `
    --set-env-vars "DATABASE_URL=$DbUrl" `
    --set-env-vars "API_TOKEN=$env:API_TOKEN" `
    --set-env-vars "ANTHROPIC_API_KEY=$env:ANTHROPIC_API_KEY" `
    --set-env-vars "E2B_API_KEY=$env:E2B_API_KEY" `
    --set-env-vars "GOOGLE_API_KEY=$env:GOOGLE_API_KEY" `
    --set-env-vars "MAX_ENGINEERS=5"

if ($LASTEXITCODE -ne 0) {
    Write-Error "Deploy failed."
    exit 1
}

$Url = gcloud run services describe $ServiceName --project $ProjectId --region $Region --format="value(status.url)"
Write-Host "Deployed. URL: $Url"
Write-Host "Health: $Url/api/v1/health"
