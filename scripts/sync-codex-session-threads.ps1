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
  [string]$Model = "gpt-5.4",
  [switch]$DryRun
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

function Normalize-Slug {
  param([AllowNull()][string]$Value)
  $raw = (Sanitize-SessionText $Value).ToLowerInvariant()
  $slug = $raw -replace "[^a-z0-9]+", "-"
  $slug = $slug.Trim("-")
  if ($slug) { return $slug }
  return "computer"
}

function Test-CodexDesktopProcess {
  try {
    $process = Get-CimInstance Win32_Process -ErrorAction Stop |
      Where-Object { $_.Name -eq "Codex.exe" -and $_.CommandLine -notmatch "--type=" } |
      Select-Object -First 1
    return [bool]$process
  } catch {
    return $false
  }
}

function Get-CodexDesktopBridgeMetadata {
  $desktopProcessDetected = Test-CodexDesktopProcess
  $desktopUiAutomationAvailable = $false
  if ($desktopProcessDetected) {
    try {
      Add-Type -AssemblyName System.Windows.Forms -ErrorAction Stop
      $desktopUiAutomationAvailable = [Environment]::UserInteractive
    } catch {
      $desktopUiAutomationAvailable = $false
    }
  }
  return @{
    codex_desktop_process_detected = [bool]$desktopProcessDetected
    desktop_process_detected = [bool]$desktopProcessDetected
    codex_desktop_bridge_connected = [bool]$desktopUiAutomationAvailable
    desktop_bridge_connected = [bool]$desktopUiAutomationAvailable
    desktop_bridge_label = if ($desktopUiAutomationAvailable) { "Codex Desktop UI automation" } else { $null }
    desktop_bridge_note = if ($desktopUiAutomationAvailable) {
      "Runner can open codex://threads/<id> on this interactive desktop and send a single prompt through the Codex Desktop UI. No Codex config is changed."
    } else {
      "Codex Desktop app-server is managed by the local desktop process; this runner has not detected an interactive desktop UI input bridge."
    }
    desktop_delivery_mode = if ($desktopUiAutomationAvailable) { "codex_desktop_ui" } else { $null }
  }
}

function Add-UniquePath {
  param(
    [System.Collections.ArrayList]$Paths,
    [AllowNull()][string]$Value
  )
  $clean = Sanitize-SessionText $Value
  if (-not $clean) { return }
  if (-not ($Paths -contains $clean)) {
    [void]$Paths.Add($clean)
  }
}

function Add-UniqueDirectory {
  param(
    [System.Collections.ArrayList]$Paths,
    [AllowNull()][string]$Value
  )
  $clean = Sanitize-SessionText $Value
  if (-not $clean) { return }
  $resolved = Resolve-Path -LiteralPath $clean -ErrorAction SilentlyContinue
  if ($resolved) {
    $clean = $resolved.Path
  }
  if (-not ($Paths -contains $clean)) {
    [void]$Paths.Add($clean)
  }
}

