[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "LanAccess.Common.ps1")
Set-Location -LiteralPath $Root

docker --context desktop-linux stop wasnd-lab-lan-gateway 2>$null | Out-Null
docker --context desktop-linux rm wasnd-lab-lan-gateway 2>$null | Out-Null
$StatePath = Get-LabLanStatePath -Root $Root
if (Test-Path -LiteralPath $StatePath) {
    Remove-Item -LiteralPath $StatePath -Force
}

Write-Host "The lab's Docker LAN gateway is disabled; desktop-loopback services remain running."
