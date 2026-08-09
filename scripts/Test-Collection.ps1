[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Image = "wasnd-lab-ee:24.6.1"
$AnsibleRoot = Join-Path $Root "ansible"

docker --context desktop-linux image inspect $Image | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "The pinned execution image is missing. Run .\lab.ps1 awx-up first."
}

docker --context desktop-linux run --rm --user 0 --env HOME=/tmp `
    --volume "${AnsibleRoot}:/source:ro" `
    $Image `
    /bin/sh -lc "cp -R /source /tmp/work && chmod -R a-x /tmp/work && cd /tmp/work/collections/ansible_collections/waslab/wasnd && ansible-test sanity --color no"
if ($LASTEXITCODE -ne 0) { throw "ansible-test sanity failed." }

$Playbooks = Get-ChildItem -LiteralPath (Join-Path $AnsibleRoot "playbooks") -Filter "*.yml" | Sort-Object Name
foreach ($Playbook in $Playbooks) {
    docker --context desktop-linux run --rm --user 0 --env HOME=/tmp `
        --env ANSIBLE_CONFIG=/work/ansible.cfg `
        --volume "${AnsibleRoot}:/work" `
        --workdir /work `
        $Image `
        ansible-playbook --syntax-check $($Playbook.FullName.Replace($AnsibleRoot, "/work").Replace("\", "/"))
    if ($LASTEXITCODE -ne 0) { throw "Syntax check failed: $($Playbook.Name)" }
}

docker --context desktop-linux run --rm --user 0 --env HOME=/tmp `
    --env ANSIBLE_CONFIG=/work/ansible.cfg `
    --volume "${AnsibleRoot}:/work" `
    --workdir /work `
    $Image `
    ansible-playbook playbooks/was_release_primitives_selftest.yml
if ($LASTEXITCODE -ne 0) { throw "Release workflow primitive self-test failed." }

Write-Host "Collection sanity, playbook syntax, and release primitive tests passed."
