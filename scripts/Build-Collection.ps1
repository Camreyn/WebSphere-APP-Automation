[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Image = "wasnd-lab-ee:24.6.1"

docker --context desktop-linux image inspect $Image | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "The pinned execution image is missing. Run .\lab.ps1 awx-up first."
}

$AnsibleRoot = Join-Path $Root "ansible"
docker --context desktop-linux run --rm --user 0 --env HOME=/tmp `
    --volume "${AnsibleRoot}:/work" `
    --workdir /work/collections/ansible_collections/waslab/wasnd `
    $Image `
    ansible-galaxy collection build --force --output-path /work/dist
if ($LASTEXITCODE -ne 0) { throw "Collection build failed." }

$Artifact = Get-ChildItem -LiteralPath (Join-Path $AnsibleRoot "dist") `
    -Filter "waslab-wasnd-*.tar.gz" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
Write-Host "Collection artifact: $($Artifact.FullName)"
