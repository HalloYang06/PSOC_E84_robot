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
  [int]$DeviceScanIntervalSeconds = 60,
  [string]$DeviceDataRepo = "",
  [switch]$DeviceDataGitPush,
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

function Limit-Text {
  param(
    [AllowNull()][string]$Value,
    [int]$MaxLength = 1800
  )
  $text = [string]$Value
  if ($text.Length -le $MaxLength) { return $text }
  return $text.Substring(0, [Math]::Max(0, $MaxLength - 3)) + "..."
}

function Format-CaptureRunnerNote {
  param(
    [Parameter(Mandatory = $true)][string]$RunnerName,
    [AllowNull()]$CaptureResult
  )
  $result = if ($CaptureResult -and $CaptureResult.result) { $CaptureResult.result } else { $null }
  if ($result) {
    $captureId = [string]$result.capture_id
    $sampleCount = [string]$result.sample_count
    $byteCount = [string]$result.byte_count
    $syncStatus = ""
    if ($result.repo_sync -and $result.repo_sync.status) {
      $syncStatus = [string]$result.repo_sync.status
    }
    if ([string]::IsNullOrWhiteSpace($sampleCount)) { $sampleCount = "0" }
    if ([string]::IsNullOrWhiteSpace($byteCount)) { $byteCount = "0" }
    $parts = @("Runner $RunnerName handled device capture")
    if (-not [string]::IsNullOrWhiteSpace($captureId)) { $parts += "capture=$captureId" }
    $parts += "samples=$sampleCount"
    $parts += "bytes=$byteCount"
    if (-not [string]::IsNullOrWhiteSpace($syncStatus)) { $parts += "repo_sync=$syncStatus" }
    if ($result.error) { $parts += ("hint=" + (Limit-Text -Value ([string]$result.error) -MaxLength 240)) }
    return (($parts -join "; ") + ".")
  }
  if ($CaptureResult -and $CaptureResult.note) {
    return "Runner $RunnerName handled device capture: $(Limit-Text -Value ([string]$CaptureResult.note) -MaxLength 1200)"
  }
  return "Runner $RunnerName handled device capture."
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
    [Parameter(Mandatory = $true)][string]$RunnerName,
    [string]$WebBase = "",
    [string]$ProjectId = "",
    [string]$ComputerNodeId = "",
    [string]$RunnerDir = "",
    [switch]$HardwareAccess
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
    $bodyText = [string]$item.body
    $payloadKind = ""
    try {
      $payload = $bodyText | ConvertFrom-Json
      $payloadKind = [string]$payload.kind
    } catch {
      $payloadKind = ""
    }
    $scanResult = $null
    $captureResult = $null
    $note = "Runner $RunnerName received platform dispatch: $title. The computer connection is reachable; enable NPC automation or bind a desktop thread before real execution."
    if ($payloadKind -eq "serial.usb.scan" -and -not [string]::IsNullOrWhiteSpace($WebBase) -and -not [string]::IsNullOrWhiteSpace($ProjectId) -and -not [string]::IsNullOrWhiteSpace($ComputerNodeId) -and -not [string]::IsNullOrWhiteSpace($RunnerDir)) {
      try {
        $scanResult = Invoke-DeviceInterfaceSync `
          -ApiBase $ApiBase `
          -WebBase $WebBase `
          -RunnerId $RunnerId `
          -ProjectId $ProjectId `
          -ComputerNodeId $ComputerNodeId `
          -RunnerDir $RunnerDir
        $note = "Runner $RunnerName scanned real device interfaces and synced $($scanResult.interface_count) interface(s) back to the platform."
      } catch {
        $note = "Runner $RunnerName tried to scan real device interfaces, but sync failed: $($_.Exception.Message)"
      }
    } elseif ($payloadKind -in @("robotics.capture.start", "robotics.capture.stop") -and -not [string]::IsNullOrWhiteSpace($WebBase) -and -not [string]::IsNullOrWhiteSpace($RunnerDir)) {
      try {
        $captureResult = Invoke-DeviceCaptureCommand `
          -WebBase $WebBase `
          -PayloadJson $bodyText `
          -RunnerDir $RunnerDir `
          -DeviceDataRepo $DeviceDataRepo `
          -DeviceDataGitPush:$DeviceDataGitPush `
          -HardwareAccess:$HardwareAccess
        $captureStatus = [string]$captureResult.result_status
        $captureNote = [string]$captureResult.note
        if ([string]::IsNullOrWhiteSpace($captureNote)) {
          $captureNote = "Device capture command finished."
        }
        $note = Format-CaptureRunnerNote -RunnerName $RunnerName -CaptureResult $captureResult
      } catch {
        $note = "Runner $RunnerName tried to handle device capture, but it failed: $($_.Exception.Message)"
        $captureResult = [ordered]@{
          result_status = "failed"
          note = $note
          result = @{
            ok = $false
            kind = $payloadKind
            error = $_.Exception.Message
          }
        }
      }
    } elseif ($payloadKind -eq "codex.desktop.dispatch" -and -not [string]::IsNullOrWhiteSpace($WebBase) -and -not [string]::IsNullOrWhiteSpace($ProjectId) -and -not [string]::IsNullOrWhiteSpace($RunnerDir)) {
      try {
        $targetWorkstationId = [string]$payload.workstation_id
        $sourceMessageId = [string]$payload.message_id
        $targetProvider = [string]$payload.provider_id
        if ([string]::IsNullOrWhiteSpace($targetProvider)) {
          $targetProvider = "codex"
        }
        if ([string]::IsNullOrWhiteSpace($targetWorkstationId) -or [string]::IsNullOrWhiteSpace($sourceMessageId)) {
          throw "Desktop dispatch payload is missing workstation_id or message_id."
        }
        $adapterScript = Download-RunnerScript -WebBase $WebBase -ScriptName "platform-workstation-adapter.py" -RunnerDir $RunnerDir
        [void](Download-RunnerScript -WebBase $WebBase -ScriptName "platform-provider-executor.py" -RunnerDir $RunnerDir)
        $adapterArgs = @(
          "--api-base", $ApiBase,
          "--project-id", $ProjectId,
          "--workstation-id", $targetWorkstationId,
          "--runner-id", $RunnerId,
          "--provider", $targetProvider,
          "--auto-ack",
          "--execute-provider-cli",
          "--ignore-automation-switch",
          "--limit", "1",
          "--message-id", $sourceMessageId,
          "--output-dir", (Join-Path $RunnerDir "inbox")
        )
        $adapterOutput = & python $adapterScript @adapterArgs 2>&1
        $adapterText = ($adapterOutput | Out-String).Trim()
        if ($LASTEXITCODE -ne 0) {
          throw $adapterText
        }
        $desktopDelivered = $false
        $desktopConfirmed = $false
        $desktopUnconfirmed = $false
        try {
          $adapterJson = $adapterText | ConvertFrom-Json
          $executions = @($adapterJson.executions).Count
          $receipts = @($adapterJson.receipts).Count
          foreach ($execution in @($adapterJson.executions)) {
            if ($execution.desktop_delivery_confirmed -eq $true) {
              $desktopConfirmed = $true
            }
            if ($execution.desktop_delivery_unconfirmed -eq $true -or $execution.desktop_delivery_confirmed -eq $false) {
              $desktopUnconfirmed = $true
            }
            if ($execution.ok -eq $true -and $execution.desktop_delivery_confirmed -eq $true) {
              $desktopDelivered = $true
            }
          }
          if ($desktopConfirmed) {
            $desktopDelivered = $true
          }
        } catch {
          $desktopDelivered = $false
          $desktopUnconfirmed = -not [string]::IsNullOrWhiteSpace($adapterText)
        }
        if ($desktopConfirmed) {
          $note = "Runner $RunnerName delivered this dispatch into the bound Codex Desktop thread and confirmed the thread received it."
        } elseif ($desktopUnconfirmed) {
          $note = "Runner $RunnerName received this dispatch on the execution computer, but Codex Desktop has not confirmed that the bound thread visibly received it. Keep this item pending and retry desktop sync."
        } else {
          $note = "Runner $RunnerName ran desktop delivery, but no delivery evidence was returned yet. The platform will keep the item visible for retry."
        }
        $captureResult = [ordered]@{
          result_status = if ($desktopConfirmed) { "completed" } else { "failed" }
          note = $note
          result = @{
            ok = $desktopConfirmed
            kind = "codex.desktop.dispatch"
            workstation_id = $targetWorkstationId
            message_id = $sourceMessageId
            desktop_delivery_confirmed = $desktopConfirmed
            desktop_delivery_unconfirmed = (-not $desktopConfirmed)
          }
        }
      } catch {
        $note = "Runner $RunnerName tried to deliver into Codex Desktop, but it failed: $($_.Exception.Message)"
        $captureResult = [ordered]@{
          result_status = "failed"
          note = $note
          result = @{
            ok = $false
            kind = "codex.desktop.dispatch"
            error = $_.Exception.Message
          }
        }
      }
    }
    $ackBody = @{ note = $note } | ConvertTo-Json -Depth 4
    $completeMetadata = @{}
    if ($scanResult) {
      $completeMetadata = @{
        runner_capability = "serial.usb.scan"
        runner_result = @{
          kind = "serial.usb.scan"
          ok = $true
          interface_count = $scanResult.interface_count
          scanned_at = $scanResult.scanned_at
          computer_node_id = $ComputerNodeId
        }
      }
    } elseif ($captureResult) {
      $capturePayload = if ($captureResult.result) { $captureResult.result } else { @{} }
      $captureKind = [string]$capturePayload.kind
      if ([string]::IsNullOrWhiteSpace($captureKind)) {
        $captureKind = "robotics.capture"
      }
      $completeMetadata = @{
        runner_capability = $captureKind
        runner_result = $capturePayload
      }
    }
    $completeStatus = "completed"
    if ($captureResult -and [string]$captureResult.result_status -eq "failed") {
      $completeStatus = "failed"
    }
    $completeBody = @{ result_status = $completeStatus; note = (Limit-Text -Value $note -MaxLength 3600); metadata = $completeMetadata } | ConvertTo-Json -Depth 12
    $messageBase = ($ApiBase.TrimEnd("/")) + "/api/runners/" + $RunnerId + "/messages/" + $messageId
    try {
      Invoke-RestMethod -Method Post -Uri ($messageBase + "/ack") -Headers @{
        "Content-Type" = "application/json"
        "X-Runner-Id" = $RunnerId
      } -Body ([System.Text.Encoding]::UTF8.GetBytes($ackBody)) | Out-Null
    } catch {
      $ackError = Resolve-RestError $_
      if ($ackError.status_code -eq 409 -or $ackError.message -match "already|closed|claimed|状态|收尾") {
        [void]$results.Add([ordered]@{
          message_id = $messageId
          title = $title
          status = "skipped_conflict"
          detail = "This queued runner command was already claimed or closed; watch loop will continue."
        })
        continue
      }
      throw
    }
    try {
      Invoke-RestMethod -Method Post -Uri ($messageBase + "/complete") -Headers @{
        "Content-Type" = "application/json"
        "X-Runner-Id" = $RunnerId
      } -Body ([System.Text.Encoding]::UTF8.GetBytes($completeBody)) | Out-Null
    } catch {
      $completeError = Resolve-RestError $_
      if ($completeError.status_code -eq 409 -or $completeError.message -match "already|closed|claimed|状态|收尾") {
        [void]$results.Add([ordered]@{
          message_id = $messageId
          title = $title
          status = "skipped_conflict"
          detail = "This queued runner command was already closed before completion; watch loop will continue."
        })
        continue
      }
      throw
    }
    [void]$results.Add([ordered]@{
      message_id = $messageId
      title = $title
      status = "completed"
      interface_count = if ($scanResult) { $scanResult.interface_count } else { $null }
      capture_id = if ($captureResult -and $captureResult.result) { $captureResult.result.capture_id } else { $null }
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
      $commands = $null
      $written = $null
      $receipts = $null
      $executions = $null
      $note = ""
      try {
        $adapterJson = $adapterText | ConvertFrom-Json
        $commands = @($adapterJson.commands).Count
        $written = @($adapterJson.written).Count
        $receipts = @($adapterJson.receipts).Count
        $executions = @($adapterJson.executions).Count
        $note = [string]$adapterJson.note
      } catch {
        $note = if ($adapterText.Length -gt 180) { $adapterText.Substring(0, 180) + "..." } else { $adapterText }
      }
      [void]$results.Add([ordered]@{
        workstation_id = $workstationId
        provider = $provider
        status = "ok"
        commands = $commands
        written = $written
        receipts = $receipts
        executions = $executions
        note = $note
      })
    } catch {
      [void]$results.Add([ordered]@{
        workstation_id = $workstationId
        provider = $provider
        status = "warning"
        note = $_.Exception.Message
      })
    }
  }
  return $results
}

