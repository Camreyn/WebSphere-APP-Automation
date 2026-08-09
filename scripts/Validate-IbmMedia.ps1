[CmdletBinding()]
param([switch]$ReportOnly)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Media = Join-Path $Root "artifacts\ibm"

$Installers = @(Get-ChildItem -LiteralPath $Media -Recurse -File -Filter "agent.installer.linux.gtk.x86_64*.zip" -ErrorAction SilentlyContinue)
$Repositories = @(Get-ChildItem -LiteralPath (Join-Path $Media "repositories") -Recurse -File -Filter "repository.config" -ErrorAction SilentlyContinue)

if ($Installers.Count -ne 1 -or $Repositories.Count -eq 0) {
    $Message = @"
Genuine WebSphere ND media gate is not satisfied.
Expected exactly one agent.installer.linux.gtk.x86_64*.zip and one or more
repository.config files below artifacts/ibm/repositories.
Found installers=$($Installers.Count), repositories=$($Repositories.Count).
See artifacts/ibm/README.md. Liberty and WAS Base will not be substituted.
"@
    if ($ReportOnly) {
        Write-Warning $Message
        return $false
    }
    throw $Message
}

Write-Host "IBM media structure present: installer=$($Installers[0].Name), repositories=$($Repositories.Count)."
return $true
