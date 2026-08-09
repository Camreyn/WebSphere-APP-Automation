[CmdletBinding()]
param()

$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "LanAccess.Common.ps1")

$State = Read-LabLanState -Root $Root
if (-not $State) {
    Write-Host "LAN access: DISABLED"
    Write-Host "Run .\lab.ps1 lan-up to start the Docker TCP gateway."
    exit 0
}

$Running = (docker --context desktop-linux inspect --format "{{.State.Running}}" $State.container 2>$null).Trim()
$PortalReady = $false
try {
    $Response = Invoke-WebRequest -UseBasicParsing -Uri "http://$($State.listen_address):8888/healthz" -TimeoutSec 3
    $PortalReady = $Response.StatusCode -eq 200
} catch {}
$Healthy = $Running -eq "true" -and $PortalReady

Write-Host ("LAN access: " + $(if ($Healthy) { "ENABLED" } else { "DEGRADED" }))
Write-Host "Mode: Docker TCP gateway (no Windows portproxy)"
Write-Host "Published address: $($State.listen_address)"
Write-Host "Portal: http://$($State.listen_address):8888/"
Write-Host "AWX: http://$($State.listen_address):32000/"
if (-not $Healthy) {
    Write-Warning "Re-run .\lab.ps1 lan-up to recreate the gateway for the current desktop address."
}
