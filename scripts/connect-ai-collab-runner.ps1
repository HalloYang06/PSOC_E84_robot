param(
  [Parameter(Mandatory = $true)]
  [string]$Server,
  [Parameter(Mandatory = $true)]
  [string]$PairingToken,
  [Parameter(Mandatory = $true)]
  [string]$ComputerNodeId,
  [string]$RunnerName = "",
  [string]$RunnerId = "",
  [string]$ProjectId = "",
  [string]$WorkspaceRoot = "",
  [string]$WebBaseUrl = "",
  [int]$Take = 12,
  [int]$CodexMaxAgeDays = 14,
  [int]$ClaudeMaxAgeHours = 24,
  [switch]$Watch,
  [int]$WatchPollSeconds = 15,
  [int]$WatchMaxLoops = 0,
  [switch]$WatchExecuteProviderCli,
  [switch]$SkipCodex,
  [switch]$SkipClaude,
  [switch]$HardwareAccess
)

$ErrorActionPreference = "Stop"
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)

function Normalize-BaseUrl {
  param([Parameter(Mandatory = $true)][string]$Value)
  return $Value.Trim().TrimEnd("/")
}

function Resolve-ApiBaseUrl {
  param([Parameter(Mandatory = $true)][string]$Value)
  $base = Normalize-BaseUrl $Value
  if ($base -match ":3000$") {
    return ($base -replace ":3000$", ":8011")
  }
  if ($base -match ":3001$") {
    return ($base -replace ":3001$", ":8011")
  }
  return $base
}

function Resolve-WebBaseUrl {
  param(
    [Parameter(Mandatory = $true)][string]$ServerValue,
    [string]$ExplicitWebBaseUrl = ""
  )
  if (-not [string]::IsNullOrWhiteSpace($ExplicitWebBaseUrl)) {
    return Normalize-BaseUrl $ExplicitWebBaseUrl
  }
  $base = Normalize-BaseUrl $ServerValue
  if ($base -match ":8010$") {
    return ($base -replace ":8010$", ":3001")
  }
  if ($base -match ":8011$") {
    return ($base -replace ":8011$", ":3001")
  }
  if ($base -match ":8000$") {
    return ($base -replace ":8000$", ":3000")
  }
  return $base
}

function Normalize-Slug {
  param([AllowNull()][string]$Value)
  $raw = ([string]$Value).ToLowerInvariant()
  $slug = $raw -replace "[^a-z0-9]+", "-"
  $slug = $slug.Trim("-")
  if ($slug) { return $slug }
  return "computer"
}

function Download-RunnerScript {
  param(
    [Parameter(Mandatory = $true)][string]$WebBase,
    [Parameter(Mandatory = $true)][string]$ScriptName,
    [Parameter(Mandatory = $true)][string]$RunnerDir
  )
  $target = Join-Path $RunnerDir $ScriptName
  $url = ($WebBase.TrimEnd("/")) + "/downloads/runner/" + $ScriptName
  Write-Host "Downloading $ScriptName from $url ..."
  Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $target
  return $target
}

function Add-StepResult {
  param(
    [System.Collections.ArrayList]$Steps,
    [string]$Name,
    [string]$Status,
    [string]$Detail = ""
  )
  [void]$Steps.Add([ordered]@{
    name = $Name
    status = $Status
    detail = $Detail
  })
}

