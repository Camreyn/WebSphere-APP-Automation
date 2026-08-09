[CmdletBinding()]
param()

$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $PSScriptRoot
$Kubectl = Join-Path $Root ".tools\kubectl.exe"
$Kubeconfig = Join-Path $Root ".data\kubeconfig"

Write-Host "Docker services"
Write-Host "---------------"
docker --context desktop-linux compose --profile was --profile was-base --profile lan ps --all

try {
    $Portal = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8888/" -TimeoutSec 5
    Write-Host "Lab portal: READY ($($Portal.StatusCode)) at http://127.0.0.1:8888/"
} catch {
    Write-Host "Lab portal: not reachable"
}

Write-Host "`nIBM WebSphere Base ILAN"
Write-Host "------------------------"
try {
    $BaseState = (docker --context desktop-linux inspect --format "{{.State.Health.Status}}" wasnd-lab-base 2>$null).Trim()
    Write-Host "Base runtime: $($BaseState.ToUpper()) at https://127.0.0.1:9143/ibm/console"
    $BaseApp = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:9180/was-lab-base/" -TimeoutSec 5
    Write-Host "Base sample application: READY ($($BaseApp.StatusCode))"
} catch {
    Write-Host "Base runtime: not ready (run .\lab.ps1 was-base-up)"
}

Write-Host "`nTrusted-LAN access"
Write-Host "------------------"
& (Join-Path $PSScriptRoot "Show-LanAccess.ps1")

Write-Host "`nAWX / Kubernetes"
Write-Host "----------------"
if ((Test-Path -LiteralPath $Kubectl) -and (Test-Path -LiteralPath $Kubeconfig)) {
    & $Kubectl --kubeconfig $Kubeconfig -n awx get awx,pods,services,pvc 2>$null
} else {
    Write-Host "NOT INSTALLED: run .\lab.ps1 awx-up"
}

try {
    $Ping = Invoke-RestMethod -Uri "http://127.0.0.1:32000/api/v2/ping/" -TimeoutSec 5
    Write-Host "AWX API: READY (version $($Ping.version))"
} catch {
    Write-Host "AWX API: not reachable"
}

Write-Host "`nIBM WebSphere ND media"
Write-Host "----------------------"
$MediaReady = & (Join-Path $PSScriptRoot "Validate-IbmMedia.ps1") -ReportOnly
if (-not $MediaReady) {
    Write-Host "WAS: BLOCKED until authorized ND 9 media is supplied"
}

try {
    $Response = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8080/was-lab/" -TimeoutSec 5
    Write-Host "Cluster application: READY ($($Response.StatusCode))"
} catch {
    Write-Host "Cluster application: not reachable"
}
