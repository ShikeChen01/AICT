# Run Alembic migrations.
# Uses .env.development (Cloud SQL) when ENV=development.
# For local Docker DB, set DATABASE_URL first or use -UseLocalDb.

param(
    [switch]$UseLocalDb
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $Root

$env:ENV = "development"
$env:PYTHONPATH = $Root

if ($UseLocalDb) {
    $env:DATABASE_URL = "postgresql+asyncpg://aict:aict@localhost:5432/aict"
    Write-Host "Using local DB: localhost:5432"
}

Write-Host "Running Alembic migrations..."
python -m alembic -c backend/alembic.ini upgrade head

if ($LASTEXITCODE -ne 0) {
    Write-Error "Migration failed."
    exit 1
}
Write-Host "Migrations complete."
