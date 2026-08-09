[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $Root

docker --context desktop-linux compose --profile was-base up -d --build was-base
if ($LASTEXITCODE -ne 0) { throw "IBM WebSphere Base ILAN failed to build or start." }

$Deadline = (Get-Date).AddMinutes(8)
do {
    $Health = (docker --context desktop-linux inspect --format "{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}" wasnd-lab-base 2>$null).Trim()
    if ($Health -eq "healthy") {
        Write-Host "IBM WebSphere traditional Base 9.0.5.28 is healthy."
        Write-Host "Run .\lab.ps1 collection-base-integration to execute genuine wsadmin and WAR deployment tests."
        exit 0
    }
    if ($Health -eq "unhealthy") {
        docker --context desktop-linux logs --tail 120 wasnd-lab-base
        throw "IBM WebSphere Base became unhealthy."
    }
    Write-Host "Waiting for WebSphere Base (state: $Health)..."
    Start-Sleep -Seconds 5
} while ((Get-Date) -lt $Deadline)

docker --context desktop-linux logs --tail 120 wasnd-lab-base
throw "Timed out waiting for IBM WebSphere Base to become healthy."
