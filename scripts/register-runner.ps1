param(
  [Parameter(Mandatory = $true)]
  [string]$Server,
  [Parameter(Mandatory = $true)]
  [string]$PairingToken,
  [Parameter(Mandatory = $true)]
  [string]$ComputerNodeId,
  [Parameter(Mandatory = $true)]
  [string]$RunnerName,
  [string]$RunnerId = "",
  [string[]]$Capabilities = @("codex", "threads", "filesystem"),
  [switch]$HardwareAccess
)

$ErrorActionPreference = "Stop"

if (-not $RunnerId) {
  $RunnerId = "runner-" + ([guid]::NewGuid().ToString("N").Substring(0, 8))
}

$body = @{
  runner_id = $RunnerId
  runner_name = $RunnerName
  capabilities = $Capabilities
  hardware_access = [bool]$HardwareAccess
  computer_node_id = $ComputerNodeId
} | ConvertTo-Json -Depth 5

$headers = @{
  "Content-Type" = "application/json"
  "x-runner-registration-token" = $PairingToken
}

function Resolve-ApiBaseUrl {
  param([Parameter(Mandatory = $true)][string]$Value)
  $base = $Value.Trim().TrimEnd("/")
  if ($base -match ":3000$") { return ($base -replace ":3000$", ":8010") }
  if ($base -match ":3001$") { return ($base -replace ":3001$", ":8011") }
  return $base
}

$apiBase = Resolve-ApiBaseUrl $Server
$url = ($apiBase.TrimEnd("/")) + "/api/runners/register"

Write-Host "Registering runner to $url ..."
$response = Invoke-RestMethod -Method Post -Uri $url -Headers $headers -Body $body
Write-Host "Runner registered."
$response | ConvertTo-Json -Depth 8