function Invoke-DeviceInterfaceSync {
  param(
    [Parameter(Mandatory = $true)][string]$ApiBase,
    [Parameter(Mandatory = $true)][string]$WebBase,
    [Parameter(Mandatory = $true)][string]$RunnerId,
    [Parameter(Mandatory = $true)][string]$ProjectId,
    [Parameter(Mandatory = $true)][string]$ComputerNodeId,
    [Parameter(Mandatory = $true)][string]$RunnerDir
  )
  $deviceScanScript = Download-RunnerScript -WebBase $WebBase -ScriptName "scan-device-interfaces.py" -RunnerDir $RunnerDir
  $scanOutput = & python $deviceScanScript `
    --sync `
    --server $ApiBase `
    --runner-id $RunnerId `
    --project-id $ProjectId `
    --computer-node-id $ComputerNodeId 2>&1
  if ($LASTEXITCODE -ne 0) {
    throw (($scanOutput | Out-String).Trim())
  }
  $scanText = ($scanOutput | Out-String).Trim()
  try {
    $scanJson = $scanText | ConvertFrom-Json
    $scanData = if ($scanJson.data) { $scanJson.data } else { $scanJson }
    return [ordered]@{
      status = "ok"
      interface_count = [int]($scanData.interface_count -as [int])
      scanned_at = [string]$scanData.scanned_at
    }
  } catch {
    return [ordered]@{
      status = "ok"
      interface_count = $null
      scanned_at = ""
    }
  }
}

function Invoke-DeviceCaptureCommand {
  param(
    [Parameter(Mandatory = $true)][string]$WebBase,
    [Parameter(Mandatory = $true)][string]$PayloadJson,
    [Parameter(Mandatory = $true)][string]$RunnerDir,
    [string]$DeviceDataRepo = "",
    [switch]$DeviceDataGitPush,
    [switch]$HardwareAccess
  )
  $captureScript = Download-RunnerScript -WebBase $WebBase -ScriptName "run-device-capture-command.py" -RunnerDir $RunnerDir
  $payloadFile = Join-Path $RunnerDir ("device-capture-payload-" + [System.Guid]::NewGuid().ToString("N") + ".json")
  [System.IO.File]::WriteAllText($payloadFile, $PayloadJson, [System.Text.UTF8Encoding]::new($false))
  $captureArgs = @(
    $captureScript,
    "--payload-file", $payloadFile,
    "--workdir", $RunnerDir
  )
  if ($HardwareAccess) {
    $captureArgs += "--hardware-access"
  }
  if (-not [string]::IsNullOrWhiteSpace($DeviceDataRepo)) {
    $captureArgs += @("--repo-root", $DeviceDataRepo)
  }
  if ($DeviceDataGitPush) {
    $captureArgs += "--git-push"
  }
  try {
    $captureOutput = & python @captureArgs 2>&1
  } finally {
    Remove-Item -LiteralPath $payloadFile -Force -ErrorAction SilentlyContinue
  }
  $captureText = ($captureOutput | Out-String).Trim()
  if ([string]::IsNullOrWhiteSpace($captureText)) {
    throw "Device capture command returned no result."
  }
  try {
    $captureJson = $captureText | ConvertFrom-Json
    $captureResult = if ($captureJson.data) { $captureJson.data } else { $captureJson }
    return $captureResult
  } catch {
    throw $captureText
  }
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
    [int]$DeviceScanIntervalSeconds = 60,
    [string]$DeviceDataRepo = "",
    [switch]$DeviceDataGitPush,
    [switch]$HardwareAccess,
    [switch]$ExecuteProviderCli
  )
  if ($PollSeconds -lt 3) {
    $PollSeconds = 3
  }
  if ($DeviceScanIntervalSeconds -lt 15) {
    $DeviceScanIntervalSeconds = 15
  }
  Write-Host "Runner watch mode started. Press Ctrl+C to stop. Poll interval: $PollSeconds seconds."
  if ($ExecuteProviderCli) {
    Write-Warning "Provider CLI execution is enabled. Use this only for read-only/review tasks unless the human explicitly approved edits."
  } else {
    Write-Host "Provider CLI execution is OFF. This runner will keep heartbeat, write inbox prompt files, and send minimal acknowledgements only."
  }

  $loop = 0
  $failureStreak = 0
  $lastDeviceScanAt = [datetime]::MinValue
  while ($true) {
    $loop += 1
    try {
      [void](Invoke-RunnerHeartbeat -ApiBase $ApiBase -RunnerId $RunnerId)
      $deviceScanResult = $null
      $secondsSinceDeviceScan = ([datetime]::UtcNow - $lastDeviceScanAt).TotalSeconds
      if ($secondsSinceDeviceScan -ge $DeviceScanIntervalSeconds) {
        try {
          $deviceScanResult = Invoke-DeviceInterfaceSync `
            -ApiBase $ApiBase `
            -WebBase $WebBase `
            -RunnerId $RunnerId `
            -ProjectId $ProjectId `
            -ComputerNodeId $ComputerNodeId `
            -RunnerDir $RunnerDir
          $lastDeviceScanAt = [datetime]::UtcNow
        } catch {
          Write-Warning "Device interface scan failed; the runner will retry automatically: $($_.Exception.Message)"
        }
      }
      $runnerCommands = Invoke-RunnerInboxPoll `
        -ApiBase $ApiBase `
        -RunnerId $RunnerId `
        -RunnerName $RunnerName `
        -WebBase $WebBase `
        -ProjectId $ProjectId `
        -ComputerNodeId $ComputerNodeId `
        -RunnerDir $RunnerDir `
        -HardwareAccess:$HardwareAccess
      $pollResults = Invoke-WorkstationInboxPoll `
        -ApiBase $ApiBase `
        -WebBase $WebBase `
        -RunnerId $RunnerId `
        -ProjectId $ProjectId `
        -ComputerNodeId $ComputerNodeId `
        -RunnerDir $RunnerDir `
        -ExecuteProviderCli:$ExecuteProviderCli
      $activePollResults = @($pollResults) | Where-Object {
        (($_.written -as [int]) -gt 0) -or (($_.receipts -as [int]) -gt 0) -or (($_.executions -as [int]) -gt 0) -or ([string]$_.status -ne "ok")
      }
      $runnerCommandRows = @($runnerCommands)
      $runnerCompleted = @($runnerCommandRows | Where-Object { [string]$_.status -eq "completed" })
      $runnerSkipped = @($runnerCommandRows | Where-Object { [string]$_.status -eq "skipped_conflict" })
      $runnerAttention = @($runnerCommandRows | Where-Object { [string]$_.status -notin @("completed", "skipped_conflict") })
      $publicRunnerCommands = @($runnerCompleted + $runnerAttention) | ForEach-Object {
        [ordered]@{
          title = [string]$_.title
          status = [string]$_.status
        }
      }
      $publicActiveWorkstations = @($activePollResults) | ForEach-Object {
        [ordered]@{
          provider = [string]$_.provider
          status = [string]$_.status
          commands = $_.commands
          written = $_.written
          receipts = $_.receipts
          executions = $_.executions
          note = [string]$_.note
        }
      }
      Write-Host ("Runner watch heartbeat ok. Loop {0}: checked {1} thread(s), runner command(s) {2}, active thread(s) {3}." -f $loop, @($pollResults).Count, @($runnerCommands).Count, @($activePollResults).Count)
      if ($deviceScanResult) {
        Write-Host ("Device interfaces synced: {0} interface(s), scanned at {1}." -f $deviceScanResult.interface_count, $deviceScanResult.scanned_at)
      }
      if (@($runnerSkipped).Count) {
        Write-Host ("Skipped {0} old command(s) that were already claimed or closed." -f @($runnerSkipped).Count)
      }
      foreach ($command in @($publicRunnerCommands)) {
        Write-Host ("Current runner command: {0} [{1}]" -f $command.title, $command.status)
      }
      foreach ($thread in @($publicActiveWorkstations)) {
        Write-Host ("Active NPC thread: provider {0}, status {1}, command(s) {2}, prompt file(s) {3}, receipt(s) {4}, execution(s) {5}." -f $thread.provider, $thread.status, $thread.commands, $thread.written, $thread.receipts, $thread.executions)
        if (-not [string]::IsNullOrWhiteSpace($thread.note)) {
          Write-Host ("Thread note: {0}" -f $thread.note)
        }
      }
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

$deviceScanStatus = "ok"
$deviceScanDetail = "Device interface scan synced to platform."
try {
  $deviceScanScript = Download-RunnerScript -WebBase $webBase -ScriptName "scan-device-interfaces.py" -RunnerDir $runnerDir
  python $deviceScanScript `
    --sync `
    --server $apiBase `
    --runner-id $RunnerId `
    --project-id $ProjectId `
    --computer-node-id $ComputerNodeId | Out-Null
} catch {
  $deviceScanStatus = "warning"
  $deviceScanDetail = $_.Exception.Message
  Write-Warning "Device interface scan skipped or failed: $deviceScanDetail"
}
Add-StepResult $steps "sync-device-interfaces" $deviceScanStatus $deviceScanDetail

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

$nextAction = if ($Watch) {
  "Keep this PowerShell window open. The runner is now heartbeating and polling workstation inbox commands."
} else {
  "Return to the platform and click Scan Threads once. For real continuous collaboration, rerun the command with -Watch."
}

Write-Host "AI collaboration runner connect finished."
Write-Host ("Connected computer: {0}" -f $RunnerName)
Write-Host ("API: {0} / Web: {1}" -f $apiBase, $webBase)
Write-Host $nextAction

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
    -DeviceScanIntervalSeconds $DeviceScanIntervalSeconds `
    -DeviceDataRepo $DeviceDataRepo `
    -DeviceDataGitPush:$DeviceDataGitPush `
    -HardwareAccess:$HardwareAccess `
    -ExecuteProviderCli:$WatchExecuteProviderCli
}
