# Windows PowerShell setup script. Mirrors scripts/setup.sh.
#
# Installs uv if missing, creates a venv, installs dependencies, runs
# chapters 1 and 2 as a smoke test.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File scripts\setup.ps1

$ErrorActionPreference = 'Stop'
$Here = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Here

Write-Host "=== Art of Agents Companion: setup ==="

# Install uv if missing. https://astral.sh/uv gives us a single PowerShell-native installer.
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "uv not found. Installing from https://astral.sh/uv/install.ps1 ..."
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
}

$uvVersion = & uv --version
Write-Host "uv version: $uvVersion"

if (-not (Test-Path .venv)) {
    Write-Host "Creating virtual environment at .venv ..."
    try { uv venv --python 3.14 .venv } catch { uv venv .venv }
}

Write-Host "Installing dependencies ..."
uv pip install --python .venv\Scripts\python.exe -r requirements.txt

Write-Host ""
Write-Host "=== Smoke test: chapters 1 and 2 ==="
& .\.venv\Scripts\python.exe chapters\01-laying-plans\run-eval.py
Write-Host ""
& .\.venv\Scripts\python.exe chapters\02-waging-war\run-eval.py

Write-Host ""
Write-Host "=== Setup complete ==="
Write-Host "Activate with:  .\.venv\Scripts\Activate.ps1"
Write-Host "Run all:        python scripts\run_all.py"
Write-Host "Run in Docker:  docker build -t aoa-companion . ; docker run --rm aoa-companion"
