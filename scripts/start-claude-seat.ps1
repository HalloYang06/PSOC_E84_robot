param(
  [Parameter(Mandatory = $true)]
  [string]$SeatName,

  [string]$ProjectRoot = "",

  [string]$SessionId = "",

  [string]$Model = "sonnet",

  [string]$RegistryPath = "",

  [switch]$PreviewOnly,

  [switch]$RegisterOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function New-SeatSlug {
  param([string]$Value)
  $normalized = ($Value.ToLowerInvariant() -replace "[^a-z0-9]+", "-").Trim("-")
  if ([string]::IsNullOrWhiteSpace($normalized)) {
    return "claude-seat"
  }
  return $normalized
}

function Load-Registry {
  param([string]$Path)
  if (-not (Test-Path -LiteralPath $Path)) {
    return [ordered]@{
      updated_at = $null
      seats = @()
    }
  }
  $raw = Get-Content -LiteralPath $Path -Raw -Encoding UTF8
  if ([string]::IsNullOrWhiteSpace($raw)) {
    return [ordered]@{
      updated_at = $null
      seats = @()
    }
  }
  $parsed = $raw | ConvertFrom-Json
  $seats = @()
  if ($null -ne $parsed -and $null -ne $parsed.seats) {
    $seats = @($parsed.seats | ForEach-Object {
      [ordered]@{
        seat_name = $_.seat_name
        seat_slug = $_.seat_slug
        provider = $_.provider
        session_id = $_.session_id
        display_name = $_.display_name
        project_root = $_.project_root
        model = $_.model
        launched_at = $_.launched_at
        updated_at = $_.updated_at
      }
    })
  }
  return [ordered]@{
    updated_at = if ($null -ne $parsed) { $parsed.updated_at } else { $null }
    seats = $seats
  }
}

function Save-Registry {
  param(
    [hashtable]$Registry,
    [string]$Path
  )
  $directory = Split-Path -Parent $Path
  if ($directory -and -not (Test-Path -LiteralPath $directory)) {
    New-Item -ItemType Directory -Path $directory -Force | Out-Null
  }
  $Registry | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $Path -Encoding UTF8
}

if (-not $ProjectRoot) {
  $ProjectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
}

if (-not $RegistryPath) {
  $RegistryPath = Join-Path $ProjectRoot "artifacts\\claude-seat-registry.json"
}

if (-not $SessionId) {
  $SessionId = [guid]::NewGuid().ToString()
}

$seatSlug = New-SeatSlug -Value $SeatName
$displayName = "Claude NPC / $SeatName"
$resolvedProjectRoot = (Resolve-Path -LiteralPath $ProjectRoot).Path
$resolvedRegistryPath = $RegistryPath
$command = "Set-Location -LiteralPath '$resolvedProjectRoot'; claude -n ""$displayName"" --session-id $SessionId --model $Model"

$preview = [ordered]@{
  seat_name = $SeatName
  seat_slug = $seatSlug
  provider = "claude"
  session_id = $SessionId
  display_name = $displayName
  project_root = $resolvedProjectRoot
  registry_path = $resolvedRegistryPath
  command = $command
  preview_only = [bool]$PreviewOnly
  register_only = [bool]$RegisterOnly
}

if ($PreviewOnly) {
  $preview | ConvertTo-Json -Depth 5
  exit 0
}

$registry = Load-Registry -Path $resolvedRegistryPath
if (-not @($registry.Keys) -contains "seats" -or $null -eq $registry.seats) {
  $registry.seats = @()
}

$now = [DateTimeOffset]::UtcNow.ToString("o")
$entry = [ordered]@{
  seat_name = $SeatName
  seat_slug = $seatSlug
  provider = "claude"
  session_id = $SessionId
  display_name = $displayName
  project_root = $resolvedProjectRoot
  model = $Model
  launched_at = $now
  updated_at = $now
}

$existing = @(@($registry.seats) | Where-Object {
  ($_["seat_name"] -eq $SeatName) -or ($_["session_id"] -eq $SessionId)
})
$registry.seats = @(@($registry.seats) | Where-Object {
  ($_["seat_name"] -ne $SeatName) -and ($_["session_id"] -ne $SessionId)
}) + @($entry)
$registry.updated_at = $now
Save-Registry -Registry $registry -Path $resolvedRegistryPath

$launched = $false
if (-not $RegisterOnly) {
  # 启动Claude CLI和消息桥接器
  $bridgeScript = Join-Path $PSScriptRoot "claude-seat-message-bridge.ps1"
  $startCommand = @"
Set-Location -LiteralPath '$resolvedProjectRoot'
Write-Host '========================================' -ForegroundColor Cyan
Write-Host 'Claude NPC 席位已启动' -ForegroundColor Green
Write-Host '席位名称: $SeatName' -ForegroundColor Yellow
Write-Host '会话ID: $SessionId' -ForegroundColor Yellow
Write-Host '模型: $Model' -ForegroundColor Yellow
Write-Host '========================================' -ForegroundColor Cyan
Write-Host ''
Write-Host '正在启动消息桥接器...' -ForegroundColor Cyan
Write-Host ''
& '$bridgeScript' -SeatName '$SeatName' -SessionId '$SessionId' -Model '$Model'
"@

  Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-ExecutionPolicy", "Bypass",
    "-Command", $startCommand
  ) | Out-Null
  $launched = $true
}

$result = [ordered]@{
  seat_name = $SeatName
  session_id = $SessionId
  display_name = $displayName
  project_root = $resolvedProjectRoot
  registry_path = $resolvedRegistryPath
  existing_entry_replaced = [bool](@($existing).Count -gt 0)
  launched = $launched
  register_only = [bool]$RegisterOnly
}

$result | ConvertTo-Json -Depth 5
