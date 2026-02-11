# Run Alembic migrations against Cloud SQL (dev).
# Loads .env.development for DATABASE_URL. Requires network access to Cloud SQL.

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

$env:ENV = "development"
$env:PYTHONPATH = $Root

if (-not $env:DATABASE_URL) {
    Write-Error "DATABASE_URL not set. Add to .env.development."
    exit 1
}

Write-Host "Running migrations against Cloud SQL..."
python -m alembic -c backend/alembic.ini upgrade head

if ($LASTEXITCODE -ne 0) {
    Write-Error "Migration failed."
    exit 1
}
Write-Host "Migrations complete."