function Resolve-RestError {
  param([Parameter(Mandatory = $true)]$ErrorRecord)
  $body = ""
  $code = ""
  $message = $ErrorRecord.Exception.Message
  $statusCode = $null

  if ($ErrorRecord.ErrorDetails -and -not [string]::IsNullOrWhiteSpace($ErrorRecord.ErrorDetails.Message)) {
    $body = [string]$ErrorRecord.ErrorDetails.Message
  }

  if ([string]::IsNullOrWhiteSpace($body) -and $ErrorRecord.Exception.Response) {
    try {
      $statusCode = [int]$ErrorRecord.Exception.Response.StatusCode
      $stream = $ErrorRecord.Exception.Response.GetResponseStream()
      if ($stream) {
        $reader = [System.IO.StreamReader]::new($stream)
        $body = $reader.ReadToEnd()
        $reader.Close()
      }
    } catch {
      $body = ""
    }
  }

  if (-not [string]::IsNullOrWhiteSpace($body)) {
    try {
      $parsed = $body | ConvertFrom-Json
      if ($parsed.error) {
        $code = [string]$parsed.error.code
        if ($parsed.error.message) {
          $message = [string]$parsed.error.message
        }
      }
    } catch {
      # Keep the original PowerShell error message when the body is not JSON.
    }
  }

  return [pscustomobject]@{
    code = $code
    message = $message
    status_code = $statusCode
    body = $body
  }
}

function Invoke-RunnerHeartbeat {
  param(
    [Parameter(Mandatory = $true)][string]$ApiBase,
    [Parameter(Mandatory = $true)][string]$RunnerId
  )
  $heartbeatUrl = ($ApiBase.TrimEnd("/")) + "/api/runners/heartbeat"
  $heartbeatBody = @{ runner_id = $RunnerId } | ConvertTo-Json -Depth 4
  return Invoke-RestMethod -Method Post -Uri $heartbeatUrl -Headers @{
    "Content-Type" = "application/json"
    "X-Runner-Id" = $RunnerId
  } -Body ([System.Text.Encoding]::UTF8.GetBytes($heartbeatBody))
}

function Get-RunnerWorkspace {
  param(
    [Parameter(Mandatory = $true)][string]$ApiBase,
    [Parameter(Mandatory = $true)][string]$RunnerId
  )
  $workspaceUrl = ($ApiBase.TrimEnd("/")) + "/api/runners/" + $RunnerId + "/workspace"
  return Invoke-RestMethod -Method Get -Uri $workspaceUrl -Headers @{
    "X-Runner-Id" = $RunnerId
  }
}

function Test-RunnerWorkspaceBinding {
  param(
    [Parameter(Mandatory = $true)]$WorkspaceResponse,
    [Parameter(Mandatory = $true)][string]$ProjectId,
    [Parameter(Mandatory = $true)][string]$ComputerNodeId
  )
  $workspaceData = if ($WorkspaceResponse.data) { $WorkspaceResponse.data } else { $WorkspaceResponse }
  foreach ($binding in @($workspaceData.bindings)) {
    if ([string]$binding.project_id -eq $ProjectId -and [string]$binding.computer_node_id -eq $ComputerNodeId) {
      return $true
    }
  }
  return $false
}

function Invoke-RunnerInboxPoll {
  param(
    [Parameter(Mandatory = $true)][string]$ApiBase,
    [Parameter(Mandatory = $true)][string]$RunnerId,
    [Parameter(Mandatory = $true)][string]$RunnerName
  )
  $inboxUrl = ($ApiBase.TrimEnd("/")) + "/api/runners/" + $RunnerId + "/inbox?limit=20"
  $response = Invoke-RestMethod -Method Get -Uri $inboxUrl -Headers @{
    "X-Runner-Id" = $RunnerId
  }
  $items = if ($response.data) { @($response.data) } else { @($response) }
  $results = [System.Collections.ArrayList]::new()
  foreach ($item in $items) {
    $status = ([string]$item.status).Trim().ToLowerInvariant()
    if ($status -notin @("pending", "queued")) {
      continue
    }
    $messageId = ([string]$item.id).Trim()
    if ([string]::IsNullOrWhiteSpace($messageId)) {
      continue
    }
    $title = ([string]$item.title).Trim()
    if ([string]::IsNullOrWhiteSpace($title)) {
      $title = "Platform dispatch"
    }
    $note = "Runner $RunnerName received platform dispatch: $title. The computer connection is reachable; enable NPC automation or bind a desktop thread before real execution."
    $ackBody = @{ note = $note } | ConvertTo-Json -Depth 4
    $completeBody = @{ result_status = "completed"; note = $note } | ConvertTo-Json -Depth 4
    $messageBase = ($ApiBase.TrimEnd("/")) + "/api/runners/" + $RunnerId + "/messages/" + $messageId
    Invoke-RestMethod -Method Post -Uri ($messageBase + "/ack") -Headers @{
      "Content-Type" = "application/json"
      "X-Runner-Id" = $RunnerId
    } -Body ([System.Text.Encoding]::UTF8.GetBytes($ackBody)) | Out-Null
    Invoke-RestMethod -Method Post -Uri ($messageBase + "/complete") -Headers @{
      "Content-Type" = "application/json"
      "X-Runner-Id" = $RunnerId
    } -Body ([System.Text.Encoding]::UTF8.GetBytes($completeBody)) | Out-Null
    [void]$results.Add([ordered]@{
      message_id = $messageId
      title = $title
      status = "completed"
    })
  }
  return $results
}

