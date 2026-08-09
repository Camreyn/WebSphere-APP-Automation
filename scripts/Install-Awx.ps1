[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $Root

$Tools = Join-Path $Root ".tools"
$Data = Join-Path $Root ".data"
$Kubeconfig = Join-Path $Data "kubeconfig"
$Kind = Join-Path $Tools "kind.exe"
$Kubectl = Join-Path $Tools "kubectl.exe"
$ClusterName = "was-aap-lab"
$KindVersion = "v0.20.0"
$KubectlVersion = "v1.27.3"
$Network = "was-aap-lab"

New-Item -ItemType Directory -Path $Tools, $Data -Force | Out-Null

function Install-CheckedDownload {
    param(
        [Parameter(Mandatory)] [string]$Uri,
        [Parameter(Mandatory)] [string]$ChecksumUri,
        [Parameter(Mandatory)] [string]$Destination
    )

    $Download = "$Destination.download"
    $ChecksumFile = "$Destination.sha256"
    Invoke-WebRequest -UseBasicParsing -Uri $Uri -OutFile $Download
    Invoke-WebRequest -UseBasicParsing -Uri $ChecksumUri -OutFile $ChecksumFile
    $Expected = ((Get-Content -LiteralPath $ChecksumFile -Raw).Trim() -split '\s+')[0].ToLowerInvariant()
    $Actual = (Get-FileHash -LiteralPath $Download -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($Expected -ne $Actual) {
        Remove-Item -LiteralPath $Download -Force
        throw "SHA-256 mismatch for $Uri (expected $Expected, received $Actual)."
    }
    Move-Item -LiteralPath $Download -Destination $Destination -Force
    Remove-Item -LiteralPath $ChecksumFile -Force
}

if (-not (Test-Path -LiteralPath $Kind)) {
    Write-Host "Downloading and verifying Kind $KindVersion..."
    $KindBase = "https://github.com/kubernetes-sigs/kind/releases/download/$KindVersion/kind-windows-amd64"
    Install-CheckedDownload -Uri $KindBase -ChecksumUri "$KindBase.sha256sum" -Destination $Kind
}

if (-not (Test-Path -LiteralPath $Kubectl)) {
    Write-Host "Downloading and verifying kubectl $KubectlVersion..."
    $KubectlBase = "https://dl.k8s.io/release/$KubectlVersion/bin/windows/amd64/kubectl.exe"
    Install-CheckedDownload -Uri $KubectlBase -ChecksumUri "$KubectlBase.sha256" -Destination $Kubectl
}

$ContextJson = docker --context desktop-linux context inspect desktop-linux
if ($LASTEXITCODE -ne 0) { throw "Docker Desktop Linux context is unavailable." }
$DockerEndpoint = (($ContextJson | ConvertFrom-Json)[0].Endpoints.docker.Host).Trim()
$PreviousDockerHost = $env:DOCKER_HOST
$env:DOCKER_HOST = $DockerEndpoint

try {
    $ExistingNode = docker ps -a --filter "name=^/${ClusterName}-control-plane$" --format "{{.Names}}"
    if (-not $ExistingNode) {
        Write-Host "Creating Kind cluster $ClusterName..."
        & $Kind create cluster `
            --name $ClusterName `
            --config (Join-Path $Root "kubernetes\kind\kind-config.yaml") `
            --kubeconfig $Kubeconfig `
            --wait 5m
        if ($LASTEXITCODE -ne 0) { throw "Kind cluster creation failed." }
    } else {
        docker start "${ClusterName}-control-plane" | Out-Null
        & $Kind export kubeconfig --name $ClusterName --kubeconfig $Kubeconfig
        if ($LASTEXITCODE -ne 0) { throw "Could not refresh the lab kubeconfig." }
    }

    $NetworkNames = @(docker network ls --format "{{.Name}}")
    if ($NetworkNames -notcontains $Network) {
        throw "Docker network $Network is missing. Run .\lab.ps1 scm first."
    }
    $Attached = docker network inspect $Network --format "{{json .Containers}}"
    if ($Attached -notmatch "${ClusterName}-control-plane") {
        docker network connect $Network "${ClusterName}-control-plane"
        if ($LASTEXITCODE -ne 0) { throw "Unable to attach Kind to $Network." }
    }

    Write-Host "Building the pinned AWX execution environment..."
    docker build `
        --file (Join-Path $Root "execution-environment\Dockerfile") `
        --tag "wasnd-lab-ee:24.6.1" `
        $Root
    if ($LASTEXITCODE -ne 0) { throw "AWX execution-environment image build failed." }

    $KindImages = docker exec "${ClusterName}-control-plane" crictl images
    if ($KindImages -notmatch "wasnd-lab-ee") {
        & $Kind load docker-image "wasnd-lab-ee:24.6.1" --name $ClusterName
        if ($LASTEXITCODE -ne 0) { throw "Unable to load the execution environment into Kind." }
    } else {
        Write-Host "Pinned AWX execution environment is already loaded in Kind."
    }

    & $Kubectl --kubeconfig $Kubeconfig apply -f (Join-Path $Root "kubernetes\awx\namespace.yaml")
    if ($LASTEXITCODE -ne 0) { throw "Unable to create the AWX namespace." }

    $AdminSecret = Join-Path $Root ".secrets\awx_admin_password"
    $AwxSecretKey = Join-Path $Root ".secrets\awx_secret_key"
    & $Kubectl --kubeconfig $Kubeconfig -n awx create secret generic was-lab-awx-admin-password `
        "--from-file=password=$AdminSecret" --dry-run=client -o yaml |
        & $Kubectl --kubeconfig $Kubeconfig apply -f -
    if ($LASTEXITCODE -ne 0) { throw "Unable to create the AWX administrator secret." }

    & $Kubectl --kubeconfig $Kubeconfig -n awx create secret generic was-lab-awx-secret-key `
        "--from-file=secret_key=$AwxSecretKey" --dry-run=client -o yaml |
        & $Kubectl --kubeconfig $Kubeconfig apply -f -
    if ($LASTEXITCODE -ne 0) { throw "Unable to create the AWX application secret." }

    Write-Host "Installing AWX Operator 2.19.1..."
    & $Kubectl --kubeconfig $Kubeconfig apply -k (Join-Path $Root "kubernetes\awx\operator")
    if ($LASTEXITCODE -ne 0) { throw "AWX Operator installation failed." }

    & $Kubectl --kubeconfig $Kubeconfig -n awx rollout status `
        deployment/awx-operator-controller-manager --timeout=10m
    if ($LASTEXITCODE -ne 0) { throw "AWX Operator did not become ready." }

    & $Kubectl --kubeconfig $Kubeconfig apply -f (Join-Path $Root "kubernetes\awx\operator\awx.yaml")
    if ($LASTEXITCODE -ne 0) { throw "AWX custom resource creation failed." }

    Write-Host "Waiting for AWX; first boot includes image pulls and database migrations..."
    $DeploymentCreated = $false
    for ($Attempt = 1; $Attempt -le 120; $Attempt++) {
        $DeploymentName = & $Kubectl --kubeconfig $Kubeconfig -n awx get `
            deployment was-lab-web --ignore-not-found -o name
        if ($DeploymentName) {
            $DeploymentCreated = $true
            break
        }
        Start-Sleep -Seconds 5
    }
    if (-not $DeploymentCreated) {
        & $Kubectl --kubeconfig $Kubeconfig -n awx get pods -o wide
        throw "AWX web deployment was not created within 10 minutes."
    }
    & $Kubectl --kubeconfig $Kubeconfig -n awx wait `
        --for=condition=available deployment/was-lab-web --timeout=20m
    if ($LASTEXITCODE -ne 0) {
        & $Kubectl --kubeconfig $Kubeconfig -n awx get pods -o wide
        throw "AWX web deployment did not become ready within 20 minutes."
    }
} finally {
    $env:DOCKER_HOST = $PreviousDockerHost
}

Write-Host "AWX is ready at http://127.0.0.1:32000/ (user: admin)."