function Add-CodexHomeCandidates {
  param([System.Collections.ArrayList]$Homes)

  if ($env:CODEX_HOME) { Add-UniqueDirectory $Homes $env:CODEX_HOME }
  if ($env:USERPROFILE) {
    Add-UniqueDirectory $Homes (Join-Path $env:USERPROFILE ".codex")
    Add-UniqueDirectory $Homes (Join-Path (Join-Path $env:USERPROFILE "AppData\Roaming") "Codex")
    Add-UniqueDirectory $Homes (Join-Path (Join-Path $env:USERPROFILE "AppData\Roaming") "OpenAI\Codex")
    Add-UniqueDirectory $Homes (Join-Path (Join-Path $env:USERPROFILE "AppData\Local") "Codex")
    Add-UniqueDirectory $Homes (Join-Path (Join-Path $env:USERPROFILE "AppData\Local") "OpenAI\Codex")
  }
  if ($HOME) { Add-UniqueDirectory $Homes (Join-Path $HOME ".codex") }
  if ($env:APPDATA) {
    Add-UniqueDirectory $Homes (Join-Path $env:APPDATA "Codex")
    Add-UniqueDirectory $Homes (Join-Path $env:APPDATA "OpenAI\Codex")
  }
  if ($env:LOCALAPPDATA) {
    Add-UniqueDirectory $Homes (Join-Path $env:LOCALAPPDATA "Codex")
    Add-UniqueDirectory $Homes (Join-Path $env:LOCALAPPDATA "OpenAI\Codex")
  }

  $usersRoot = Join-Path $env:SystemDrive "Users"
  if (Test-Path -LiteralPath $usersRoot) {
    Get-ChildItem -LiteralPath $usersRoot -Directory -ErrorAction SilentlyContinue | ForEach-Object {
      Add-UniqueDirectory $Homes (Join-Path $_.FullName ".codex")
      Add-UniqueDirectory $Homes (Join-Path (Join-Path $_.FullName "AppData\Roaming") "Codex")
      Add-UniqueDirectory $Homes (Join-Path (Join-Path $_.FullName "AppData\Roaming") "OpenAI\Codex")
      Add-UniqueDirectory $Homes (Join-Path (Join-Path $_.FullName "AppData\Local") "Codex")
      Add-UniqueDirectory $Homes (Join-Path (Join-Path $_.FullName "AppData\Local") "OpenAI\Codex")
    }
  }
}

function Resolve-CodexSessionIndexPath {
  param([AllowNull()][string]$ExplicitPath)

  $candidates = [System.Collections.ArrayList]::new()
  $explicit = Sanitize-SessionText $ExplicitPath
  if ($explicit) {
    Add-UniquePath $candidates $explicit
  } else {
    $homes = [System.Collections.ArrayList]::new()
    Add-CodexHomeCandidates $homes
    foreach ($homeDir in $homes) {
      Add-UniquePath $candidates (Join-Path $homeDir "session_index.jsonl")
    }
  }

  $existing = @()
  foreach ($candidate in $candidates) {
    if (Test-Path -LiteralPath $candidate) {
      $file = Get-Item -LiteralPath $candidate -ErrorAction SilentlyContinue
      if ($file) { $existing += $file }
    }
  }

  $selected = $existing | Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1
  return [ordered]@{
    path = if ($selected) { $selected.FullName } else { "" }
    checked = @($candidates)
  }
}

function Resolve-CodexSessionDirectories {
  param([AllowNull()][string]$ExplicitIndexPath)

  $directories = [System.Collections.ArrayList]::new()
  $explicit = Sanitize-SessionText $ExplicitIndexPath
  if ($explicit) {
    $parent = Split-Path -Parent $explicit
    if ($parent) {
      Add-UniqueDirectory $directories (Join-Path $parent "sessions")
    }
  }

  $homes = [System.Collections.ArrayList]::new()
  Add-CodexHomeCandidates $homes
  foreach ($homeDir in $homes) {
    Add-UniqueDirectory $directories (Join-Path $homeDir "sessions")
    Add-UniqueDirectory $directories (Join-Path $homeDir "Sessions")
  }

  return @($directories)
}

function Session-IdFromFile {
  param([System.IO.FileInfo]$File)
  $name = [string]$File.BaseName
  if ($name -match "([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})$") {
    return $Matches[1].ToLowerInvariant()
  }
  $hashInput = $File.FullName.ToLowerInvariant()
  $sha = [System.Security.Cryptography.SHA256]::Create()
  try {
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($hashInput)
    $hash = ($sha.ComputeHash($bytes) | ForEach-Object { $_.ToString("x2") }) -join ""
    return $hash.Substring(0, 32)
  } finally {
    $sha.Dispose()
  }
}

