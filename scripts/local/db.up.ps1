# Start local PostgreSQL for development.
# Optional: use this when testing fully locally instead of the shared dev DB.

$ContainerName = "aict-postgres-local"
$Image = "postgres:16"
$Port = "5432"

if (docker ps -a --format '{{.Names}}' | Select-String -Pattern "^$ContainerName$" -Quiet) {
    Write-Host "Container $ContainerName exists. Starting if stopped..."
    docker start $ContainerName 2>$null
} else {
    Write-Host "Creating and starting $ContainerName..."
    docker run --name $ContainerName `
        -e POSTGRES_USER=aict `
        -e POSTGRES_PASSWORD=aict `
        -e POSTGRES_DB=aict `
        -p "${Port}:5432" `
        -d $Image
}

Write-Host "Waiting for PostgreSQL to be ready..."
$maxAttempts = 30
$attempt = 0
do {
    Start-Sleep -Seconds 2
    $ready = docker exec $ContainerName pg_isready -U aict 2>$null
    if ($LASTEXITCODE -eq 0) { break }
    $attempt++
} while ($attempt -lt $maxAttempts)

if ($attempt -ge $maxAttempts) {
    Write-Error "PostgreSQL did not become ready in time."
    exit 1
}

Write-Host "PostgreSQL is ready."
Write-Host "For local DB, set: `$env:DATABASE_URL = 'postgresql+asyncpg://aict:aict@localhost:5432/aict'"
