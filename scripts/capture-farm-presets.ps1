param(
  [string[]]$Names = @(),
  [int]$WaitMs = 6500
)

$ErrorActionPreference = "Stop"

$baseUrl = "http://127.0.0.1:3070/harvest-moon-phaser3-game/index.html"
$repoRoot = Split-Path -Parent $PSScriptRoot
$artifactsDir = Join-Path $repoRoot "artifacts"
if (-not (Test-Path -LiteralPath $artifactsDir)) {
  New-Item -ItemType Directory -Path $artifactsDir | Out-Null
}

$viewport = "1440,900"
$waitMs = $WaitMs

$presets = @(
  @{ name = "farm-project"; scene = "map-farm"; x = 680; y = 1730; focus = "project"; note = "project homebase" },
  @{ name = "farm-home-outer"; scene = "map-farm"; x = 680; y = 1730; note = "home outer" },
  @{ name = "farm-requirements"; scene = "map-farm"; x = 1240; y = 1320; note = "requirements sign" },
  @{ name = "farm-ai"; scene = "map-farm"; x = 1083; y = 1838; note = "ai statue" },
  @{ name = "farm-tasks"; scene = "map-farm"; x = 2060; y = 1840; note = "task field" },
  @{ name = "farm-computers-outer"; scene = "map-farm"; x = 1600; y = 1715; note = "cowshed outer" },
  @{ name = "farm-chat-outer-focus"; scene = "map-farm"; x = 2230; y = 1720; focus = "chat"; note = "chat courtyard" },
  @{ name = "farm-chat-outer"; scene = "map-farm"; x = 2230; y = 1720; note = "coop outer" },
  @{ name = "farm-delivery-outer-focus"; scene = "map-farm"; x = 2088; y = 2450; focus = "delivery"; note = "delivery workshop outer" },
  @{ name = "farm-delivery-outer"; scene = "map-farm"; x = 2088; y = 2450; note = "toolshed outer" },
  @{ name = "farm-approvals"; scene = "map-farm"; x = 80; y = 2200; note = "left exit" },
  @{ name = "home-room"; scene = "map-home"; x = 1030; y = 520; note = "home room" },
  @{ name = "cowshed-room"; scene = "map-cowshed"; x = 930; y = 980; note = "cowshed room" },
  @{ name = "coop-room"; scene = "map-coop"; x = 860; y = 560; note = "coop room" },
  @{ name = "toolshed-room"; scene = "map-toolshed"; x = 640; y = 640; note = "toolshed room" }
)

$selectedPresets = if ($Names -and $Names.Count -gt 0) {
  $presets | Where-Object { $Names -contains $_.name }
} else {
  $presets
}

foreach ($preset in $selectedPresets) {
  $url = "{0}?autostart=1&scene={1}&x={2}&y={3}" -f $baseUrl, $preset.scene, $preset.x, $preset.y
  if ($preset.ContainsKey("focus") -and $preset.focus) {
    $url += "&focus=" + $preset.focus
  }
  $path = Join-Path $artifactsDir ($preset.name + ".png")

  if (Test-Path -LiteralPath $path) {
    Remove-Item -LiteralPath $path -Force
  }

  $command = 'npx playwright screenshot --browser chromium --viewport-size ' + $viewport + ' --wait-for-timeout ' + $waitMs + ' --timeout 30000 "' + $url + '" "' + $path + '"'
  cmd /c $command

  if (-not (Test-Path -LiteralPath $path)) {
    throw "截图失败: $($preset.name)"
  }

  Write-Output "$($preset.name)`t$($preset.note)`t$path"
}
