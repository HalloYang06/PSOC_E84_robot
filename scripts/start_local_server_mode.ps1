param(
    [int]$WebPort = 3000,
    [int]$ApiPort = 8010,
    [string]$LanIp = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$apiDir = Join-Path $repoRoot "apps\\api"
$webDir = Join-Path $repoRoot "apps\\web"
$artifactsDir = Join-Path $repoRoot "artifacts"
$statusPath = Join-Path $artifactsDir "local-server-mode-status.json"

function Get-PrimaryLanIp {
    $defaultRoute = Get-NetRoute -DestinationPrefix "0.0.0.0/0" |
        Where-Object { $_.InterfaceAlias -ne "Meta" } |
        Sort-Object RouteMetric, InterfaceMetric |
        Select-Object -First 1
    if (-not $defaultRoute) {
        throw "No default IPv4 route found."
    }
    $ip = Get-NetIPAddress -AddressFamily IPv4 -InterfaceIndex $defaultRoute.ifIndex |
        Where-Object { $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254*" } |
        Select-Object -First 1 -ExpandProperty IPAddress
    if (-not $ip) {
        throw "No usable IPv4 address found on interface $($defaultRoute.InterfaceAlias)."
    }
    return $ip
}

function Ensure-FirewallRule {
    param(
        [string]$Name,
        [int]$Port
    )
    $existing = Get-NetFirewallRule -DisplayName $Name -ErrorAction SilentlyContinue
    if ($existing) {
        Set-NetFirewallRule -DisplayName $Name -Enabled True -Profile Public,Private | Out-Null
        return
    }
    try {
        New-NetFirewallRule `
            -DisplayName $Name `
            -Direction Inbound `
            -Action Allow `
            -Enabled True `
            -Profile Public,Private `
            -Protocol TCP `
            -LocalPort $Port `
            -RemoteAddress LocalSubnet | Out-Null
    } catch {
        Write-Warning "Could not create firewall rule '$Name'. Run this script as administrator to open inbound access."
    }
}

function Stop-PortListeners {
    param([int[]]$Ports)
    $connections = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
        Where-Object { $Ports -contains $_.LocalPort } |
        Select-Object -ExpandProperty OwningProcess -Unique
    foreach ($processId in $connections) {
        if ($processId -and $processId -ne $PID) {
            Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
        }
    }
}

function Wait-HttpOk {
    param(
        [string]$Url,
        [int]$TimeoutSeconds = 120
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 10
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 400) {
                return
            }
        } catch {
            Start-Sleep -Seconds 2
            continue
        }
        Start-Sleep -Seconds 2
    }
    throw "Timed out waiting for $Url"
}

if (-not $LanIp) {
    $LanIp = Get-PrimaryLanIp
}

$webUrl = "http://$LanIp`:$WebPort"
$apiUrl = "http://$LanIp`:$ApiPort"
$internalApiUrl = "http://127.0.0.1:$ApiPort"
$allowedOrigins = "$webUrl,http://127.0.0.1:$WebPort,http://localhost:$WebPort"

New-Item -ItemType Directory -Force -Path $artifactsDir | Out-Null

Stop-PortListeners -Ports @($WebPort, $ApiPort)
Ensure-FirewallRule -Name "AI Collab Platform Web $WebPort" -Port $WebPort
Ensure-FirewallRule -Name "AI Collab Platform API $ApiPort" -Port $ApiPort

$env:INTERNAL_API_BASE_URL = $internalApiUrl
$env:NEXT_PUBLIC_API_BASE_URL = $apiUrl
$env:NEXT_PUBLIC_SUPERTOKENS_API_DOMAIN = $apiUrl
$env:CORS_ALLOWED_ORIGINS = $allowedOrigins

Push-Location $repoRoot
try {
    & npm.cmd run build:web
} finally {
    Pop-Location
}

$apiOut = Join-Path $apiDir "api-lan8010-current.out.log"
$apiErr = Join-Path $apiDir "api-lan8010-current.err.log"
$webOut = Join-Path $webDir "web-lan3000-current.out.log"
$webErr = Join-Path $webDir "web-lan3000-current.err.log"

$apiCommand = @"
`$env:CORS_ALLOWED_ORIGINS = '$allowedOrigins'
Set-Location '$apiDir'
python -m uvicorn app.main:app --host 0.0.0.0 --port $ApiPort
"@
$apiProcess = Start-Process -FilePath "powershell.exe" `
    -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", $apiCommand) `
    -RedirectStandardOutput $apiOut `
    -RedirectStandardError $apiErr `
    -PassThru

$webCommand = @"
`$env:INTERNAL_API_BASE_URL = '$internalApiUrl'
`$env:NEXT_PUBLIC_API_BASE_URL = '$apiUrl'
`$env:NEXT_PUBLIC_SUPERTOKENS_API_DOMAIN = '$apiUrl'
Set-Location '$repoRoot'
& npm.cmd --workspace apps/web run start -- --hostname 0.0.0.0 --port $WebPort
"@
$webProcess = Start-Process -FilePath "powershell.exe" `
    -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", $webCommand) `
    -RedirectStandardOutput $webOut `
    -RedirectStandardError $webErr `
    -PassThru

Wait-HttpOk -Url "http://127.0.0.1:$ApiPort/api/health"
Wait-HttpOk -Url "http://127.0.0.1:$WebPort/login"
Wait-HttpOk -Url "$apiUrl/api/health"
Wait-HttpOk -Url "$webUrl/login"

$status = [ordered]@{
    lan_ip = $LanIp
    web_url = $webUrl
    api_url = $apiUrl
    api_pid = $apiProcess.Id
    web_pid = $webProcess.Id
    firewall_rules = @(
        "AI Collab Platform Web $WebPort",
        "AI Collab Platform API $ApiPort"
    )
    logs = @{
        api_out = $apiOut
        api_err = $apiErr
        web_out = $webOut
        web_err = $webErr
    }
}

$status | ConvertTo-Json -Depth 4 | Set-Content -Path $statusPath -Encoding UTF8
$status | ConvertTo-Json -Depth 4