function Invoke-WorkstationInboxPoll {
  param(
    [Parameter(Mandatory = $true)][string]$ApiBase,
    [Parameter(Mandatory = $true)][string]$WebBase,
    [Parameter(Mandatory = $true)][string]$RunnerId,
    [Parameter(Mandatory = $true)][string]$ProjectId,
    [Parameter(Mandatory = $true)][string]$ComputerNodeId,
    [Parameter(Mandatory = $true)][string]$RunnerDir,
    [switch]$ExecuteProviderCli
  )

  $adapterScript = Join-Path $RunnerDir "platform-workstation-adapter.py"
  $providerExecutorScript = Join-Path $RunnerDir "platform-provider-executor.py"
  if (-not (Test-Path -LiteralPath $adapterScript)) {
    $adapterScript = Download-RunnerScript -WebBase $WebBase -ScriptName "platform-workstation-adapter.py" -RunnerDir $RunnerDir
  }
  if (-not (Test-Path -LiteralPath $providerExecutorScript)) {
    [void](Download-RunnerScript -WebBase $WebBase -ScriptName "platform-provider-executor.py" -RunnerDir $RunnerDir)
  }

  $workspaceResponse = Get-RunnerWorkspace -ApiBase $ApiBase -RunnerId $RunnerId
  $workspaceData = if ($workspaceResponse.data) { $workspaceResponse.data } else { $workspaceResponse }
  $workstations = @($workspaceData.workstations) | Where-Object {
    [string]$_.project_id -eq $ProjectId -and [string]$_.computer_node_id -eq $ComputerNodeId
  }

  $results = [System.Collections.ArrayList]::new()
  foreach ($workstation in $workstations) {
    $workstationId = [string]$workstation.workstation_id
    if ([string]::IsNullOrWhiteSpace($workstationId)) {
      continue
    }
    $provider = [string]$workstation.ai_provider_id
    if ([string]::IsNullOrWhiteSpace($provider)) {
      $provider = [string]$workstation.ai_provider_label
    }
    if ([string]::IsNullOrWhiteSpace($provider)) {
      $provider = "generic"
    }
    $adapterArgs = @(
      "--api-base", $ApiBase,
      "--project-id", $ProjectId,
      "--workstation-id", $workstationId,
      "--runner-id", $RunnerId,
      "--provider", $provider,
      "--auto-ack",
      "--limit", "20",
      "--output-dir", (Join-Path $RunnerDir "inbox")
    )
    if ($ExecuteProviderCli) {
      $adapterArgs += "--execute-provider-cli"
    }
    try {
      $adapterOutput = & python $adapterScript @adapterArgs 2>&1
      $adapterText = ($adapterOutput | Out-String).Trim()
      [void]$results.Add([ordered]@{
        workstation_id = $workstationId
        provider = $provider
        status = "ok"
        output = $adapterText
      })
    } catch {
      [void]$results.Add([ordered]@{
        workstation_id = $workstationId
        provider = $provider
        status = "warning"
        output = $_.Exception.Message
      })
    }
  }
  return $results
}

