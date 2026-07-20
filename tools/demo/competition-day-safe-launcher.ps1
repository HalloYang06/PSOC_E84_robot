param(
  [ValidateSet("status", "prepare-backup", "open-cloud", "play-vla", "play-tour", "open-plan")]
  [string]$Action = "status",
  [string]$LegacyRoot = "",
  [string]$BackupDir = "D:\rehab-arm-competition-demo-20260721"
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()

$cloudUrl = "http://106.55.62.122:3001/projects/e201f41c-25a6-46e1-baf8-be6dcb83284c/rehab-arm-control"
$healthUrl = "http://106.55.62.122:8011/health"
$legacyMarker = "scripts\rehab-arm-demo-director.py"
if (-not $LegacyRoot) {
  $LegacyRoot = Get-ChildItem -LiteralPath "D:\" -Directory -ErrorAction SilentlyContinue |
    Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName $legacyMarker) } |
    Select-Object -First 1 -ExpandProperty FullName
}
if (-not $LegacyRoot -or -not (Test-Path -LiteralPath (Join-Path $LegacyRoot $legacyMarker))) {
  throw "Cannot locate the legacy demo workspace. Pass -LegacyRoot with the directory containing $legacyMarker."
}
$vlaVideo = Join-Path $LegacyRoot "docs\screenshots\rehab-arm-demo-director\vla-three-video-sync-review\vla_closed_loop_frame_mapped_v8_platform_L11_A_plus1_clean.mp4"
$tourVideo = Join-Path $LegacyRoot "docs\screenshots\rehab-arm-demo-director\20260707T205146-platform-feature-tour-frames.mp4"
$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$plan = Join-Path $repoRoot "docs\demo\competition-live-demo-plan-20260721.md"
$runCard = Join-Path $repoRoot "docs\demo\competition-day-run-card-20260721.md"

function Test-HttpEndpoint([string]$Uri) {
  try {
    $watch = [Diagnostics.Stopwatch]::StartNew()
    $response = Invoke-WebRequest -UseBasicParsing -Uri $Uri -TimeoutSec 8
    $watch.Stop()
    return [pscustomobject]@{
      Uri = $Uri
      Ok = $response.StatusCode -eq 200
      Status = $response.StatusCode
      LatencyMs = [math]::Round($watch.Elapsed.TotalMilliseconds)
    }
  } catch {
    return [pscustomobject]@{
      Uri = $Uri
      Ok = $false
      Status = "unreachable"
      LatencyMs = $null
    }
  }
}

function Show-Status {
  Write-Host "=== Network addresses ==="
  Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object { $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254.*" } |
    Select-Object InterfaceAlias,IPAddress,PrefixLength |
    Format-Table -AutoSize

  Write-Host "=== Cloud ==="
  Test-HttpEndpoint $healthUrl | Format-Table -AutoSize
  Test-HttpEndpoint $cloudUrl | Format-Table -AutoSize

  Write-Host "=== Offline evidence ==="
  @($vlaVideo, $tourVideo, $plan, $runCard) | ForEach-Object {
    [pscustomobject]@{
      Path = $_
      Exists = Test-Path -LiteralPath $_
      SizeMB = if (Test-Path -LiteralPath $_) { [math]::Round((Get-Item -LiteralPath $_).Length / 1MB, 2) } else { $null }
    }
  } | Format-Table -AutoSize

  $deviceLanReady = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object { $_.IPAddress -like "192.168.3.*" }
  if (-not $deviceLanReady) {
    Write-Warning "This PC is not on 192.168.3.0/24. Device ping failures do not prove that NanoPi or MuJoCo is powered off."
  }
}

switch ($Action) {
  "status" {
    Show-Status
  }
  "prepare-backup" {
    New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null
    Copy-Item -LiteralPath $vlaVideo -Destination (Join-Path $BackupDir "01-vla-closed-loop.mp4") -Force
    Copy-Item -LiteralPath $tourVideo -Destination (Join-Path $BackupDir "02-platform-feature-tour.mp4") -Force
    Copy-Item -LiteralPath $runCard -Destination $BackupDir -Force
    Copy-Item -LiteralPath $plan -Destination $BackupDir -Force
    Write-Host "Backup package ready: $BackupDir"
    Get-ChildItem -LiteralPath $BackupDir | Select-Object Name,Length,LastWriteTime | Format-Table -AutoSize
  }
  "open-cloud" {
    Start-Process $cloudUrl
  }
  "play-vla" {
    Start-Process -FilePath $vlaVideo
  }
  "play-tour" {
    Start-Process -FilePath $tourVideo
  }
  "open-plan" {
    Start-Process -FilePath $plan
  }
}
