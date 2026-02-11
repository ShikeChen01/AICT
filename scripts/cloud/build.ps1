# Build backend image and push to Artifact Registry.
# Requires: gcloud, Docker. Loads values from .env.development.

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
if (-not $Registry) {
    Write-Error "GCLOUD_ARTIFACT_REGISTRY_URL not set. Add to .env.development."
    exit 1
}

$ImageTag = "${Registry}/backend:latest"
Write-Host "Building and pushing $ImageTag"
$ProjectId = $env:GCLOUD_PROJECT_ID
if (-not $ProjectId) {
    $ProjectId = ($Registry -split "/")[1]
}
if (-not $ProjectId) {
    Write-Error "Unable to determine GCP project. Set GCLOUD_PROJECT_ID in .env.development."
    exit 1
}
Write-Host "Using GCP project: $ProjectId"

# Build and push (Cloud Build)
gcloud builds submit --project $ProjectId --tag $ImageTag --timeout=1200 .

if ($LASTEXITCODE -ne 0) {
    Write-Error "Build failed."
    exit 1
}
Write-Host "Image pushed: $ImageTag"
