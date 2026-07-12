[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "../..")).Path
Set-Location $repoRoot

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,

        [Parameter(Mandatory = $true)]
        [string[]]$ArgumentList
    )

    Write-Host "> $FilePath $($ArgumentList -join ' ')"
    & $FilePath @ArgumentList
    if ($LASTEXITCODE -ne 0) {
        throw "$FilePath exited with code $LASTEXITCODE"
    }
}

$trackedBefore = @(& git status --short --untracked-files=no)
if ($LASTEXITCODE -ne 0) {
    throw "git status failed before verification"
}
$trackedBeforeText = $trackedBefore -join "`n"
$trackedDiffBefore = @(& git diff --binary HEAD --)
if ($LASTEXITCODE -ne 0) {
    throw "git diff failed before verification"
}
$trackedDiffBeforeText = $trackedDiffBefore -join "`n"
$verificationError = $null

try {
    Invoke-Checked python @("-m", "pytest", "tools/test", "-q")
    Invoke-Checked python @("-m", "pytest", "ai/vla/tests", "-q")
    Invoke-Checked python @(
        "-m", "pytest",
        "platform/api/tests/test_rehab_arm_app_backend.py",
        "platform/api/tests/test_rehab_arm_app_live_emg.py",
        "platform/api/tests/test_rehab_arm_sync.py",
        "platform/api/tests/test_rehab_arm_vla_closed_loop_status.py",
        "-q"
    )
    Invoke-Checked npm @("--prefix", "platform", "ci")
    Invoke-Checked npm @("--prefix", "platform", "run", "build:web")
    Invoke-Checked npm @("--prefix", "apps/mobile", "ci")
    Invoke-Checked npm @("--prefix", "apps/mobile", "run", "sync:web")

    if ($null -ne (Get-Command docker -ErrorAction SilentlyContinue)) {
        Invoke-Checked docker @(
            "compose", "-f", "platform/deploy/docker-compose.yml", "config", "--quiet"
        )
        Invoke-Checked docker @(
            "compose", "-f", "platform/deploy/docker-compose.public.yml", "config", "--quiet"
        )
    }
    else {
        Write-Host "Docker CLI not found; compose config checks skipped."
    }
}
catch {
    $verificationError = $_
}

$trackedAfter = @(& git status --short --untracked-files=no)
if ($LASTEXITCODE -ne 0) {
    throw "git status failed after verification"
}
$trackedAfterText = $trackedAfter -join "`n"
$trackedDiffAfter = @(& git diff --binary HEAD --)
if ($LASTEXITCODE -ne 0) {
    throw "git diff failed after verification"
}
$trackedDiffAfterText = $trackedDiffAfter -join "`n"

Write-Host "> git status --short"
& git status --short
if ($LASTEXITCODE -ne 0) {
    throw "final git status failed"
}

if (
    $trackedAfterText -ne $trackedBeforeText -or
    $trackedDiffAfterText -ne $trackedDiffBeforeText
) {
    throw "Verification generated tracked changes.`nBefore:`n$trackedBeforeText`nAfter:`n$trackedAfterText"
}

if ($null -ne $verificationError) {
    throw $verificationError
}

Write-Host "Repository verification passed without generating tracked changes."
