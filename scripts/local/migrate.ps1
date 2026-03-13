# Run Alembic migrations.
# Uses .env.development for normal development config.
# For the local Docker Postgres DB, set DATABASE_URL first or use -UseLocalDb.

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

Write-Host "Running database migrations..."
python -m backend.scripts.upgrade_db

if ($LASTEXITCODE -ne 0) {
    Write-Error "Migration failed."
    exit 1
}
Write-Host "Migrations complete."
