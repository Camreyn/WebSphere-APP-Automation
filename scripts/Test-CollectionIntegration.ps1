[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
& (Join-Path $PSScriptRoot "Validate-IbmMedia.ps1") | Out-Null

$Running = @(docker --context desktop-linux compose --profile was ps --status running --services)
foreach ($Service in @("was-dmgr", "was-node1", "was-node2", "haproxy")) {
    if ($Running -notcontains $Service) {
        throw "WAS integration requires the running genuine topology. Run .\lab.ps1 was-up first."
    }
}

$Password = (Get-Content -Raw -LiteralPath (Join-Path $Root ".secrets\was_admin_password")).Trim()
$Vars = Join-Path $Root ".data\collection-integration-vars.yml"
@"
---
was_admin_user: wsadmin
was_admin_password: '$($Password.Replace("'", "''"))'
"@ | Set-Content -LiteralPath $Vars -Encoding UTF8

$AnsibleRoot = Join-Path $Root "ansible"
$PrivateKey = Join-Path $Root ".secrets\ansible_lab"
$Image = "wasnd-lab-ee:24.6.1"
try {
    foreach ($Playbook in @(
        "playbooks/was_status.yml",
        "playbooks/was_sync_nodes.yml",
        "playbooks/was_set_jvm_heap.yml",
        "playbooks/was_set_jvm_heap.yml",
        "playbooks/was_deploy_sample.yml",
        "playbooks/was_deploy_sample.yml",
        "playbooks/was_start_cluster.yml",
        "playbooks/was_rolling_restart.yml",
        "playbooks/was_healthcheck.yml"
    )) {
        docker --context desktop-linux run --rm --user 0 --env HOME=/tmp `
            --env ANSIBLE_CONFIG=/runner/project/ansible.cfg `
            --network was-aap-lab `
            --volume "${AnsibleRoot}:/runner/project:ro" `
            --volume "${PrivateKey}:/runner/ssh_key:ro" `
            --volume "${Vars}:/runner/vars.yml:ro" `
            --workdir /runner/project `
            $Image `
            /bin/sh -lc "cp /runner/ssh_key /tmp/ssh_key && chmod 0600 /tmp/ssh_key && ansible-playbook --private-key /tmp/ssh_key -e @/runner/vars.yml $Playbook"
        if ($LASTEXITCODE -ne 0) { throw "Collection integration failed: $Playbook" }
    }
} finally {
    Remove-Item -LiteralPath $Vars -Force -ErrorAction SilentlyContinue
}

Write-Host "Genuine WebSphere ND collection integration passed."
