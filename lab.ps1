[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet(
        "help", "init", "preflight", "sample-app", "sample-release", "portal", "scm", "awx-up", "awx-down",
        "lan-up", "lan-down", "lan-status",
        "bootstrap-awx", "awx-base-integration", "was-build", "was-up", "was-base-up", "was-base-down", "up", "down", "status", "urls",
        "collection-build", "collection-test", "collection-integration", "collection-base-integration",
        "verify", "destroy"
    )]
    [string]$Command = "help",
    [string]$ListenAddress,
    [string]$ReleaseVersion = "lab-1",
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
Set-Location -LiteralPath $Root

function Invoke-ProjectScript {
    param([string]$Name)
    & (Join-Path $Root "scripts\$Name")
}

function Invoke-VenvPython {
    param([string[]]$Arguments)
    $Python = Join-Path $Root ".venv\Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $Python)) {
        throw "Project virtual environment is missing. Run .\lab.ps1 init."
    }
    & $Python @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Python command failed with code $LASTEXITCODE"
    }
}

function Show-Help {
    @"
Local WebSphere ND 9 + AWX lab

  .\lab.ps1 init            Create .venv, generated secrets, SSH key, sample WAR, and test EARs
  .\lab.ps1 preflight       Check Docker, ports, tools, and IBM media gate
  .\lab.ps1 sample-release  Build an immutable sample release and release.yml
  .\lab.ps1 portal          Build and start the one-stop LAN portal on port 8888
  .\lab.ps1 scm             Publish ansible/ to the local read-only Git service
  .\lab.ps1 awx-up          Create Kind, install AWX, and load the lab execution image
  .\lab.ps1 lan-up          Publish all lab services on the desktop LAN IPv4 address
  .\lab.ps1 lan-status      Show persistent forwarding and firewall status
  .\lab.ps1 lan-down        Remove only this lab's LAN forwarding and firewall rule
  .\lab.ps1 bootstrap-awx   Create the AWX inventory, credentials, project, and job templates
  .\lab.ps1 awx-base-integration Launch and verify all genuine Base AWX templates
  .\lab.ps1 collection-build Build waslab.wasnd as an offline Galaxy artifact
  .\lab.ps1 collection-test Run collection sanity and every playbook syntax check
  .\lab.ps1 collection-integration Run media-gated tests against genuine WAS ND
  .\lab.ps1 was-base-up    Start IBM's official traditional WAS Base 9.0.5.28 ILAN target
  .\lab.ps1 was-base-down  Stop the ILAN Base target without deleting its profile
  .\lab.ps1 collection-base-integration Run genuine wsadmin and WAR tests against Base
  .\lab.ps1 was-build       Build genuine WAS ND from authorized artifacts/ibm media
  .\lab.ps1 was-up          Start Dmgr01, both AppSrv01 nodes, and HAProxy
  .\lab.ps1 up              Bring up both control plane and WAS runtime
  .\lab.ps1 down            Stop the lab without deleting data
  .\lab.ps1 status          Show Docker, Kubernetes, media, and endpoint status
  .\lab.ps1 urls            Print every relevant URL and port
  .\lab.ps1 verify          Run static tests plus non-destructive live checks
  .\lab.ps1 destroy -Force  Permanently remove Kind and WAS profile volumes
"@ | Write-Host
}

