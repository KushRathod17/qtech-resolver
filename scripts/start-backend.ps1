# Starts the backend API on http://localhost:8000.
#
# Uses --host "::" (dual-stack) rather than the uvicorn default of 127.0.0.1
# (IPv4-only). Chrome resolves "localhost" to the IPv6 address ::1 first --
# with an IPv4-only server that connection is refused outright (no response,
# no headers), which Chrome's devtools mislabels as a missing CORS header. It
# looks like a CORS bug; the server was just never reachable on that address.
# "::" listens on both IPv4 and IPv6, so localhost resolves either way.
#
#   .\scripts\start-backend.ps1

$backend = Join-Path $PSScriptRoot '..\backend'

if (-not (Test-Path (Join-Path $backend 'app\main.py'))) {
    Write-Host "Couldn't find backend\app\main.py under $backend" -ForegroundColor Red
    exit 1
}

Push-Location $backend
try {
    python -m uvicorn app.main:app --reload --host "::" --port 8000
} finally {
    Pop-Location
}
