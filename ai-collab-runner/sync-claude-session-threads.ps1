param(
  [Parameter(Mandatory = $true)]
  [string]$Server,
  [Parameter(Mandatory = $true)]
  [string]$RunnerId,
  [Parameter(Mandatory = $true)]
  [string]$ProjectId,
  [Parameter(Mandatory = $true)]
  [string]$ComputerNodeId,
  [string]$ClaudeHome = "",
  [string]$WorkspaceRoot = "",
  [int]$Take = 12,
  [int]$MaxAgeHours = 24,
  [string]$Model = "sonnet"
)

$ErrorActionPreference = "Stop"
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)

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

function Normalize-ComparablePath {
  param([AllowNull()][string]$Value)
  return (Sanitize-SessionText $Value).Replace("\", "/").ToLowerInvariant()
}

function Convert-EpochMillisToUtc {
  param([AllowNull()]$Value)
  try {
    $millis = [double]$Value
  } catch {
    return $null
  }
  if ($millis -le 0) {
    return $null
  }
  try {
    return [DateTimeOffset]::FromUnixTimeMilliseconds([int64]$millis).UtcDateTime
  } catch {
    return $null
  }
}

function Parse-AnyDateUtc {
  param([AllowNull()][string]$Value)
  if ([string]::IsNullOrWhiteSpace($Value)) {
    return $null
  }
  try {
    return ([DateTimeOffset]::Parse($Value)).UtcDateTime
  } catch {
    return $null
  }
}

function Test-ProcessAlive {
  param([AllowNull()]$ProcessId)
  try {
    $pidNumber = [int]$ProcessId
  } catch {
    return $false
  }
  if ($pidNumber -le 0) {
    return $false
  }
  return [bool](Get-Process -Id $pidNumber -ErrorAction SilentlyContinue)
}

function Extract-MessageText {
  param([AllowNull()]$Message)
  if ($null -eq $Message) {
    return ""
  }
  if ($Message -is [string]) {
    return Sanitize-SessionText $Message
  }
  $content = $Message.content
  if ($content -is [string]) {
    return Sanitize-SessionText $content
  }
  if ($content -is [System.Collections.IEnumerable]) {
    $parts = @()
    foreach ($item in $content) {
      if ($item -is [string]) {
        $parts += $item
      } elseif ($item.type -eq "text") {
        $parts += [string]$item.text
      }
    }
    return Sanitize-SessionText ($parts -join " ")
  }
  return ""
}

function Add-Or-MergeSession {
  param(
    [hashtable]$Map,
    [hashtable]$Session
  )
  $sessionId = [string]$Session.session_id
  if (-not $sessionId) {
    return
  }
  if (-not $Map.ContainsKey($sessionId)) {
    $Map[$sessionId] = $Session
    return
  }
  $existing = $Map[$sessionId]
  $existingTime = Parse-AnyDateUtc $existing.last_activity_at
  $nextTime = Parse-AnyDateUtc $Session.last_activity_at
  if ($nextTime -and ((-not $existingTime) -or $nextTime -gt $existingTime)) {
    foreach ($key in $Session.Keys) {
      if ($Session[$key]) {
        $existing[$key] = $Session[$key]
      }
    }
  } else {
    if ($Session.live_process_seen) {
      $existing.live_process_seen = $true
    }
    if (-not $existing.source_file -and $Session.source_file) {
      $existing.source_file = $Session.source_file
    }
  }
}

if (-not $ClaudeHome) {
  $ClaudeHome = if ($env:CLAUDE_HOME) { $env:CLAUDE_HOME } else { Join-Path $env:USERPROFILE ".claude" }
}
if (-not $WorkspaceRoot) {
  $WorkspaceRoot = (Get-Location).Path
}

$workspaceComparable = Normalize-ComparablePath $WorkspaceRoot
$claudeRoot = Resolve-Path -LiteralPath $ClaudeHome -ErrorAction SilentlyContinue
if (-not $claudeRoot) {
  throw "Claude home not found: $ClaudeHome"
}

$now = (Get-Date).ToUniversalTime()
$cutoff = $now.AddHours(-1 * [Math]::Abs($MaxAgeHours))
$sessions = @{}

$liveSessionsRoot = Join-Path $claudeRoot.Path "sessions"
if (Test-Path -LiteralPath $liveSessionsRoot) {
  Get-ChildItem -LiteralPath $liveSessionsRoot -Filter "*.json" -File -ErrorAction SilentlyContinue |
    ForEach-Object {
      try {
        $payload = Get-Content -LiteralPath $_.FullName -Raw -Encoding UTF8 | ConvertFrom-Json
      } catch {
        return
      }
      $sessionId = Sanitize-SessionText ([string]$payload.sessionId)
      $cwd = Sanitize-SessionText ([string]$payload.cwd)
      if (-not $sessionId -or -not $cwd) {
        return
      }
      if ($workspaceComparable -and -not ((Normalize-ComparablePath $cwd).Contains($workspaceComparable))) {
        return
      }
      $startedAt = Convert-EpochMillisToUtc $payload.startedAt
      $alive = Test-ProcessAlive $payload.pid
      $recentExit = $startedAt -and $startedAt -gt $cutoff
      if (-not $alive -and -not $recentExit) {
        return
      }
      Add-Or-MergeSession $sessions @{
        session_id = $sessionId
        cwd = $cwd
        last_activity_at = if ($startedAt) { $startedAt.ToString("o") } else { "" }
        source_kind = "live_session_file"
        source_file = $_.FullName
        project_slug = "(live-session)"
        live_process_seen = $alive
        latest_user_message = ""
        latest_assistant_message = ""
      }
    }
}

$projectsRoot = Join-Path $claudeRoot.Path "projects"
if (Test-Path -LiteralPath $projectsRoot) {
  Get-ChildItem -LiteralPath $projectsRoot -Filter "*.jsonl" -File -Recurse -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 80 |
    ForEach-Object {
      $sessionId = ""
      $cwd = ""
      $gitBranch = ""
      $latestAt = $null
      $latestUser = ""
      $latestAssistant = ""
      try {
        $lines = Get-Content -LiteralPath $_.FullName -Encoding UTF8 -Tail 500
      } catch {
        return
      }
      foreach ($line in $lines) {
        if ([string]::IsNullOrWhiteSpace($line)) {
          continue
        }
        try {
          $item = $line | ConvertFrom-Json
        } catch {
          continue
        }
        if ($null -ne $item.sessionId) {
          $sessionId = Sanitize-SessionText ([string]$item.sessionId)
        }
        if ($null -ne $item.cwd) {
          $cwd = Sanitize-SessionText ([string]$item.cwd)
        }
        if ($null -ne $item.gitBranch) {
          $gitBranch = Sanitize-SessionText ([string]$item.gitBranch)
        }
        $timestamp = Parse-AnyDateUtc ([string]$item.timestamp)
        if ($timestamp -and ((-not $latestAt) -or $timestamp -gt $latestAt)) {
          $latestAt = $timestamp
        }
        if ($item.type -eq "user") {
          $latestUser = Extract-MessageText $item.message
        } elseif ($item.type -eq "assistant") {
          $latestAssistant = Extract-MessageText $item.message
        }
      }
      if (-not $sessionId -or -not $cwd) {
        return
      }
      if ($workspaceComparable -and -not ((Normalize-ComparablePath $cwd).Contains($workspaceComparable))) {
        return
      }
      if ($latestAt -and $latestAt -lt $cutoff) {
        return
      }
      Add-Or-MergeSession $sessions @{
        session_id = $sessionId
        cwd = $cwd
        git_branch = $gitBranch
        last_activity_at = if ($latestAt) { $latestAt.ToString("o") } else { "" }
        source_kind = "project_jsonl"
        source_file = $_.FullName
        project_slug = $_.Directory.Name
        live_process_seen = $false
        latest_user_message = $latestUser
        latest_assistant_message = $latestAssistant
      }
    }
}

$sessionRows = @($sessions.Values) |
  Sort-Object { Parse-AnyDateUtc $_.last_activity_at } -Descending |
  Select-Object -First $Take

if (-not $sessionRows.Count) {
  throw "No live Claude sessions found for workspace $WorkspaceRoot"
}

$workstations = @()
foreach ($session in $sessionRows) {
  $sessionId = Sanitize-SessionText ([string]$session.session_id)
  if (-not $sessionId) {
    continue
  }
  $sessionCwdComparable = Normalize-ComparablePath ([string]$session.cwd)
  $rawProjectSlug = Sanitize-SessionText ([string]$session.project_slug)
  $namePart = if ($rawProjectSlug -eq "(live-session)") {
    "(live-session)"
  } elseif ($workspaceComparable -and $sessionCwdComparable.Contains($workspaceComparable)) {
    "current-workspace"
  } elseif ($rawProjectSlug) {
    $rawProjectSlug
  } else {
    $sessionId.Substring(0, [Math]::Min(8, $sessionId.Length))
  }
  $status = if ($session.live_process_seen) { "active" } else { "open" }
  $workstations += @{
    workstation_id = "claude-session-$sessionId"
    workstation_name = "Claude / $namePart"
    workstation_status = $status
    cwd = Sanitize-SessionText ([string]$session.cwd)
    model = Sanitize-SessionText $Model
    description = "Synced from local Claude Code session files"
    notes = Sanitize-SessionText ("last_activity_at=$($session.last_activity_at); source=$($session.source_kind)")
    ai_provider_id = "claude"
    ai_provider_label = "Claude"
    skill_loadout = @(
      "github-repo-bootstrap",
      "ai-collab-productizer",
      "continuous-orchestrator",
      "handoff-path-output",
      "verify-before-claim",
      "thread-bridge-writeback"
    )
    metadata = @{
      source = "runner_claude_session_scan"
      connection_kind = "local"
      provider_family = "claude"
      session_id = $sessionId
      workspace_root = Sanitize-SessionText $WorkspaceRoot
      live_process_seen = [bool]$session.live_process_seen
      source_file = Sanitize-SessionText ([string]$session.source_file)
      source_kind = Sanitize-SessionText ([string]$session.source_kind)
    }
  }
}

if (-not $workstations.Count) {
  throw "No Claude sessions could be converted into platform workstations"
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

Write-Host "Syncing $($workstations.Count) Claude session threads to $url ..."
$utf8Body = [System.Text.Encoding]::UTF8.GetBytes($body)
$response = Invoke-RestMethod -Method Post -Uri $url -Headers $headers -ContentType "application/json; charset=utf-8" -Body $utf8Body
Write-Host "Claude session threads synced."
$response | ConvertTo-Json -Depth 8
