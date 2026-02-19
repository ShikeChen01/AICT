# Run frontend locally.
# Uses Vite proxy backend from VITE_BACKEND_URL or frontend/vite.config.ts default.

param(
    [int]$Port = 3000
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$FrontendDir = Join-Path $Root "frontend"

if (-not (Test-Path $FrontendDir)) {
    Write-Error "Frontend directory not found at: $FrontendDir"
    exit 1
}

Set-Location $FrontendDir

# Load .env.development and map API token for Vite client auth
$EnvFile = Join-Path $Root ".env.development"
if (Test-Path $EnvFile) {
    Get-Content $EnvFile | ForEach-Object {
        if ($_ -match '^\s*([^#][^=]+)=(.*)$') {
            $key = $matches[1].Trim()
            $val = $matches[2].Trim().Trim('"').Trim("'")
            [Environment]::SetEnvironmentVariable($key, $val, "Process")
        }
    }
}
if (-not $env:VITE_API_TOKEN -and $env:API_TOKEN) {
    $env:VITE_API_TOKEN = $env:API_TOKEN
}

Write-Host "Starting frontend at http://localhost:${Port}"
npm run dev -- --port $Port
