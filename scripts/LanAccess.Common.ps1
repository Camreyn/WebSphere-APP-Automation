$script:LabLanPorts = @(
    2220, 2221, 2222, 2230,
    8080, 8404, 8879, 8880, 8888, 9043, 9060, 9081, 9082,
    9143, 9160, 9180, 9418, 9444, 9445, 9543,
    32000
)

function Get-LabLanStatePath {
    param([Parameter(Mandatory)][string]$Root)
    return Join-Path $Root ".data\lan-access.json"
}

function Get-LabPrimaryIPv4Address {
    $Candidates = foreach ($Configuration in Get-NetIPConfiguration -ErrorAction SilentlyContinue) {
        if (-not $Configuration.IPv4DefaultGateway) { continue }
        foreach ($Address in $Configuration.IPv4Address) {
            if ($Address.IPAddress -and -not $Address.IPAddress.StartsWith("169.254.")) {
                [pscustomobject]@{
                    Address = $Address.IPAddress
                    Metric = $Configuration.NetIPv4Interface.InterfaceMetric
                }
            }
        }
    }
    $Selected = $Candidates | Sort-Object Metric | Select-Object -First 1
    if ($Selected) { return $Selected.Address }

    # Some constrained PowerShell hosts cannot query Get-NetIPConfiguration.
    # A UDP route selection discovers the desktop address without sending data.
    $Socket = New-Object Net.Sockets.Socket(
        [Net.Sockets.AddressFamily]::InterNetwork,
        [Net.Sockets.SocketType]::Dgram,
        [Net.Sockets.ProtocolType]::Udp
    )
    try {
        $Socket.Connect("192.0.2.1", 9)
        return ([Net.IPEndPoint]$Socket.LocalEndPoint).Address.ToString()
    } finally {
        $Socket.Dispose()
    }
}

function Assert-LabListenAddress {
    param([Parameter(Mandatory)][string]$ListenAddress)

    $Parsed = $null
    if (-not [Net.IPAddress]::TryParse($ListenAddress, [ref]$Parsed) -or
        $Parsed.AddressFamily -ne [Net.Sockets.AddressFamily]::InterNetwork -or
        [Net.IPAddress]::IsLoopback($Parsed) -or
        $ListenAddress -eq "0.0.0.0") {
        throw "ListenAddress must be a specific, non-loopback IPv4 address assigned to this desktop."
    }
}

function Read-LabLanState {
    param([Parameter(Mandatory)][string]$Root)
    $Path = Get-LabLanStatePath -Root $Root
    if (-not (Test-Path -LiteralPath $Path)) { return $null }
    try {
        return Get-Content -Raw -LiteralPath $Path | ConvertFrom-Json
    } catch {
        throw "LAN state file is invalid: $Path"
    }
}

function Write-LabLanState {
    param(
        [Parameter(Mandatory)][string]$Root,
        [Parameter(Mandatory)][string]$ListenAddress
    )
    $Path = Get-LabLanStatePath -Root $Root
    New-Item -ItemType Directory -Path (Split-Path -Parent $Path) -Force | Out-Null
    [ordered]@{
        mode = "docker_tcp_gateway"
        listen_address = $ListenAddress
        ports = $script:LabLanPorts
        container = "wasnd-lab-lan-gateway"
        updated_at = (Get-Date).ToUniversalTime().ToString("o")
    } | ConvertTo-Json | Set-Content -LiteralPath $Path -Encoding UTF8
}
