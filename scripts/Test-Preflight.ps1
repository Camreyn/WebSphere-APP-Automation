[CmdletBinding()]
param()

$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $Root

$Failed = $false
foreach ($Command in @("docker", "python", "git", "kubectl", "ssh-keygen")) {
    if (Get-Command $Command -ErrorAction SilentlyContinue) {
        Write-Host "PASS tool: $Command"
    } else {
        Write-Host "FAIL tool: $Command"
        $Failed = $true
    }
}

docker --context desktop-linux info --format "PASS Docker: {{.ServerVersion}} / {{.OSType}} / {{.Architecture}} / {{.NCPU}} CPUs / {{.MemTotal}} bytes"
if ($LASTEXITCODE -ne 0) { $Failed = $true }

foreach ($Port in @(2220, 2221, 2222, 8080, 8404, 8888, 8879, 9043, 9060, 9081, 9082, 9418, 9444, 9445, 32000)) {
    $Listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if ($Listener) { Write-Host "INFO port $Port is currently in use." } else { Write-Host "PASS port $Port is available." }
}

$MediaReady = & (Join-Path $PSScriptRoot "Validate-IbmMedia.ps1") -ReportOnly
if (-not $MediaReady) {
    Write-Host "BLOCKED WAS runtime: authorized IBM ND media has not been provided."
}

if ($Failed) { exit 1 }
Write-Host "Preflight completed. AWX can proceed independently of the IBM media gate."
