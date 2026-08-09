[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $Root

$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
& $VenvPython (Join-Path $Root "tools\build_war.py")
if ($LASTEXITCODE -ne 0) { throw "Sample WAR build failed." }
& $VenvPython (Join-Path $Root "tools\build_test_ears.py")
if ($LASTEXITCODE -ne 0) { throw "Test EAR build failed." }

$GeneratedRoot = [System.IO.Path]::GetFullPath((Join-Path $Root ".data"))
$Work = [System.IO.Path]::GetFullPath((Join-Path $GeneratedRoot "scm-work"))
$BareParent = [System.IO.Path]::GetFullPath((Join-Path $GeneratedRoot "scm"))
$Bare = Join-Path $BareParent "was-lab.git"
if (-not $Work.StartsWith($GeneratedRoot) -or -not $Bare.StartsWith($GeneratedRoot)) {
    throw "Generated SCM paths escaped the project .data directory."
}

New-Item -ItemType Directory -Path $Work -Force | Out-Null
New-Item -ItemType Directory -Path $BareParent -Force | Out-Null

if (-not (Test-Path -LiteralPath (Join-Path $Work ".git"))) {
    git -C $Work init -b main | Out-Null
    git -C $Work config user.name "WAS Lab Automation"
    git -C $Work config user.email "was-lab@localhost"
    git -C $Work config core.autocrlf false
} else {
    git -C $Work config core.autocrlf false
    git -C $Work rm -r --ignore-unmatch . | Out-Null
}

Copy-Item -Path (Join-Path $Root "ansible\*") -Destination $Work -Recurse -Force
$CopiedDist = [System.IO.Path]::GetFullPath((Join-Path $Work "dist"))
if ($CopiedDist.StartsWith($Work) -and (Test-Path -LiteralPath $CopiedDist)) {
    Remove-Item -LiteralPath $CopiedDist -Recurse -Force
}
$GeneratedDirectories = @(
    Get-ChildItem -LiteralPath $Work -Recurse -Directory -Force |
        Where-Object { $_.Name -in @("__pycache__", ".ansible") -or $_.FullName.EndsWith("tests\output") }
)
foreach ($Directory in $GeneratedDirectories) {
    $Resolved = [System.IO.Path]::GetFullPath($Directory.FullName)
    if (-not $Resolved.StartsWith($Work)) {
        throw "Generated SCM cleanup path escaped the project work directory: $Resolved"
    }
    if (Test-Path -LiteralPath $Resolved) {
        Remove-Item -LiteralPath $Resolved -Recurse -Force
    }
}
Get-ChildItem -LiteralPath $Work -Recurse -File -Filter "*.pyc" -Force |
    Remove-Item -Force
git -C $Work add -A
git -C $Work diff --cached --quiet
if ($LASTEXITCODE -ne 0) {
    git -C $Work commit -m "Publish local AWX project snapshot" | Out-Null
}

if (-not (Test-Path -LiteralPath (Join-Path $Bare "HEAD"))) {
    git clone --bare $Work $Bare | Out-Null
} else {
    git --git-dir=$Bare fetch $Work "+refs/heads/main:refs/heads/main" --force | Out-Null
}
git --git-dir=$Bare symbolic-ref HEAD refs/heads/main
New-Item -ItemType File -Path (Join-Path $Bare "git-daemon-export-ok") -Force | Out-Null

docker --context desktop-linux compose up -d --build scm portal
if ($LASTEXITCODE -ne 0) { throw "Local Git service failed to start." }

Start-Sleep -Seconds 2
git ls-remote git://127.0.0.1:9418/was-lab.git | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Local Git service is not readable." }
Write-Host "AWX project published at git://172.29.0.10:9418/was-lab.git"
Write-Host "Lab portal is available at http://127.0.0.1:8888/. Run .\lab.ps1 lan-up for trusted-LAN access."
