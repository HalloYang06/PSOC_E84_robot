param(
  [int]$ApiPort = 8000,
  [int]$WebPort = 3124,
  [string]$ProjectId = "10f6a858-f3e4-467c-87f5-726caa3cc2be",
  [string]$LoginEmail = "codex-platform-npc@local.dev",
  [string]$LoginPassword = "password",
  [switch]$SkipCapture
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$apiRoot = Join-Path $repoRoot "apps\api"
$webRoot = Join-Path $repoRoot "apps\web"
$artifactsRoot = Join-Path $repoRoot "artifacts"
$captureScript = Join-Path $repoRoot "scripts\capture-auth-screenshot.mjs"

New-Item -ItemType Directory -Force -Path $artifactsRoot | Out-Null

function Start-LoggedProcess {
  param(
    [Parameter(Mandatory = $true)][string]$FilePath,
    [Parameter(Mandatory = $true)][string[]]$Arguments,
    [Parameter(Mandatory = $true)][string]$WorkingDirectory,
    [Parameter(Mandatory = $true)][string]$StdOutPath,
    [Parameter(Mandatory = $true)][string]$StdErrPath,
    [hashtable]$EnvironmentOverrides = @{}
  )

  $psi = New-Object System.Diagnostics.ProcessStartInfo
  $psi.FileName = $FilePath
  $psi.Arguments = [string]::Join(" ", ($Arguments | ForEach-Object {
        if ($_ -match '\s') { '"' + ($_ -replace '"', '\"') + '"' } else { $_ }
      }))
  $psi.WorkingDirectory = $WorkingDirectory
  $psi.UseShellExecute = $false
  $psi.RedirectStandardOutput = $true
  $psi.RedirectStandardError = $true
  foreach ($key in $EnvironmentOverrides.Keys) {
    $psi.Environment[$key] = [string]$EnvironmentOverrides[$key]
  }

  $proc = New-Object System.Diagnostics.Process
  $proc.StartInfo = $psi
  $proc.EnableRaisingEvents = $true

  $stdoutWriter = [System.IO.StreamWriter]::new($StdOutPath, $true, [System.Text.UTF8Encoding]::new($false))
  $stderrWriter = [System.IO.StreamWriter]::new($StdErrPath, $true, [System.Text.UTF8Encoding]::new($false))

  $proc.add_OutputDataReceived({
      param($sender, $eventArgs)
      if ($null -ne $eventArgs.Data) {
        $stdoutWriter.WriteLine($eventArgs.Data)
        $stdoutWriter.Flush()
      }
    })
  $proc.add_ErrorDataReceived({
      param($sender, $eventArgs)
      if ($null -ne $eventArgs.Data) {
        $stderrWriter.WriteLine($eventArgs.Data)
        $stderrWriter.Flush()
      }
    })

  if (-not $proc.Start()) {
    throw "Failed to start process: $FilePath"
  }
  $proc.BeginOutputReadLine()
  $proc.BeginErrorReadLine()
  return @{
    Process = $proc
    StdOutWriter = $stdoutWriter
    StdErrWriter = $stderrWriter
  }
}

function Wait-ForHttpReady {
  param(
    [Parameter(Mandatory = $true)][string]$Url,
    [int]$TimeoutSeconds = 30
  )

  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
  while ((Get-Date) -lt $deadline) {
    try {
      $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3
      if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) {
        return
      }
    } catch {
      Start-Sleep -Milliseconds 500
    }
  }
  throw "Timed out waiting for $Url"
}

function Stop-LoggedProcess {
  param([hashtable]$Record)
  if (-not $Record) { return }
  $proc = $Record.Process
  if ($proc -and -not $proc.HasExited) {
    try {
      $proc.Kill()
      $proc.WaitForExit(5000) | Out-Null
    } catch {}
  }
  foreach ($writerKey in @("StdOutWriter", "StdErrWriter")) {
    $writer = $Record[$writerKey]
    if ($writer) {
      try { $writer.Dispose() } catch {}
    }
  }
}

$timestamp = Get-Date -Format "yyyy-MM-dd-HHmmss"
$apiRecord = $null
$webRecord = $null

try {
  $apiRecord = Start-LoggedProcess `
    -FilePath "python" `
    -Arguments @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "$ApiPort") `
    -WorkingDirectory $apiRoot `
    -StdOutPath (Join-Path $repoRoot "api-ephemeral-$timestamp.out.log") `
    -StdErrPath (Join-Path $repoRoot "api-ephemeral-$timestamp.err.log")

  $webRecord = Start-LoggedProcess `
    -FilePath "node" `
    -Arguments @((Join-Path $repoRoot "node_modules\next\dist\bin\next"), "start", "--port", "$WebPort") `
    -WorkingDirectory $webRoot `
    -StdOutPath (Join-Path $webRoot "web-ephemeral-$timestamp.out.log") `
    -StdErrPath (Join-Path $webRoot "web-ephemeral-$timestamp.err.log")

  Wait-ForHttpReady -Url "http://127.0.0.1:$ApiPort/api/health" -TimeoutSeconds 30
  Wait-ForHttpReady -Url "http://127.0.0.1:$WebPort/" -TimeoutSeconds 30

  if (-not $SkipCapture) {
    $projectBase = Join-Path $artifactsRoot "project-live-$WebPort-ephemeral-$timestamp"
    $farmBase = Join-Path $artifactsRoot "farm-live-$WebPort-ephemeral-$timestamp"

    & node $captureScript `
      --url "http://127.0.0.1:$WebPort/projects/$ProjectId" `
      --output "$projectBase.png" `
      --html-dump "$projectBase.html" `
      --text-dump "$projectBase.txt" `
      --login-email $LoginEmail `
      --login-password $LoginPassword `
      --expected-url-contains "/projects/$ProjectId"
    if ($LASTEXITCODE -ne 0) {
      throw "Project screenshot capture failed"
    }

    & node $captureScript `
      --url "http://127.0.0.1:$WebPort/harvest-moon-phaser3-game/index.html?project=$ProjectId" `
      --output "$farmBase.png" `
      --html-dump "$farmBase.html" `
      --text-dump "$farmBase.txt" `
      --no-auth true `
      --markers "Harvest Moon Phaser 3 Game|Enter"
    if ($LASTEXITCODE -ne 0) {
      throw "Farm screenshot capture failed"
    }

    Write-Output "PROJECT_PNG=$projectBase.png"
    Write-Output "PROJECT_HTML=$projectBase.html"
    Write-Output "FARM_PNG=$farmBase.png"
    Write-Output "FARM_HTML=$farmBase.html"
  }
} finally {
  Stop-LoggedProcess -Record $webRecord
  Stop-LoggedProcess -Record $apiRecord
}
