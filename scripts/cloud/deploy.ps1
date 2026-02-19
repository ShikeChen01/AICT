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
# This preserves the exact encoding that works with asyncpg/SQLAlchemy.
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

$ServiceName = "aict-backend-dev"
$Region = $env:GCLOUD_REGION
if (-not $Region) { $Region = "us-east1" }

Write-Host "Deploying $ServiceName to Cloud Run (region: $Region)..."

# Write env vars to a temporary YAML file.
# Use single-quoted YAML strings so special characters in URLs/keys are preserved.
$EnvFile = Join-Path $Root "tmp_env_vars.yaml"
$yamlLines = @(
    "ENV: 'development'"
    "DATABASE_URL: '$DbUrl'"
    "API_TOKEN: '$($env:API_TOKEN)'"
    "FIREBASE_CREDENTIALS_PATH: '$($env:FIREBASE_CREDENTIALS_PATH)'"
    "FIREBASE_PROJECT_ID: '$($env:FIREBASE_PROJECT_ID)'"
    "CLAUDE_API_KEY: '$($env:CLAUDE_API_KEY)'"
    "GEMINI_API_KEY: '$($env:GEMINI_API_KEY)'"
    "CLAUDE_MODEL: '$($env:CLAUDE_MODEL)'"
    "GEMINI_MODEL: '$($env:GEMINI_MODEL)'"
    "MANAGER_MODEL_DEFAULT: '$($env:MANAGER_MODEL_DEFAULT)'"
    "CTO_MODEL_DEFAULT: '$($env:CTO_MODEL_DEFAULT)'"
    "ENGINEER_MODEL_DEFAULT: '$($env:ENGINEER_MODEL_DEFAULT)'"
    "LLM_USE_LEGACY_HTTP: '$($env:LLM_USE_LEGACY_HTTP)'"
    "E2B_API_KEY: '$($env:E2B_API_KEY)'"
    "GITHUB_TOKEN: '$($env:GITHUB_TOKEN)'"
    "PROVISION_REPOS_ON_STARTUP: 'true'"
    "CLONE_CODE_REPO_ON_STARTUP: 'true'"
    "MAX_ENGINEERS: '5'"
)
[System.IO.File]::WriteAllLines($EnvFile, $yamlLines)

try {
    gcloud run deploy $ServiceName `
        --project $ProjectId `
        --image $ImageTag `
        --region $Region `
        --platform managed `
        --allow-unauthenticated `
        --add-cloudsql-instances $ConnName `
        --env-vars-file $EnvFile `
        --min-instances 1 `
        --cpu-boost
}
finally {
    Remove-Item $EnvFile -Force -ErrorAction SilentlyContinue
}

if ($LASTEXITCODE -ne 0) {
    Write-Error "Deploy failed."
    exit 1
}

$Url = gcloud run services describe $ServiceName --project $ProjectId --region $Region --format="value(status.url)"
Write-Host "Deployed. URL: $Url"
Write-Host "Health: $Url/api/v1/health"