function Short-SessionTitle {
  param(
    [AllowNull()][string]$Value,
    [int]$MaxLength = 48
  )
  $clean = Sanitize-SessionText $Value
  if (-not $clean) { return "" }
  $clean = $clean -replace "^\s*#+\s*", ""
  $clean = $clean -replace "\[([^\]]+)\]\([^)]+\)", '$1'
  $clean = $clean -replace "https?://\S+", ""
  $clean = $clean -replace "\s+", " "
  $clean = $clean.Trim(" -:`t`r`n")
  if (-not $clean) { return "" }
  if ($clean.Length -gt $MaxLength) {
    return ($clean.Substring(0, $MaxLength).Trim() + "...")
  }
  return $clean
}

function Test-PlatformProbeSession {
  param(
    [AllowNull()][string]$Title,
    [AllowNull()][string]$SourceFile
  )
  $cleanTitle = Sanitize-SessionText $Title
  if ($cleanTitle -match "AI_COLLAB_DESKTOP_BRIDGE_PROBE") { return $true }
  if ($cleanTitle -match "平台桌面投递连通性测试") { return $true }

  $filePath = Sanitize-SessionText $SourceFile
  if ($filePath -and (Test-Path -LiteralPath $filePath)) {
    try {
      $head = (Get-Content -LiteralPath $filePath -Encoding UTF8 -TotalCount 80 -ErrorAction SilentlyContinue) -join "`n"
      if ($head -match "AI_COLLAB_DESKTOP_BRIDGE_PROBE" -or $head -match "平台桌面投递连通性测试") {
        return $true
      }
    } catch {
      return $false
    }
  }
  return $false
}

function Session-NameFromFile {
  param(
    [System.IO.FileInfo]$File,
    [string]$SessionId,
    [switch]$ReturnSource
  )
  $firstUserTitle = ""
  try {
    foreach ($line in (Get-Content -LiteralPath $File.FullName -Encoding UTF8 -TotalCount 260 -ErrorAction SilentlyContinue)) {
      $cleanLine = Sanitize-SessionText $line
      if (-not $cleanLine) { continue }
      $entry = $null
      try {
        $entry = $cleanLine | ConvertFrom-Json -ErrorAction Stop
      } catch {
        continue
      }
      if (-not $entry -or -not $entry.payload) { continue }
      $payload = $entry.payload
      $threadName = Short-SessionTitle ([string]$payload.thread_name)
      if ($threadName) {
        if ($ReturnSource) {
          return [ordered]@{ title = $threadName; source = "thread_name_updated" }
        }
        return $threadName
      }
      if (-not $firstUserTitle -and [string]$entry.type -eq "event_msg" -and [string]$payload.type -eq "user_message") {
        $firstUserTitle = Short-SessionTitle ([string]$payload.message)
      }
    }
  } catch {
    # Keep scanning resilient. A huge or partially written session file should not block runner sync.
  }
  if ($firstUserTitle) {
    if ($ReturnSource) {
      return [ordered]@{ title = $firstUserTitle; source = "first_user_message" }
    }
    return $firstUserTitle
  }
  $stamp = $File.LastWriteTime.ToString("MM-dd HH:mm")
  $short = if ($SessionId.Length -gt 8) { $SessionId.Substring(0, 8) } else { $SessionId }
  $fallbackTitle = "Codex / $stamp / $short"
  if ($ReturnSource) {
    return [ordered]@{ title = $fallbackTitle; source = "file_timestamp" }
  }
  return $fallbackTitle
}

