[CmdletBinding()]
param()

$Root = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "LanAccess.Common.ps1")
$Kubectl = Join-Path $Root ".tools\kubectl.exe"
$Kubeconfig = Join-Path $Root ".data\kubeconfig"
$KubernetesApi = "not installed"
if ((Test-Path -LiteralPath $Kubectl) -and (Test-Path -LiteralPath $Kubeconfig)) {
    $KubernetesApi = (& $Kubectl --kubeconfig $Kubeconfig config view --minify `
        -o "jsonpath={.clusters[0].cluster.server}").Trim()
}

$LanState = Read-LabLanState -Root $Root
$LanAddress = $null
if ($LanState) {
    $LanAddress = $LanState.listen_address
} else {
    try { $LanAddress = Get-LabPrimaryIPv4Address } catch {}
}

$LanHeading = if ($LanState) {
    "Trusted-LAN endpoints ($LanAddress)"
} elseif ($LanAddress) {
    "Trusted-LAN endpoints (DISABLED; run .\lab.ps1 lan-up for $LanAddress)"
} else {
    "Trusted-LAN endpoints (DISABLED; no primary IPv4 address detected)"
}
$LanHost = if ($LanAddress) { $LanAddress } else { "DESKTOP-IP" }

@"
Desktop-local endpoints
-----------------------
Lab portal                 http://127.0.0.1:8888/
AWX web UI                 http://127.0.0.1:32000/
AWX REST API               http://127.0.0.1:32000/api/v2/
WAS Base console HTTPS     https://127.0.0.1:9143/ibm/console
WAS Base console HTTP      http://127.0.0.1:9160/ibm/console
WAS Base SOAP              127.0.0.1:8880
WAS Base sample HTTP       http://127.0.0.1:9180/was-lab-base/
WAS Base sample HTTPS      https://127.0.0.1:9543/was-lab-base/
WAS admin console HTTPS    https://127.0.0.1:9043/ibm/console
WAS admin console HTTP     http://127.0.0.1:9060/ibm/console
WAS deployment manager SOAP 127.0.0.1:8879
Clustered sample app       http://127.0.0.1:8080/was-lab/
HAProxy statistics         http://127.0.0.1:8404/stats
Node 1 direct HTTP         http://127.0.0.1:9081/was-lab/
Node 1 direct HTTPS        https://127.0.0.1:9444/was-lab/
Node 2 direct HTTP         http://127.0.0.1:9082/was-lab/
Node 2 direct HTTPS        https://127.0.0.1:9445/was-lab/
Local Git (host)           git://127.0.0.1:9418/was-lab.git
Local Git (AWX network)    git://172.29.0.10:9418/was-lab.git
Kubernetes API             $KubernetesApi (desktop only; use .data/kubeconfig)

$LanHeading
$('-' * $LanHeading.Length)
Lab portal                 http://${LanHost}:8888/
AWX web UI                 http://${LanHost}:32000/
AWX REST API               http://${LanHost}:32000/api/v2/
WAS Base console HTTPS     https://${LanHost}:9143/ibm/console
WAS Base console HTTP      http://${LanHost}:9160/ibm/console
WAS Base SOAP              ${LanHost}:8880
WAS Base sample HTTP       http://${LanHost}:9180/was-lab-base/
WAS Base sample HTTPS      https://${LanHost}:9543/was-lab-base/
WAS admin console HTTPS    https://${LanHost}:9043/ibm/console
WAS admin console HTTP     http://${LanHost}:9060/ibm/console
WAS deployment manager SOAP ${LanHost}:8879
Clustered sample app       http://${LanHost}:8080/was-lab/
HAProxy statistics         http://${LanHost}:8404/stats
Node 1 direct HTTP         http://${LanHost}:9081/was-lab/
Node 1 direct HTTPS        https://${LanHost}:9444/was-lab/
Node 2 direct HTTP         http://${LanHost}:9082/was-lab/
Node 2 direct HTTPS        https://${LanHost}:9445/was-lab/
Git project                git://${LanHost}:9418/was-lab.git

SSH
---
Deployment manager         ssh -i .secrets/ansible_lab -p 2220 ansible@${LanHost}
Application node 1         ssh -i .secrets/ansible_lab -p 2221 ansible@${LanHost}
Application node 2         ssh -i .secrets/ansible_lab -p 2222 ansible@${LanHost}
WebSphere Base AppSrv01    ssh -i .secrets/ansible_lab -p 2230 ansible@${LanHost}

Internal Docker addresses
-------------------------
Portal                      172.29.0.11:80
SCM                         172.29.0.10:9418
Deployment manager          172.29.0.20:22,8879,9043,9060
Application node 1          172.29.0.21:22,9080,9443
Application node 2          172.29.0.22:22,9080,9443
HAProxy                     172.29.0.30:8080,8404
WebSphere Base              172.29.0.40:22,8880,9043,9060,9080,9443
"@ | Write-Host
