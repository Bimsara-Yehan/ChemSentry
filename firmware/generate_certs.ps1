Param(
    [string]$OutDir = "./certs",
    [string]$Devices = "device1,device2"
)

Write-Host "Running cert generator -> output: $OutDir; devices: $Devices"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

if (Test-Path (Join-Path $scriptDir ".venv-3.11\Scripts\Activate.ps1")) {
    Write-Host "Activating .venv-3.11"
    . "$scriptDir\.venv-3.11\Scripts\Activate.ps1"
}

python "$scriptDir\generate_certs.py" --out (Resolve-Path $OutDir) --devices $Devices
