[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$AnsibleRoot = Join-Path $Root "ansible"
$PrivateKey = Join-Path $Root ".secrets\ansible_lab"
$PasswordPath = Join-Path $Root ".secrets\was_admin_password"
$Vars = Join-Path $Root ".data\collection-base-integration-vars.yml"
$Image = "wasnd-lab-ee:24.6.1"

$Running = @(docker --context desktop-linux compose --profile was-base ps --status running --services)
if ($Running -notcontains "was-base") {
    throw "Base integration requires IBM WebSphere Base ILAN. Run .\lab.ps1 was-base-up first."
}

docker --context desktop-linux image inspect $Image | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "The pinned execution image is missing. Run .\lab.ps1 awx-up first."
}
if (-not (Test-Path -LiteralPath $PrivateKey) -or -not (Test-Path -LiteralPath $PasswordPath)) {
    throw "Generated lab credentials are missing. Run .\lab.ps1 init."
}

$Password = (Get-Content -Raw -LiteralPath $PasswordPath).Trim()
@"
---
was_admin_user: wsadmin
was_admin_password: '$($Password.Replace("'", "''"))'
"@ | Set-Content -LiteralPath $Vars -Encoding UTF8

try {
    foreach ($Playbook in @(
        "playbooks/was_base_status.yml",
        "playbooks/was_base_deploy_sample.yml",
        "playbooks/was_base_deploy_sample.yml",
        "playbooks/was_base_healthcheck.yml"
    )) {
        Write-Host "Running genuine Base integration: $Playbook"
        docker --context desktop-linux run --rm --user 0 --env HOME=/tmp `
            --env ANSIBLE_CONFIG=/runner/project/ansible.cfg `
            --network was-aap-lab `
            --volume "${AnsibleRoot}:/runner/project:ro" `
            --volume "${PrivateKey}:/runner/ssh_key:ro" `
            --volume "${Vars}:/runner/vars.yml:ro" `
            --workdir /runner/project `
            $Image `
            /bin/sh -lc "cp /runner/ssh_key /tmp/ssh_key && chmod 0600 /tmp/ssh_key && ansible-playbook --inventory inventory/base.yml --private-key /tmp/ssh_key -e @/runner/vars.yml $Playbook"
        if ($LASTEXITCODE -ne 0) { throw "Base collection integration failed: $Playbook" }
    }
} finally {
    Remove-Item -LiteralPath $Vars -Force -ErrorAction SilentlyContinue
}

Write-Host "Genuine IBM WebSphere traditional Base 9.0.5.28 wsadmin and application integration passed."
