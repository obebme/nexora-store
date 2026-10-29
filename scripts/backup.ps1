$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $PSScriptRoot
$backupDirectory = Join-Path $projectRoot 'backups'
$timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$backupName = "nexora-$timestamp.dump"
$containerPath = "/tmp/$backupName"
$localPath = Join-Path $backupDirectory $backupName

New-Item -ItemType Directory -Force -Path $backupDirectory | Out-Null
Push-Location $projectRoot
try {
    docker compose exec -T db sh -c 'pg_dump --format=custom --no-owner --username="$POSTGRES_USER" "$POSTGRES_DB" > "$1"' backup $containerPath
    if ($LASTEXITCODE -ne 0) {
        throw 'Database dump failed.'
    }

    docker compose cp "db:$containerPath" $localPath
    if ($LASTEXITCODE -ne 0) {
        throw 'Could not copy the database dump from the container.'
    }

    Write-Output "Database backup created: $localPath"
}
finally {
    docker compose exec -T db rm -f -- $containerPath | Out-Null
    Pop-Location
}
