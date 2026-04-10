param(
    [string]$BindHost = "127.0.0.1",
    [int]$Port = 8000,
    [switch]$Reload
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repoRoot = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $venvPython)) {
    throw "Missing .venv interpreter. Run scripts\create_venv.ps1 and scripts\install_deps.ps1 first."
}

Set-Location $repoRoot

$uvicornArgs = @(
    "-m", "uvicorn",
    "tradingagents.web.api.app:app",
    "--host", $BindHost,
    "--port", "$Port"
)

if ($Reload) {
    $uvicornArgs += "--reload"
}

Write-Host "Starting TradingAgents Web API on http://$BindHost`:$Port"
& $venvPython @uvicornArgs
