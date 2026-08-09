[CmdletBinding()]
param([string]$ListenAddress)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "LanAccess.Common.ps1")
Set-Location -LiteralPath $Root

if (-not $ListenAddress) {
    $ListenAddress = Get-LabPrimaryIPv4Address
}
Assert-LabListenAddress -ListenAddress $ListenAddress

$PreviousAddress = $env:LAB_LAN_ADDRESS
try {
    $env:LAB_LAN_ADDRESS = $ListenAddress
    docker --context desktop-linux compose --profile lan up -d --force-recreate lan-gateway
    if ($LASTEXITCODE -ne 0) { throw "The Docker LAN gateway failed to start." }
} finally {
    $env:LAB_LAN_ADDRESS = $PreviousAddress
}

$Deadline = (Get-Date).AddSeconds(45)
do {
    try {
        $Response = Invoke-WebRequest -UseBasicParsing -Uri "http://${ListenAddress}:8888/healthz" -TimeoutSec 3
        if ($Response.StatusCode -eq 200) { break }
    } catch {}
    Start-Sleep -Seconds 2
} while ((Get-Date) -lt $Deadline)
if (-not $Response -or $Response.StatusCode -ne 200) {
    docker --context desktop-linux logs --tail 100 wasnd-lab-lan-gateway
    throw "The LAN gateway started but its portal route is not reachable."
}

Write-LabLanState -Root $Root -ListenAddress $ListenAddress
Write-Host "Lab LAN access is enabled for every reachable client at $ListenAddress."
Write-Host "Portal: http://${ListenAddress}:8888/"
Write-Host "AWX:    http://${ListenAddress}:32000/"
Write-Warning "AWX HTTP, Git protocol, and HTTP lab endpoints are unencrypted trusted-LAN services."
