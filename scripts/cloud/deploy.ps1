# Deploy backend to Cloud Run with self-hosted Postgres VM.
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

$ServiceName = "aict-backend-dev"
$Region = $env:GCLOUD_REGION
if (-not $Region) { $Region = "us-central1" }

Write-Host "Deploying $ServiceName to Cloud Run (region: $Region, vpc-connector: $VpcConnector)..."

# Write env vars to a temporary YAML file.
$EnvFile = Join-Path $Root "tmp_env_vars.yaml"
# PORT and K_SERVICE are reserved by Cloud Run; do not set them here.
$yamlLines = @(
    "ENV: 'development'"
    "DATABASE_URL: '$DbUrl'"
    "DB_SSL_MODE: '$DbSslMode'"
    "API_TOKEN: '$($env:API_TOKEN)'"
    "FIREBASE_CREDENTIALS_PATH: '$($env:FIREBASE_CREDENTIALS_PATH)'"
    "FIREBASE_PROJECT_ID: '$($env:FIREBASE_PROJECT_ID)'"
    "CLAUDE_API_KEY: '$($env:CLAUDE_API_KEY)'"
    "GEMINI_API_KEY: '$($env:GEMINI_API_KEY)'"
    "OPENAI_API_KEY: '$($env:OPENAI_API_KEY)'"
    "MOONSHOT_API_KEY: '$($env:MOONSHOT_API_KEY)'"
    "CLAUDE_MODEL: '$($env:CLAUDE_MODEL)'"
    "GEMINI_MODEL: '$($env:GEMINI_MODEL)'"
    "MANAGER_MODEL_DEFAULT: '$($env:MANAGER_MODEL_DEFAULT)'"
    "CTO_MODEL_DEFAULT: '$($env:CTO_MODEL_DEFAULT)'"
    "ENGINEER_MODEL_DEFAULT: '$($env:ENGINEER_MODEL_DEFAULT)'"
    "LLM_USE_LEGACY_HTTP: '$($env:LLM_USE_LEGACY_HTTP)'"
    "GITHUB_TOKEN: '$($env:GITHUB_TOKEN)'"
    "SANDBOX_ORCHESTRATOR_HOST: '$($env:SANDBOX_ORCHESTRATOR_HOST)'"
    "SANDBOX_ORCHESTRATOR_PORT: '$($env:SANDBOX_ORCHESTRATOR_PORT)'"
    "SANDBOX_ORCHESTRATOR_TOKEN: '$($env:SANDBOX_ORCHESTRATOR_TOKEN)'"
    "PROVISION_REPOS_ON_STARTUP: 'true'"
    "CLONE_CODE_REPO_ON_STARTUP: 'true'"
    "MAX_ENGINEERS: '5'"
    "SECRET_ENCRYPTION_KEY: '$($env:SECRET_ENCRYPTION_KEY)'"
    "ALLOWED_ORIGINS: 'https://aict-487016.web.app,http://localhost:3000,http://localhost:5173,http://localhost:8000'"
    "VOYAGE_API_KEY: '$($env:VOYAGE_API_KEY)'"
)
[System.IO.File]::WriteAllLines($EnvFile, $yamlLines)

try {
    # --timeout 3600 : Allow WebSocket connections (VNC, screen stream) to live up
    #   to 1 hour.  The default (300s) kills long-lived VNC sessions prematurely.
    #   routed to the same instance (required for stateful VNC proxy).
    # --no-cpu-throttling : Full CPU during startup so the container can listen on PORT in time.
    gcloud run deploy $ServiceName `
        --project $ProjectId `
        --image $ImageTag `
        --region $Region `
        --platform managed `
        --allow-unauthenticated `
        --vpc-connector $VpcConnector `
        --vpc-egress private-ranges-only `
        --env-vars-file $EnvFile `
        --min-instances 1 `
        --cpu-boost `
        --no-cpu-throttling `
        --timeout 3600 `
        --session-affinity
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