function Get-CodexSessionFileRows {
  param(
    [array]$SessionDirectories,
    [datetime]$Cutoff,
    [int]$Limit
  )

  $files = [System.Collections.ArrayList]::new()
  foreach ($directory in $SessionDirectories) {
    if (-not (Test-Path -LiteralPath $directory)) { continue }
    Get-ChildItem -LiteralPath $directory -Recurse -File -Include "*.jsonl", "*.json" -ErrorAction SilentlyContinue |
      Where-Object { $_.LastWriteTimeUtc -ge $Cutoff } |
      ForEach-Object { [void]$files.Add($_) }
  }

  $seen = @{}
  $rows = [System.Collections.ArrayList]::new()
  foreach ($file in ($files | Sort-Object LastWriteTimeUtc -Descending)) {
    $sessionId = Session-IdFromFile $file
    if (-not $sessionId -or $seen.ContainsKey($sessionId)) { continue }
    $seen[$sessionId] = $true
    $titleInfo = Session-NameFromFile -File $file -SessionId $sessionId -ReturnSource
    [void]$rows.Add([pscustomobject]@{
      id = $sessionId
      thread_name = [string]$titleInfo.title
      thread_name_source = [string]$titleInfo.source
      updated_at = $file.LastWriteTimeUtc.ToString("o")
      source_kind = "session_file_fallback"
      source_file = $file.FullName
    })
    if ($rows.Count -ge $Limit) { break }
  }
  return @($rows)
}

function Resolve-WorkspaceRoot {
  param([AllowNull()][string]$Value)
  $raw = Sanitize-SessionText $Value
  if (-not $raw) {
    $raw = (Get-Location).Path
  }
  $resolved = Resolve-Path -LiteralPath $raw -ErrorAction SilentlyContinue
  if ($resolved) { return $resolved.Path }
  return $raw
}

function New-FallbackWorkstation {
  param(
    [string]$ProviderId,
    [string]$ProviderLabel,
    [string]$Issue,
    [array]$CheckedPaths,
    [string]$Root,
    [hashtable]$DesktopBridgeMetadata
  )
  $nodeSlug = Normalize-Slug $ComputerNodeId
  return @{
    workstation_id = "$ProviderId-manual-$nodeSlug"
    workstation_name = "$ProviderLabel / manual bind on $ComputerNodeId"
    workstation_status = "needs_binding"
    cwd = $Root
    model = Sanitize-SessionText $Model
    description = "$ProviderLabel session files were not found yet; bind this slot manually or open $ProviderLabel on this computer and scan again."
    notes = Sanitize-SessionText $Issue
    ai_provider_id = Sanitize-SessionText $ProviderId
    ai_provider_label = Sanitize-SessionText $ProviderLabel
    skill_loadout = @(
      "github-repo-bootstrap",
      "ai-collab-productizer",
      "continuous-orchestrator",
      "handoff-path-output",
      "verify-before-claim"
    )
    metadata = @{
      connection_kind = "local"
      provider_family = Sanitize-SessionText $ProviderId
      workspace_root = $Root
      scan_root = $scanRootForMetadata
      scan_status = "needs_manual_bind"
      scan_issue = Sanitize-SessionText $Issue
      checked_paths = @($CheckedPaths)
      manual_bind_hint = "Open $ProviderLabel on this computer, or run sync-runner-threads.ps1 with a custom ThreadId/ThreadName."
      codex_desktop_process_detected = [bool]$DesktopBridgeMetadata.codex_desktop_process_detected
      desktop_process_detected = [bool]$DesktopBridgeMetadata.desktop_process_detected
      codex_desktop_bridge_connected = [bool]$DesktopBridgeMetadata.codex_desktop_bridge_connected
      desktop_bridge_connected = [bool]$DesktopBridgeMetadata.desktop_bridge_connected
      desktop_bridge_label = $DesktopBridgeMetadata.desktop_bridge_label
      desktop_bridge_note = $DesktopBridgeMetadata.desktop_bridge_note
      desktop_delivery_mode = $DesktopBridgeMetadata.desktop_delivery_mode
    }
  }
}

