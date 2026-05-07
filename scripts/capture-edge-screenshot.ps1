param(
  [Parameter(Mandatory = $true)]
  [string]$Url,
  [Parameter(Mandatory = $true)]
  [string]$Output,
  [string]$HtmlDump = "",
  [string]$TextDump = "",
  [string]$Markers = "",
  [int]$ViewportWidth = 1680,
  [int]$ViewportHeight = 1260,
  [int]$VirtualTimeBudget = 12000,
  [int]$MaxWaitSeconds = 15
)

$ErrorActionPreference = "Stop"

function Get-EdgePath {
  $paths = @(
    "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "C:\Program Files\Microsoft\Edge\Application\msedge.exe"
  )
  foreach ($path in $paths) {
    if (Test-Path $path) {
      return $path
    }
  }
  throw "Microsoft Edge not found"
}

New-Item -ItemType Directory -Force -Path ([System.IO.Path]::GetDirectoryName($Output)) | Out-Null
if ($HtmlDump) {
  New-Item -ItemType Directory -Force -Path ([System.IO.Path]::GetDirectoryName($HtmlDump)) | Out-Null
}
if ($TextDump) {
  New-Item -ItemType Directory -Force -Path ([System.IO.Path]::GetDirectoryName($TextDump)) | Out-Null
}

$html = (Invoke-WebRequest -Uri $Url -UseBasicParsing).Content
if ($HtmlDump) {
  [System.IO.File]::WriteAllText($HtmlDump, $html, [System.Text.Encoding]::UTF8)
}
if ($TextDump) {
  $text = [System.Text.RegularExpressions.Regex]::Replace($html, "<script[\s\S]*?</script>", " ", "IgnoreCase")
  $text = [System.Text.RegularExpressions.Regex]::Replace($text, "<style[\s\S]*?</style>", " ", "IgnoreCase")
  $text = [System.Text.RegularExpressions.Regex]::Replace($text, "<[^>]+>", " ")
  [System.IO.File]::WriteAllText($TextDump, $text, [System.Text.Encoding]::UTF8)
}
if ($Markers) {
  $missing = @()
  foreach ($marker in ($Markers -split "\|")) {
    $trimmed = $marker.Trim()
    if ($trimmed -and -not $html.Contains($trimmed)) {
      $missing += $trimmed
    }
  }
  if ($missing.Count -gt 0) {
    throw "Markers not found: $($missing -join ', ')"
  }
}

$edge = Get-EdgePath
$userDataDir = Join-Path $env:TEMP ("codex-edge-capture-" + [System.Guid]::NewGuid().ToString("N"))
$tempScreenshot = Join-Path $env:TEMP ("codex-edge-shot-" + [System.Guid]::NewGuid().ToString("N") + ".png")
New-Item -ItemType Directory -Force -Path $userDataDir | Out-Null
Remove-Item $Output -Force -ErrorAction SilentlyContinue
Remove-Item $tempScreenshot -Force -ErrorAction SilentlyContinue

$arguments = @(
  "--headless=new",
  "--disable-gpu",
  "--no-first-run",
  "--no-default-browser-check",
  "--user-data-dir=$userDataDir",
  "--window-size=$ViewportWidth,$ViewportHeight",
  "--virtual-time-budget=$VirtualTimeBudget",
  "--screenshot=$tempScreenshot",
  $Url
)

$process = Start-Process -FilePath $edge -ArgumentList $arguments -PassThru
try {
  $deadline = (Get-Date).AddSeconds($MaxWaitSeconds)
  while ((Get-Date) -lt $deadline) {
    if (Test-Path $tempScreenshot) {
      break
    }
    if ($process.HasExited) {
      break
    }
    Start-Sleep -Milliseconds 500
    try {
      $process.Refresh()
    } catch {
    }
  }
  if (-not (Test-Path $tempScreenshot)) {
    if (-not $process.HasExited) {
      Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
    }
    throw "Screenshot was not created within $MaxWaitSeconds seconds"
  }
} finally {
  if (-not $process.HasExited) {
    Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
  }
  Remove-Item $userDataDir -Recurse -Force -ErrorAction SilentlyContinue
}

Copy-Item -Path $tempScreenshot -Destination $Output -Force
Remove-Item $tempScreenshot -Force -ErrorAction SilentlyContinue

Write-Output $Output
