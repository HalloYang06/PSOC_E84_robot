param(
  [Parameter(Mandatory = $true)]
  [string]$Server,
  [Parameter(Mandatory = $true)]
  [string]$RunnerId,
  [Parameter(Mandatory = $true)]
  [string]$ProjectId,
  [Parameter(Mandatory = $true)]
  [string]$ComputerNodeId,
  [string]$ThreadId = "codex-mainline",
  [string]$ThreadName = "Codex Mainline",
  [string]$Status = "active",
  [string]$Cwd = "",
  [string]$Model = "gpt-5.4",
  [string]$Description = "Manually registered AI thread on this runner computer",
  [string]$Notes = "Synced from the computer-side agent",
  [string]$AiProviderId = "codex"
)

$ErrorActionPreference = "Stop"
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)

function Sanitize-RunnerText {
  param(
    [AllowNull()]
    [string]$Text
  )

  if ([string]::IsNullOrWhiteSpace($Text)) {
    return ""
  }

  $clean = $Text.Normalize([Text.NormalizationForm]::FormKC)
  $clean = $clean -replace "[\u0000-\u0008\u000B\u000C\u000E-\u001F]", " "
  $clean = $clean -replace "[^\u0020-\uD7FF\uE000-\uFFFD]", ""
  $clean = $clean -replace "\s+", " "
  return $clean.Trim()
}

$cwdForPlatform = if ([string]::IsNullOrWhiteSpace($Cwd)) { $null } else { Sanitize-RunnerText $Cwd }

$body = @{
  project_id = $ProjectId
  computer_node_id = $ComputerNodeId
  workstations = @(
    @{
      workstation_id = Sanitize-RunnerText $ThreadId
      workstation_name = Sanitize-RunnerText $ThreadName
      workstation_status = Sanitize-RunnerText $Status
      cwd = $cwdForPlatform
      model = Sanitize-RunnerText $Model
      description = Sanitize-RunnerText $Description
      notes = Sanitize-RunnerText $Notes
      ai_provider_id = Sanitize-RunnerText $AiProviderId
    }
  )
} | ConvertTo-Json -Depth 8 -Compress

$headers = @{
  "x-runner-id" = $RunnerId
}

function Resolve-ApiBaseUrl {
  param([Parameter(Mandatory = $true)][string]$Value)
  $base = $Value.Trim().TrimEnd("/")
  if ($base -match ":3000$") { return ($base -replace ":3000$", ":8010") }
  if ($base -match ":3001$") { return ($base -replace ":3001$", ":8011") }
  return $base
}

$apiBase = Resolve-ApiBaseUrl $Server
$url = ($apiBase.TrimEnd("/")) + "/api/runners/$RunnerId/thread-workstations/sync"

Write-Host "Syncing runner thread workstations to $url ..."
$utf8Body = [System.Text.Encoding]::UTF8.GetBytes($body)
$response = Invoke-RestMethod -Method Post -Uri $url -Headers $headers -ContentType "application/json; charset=utf-8" -Body $utf8Body
Write-Host "Runner thread workstations synced."
$response | ConvertTo-Json -Depth 8