$workspaceRootProvided = -not [string]::IsNullOrWhiteSpace($WorkspaceRoot)
$workspaceRootResolved = Resolve-WorkspaceRoot $WorkspaceRoot
$projectWorkspaceRoot = if ($workspaceRootProvided) { $workspaceRootResolved } else { $null }
$scanRootForMetadata = if ($workspaceRootProvided) { $workspaceRootResolved } else { $null }
$sessionIndexInfo = Resolve-CodexSessionIndexPath $SessionIndexPath
$resolvedSessionIndexPath = [string]$sessionIndexInfo.path
$checkedSessionIndexPaths = @($sessionIndexInfo.checked)
$checkedSessionDirectories = @(Resolve-CodexSessionDirectories $SessionIndexPath)
$scanIssue = ""
$rows = [System.Collections.ArrayList]::new()
$cutoff = (Get-Date).ToUniversalTime().AddDays(-1 * [Math]::Abs($MaxAgeDays))

if ($resolvedSessionIndexPath) {
  $seenIds = @{}

  Get-Content -LiteralPath $resolvedSessionIndexPath -Encoding UTF8 |
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
      [void]$script:rows.Add($_)
    }

  if ($rows.Count -gt $Take) {
    $trimmedRows = [System.Collections.ArrayList]::new()
    $rows | Select-Object -First $Take | ForEach-Object { [void]$trimmedRows.Add($_) }
    $rows = $trimmedRows
  }
  if (-not $rows.Count) {
    $scanIssue = "No recent Codex sessions found in $resolvedSessionIndexPath within the last $MaxAgeDays day(s)."
  }
} else {
  $scanIssue = "Codex session index was not found. Checked indexes: $($checkedSessionIndexPaths -join '; ')"
}

$fileRows = @(Get-CodexSessionFileRows -SessionDirectories $checkedSessionDirectories -Cutoff $cutoff -Limit $Take)
if ($fileRows.Count) {
  $seenIds = @{}
  foreach ($row in $rows) {
    if ($row -and $row.id) {
      $seenIds[[string]$row.id] = $true
    }
  }
  foreach ($row in $fileRows) {
    if ($row -and $row.id -and -not $seenIds.ContainsKey([string]$row.id)) {
      [void]$rows.Add($row)
      $seenIds[[string]$row.id] = $true
    }
  }
  $sortedRows = [System.Collections.ArrayList]::new()
  $rows | Sort-Object { [datetime]($_.updated_at) } -Descending | Select-Object -First $Take | ForEach-Object { [void]$sortedRows.Add($_) }
  $rows = $sortedRows
  if ($scanIssue) {
    Write-Host "Codex session index warning: $scanIssue"
  }
  $scanIssue = ""
} elseif ($scanIssue) {
  $scanIssue = "$scanIssue; checked session directories: $($checkedSessionDirectories -join '; ')"
}

