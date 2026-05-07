param(
  [string]$RepoRoot = ""
)

$ErrorActionPreference = "Stop"

if (-not $RepoRoot) {
  $RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}

$logDir = Join-Path $RepoRoot "artifacts"
$logPath = Join-Path $logDir "codex-heartbeat.log"
if (-not (Test-Path -LiteralPath $logDir)) {
  New-Item -ItemType Directory -Path $logDir | Out-Null
}

$stamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
$line = "[{0}] Continue backend chain: computer onboarding, thread scan, AI seats, command receipts. Remove temporary validation leftovers after verification." -f $stamp
Add-Content -LiteralPath $logPath -Value $line -Encoding UTF8
