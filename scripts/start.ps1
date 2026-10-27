param([switch]$Demo)
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)
function Check-Exit { if ($LASTEXITCODE -ne 0) { throw "Command failed (exit $LASTEXITCODE)." } }
if (-not (Get-Command python -ErrorAction SilentlyContinue)) { throw "Install Python 3.11+ first, with Python added to PATH." }
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) { throw "Install Node.js 22 LTS first." }
if (-not (Test-Path .venv\Scripts\python.exe)) { python -m venv .venv; Check-Exit }
& .\.venv\Scripts\python.exe -m pip install -e . -c requirements.lock
Check-Exit
Push-Location web
try {
    npm ci
    Check-Exit
    npm run build
    Check-Exit
} finally { Pop-Location }
if ($Demo) { & .\.venv\Scripts\deskpad.exe --demo }
else { & .\.venv\Scripts\deskpad.exe }
Check-Exit