switch ($Command) {
    "help" { Show-Help }
    "init" { Invoke-ProjectScript "Initialize-Lab.ps1" }
    "preflight" { Invoke-ProjectScript "Test-Preflight.ps1" }
    "sample-app" {
        Invoke-ProjectScript "Initialize-Lab.ps1"
        Invoke-VenvPython @("tools/build_war.py")
    }
    "sample-release" {
        Invoke-ProjectScript "Initialize-Lab.ps1"
        $Arguments = @(
            "tools/build_sample_release.py",
            "--root", $Root,
            "--version", $ReleaseVersion
        )
        if ($Force) { $Arguments += "--force" }
        Invoke-VenvPython $Arguments
    }
    "portal" {
        docker --context desktop-linux compose up -d --build portal
        if ($LASTEXITCODE -ne 0) { throw "Lab portal failed to start." }
    }
    "scm" {
        Invoke-ProjectScript "Initialize-Lab.ps1"
        Invoke-ProjectScript "Publish-Scm.ps1"
    }
    "awx-up" {
        Invoke-ProjectScript "Initialize-Lab.ps1"
        Invoke-ProjectScript "Publish-Scm.ps1"
        Invoke-ProjectScript "Install-Awx.ps1"
    }
    "awx-down" {
        $Container = docker --context desktop-linux ps -a --filter "name=^/was-aap-lab-control-plane$" --format "{{.Names}}"
        if ($Container) { docker --context desktop-linux stop was-aap-lab-control-plane | Out-Null }
    }
    "lan-up" {
        $Arguments = @{}
        if ($ListenAddress) { $Arguments.ListenAddress = $ListenAddress }
        & (Join-Path $Root "scripts\Enable-LanAccess.ps1") @Arguments
    }
    "lan-down" { Invoke-ProjectScript "Disable-LanAccess.ps1" }
    "lan-status" { Invoke-ProjectScript "Show-LanAccess.ps1" }
    "bootstrap-awx" {
        Invoke-ProjectScript "Publish-Scm.ps1"
        Invoke-VenvPython @("tools/awx_bootstrap.py", "--root", $Root)
    }
    "awx-base-integration" {
        Invoke-VenvPython @("tools/test_awx_base.py", "--root", $Root)
    }
    "collection-build" { Invoke-ProjectScript "Build-Collection.ps1" }
    "collection-test" { Invoke-ProjectScript "Test-Collection.ps1" }
    "collection-integration" { Invoke-ProjectScript "Test-CollectionIntegration.ps1" }
    "collection-base-integration" { Invoke-ProjectScript "Test-CollectionBaseIntegration.ps1" }
    "was-base-up" {
        Invoke-ProjectScript "Initialize-Lab.ps1"
        Invoke-ProjectScript "Start-WasBase.ps1"
    }
    "was-base-down" {
        docker --context desktop-linux compose --profile was-base stop was-base
        if ($LASTEXITCODE -ne 0) { throw "WebSphere Base failed to stop." }
    }
    "was-build" {
        Invoke-ProjectScript "Initialize-Lab.ps1"
        Invoke-ProjectScript "Validate-IbmMedia.ps1"
        docker --context desktop-linux compose --profile was build was-dmgr
        if ($LASTEXITCODE -ne 0) { throw "WebSphere ND image build failed." }
    }
    "was-up" {
        Invoke-ProjectScript "Validate-IbmMedia.ps1"
        docker --context desktop-linux compose --profile was up -d was-dmgr was-node1 was-node2 haproxy
        if ($LASTEXITCODE -ne 0) { throw "WebSphere services failed to start." }
    }
    "up" {
        Invoke-ProjectScript "Initialize-Lab.ps1"
        Invoke-ProjectScript "Publish-Scm.ps1"
        Invoke-ProjectScript "Install-Awx.ps1"
        Invoke-ProjectScript "Validate-IbmMedia.ps1"
        docker --context desktop-linux compose --profile was build was-dmgr
        if ($LASTEXITCODE -ne 0) { throw "WebSphere ND image build failed." }
        docker --context desktop-linux compose --profile was up -d was-dmgr was-node1 was-node2 haproxy
        if ($LASTEXITCODE -ne 0) { throw "WebSphere services failed to start." }
        Invoke-VenvPython @("tools/awx_bootstrap.py", "--root", $Root)
    }
    "down" {
        docker --context desktop-linux compose --profile was --profile was-base --profile lan stop
        $Container = docker --context desktop-linux ps --filter "name=^/was-aap-lab-control-plane$" --format "{{.Names}}"
        if ($Container) { docker --context desktop-linux stop was-aap-lab-control-plane | Out-Null }
    }
    "status" { Invoke-ProjectScript "Show-LabStatus.ps1" }
    "urls" { Invoke-ProjectScript "Show-Urls.ps1" }
    "verify" {
        Invoke-VenvPython @("-m", "pytest")
        Invoke-VenvPython @("tools/verify_live.py", "--root", $Root)
    }
    "destroy" {
        if (-not $Force) {
            throw "destroy deletes AWX data and all WebSphere profiles. Re-run with -Force."
        }
        $Kind = Join-Path $Root ".tools\kind.exe"
        if (Test-Path -LiteralPath $Kind) {
            $PreviousDockerHost = $env:DOCKER_HOST
            try {
                $env:DOCKER_HOST = (docker context inspect desktop-linux --format "{{.Endpoints.docker.Host}}").Trim()
                & $Kind delete cluster --name was-aap-lab
            } finally {
                $env:DOCKER_HOST = $PreviousDockerHost
            }
        }
        docker --context desktop-linux compose --profile was --profile was-base --profile lan down --volumes --remove-orphans
    }
}
