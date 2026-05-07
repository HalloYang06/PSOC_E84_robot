Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$statusPath = Join-Path $repoRoot "artifacts\\local-server-mode-status.json"

if (-not (Test-Path $statusPath)) {
    Write-Output "No local server mode status file found."
    exit 0
}

$status = Get-Content -Path $statusPath -Raw | ConvertFrom-Json

foreach ($processId in @($status.api_pid, $status.web_pid)) {
    if ($processId) {
        Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
    }
}

Remove-Item -LiteralPath $statusPath -Force
Write-Output "Stopped local server mode."
