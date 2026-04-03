$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repoRoot = Split-Path -Parent $PSScriptRoot
$venvPath = Join-Path $repoRoot ".venv"
$venvPython = Join-Path $venvPath "Scripts\python.exe"
$venvTemp = Join-Path $venvPath ".tmp"

New-Item -ItemType Directory -Force -Path $venvTemp | Out-Null
$env:TEMP = $venvTemp
$env:TMP = $venvTemp

if (-not (Test-Path -LiteralPath $venvPython)) {
    Write-Host "Creating virtual environment at $venvPath"
    $pythonCommand = Get-Command py -ErrorAction SilentlyContinue
    if ($pythonCommand) {
        & py -3 -m venv $venvPath
    } else {
        & python -m venv $venvPath
    }
} else {
    Write-Host "Virtual environment already exists at $venvPath"
}

$pipAvailable = $true
try {
    & $venvPython -m pip --version *>$null
    $pipAvailable = $LASTEXITCODE -eq 0
} catch {
    $pipAvailable = $false
}

if (-not $pipAvailable) {
    Write-Host "Bootstrapping pip with ensurepip"
    $escapedVenvTemp = $venvTemp.Replace("\", "\\").Replace("'", "\\'")
    $ensurePipScript = @'
import ensurepip
import tempfile

tempfile.tempdir = '__VENV_TEMP__'
ensurepip.bootstrap(upgrade=True, default_pip=True)
'@.Replace("__VENV_TEMP__", $escapedVenvTemp)
    & $venvPython -c $ensurePipScript
}

Write-Host "Upgrading pip in $venvPath"
& $venvPython -m pip install --upgrade pip
