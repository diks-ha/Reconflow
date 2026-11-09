param(
    [ValidateSet("config", "migrate", "seed", "serve")]
    [string]$Action = "serve",
    [string]$Email,
    [string]$FullName,
    [ValidateSet("FINANCE_EXECUTIVE", "FINANCE_COFOUNDER")]
    [string]$Role = "FINANCE_EXECUTIVE",
    [switch]$DemoData
)

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

$envFile = Join-Path $PSScriptRoot ".env"
$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $envFile)) {
    throw "backend/.env was not found. Create it from .env.example and set database credentials privately."
}
if (-not (Test-Path -LiteralPath $python)) {
    throw "The project virtual environment was not found. Create backend/.venv and install requirements.txt first."
}

# Explicitly load the project file into this process so a stale inherited
# DATABASE_URL cannot silently redirect migrations, seeding, or the API.
$databaseLine = Get-Content -LiteralPath $envFile | Where-Object { $_ -match '^\s*DATABASE_URL\s*=' } | Select-Object -First 1
if (-not $databaseLine) {
    throw "DATABASE_URL is missing from backend/.env."
}
$databaseUrl = ($databaseLine -split "=", 2)[1].Trim().Trim('"').Trim("'")
if (-not $databaseUrl) {
    throw "DATABASE_URL is empty in backend/.env."
}
$env:DATABASE_URL = $databaseUrl

if ($Action -eq "config") {
    & $python -c "from urllib.parse import urlsplit; from app.core.config import get_settings; u=urlsplit(get_settings().database_url); print(f'Database target: {u.hostname}:{u.port or 5432} ({u.scheme})')"
    exit $LASTEXITCODE
}

if ($Action -eq "migrate") {
    & $python -m alembic upgrade head
    exit $LASTEXITCODE
}

if ($Action -eq "seed") {
    $seedArgs = @()
    if ($Email) {
        $seedArgs += @("--email", $Email)
        if ($FullName) { $seedArgs += @("--full-name", $FullName) }
        $seedArgs += @("--role", $Role)
        if ($DemoData) { $seedArgs += "--demo-data" }
    } elseif ($DemoData) {
        throw "-DemoData requires -Email so sample data has an owner."
    }
    & $python (Join-Path $PSScriptRoot "seed.py") @seedArgs
    exit $LASTEXITCODE
}

& $python -m uvicorn app.main:app --reload
exit $LASTEXITCODE
