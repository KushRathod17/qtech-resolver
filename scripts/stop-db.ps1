# Stops the private QTech Postgres cluster (port 5433).
# Shutting down cleanly avoids the crash-recovery / orphaned-shared-memory mess
# that a hard kill leaves behind.
#
#   .\scripts\stop-db.ps1

$bin  = 'C:\Program Files\PostgreSQL\18\bin'
$data = 'C:\Users\Kanishk\pgdata-qtech'

& (Join-Path $bin 'pg_isready.exe') -p 5433 -q
if ($LASTEXITCODE -ne 0) {
    Write-Host "Postgres is not running on port 5433." -ForegroundColor Yellow
    exit 0
}

& (Join-Path $bin 'pg_ctl.exe') -D $data -m fast stop
Write-Host "Postgres stopped." -ForegroundColor Green
