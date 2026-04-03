$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repoRoot = Split-Path -Parent $PSScriptRoot
$venvPath = Join-Path $repoRoot ".venv"
$venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
$venvTemp = Join-Path $venvPath ".tmp"

if (-not (Test-Path -LiteralPath $venvPython)) {
    throw "Missing .venv interpreter. Run scripts\create_venv.ps1 first."
}

New-Item -ItemType Directory -Force -Path $venvTemp | Out-Null
$env:TEMP = $venvTemp
$env:TMP = $venvTemp

Set-Location $repoRoot

Write-Host "Installing TradingAgents and dependencies into .venv"
& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install .
