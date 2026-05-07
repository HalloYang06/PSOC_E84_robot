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

$url = ($Server.TrimEnd("/")) + "/api/runners/register"

Write-Host "Registering runner to $url ..."
$response = Invoke-RestMethod -Method Post -Uri $url -Headers $headers -Body $body
Write-Host "Runner registered."
$response | ConvertTo-Json -Depth 8
