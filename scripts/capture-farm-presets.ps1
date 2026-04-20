$ErrorActionPreference = "Stop"

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$baseUrl = "http://127.0.0.1:3070/harvest-moon-phaser3-game/index.html"
$repoRoot = Split-Path -Parent $PSScriptRoot
$artifactsDir = Join-Path $repoRoot "artifacts"
if (-not (Test-Path -LiteralPath $artifactsDir)) {
  New-Item -ItemType Directory -Path $artifactsDir | Out-Null
}

$presets = @(
  @{ name = "farm-home-outer"; scene = "map-farm"; x = 680; y = 1730; note = "home outer" },
  @{ name = "farm-requirements"; scene = "map-farm"; x = 1240; y = 1320; note = "requirements sign" },
  @{ name = "farm-ai"; scene = "map-farm"; x = 1083; y = 1838; note = "ai statue" },
  @{ name = "farm-tasks"; scene = "map-farm"; x = 2060; y = 1840; note = "task field" },
  @{ name = "farm-computers-outer"; scene = "map-farm"; x = 1600; y = 1715; note = "cowshed outer" },
  @{ name = "farm-chat-outer"; scene = "map-farm"; x = 2230; y = 1720; note = "coop outer" },
  @{ name = "farm-delivery-outer"; scene = "map-farm"; x = 2088; y = 2450; note = "toolshed outer" },
  @{ name = "farm-approvals"; scene = "map-farm"; x = 80; y = 2200; note = "left exit" },
  @{ name = "home-room"; scene = "map-home"; x = 1030; y = 520; note = "home room" },
  @{ name = "cowshed-room"; scene = "map-cowshed"; x = 930; y = 980; note = "cowshed room" },
  @{ name = "coop-room"; scene = "map-coop"; x = 860; y = 560; note = "coop room" },
  @{ name = "toolshed-room"; scene = "map-toolshed"; x = 640; y = 640; note = "toolshed room" }
)

function Capture-Screen {
  param([string]$Path)

  if (Test-Path -LiteralPath $Path) {
    Remove-Item -LiteralPath $Path -Force
  }

  $bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
  $bmp = New-Object System.Drawing.Bitmap $bounds.Width, $bounds.Height
  $graphics = [System.Drawing.Graphics]::FromImage($bmp)
  $graphics.CopyFromScreen($bounds.Location, [System.Drawing.Point]::Empty, $bounds.Size)
  $tempPath = Join-Path $env:TEMP ([System.IO.Path]::GetFileName($Path))
  if (Test-Path -LiteralPath $tempPath) {
    Remove-Item -LiteralPath $tempPath -Force
  }
  $bmp.Save($tempPath, [System.Drawing.Imaging.ImageFormat]::Png)
  $graphics.Dispose()
  $bmp.Dispose()
  Copy-Item -LiteralPath $tempPath -Destination $Path -Force
  Remove-Item -LiteralPath $tempPath -Force
}

foreach ($preset in $presets) {
  $url = "{0}?scene={1}&x={2}&y={3}" -f $baseUrl, $preset.scene, $preset.x, $preset.y
  Start-Process $url
  Start-Sleep -Seconds 4

  $ws = New-Object -ComObject WScript.Shell
  $null = $ws.AppActivate("Harvest Moon")
  Start-Sleep -Milliseconds 500

  $path = Join-Path $artifactsDir ($preset.name + ".png")
  Capture-Screen -Path $path
  Write-Output "$($preset.name)`t$($preset.note)`t$path"
}
