param(
    [string]$BindHost = "127.0.0.1",
    [int]$ApiPort = 8000,
    [int]$WebPort = 5173,
    [switch]$Reload
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repoRoot = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
$webUiDir = Join-Path $repoRoot "web-ui"
$webPackageJson = Join-Path $webUiDir "package.json"
$webNodeModules = Join-Path $webUiDir "node_modules"

if (-not (Test-Path -LiteralPath $venvPython)) {
    throw "Missing .venv interpreter. Run scripts\create_venv.ps1 and scripts\install_deps.ps1 first."
}

if (-not (Test-Path -LiteralPath $webPackageJson)) {
    throw "Missing web-ui package.json. Please make sure the frontend project exists under web-ui."
}

if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    throw "npm is not available in PATH. Please install Node.js first."
}

if (-not (Test-Path -LiteralPath $webNodeModules)) {
    Write-Host "Installing frontend dependencies under web-ui"
    Push-Location $webUiDir
    try {
        & npm install
    } finally {
        Pop-Location
    }
}

Write-Host "Restarting CLIProxyAPI"

$apiArgs = @(
    "-NoExit",
    "-ExecutionPolicy", "Bypass",
    "-File", "`"$PSScriptRoot\start_api.ps1`"",
    "-BindHost", $BindHost,
    "-Port", "$ApiPort"
)

if ($Reload) {
    $apiArgs += "-Reload"
}

$webCommand = "Set-Location `"$webUiDir`"; `$env:VITE_DEV_HOST='$BindHost'; `$env:VITE_PORT='$WebPort'; `$env:VITE_API_TARGET='http://$BindHost`:$ApiPort'; npm run dev"
$webArgs = @(
    "-NoExit",
    "-ExecutionPolicy", "Bypass",
    "-Command", $webCommand
)

Write-Host "Starting TradingAgents Web API on http://$BindHost`:$ApiPort"
Start-Process powershell.exe -ArgumentList $apiArgs -WorkingDirectory $repoRoot

Write-Host "Starting TradingAgents Web UI on http://$BindHost`:$WebPort"
Start-Process powershell.exe -ArgumentList $webArgs -WorkingDirectory $webUiDir

Write-Host "CLIProxyAPI, frontend, and backend startup commands have been launched."
