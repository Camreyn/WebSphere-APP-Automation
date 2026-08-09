[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $Root

foreach ($Directory in @(".secrets", ".tools", ".data", ".data\scm", "artifacts\apps", "reports")) {
    New-Item -ItemType Directory -Path (Join-Path $Root $Directory) -Force | Out-Null
}

if (-not (Test-Path -LiteralPath (Join-Path $Root ".env"))) {
    Copy-Item -LiteralPath (Join-Path $Root ".env.example") -Destination (Join-Path $Root ".env")
}

function New-HexSecret {
    param([int]$Bytes = 24)
    $Buffer = New-Object byte[] $Bytes
    $Generator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $Generator.GetBytes($Buffer) } finally { $Generator.Dispose() }
    return (($Buffer | ForEach-Object { $_.ToString("x2") }) -join "")
}

foreach ($Secret in @(
    @{ Name = "was_admin_password"; Bytes = 24 },
    @{ Name = "awx_admin_password"; Bytes = 24 },
    @{ Name = "awx_secret_key"; Bytes = 48 }
)) {
    $Path = Join-Path $Root ".secrets\$($Secret.Name)"
    if (-not (Test-Path -LiteralPath $Path)) {
        Set-Content -LiteralPath $Path -Value (New-HexSecret -Bytes $Secret.Bytes) -NoNewline -Encoding ASCII
    }
}

$SshKey = Join-Path $Root ".secrets\ansible_lab"
if (-not (Test-Path -LiteralPath $SshKey)) {
    $SshKeygen = Get-Command ssh-keygen -ErrorAction SilentlyContinue
    if (-not $SshKeygen) { throw "ssh-keygen is required to create the AWX Machine credential." }
    # Windows PowerShell otherwise removes the empty argument before OpenSSH sees it.
    & $SshKeygen.Source -q -t ed25519 -N '""' -f $SshKey -C "ansible@wasnd-lab"
    # Some sandboxed Windows OpenSSH builds create the valid private key but fail
    # while opening the companion .pub file. Rebuild it deterministically below.
    if ($LASTEXITCODE -ne 0 -and -not (Test-Path -LiteralPath $SshKey)) {
        throw "ssh-keygen failed."
    }
}

$SshPublicKey = "$SshKey.pub"
if (-not (Test-Path -LiteralPath $SshPublicKey) -or (Get-Item -LiteralPath $SshPublicKey).Length -eq 0) {
    $PublicKey = & ssh-keygen -y -f $SshKey
    if ($LASTEXITCODE -ne 0 -or -not $PublicKey) { throw "Unable to derive the SSH public key." }
    if (Test-Path -LiteralPath $SshPublicKey) {
        # The failed OpenSSH write can leave a zero-byte file with a private-key ACL.
        Remove-Item -LiteralPath $SshPublicKey -Force
    }
    Set-Content -LiteralPath $SshPublicKey -Value "$PublicKey ansible@wasnd-lab" -NoNewline -Encoding ASCII
}

$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
$ProjectTemp = Join-Path $Root ".data\tmp"
New-Item -ItemType Directory -Path $ProjectTemp -Force | Out-Null
$PreviousTemp = $env:TEMP
$PreviousTmp = $env:TMP
$env:TEMP = $ProjectTemp
$env:TMP = $ProjectTemp
try {
    if (-not (Test-Path -LiteralPath $VenvPython)) {
        & python -m venv (Join-Path $Root ".venv")
        if ($LASTEXITCODE -ne 0) { throw "Unable to create the project virtual environment." }
    }

    if (-not (Test-Path -LiteralPath (Join-Path $Root ".venv\Scripts\pip.exe"))) {
        & $VenvPython -m ensurepip --upgrade --default-pip
        if ($LASTEXITCODE -ne 0) { throw "Unable to install pip into the project virtual environment." }
    }

    & $VenvPython -m pip install --quiet --disable-pip-version-check -r (Join-Path $Root "requirements-dev.txt")
    if ($LASTEXITCODE -ne 0) { throw "Unable to install project Python dependencies into .venv." }

    & $VenvPython (Join-Path $Root "tools\build_war.py")
    if ($LASTEXITCODE -ne 0) { throw "Unable to build the sample WAR." }

    & $VenvPython (Join-Path $Root "tools\build_test_ears.py")
    if ($LASTEXITCODE -ne 0) { throw "Unable to build the test EAR files." }
} finally {
    $env:TEMP = $PreviousTemp
    $env:TMP = $PreviousTmp
}

Write-Host "Lab initialization complete. Generated values remain under ignored .secrets/."
