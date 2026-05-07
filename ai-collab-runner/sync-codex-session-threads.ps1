param(
  [Parameter(Mandatory = $true)]
  [string]$Server,
  [Parameter(Mandatory = $true)]
  [string]$RunnerId,
  [Parameter(Mandatory = $true)]
  [string]$ProjectId,
  [Parameter(Mandatory = $true)]
  [string]$ComputerNodeId,
  [string]$SessionIndexPath = "",
  [int]$Take = 12,
  [int]$MaxAgeDays = 14,
  [string]$WorkspaceRoot = "",
  [string]$AiProviderId = "codex",
  [string]$AiProviderLabel = "Codex",
  [string]$Model = "gpt-5.4"
)

$ErrorActionPreference = "Stop"
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)

if ([string]::IsNullOrWhiteSpace($SessionIndexPath)) {
  $codexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $env:USERPROFILE ".codex" }
  $SessionIndexPath = Join-Path $codexHome "session_index.jsonl"
}

if ([string]::IsNullOrWhiteSpace($SessionIndexPath)) {
  throw "Could not resolve Codex session index. Pass -SessionIndexPath or set CODEX_HOME / USERPROFILE."
}

if (-not (Test-Path -LiteralPath $SessionIndexPath)) {
  throw "Session index not found: $SessionIndexPath"
}

function Sanitize-SessionText {
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

$cutoff = (Get-Date).ToUniversalTime().AddDays(-1 * [Math]::Abs($MaxAgeDays))
$seenIds = @{}
$rows = @()

Get-Content -LiteralPath $SessionIndexPath -Encoding UTF8 |
  Where-Object { $_.Trim() } |
  ForEach-Object {
    try {
      $_ | ConvertFrom-Json
    } catch {
      $null
    }
  } |
  Where-Object { $_ -and $_.id } |
  Sort-Object { [datetime]($_.updated_at) } -Descending |
  ForEach-Object {
    $sessionId = [string]$_.id
    if ($seenIds.ContainsKey($sessionId)) {
      return
    }
    $updatedAt = [datetime]$_.updated_at
    if ($updatedAt.ToUniversalTime() -lt $cutoff) {
      return
    }
    $seenIds[$sessionId] = $true
    $rows += $_
  }

if ($rows.Count -gt $Take) {
  $rows = $rows | Select-Object -First $Take
}

if (-not $WorkspaceRoot) {
  $scriptRepoRoot = $null
  if (-not [string]::IsNullOrWhiteSpace($PSScriptRoot)) {
    $scriptRepoRoot = Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..") -ErrorAction SilentlyContinue
  }
  if ($scriptRepoRoot) {
    $WorkspaceRoot = $scriptRepoRoot.Path
  } else {
    $WorkspaceRoot = (Resolve-Path ".").Path
  }
}

if ([string]::IsNullOrWhiteSpace($WorkspaceRoot)) {
  throw "Could not resolve workspace root. Pass -WorkspaceRoot from the target computer."
}

$repoRoot = (Resolve-Path -LiteralPath $WorkspaceRoot).Path
$defaultSkillLoadout = @(
  "github-repo-bootstrap",
  "ai-collab-productizer",
  "continuous-orchestrator",
  "handoff-path-output",
  "verify-before-claim"
)
$workstations = @()
foreach ($row in $rows) {
  $sessionId = [string]$row.id
  $name = Sanitize-SessionText ([string]$row.thread_name)
  if (-not $name) {
    $name = "Codex Session $($sessionId.Substring(0, [Math]::Min(8, $sessionId.Length)))"
  }

  $workstations += @{
    workstation_id = "codex-session-$sessionId"
    workstation_name = $name
    workstation_status = "active"
    cwd = $repoRoot
    model = Sanitize-SessionText $Model
    description = "Synced from local Codex session index"
    notes = Sanitize-SessionText ("updated_at=$($row.updated_at)")
    ai_provider_id = Sanitize-SessionText $AiProviderId
    ai_provider_label = Sanitize-SessionText $AiProviderLabel
    skill_loadout = $defaultSkillLoadout
    metadata = @{
      connection_kind = "local"
      provider_family = Sanitize-SessionText $AiProviderId
      workspace_root = $repoRoot
    }
  }
}

if (-not $workstations.Count) {
  throw "No recent Codex sessions found in $SessionIndexPath within the last $MaxAgeDays day(s)"
}

$body = @{
  project_id = $ProjectId
  computer_node_id = $ComputerNodeId
  workstations = $workstations
} | ConvertTo-Json -Depth 8 -Compress

$headers = @{
  "x-runner-id" = $RunnerId
}

$url = ($Server.TrimEnd("/")) + "/api/runners/$RunnerId/thread-workstations/sync"

Write-Host "Syncing $($workstations.Count) Codex session threads to $url ..."
$utf8Body = [System.Text.Encoding]::UTF8.GetBytes($body)
$response = Invoke-RestMethod -Method Post -Uri $url -Headers $headers -ContentType "application/json; charset=utf-8" -Body $utf8Body
Write-Host "Codex session threads synced."
$response | ConvertTo-Json -Depth 8
