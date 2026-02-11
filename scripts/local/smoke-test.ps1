# Smoke test for local development environment.
# Validates backend health, API endpoints, and frontend availability.
#
# Usage: .\smoke-test.ps1 [-BackendUrl "http://localhost:8000"] [-FrontendUrl "http://localhost:3000"]

param(
    [string]$BackendUrl = "http://localhost:8000",
    [string]$FrontendUrl = "http://localhost:3000"
)

$ErrorActionPreference = "Continue"
$AllPassed = $true

function Write-TestResult {
    param([string]$Test, [bool]$Passed, [string]$Detail = "")
    
    $status = if ($Passed) { "[PASS]" } else { "[FAIL]" }
    $color = if ($Passed) { "Green" } else { "Red" }
    
    Write-Host "$status $Test" -ForegroundColor $color
    if ($Detail -and -not $Passed) {
        Write-Host "       $Detail" -ForegroundColor DarkGray
    }
    
    return $Passed
}

function Test-Endpoint {
    param([string]$Name, [string]$Url, [int]$ExpectedStatus = 200)
    
    try {
        $response = Invoke-WebRequest -Uri $Url -Method GET -UseBasicParsing -TimeoutSec 10 -ErrorAction Stop
        $passed = $response.StatusCode -eq $ExpectedStatus
        return Write-TestResult $Name $passed "Status: $($response.StatusCode)"
    }
    catch {
        return Write-TestResult $Name $false $_.Exception.Message
    }
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  AICT Smoke Test Suite" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Backend:  $BackendUrl"
Write-Host "Frontend: $FrontendUrl"
Write-Host ""
Write-Host "----------------------------------------"
Write-Host ""

# Backend Tests
Write-Host "Backend Tests:" -ForegroundColor Yellow
Write-Host ""

if (-not (Test-Endpoint "Health check (/api/v1/health)" "$BackendUrl/api/v1/health")) { $AllPassed = $false }
if (-not (Test-Endpoint "Internal health (/internal/agent/health)" "$BackendUrl/internal/agent/health")) { $AllPassed = $false }

# Test protected endpoints (expect 401 without token)
try {
    $response = Invoke-WebRequest -Uri "$BackendUrl/api/v1/tasks?project_id=00000000-0000-0000-0000-000000000001" -Method GET -UseBasicParsing -TimeoutSec 10 -ErrorAction Stop
    $passed = $false
    Write-TestResult "Tasks endpoint auth (should require token)" $false "Got $($response.StatusCode) instead of 401"
}
catch {
    if ($_.Exception.Response.StatusCode.value__ -eq 401) {
        if (-not (Write-TestResult "Tasks endpoint auth (should require token)" $true)) { $AllPassed = $false }
    } else {
        if (-not (Write-TestResult "Tasks endpoint auth (should require token)" $false $_.Exception.Message)) { $AllPassed = $false }
    }
}

# Test with auth token
$headers = @{
    "Authorization" = "Bearer change-me-in-production"
    "Content-Type" = "application/json"
}

try {
    $response = Invoke-WebRequest -Uri "$BackendUrl/api/v1/tasks?project_id=00000000-0000-0000-0000-000000000001" -Method GET -Headers $headers -UseBasicParsing -TimeoutSec 10 -ErrorAction Stop
    # 200 is OK even if project doesn't exist (returns empty list or 404)
    $passed = $response.StatusCode -eq 200 -or $response.StatusCode -eq 404
    if (-not (Write-TestResult "Tasks endpoint with auth" $passed "Status: $($response.StatusCode)")) { $AllPassed = $false }
}
catch {
    $status = $_.Exception.Response.StatusCode.value__
    # 404 is OK if project doesn't exist
    if ($status -eq 404) {
        if (-not (Write-TestResult "Tasks endpoint with auth" $true "Project not found (expected)")) { $AllPassed = $false }
    } else {
        if (-not (Write-TestResult "Tasks endpoint with auth" $false $_.Exception.Message)) { $AllPassed = $false }
    }
}

Write-Host ""

# Frontend Tests
Write-Host "Frontend Tests:" -ForegroundColor Yellow
Write-Host ""

try {
    $response = Invoke-WebRequest -Uri $FrontendUrl -Method GET -UseBasicParsing -TimeoutSec 10 -ErrorAction Stop
    $hasHtml = $response.Content -match "<html"
    if (-not (Write-TestResult "Frontend serves HTML" $hasHtml "Response: $($response.Content.Substring(0, [Math]::Min(100, $response.Content.Length)))")) { $AllPassed = $false }
}
catch {
    if (-not (Write-TestResult "Frontend serves HTML" $false $_.Exception.Message)) { $AllPassed = $false }
}

try {
    $response = Invoke-WebRequest -Uri "$FrontendUrl/src/main.tsx" -Method GET -UseBasicParsing -TimeoutSec 10 -ErrorAction Stop
    $passed = $response.StatusCode -eq 200
    if (-not (Write-TestResult "Frontend serves TypeScript" $passed)) { $AllPassed = $false }
}
catch {
    if (-not (Write-TestResult "Frontend serves TypeScript" $false $_.Exception.Message)) { $AllPassed = $false }
}

Write-Host ""
Write-Host "----------------------------------------"
Write-Host ""

if ($AllPassed) {
    Write-Host "All tests passed!" -ForegroundColor Green
    exit 0
} else {
    Write-Host "Some tests failed." -ForegroundColor Red
    exit 1
}
