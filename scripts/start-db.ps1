# Starts the private QTech Postgres cluster (port 5433).
#
# This cluster lives in your user profile and is NOT a Windows service, so it
# does not start automatically at boot — run this once per reboot. It needs no
# Administrator rights, which is the whole point of it existing.
#
#   .\scripts\start-db.ps1

$bin  = 'C:\Program Files\PostgreSQL\18\bin'
$data = 'C:\Users\Kanishk\pgdata-qtech'

if (-not (Test-Path $data)) {
    Write-Host "Data directory not found: $data" -ForegroundColor Red
    exit 1
}

# Already up? Then there is nothing to do.
& (Join-Path $bin 'pg_isready.exe') -p 5433 -q
if ($LASTEXITCODE -eq 0) {
    Write-Host "Postgres is already running on port 5433." -ForegroundColor Green
    exit 0
}

# A crashed cluster can leave orphaned children holding the shared memory block,
# which makes the next startup fail with "pre-existing shared memory block is
# still in use". Clear only OUR orphans — never the system cluster on 5432.
$orphans = Get-CimInstance Win32_Process -Filter "Name='postgres.exe'" | Where-Object {
    $owner = Invoke-CimMethod -InputObject $_ -MethodName GetOwner
    ($owner.User -eq $env:USERNAME) -and
    -not (Get-Process -Id $_.ParentProcessId -ErrorAction SilentlyContinue)
}
foreach ($p in $orphans) {
    Write-Host "Clearing orphaned postgres process $($p.ProcessId)..." -ForegroundColor Yellow
    Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
}
if ($orphans) {
    Start-Sleep -Seconds 2
    Remove-Item (Join-Path $data 'postmaster.pid') -ErrorAction SilentlyContinue
}

& (Join-Path $bin 'pg_ctl.exe') -D $data -l (Join-Path $data 'server.log') start

for ($i = 1; $i -le 25; $i++) {
    Start-Sleep -Seconds 1
    & (Join-Path $bin 'pg_isready.exe') -p 5433 -q
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Postgres ready on port 5433." -ForegroundColor Green
        exit 0
    }
}

Write-Host "Server did not become ready. Last lines of the log:" -ForegroundColor Red
Get-Content (Join-Path $data 'server.log') -Tail 15
exit 1
