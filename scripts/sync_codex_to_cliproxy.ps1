$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir
$pythonFromVenv = Join-Path $repoRoot ".venv\Scripts\python.exe"
$pythonCmd = if (Test-Path $pythonFromVenv) { $pythonFromVenv } else { "python" }
$pythonScript = Join-Path $scriptDir "sync_codex_to_cliproxy.py"
$cliProxyRoot = "D:\Tools\CLIProxyAPI"
$cliProxyExe = Join-Path $cliProxyRoot "app\cli-proxy-api.exe"
$cliProxyConfig = Join-Path $cliProxyRoot "app\config.yaml"
$cliProxyLogDir = Join-Path $cliProxyRoot "logs"

$proxy = $env:HTTPS_PROXY
if (-not $proxy) { $proxy = $env:https_proxy }
if (-not $proxy) { $proxy = $env:ALL_PROXY }
if (-not $proxy) { $proxy = $env:all_proxy }
if (-not $proxy) { $proxy = $env:HTTP_PROXY }
if (-not $proxy) { $proxy = $env:http_proxy }

$argsList = @($pythonScript)
if ($proxy) {
    $argsList += @("--proxy", $proxy)
}

Write-Host "Using Python: $pythonCmd"
if ($proxy) {
    Write-Host "Using proxy: $proxy"
} else {
    Write-Host "Using proxy: none"
}

& $pythonCmd @argsList
$syncExitCode = $LASTEXITCODE

if ($syncExitCode -eq 10) {
    Write-Host "Codex token and CLIProxyAPI auth are still valid. Skipping CLIProxyAPI restart."
    exit 0
}

if ($syncExitCode -ne 0) {
    exit $syncExitCode
}

if (-not (Test-Path $cliProxyExe)) {
    Write-Warning "CLIProxyAPI executable not found at $cliProxyExe. Skipping restart."
    exit 0
}

if (-not (Test-Path $cliProxyConfig)) {
    Write-Warning "CLIProxyAPI config not found at $cliProxyConfig. Skipping restart."
    exit 0
}

if (-not (Test-Path $cliProxyLogDir)) {
    New-Item -ItemType Directory -Path $cliProxyLogDir | Out-Null
}

$stdoutLog = Join-Path $cliProxyLogDir "stdout.log"
$stderrLog = Join-Path $cliProxyLogDir "stderr.log"

Get-Process -Name "cli-proxy-api" -ErrorAction SilentlyContinue | Stop-Process -Force

$proc = Start-Process `
    -FilePath $cliProxyExe `
    -ArgumentList @("-config", $cliProxyConfig) `
    -WorkingDirectory (Split-Path $cliProxyExe -Parent) `
    -PassThru `
    -WindowStyle Hidden `
    -RedirectStandardOutput $stdoutLog `
    -RedirectStandardError $stderrLog

Start-Sleep -Seconds 4

if (Get-Process -Id $proc.Id -ErrorAction SilentlyContinue) {
    Write-Host "CLIProxyAPI restarted successfully. PID: $($proc.Id)"
} else {
    Write-Warning "CLIProxyAPI restart may have failed. Check logs:"
    Write-Warning "  $stdoutLog"
    Write-Warning "  $stderrLog"
}