function Start-RunnerWatchLoop {
  param(
    [Parameter(Mandatory = $true)][string]$ApiBase,
    [Parameter(Mandatory = $true)][string]$WebBase,
    [Parameter(Mandatory = $true)][string]$RunnerId,
    [Parameter(Mandatory = $true)][string]$ProjectId,
    [Parameter(Mandatory = $true)][string]$ComputerNodeId,
    [Parameter(Mandatory = $true)][string]$RunnerDir,
    [int]$PollSeconds = 15,
    [int]$MaxLoops = 0,
    [switch]$ExecuteProviderCli
  )
  if ($PollSeconds -lt 3) {
    $PollSeconds = 3
  }
  Write-Host "Runner watch mode started. Press Ctrl+C to stop. Poll interval: $PollSeconds seconds."
  if ($ExecuteProviderCli) {
    Write-Warning "Provider CLI execution is enabled. Use this only for read-only/review tasks unless the human explicitly approved edits."
  } else {
    Write-Host "Provider CLI execution is OFF. This runner will keep heartbeat, write inbox prompt files, and send minimal acknowledgements only."
  }

  $loop = 0
  $failureStreak = 0
  while ($true) {
    $loop += 1
    try {
      [void](Invoke-RunnerHeartbeat -ApiBase $ApiBase -RunnerId $RunnerId)
      $runnerCommands = Invoke-RunnerInboxPoll -ApiBase $ApiBase -RunnerId $RunnerId -RunnerName $RunnerName
      $pollResults = Invoke-WorkstationInboxPoll `
        -ApiBase $ApiBase `
        -WebBase $WebBase `
        -RunnerId $RunnerId `
        -ProjectId $ProjectId `
        -ComputerNodeId $ComputerNodeId `
        -RunnerDir $RunnerDir `
        -ExecuteProviderCli:$ExecuteProviderCli
      $summary = [ordered]@{
        loop = $loop
        at = (Get-Date).ToString("o")
        runner_id = $RunnerId
        project_id = $ProjectId
        computer_node_id = $ComputerNodeId
        workstation_count = @($pollResults).Count
        runner_command_count = @($runnerCommands).Count
        execute_provider_cli = [bool]$ExecuteProviderCli
        runner_commands = $runnerCommands
        results = $pollResults
      }
      $summary | ConvertTo-Json -Depth 12
      if ($failureStreak -gt 0) {
        Write-Host "Runner watch recovered after $failureStreak failed loop(s)."
      }
      $failureStreak = 0
    } catch {
      $failureStreak += 1
      Write-Warning "Runner watch loop failed: $($_.Exception.Message)"
      Write-Warning "Runner watch is still active. Consecutive failed loop(s): $failureStreak. Next retry in $PollSeconds seconds."
    }

    if ($MaxLoops -gt 0 -and $loop -ge $MaxLoops) {
      Write-Host "Runner watch mode reached max loops: $MaxLoops"
      break
    }
    Start-Sleep -Seconds $PollSeconds
  }
}

$workspaceRootProvided = -not [string]::IsNullOrWhiteSpace($WorkspaceRoot)
if ([string]::IsNullOrWhiteSpace($RunnerId)) {
  $RunnerId = "runner-" + (Normalize-Slug $ComputerNodeId)
}
if ([string]::IsNullOrWhiteSpace($RunnerName)) {
  $RunnerName = "$ComputerNodeId Runner"
}

$apiBase = Resolve-ApiBaseUrl $Server
$webBase = Resolve-WebBaseUrl -ServerValue $Server -ExplicitWebBaseUrl $WebBaseUrl
$runnerDir = Join-Path (Get-Location).Path "ai-collab-runner"
New-Item -ItemType Directory -Force -Path $runnerDir | Out-Null

$steps = [System.Collections.ArrayList]::new()

$registerBody = @{
  runner_id = $RunnerId
  runner_name = $RunnerName
  capabilities = @("codex", "claude", "qwen", "threads", "filesystem")
  hardware_access = [bool]$HardwareAccess
  computer_node_id = $ComputerNodeId
} | ConvertTo-Json -Depth 6

$registerHeaders = @{
  "Content-Type" = "application/json"
  "x-runner-registration-token" = $PairingToken
}

$registerUrl = ($apiBase.TrimEnd("/")) + "/api/runners/register"
Write-Host "Registering runner to $registerUrl ..."
$registerData = $null
try {
  $registerResponse = Invoke-RestMethod -Method Post -Uri $registerUrl -Headers $registerHeaders -Body ([System.Text.Encoding]::UTF8.GetBytes($registerBody))
  Add-StepResult $steps "register-runner" "ok" "Runner registered as $RunnerId"
  $registerData = if ($registerResponse.data) { $registerResponse.data } else { $registerResponse }
} catch {
  $registerError = Resolve-RestError $_
  if ($registerError.code -eq "PAIRING_TOKEN_INVALID") {
    if ([string]::IsNullOrWhiteSpace($ProjectId)) {
      throw "Runner registration failed: pairing token is invalid and -ProjectId was not provided, so the script cannot check whether this runner is already bound. Return to the platform, regenerate the pairing command, and run the new command."
    }
    Write-Warning "Pairing token was rejected. Checking whether runner '$RunnerId' is already bound to project '$ProjectId' / computer '$ComputerNodeId' ..."
    try {
      $workspaceResponse = Get-RunnerWorkspace -ApiBase $apiBase -RunnerId $RunnerId
    } catch {
      $workspaceError = Resolve-RestError $_
      throw "Runner registration failed: pairing token is invalid, and existing runner self-check failed for '$RunnerId' [$($workspaceError.code)] $($workspaceError.message). Return to the platform, generate a fresh pairing token for computer '$ComputerNodeId', and run the new command."
    }
    if (-not (Test-RunnerWorkspaceBinding -WorkspaceResponse $workspaceResponse -ProjectId $ProjectId -ComputerNodeId $ComputerNodeId)) {
      throw "Runner registration failed: pairing token is invalid, and existing runner '$RunnerId' is not bound to project '$ProjectId' / computer '$ComputerNodeId'. Return to the platform, generate a fresh pairing token for this computer, and run the new command."
    }
    try {
      $heartbeatResponse = Invoke-RunnerHeartbeat -ApiBase $apiBase -RunnerId $RunnerId
      $registerData = if ($heartbeatResponse.data) { $heartbeatResponse.data } else { $heartbeatResponse }
    } catch {
      $heartbeatError = Resolve-RestError $_
      Write-Warning "Existing runner binding was verified, but heartbeat failed: [$($heartbeatError.code)] $($heartbeatError.message)"
      $workspaceData = if ($workspaceResponse.data) { $workspaceResponse.data } else { $workspaceResponse }
      $registerData = $workspaceData.runner
    }
    Add-StepResult $steps "register-runner" "reused" "Pairing token is no longer current, but runner $RunnerId is already bound to this project computer. Continuing with thread sync."
  } else {
    throw "Runner registration failed: [$($registerError.code)] $($registerError.message)"
  }
}
if ([string]::IsNullOrWhiteSpace($ProjectId)) {
  $bindings = @($registerData.computer_node_bindings)
  if ($bindings.Count -gt 0 -and $bindings[0].project_id) {
    $ProjectId = [string]$bindings[0].project_id
  }
}
if ([string]::IsNullOrWhiteSpace($ProjectId)) {
  throw "ProjectId could not be resolved from registration response. Pass -ProjectId from the platform command."
}

$supportScriptStatus = "ok"
$supportScriptDetail = "Runner support scripts refreshed from platform downloads."
try {
  [void](Download-RunnerScript -WebBase $webBase -ScriptName "platform-workstation-adapter.py" -RunnerDir $runnerDir)
  [void](Download-RunnerScript -WebBase $webBase -ScriptName "platform-provider-executor.py" -RunnerDir $runnerDir)
} catch {
  $supportScriptStatus = "warning"
  $supportScriptDetail = $_.Exception.Message
  Write-Warning "Runner support script refresh failed: $supportScriptDetail"
  $adapterScript = Join-Path $runnerDir "platform-workstation-adapter.py"
  if ($Watch -and -not (Test-Path -LiteralPath $adapterScript)) {
    throw "Runner watch cannot start because platform-workstation-adapter.py could not be downloaded and no local copy exists: $supportScriptDetail"
  }
}
Add-StepResult $steps "refresh-runner-support-scripts" $supportScriptStatus $supportScriptDetail

if (-not $SkipCodex) {
  try {
    $codexScript = Download-RunnerScript -WebBase $webBase -ScriptName "sync-codex-session-threads.ps1" -RunnerDir $runnerDir
    $codexArgs = @{
      Server = $apiBase
      RunnerId = $RunnerId
      ProjectId = $ProjectId
      ComputerNodeId = $ComputerNodeId
      Take = $Take
      MaxAgeDays = $CodexMaxAgeDays
    }
    if ($workspaceRootProvided) {
      $codexArgs["WorkspaceRoot"] = $WorkspaceRoot
    }
    & $codexScript @codexArgs
    Add-StepResult $steps "sync-codex-session-threads" "ok" "Codex session scan completed."
  } catch {
    Write-Warning "Codex session scan skipped or failed: $($_.Exception.Message)"
    Add-StepResult $steps "sync-codex-session-threads" "warning" $_.Exception.Message
  }
}

if (-not $SkipClaude) {
  try {
    $claudeScript = Download-RunnerScript -WebBase $webBase -ScriptName "sync-claude-session-threads.ps1" -RunnerDir $runnerDir
    $claudeArgs = @{
      Server = $apiBase
      RunnerId = $RunnerId
      ProjectId = $ProjectId
      ComputerNodeId = $ComputerNodeId
      Take = $Take
      MaxAgeHours = $ClaudeMaxAgeHours
    }
    if ($workspaceRootProvided) {
      $claudeArgs["WorkspaceRoot"] = $WorkspaceRoot
    }
    & $claudeScript @claudeArgs
    Add-StepResult $steps "sync-claude-session-threads" "ok" "Claude session scan completed."
  } catch {
    Write-Warning "Claude session scan skipped or failed: $($_.Exception.Message)"
    Add-StepResult $steps "sync-claude-session-threads" "warning" $_.Exception.Message
  }
}

$summary = [ordered]@{
  runner_id = $RunnerId
  computer_node_id = $ComputerNodeId
  project_id = $ProjectId
  api_base = $apiBase
  web_base = $webBase
  workspace_root = if ($workspaceRootProvided) { $WorkspaceRoot } else { $null }
  runner_dir = $runnerDir
  steps = $steps
  watch_enabled = [bool]$Watch
  watch_execute_provider_cli = [bool]$WatchExecuteProviderCli
  next_action = if ($Watch) {
    "Keep this PowerShell window open. The runner is now heartbeating and polling workstation inbox commands."
  } else {
    "Return to the platform and click Scan Threads once. For real continuous collaboration, rerun the command with -Watch."
  }
}

Write-Host "AI collaboration runner connect finished."
$summary | ConvertTo-Json -Depth 8

if ($Watch) {
  Start-RunnerWatchLoop `
    -ApiBase $apiBase `
    -WebBase $webBase `
    -RunnerId $RunnerId `
    -ProjectId $ProjectId `
    -ComputerNodeId $ComputerNodeId `
    -RunnerDir $runnerDir `
    -PollSeconds $WatchPollSeconds `
    -MaxLoops $WatchMaxLoops `
    -ExecuteProviderCli:$WatchExecuteProviderCli
}