$defaultSkillLoadout = @(
  "github-repo-bootstrap",
  "ai-collab-productizer",
  "continuous-orchestrator",
  "handoff-path-output",
  "verify-before-claim"
)
$desktopBridgeMetadata = Get-CodexDesktopBridgeMetadata
$workstations = [System.Collections.ArrayList]::new()
foreach ($row in $rows) {
  $sessionId = [string]$row.id
  $name = Sanitize-SessionText ([string]$row.thread_name)
  if (-not $name) {
    $name = "Codex Session $($sessionId.Substring(0, [Math]::Min(8, $sessionId.Length)))"
  }
  $sourceKind = Sanitize-SessionText ([string]$row.source_kind)
  $sourceFile = Sanitize-SessionText ([string]$row.source_file)
  $threadNameSource = Sanitize-SessionText ([string]$row.thread_name_source)
  if (Test-PlatformProbeSession -Title $name -SourceFile $sourceFile) {
    Write-Host "Skipping platform probe Codex session $sessionId ..."
    continue
  }

  [void]$workstations.Add(@{
    workstation_id = "codex-session-$sessionId"
    workstation_name = $name
    workstation_status = "active"
    cwd = $projectWorkspaceRoot
    model = Sanitize-SessionText $Model
    description = if ($sourceKind -eq "session_file_fallback") { "Synced from local Codex session files" } else { "Synced from local Codex session index" }
    notes = Sanitize-SessionText ("updated_at=$($row.updated_at)")
    ai_provider_id = Sanitize-SessionText $AiProviderId
    ai_provider_label = Sanitize-SessionText $AiProviderLabel
    skill_loadout = $defaultSkillLoadout
    metadata = @{
      connection_kind = "local"
      provider_family = Sanitize-SessionText $AiProviderId
      workspace_root = $projectWorkspaceRoot
      scan_root = $scanRootForMetadata
      session_index_path = $resolvedSessionIndexPath
      source_kind = $sourceKind
      source_file = $sourceFile
      thread_name_source = $threadNameSource
      scan_status = "active_session_found"
      checked_session_directories = @($checkedSessionDirectories)
      codex_desktop_process_detected = $desktopBridgeMetadata.codex_desktop_process_detected
      desktop_process_detected = $desktopBridgeMetadata.desktop_process_detected
      codex_desktop_bridge_connected = $desktopBridgeMetadata.codex_desktop_bridge_connected
      desktop_bridge_connected = $desktopBridgeMetadata.desktop_bridge_connected
      desktop_bridge_label = $desktopBridgeMetadata.desktop_bridge_label
      desktop_bridge_note = $desktopBridgeMetadata.desktop_bridge_note
      desktop_delivery_mode = $desktopBridgeMetadata.desktop_delivery_mode
    }
  })
}

if (-not $workstations.Count) {
  Write-Warning $scanIssue
  [void]$workstations.Add((New-FallbackWorkstation -ProviderId $AiProviderId -ProviderLabel $AiProviderLabel -Issue $scanIssue -CheckedPaths $checkedSessionIndexPaths -Root $projectWorkspaceRoot -DesktopBridgeMetadata $desktopBridgeMetadata))
  $workstations[0].metadata.checked_session_directories = @($checkedSessionDirectories)
}

$body = @{
  project_id = $ProjectId
  computer_node_id = $ComputerNodeId
  workstations = $workstations
} | ConvertTo-Json -Depth 8 -Compress

$headers = @{
  "x-runner-id" = $RunnerId
}

function Resolve-ApiBaseUrl {
  param([Parameter(Mandatory = $true)][string]$Value)
  $base = $Value.Trim().TrimEnd("/")
  if ($base -match ":3000$") { return ($base -replace ":3000$", ":8011") }
  if ($base -match ":3001$") { return ($base -replace ":3001$", ":8011") }
  return $base
}

$apiBase = Resolve-ApiBaseUrl $Server
$url = ($apiBase.TrimEnd("/")) + "/api/runners/$RunnerId/thread-workstations/sync"

Write-Host "Syncing $($workstations.Count) Codex session thread slot(s) to $url ..."
if ($DryRun) {
  Write-Host "Dry run enabled; not posting to platform."
  $body
  exit 0
}
$utf8Body = [System.Text.Encoding]::UTF8.GetBytes($body)
$response = Invoke-RestMethod -Method Post -Uri $url -Headers $headers -ContentType "application/json; charset=utf-8" -Body $utf8Body
Write-Host "Codex session thread slots synced."
$responseData = if ($response.data) { $response.data } else { $response }
$syncedRows = @($responseData.workstations)
$visibleNames = $syncedRows |
  Select-Object -First 6 |
  ForEach-Object {
    $name = [string]$_.name
    if ([string]::IsNullOrWhiteSpace($name)) { $name = [string]$_.id }
    if ($name.Length -gt 40) { $name = $name.Substring(0, 40) + "..." }
    $name
  }
Write-Host ("Synced {0} Codex thread slot(s). Visible examples: {1}" -f @($syncedRows).Count, ($visibleNames -join " / "))
