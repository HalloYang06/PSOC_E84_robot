param(
  [string]$WorkstationId = "codex-session-019db461-8c20-7df2-840f-1bb7c5bce410",
  [switch]$SkipWorkstationPatchSmoke
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$apiRoot = Join-Path $repoRoot "apps\api"

$tests = @(
  "tests/test_runner_relay.py::test_runner_relay_command_round_trip",
  "tests/test_runner_relay.py::test_runner_relay_command_accepts_structured_dispatch_id_without_legacy_body_hint",
  "tests/test_requirement_autonomy_flow.py::test_requirement_autonomy_sweep_dispatches_and_creates_follow_up_for_platform_templates",
  "tests/test_requirement_autonomy_flow.py::test_runner_completion_backfills_requirement_final_reply_and_follow_up"
)

Write-Host "Verifying AI collaboration loop in $apiRoot" -ForegroundColor Cyan
Write-Host ""
Write-Host "This proof run covers:" -ForegroundColor Yellow
Write-Host "1. runner command -> ack -> complete -> task status round trip"
Write-Host "2. structured dispatch_id bridging without legacy body parsing"
Write-Host "3. requirement autonomy sweep -> dispatch -> follow-up dispatch"
Write-Host "4. runner completion -> minimal ack/final reply -> follow-up requirement"
Write-Host "5. live workstation PATCH smoke after fresh API restart"
Write-Host "6. live NPC requirement audit for NPC1/NPC2/NPC3"
Write-Host "7. live NPC bridge audit for local consumer wrappers/state"
Write-Host ""

Push-Location $apiRoot
try {
  python -m pytest @tests -q
}
finally {
  Pop-Location
}

if (-not $SkipWorkstationPatchSmoke -and $WorkstationId) {
  Write-Host ""
  Write-Host "Running live workstation PATCH smoke..." -ForegroundColor Yellow
  Push-Location $repoRoot
  try {
    python scripts/verify-workstation-patch-smoke.py --workstation-id $WorkstationId
  }
  finally {
    Pop-Location
  }
}

Write-Host ""
Write-Host "Running live NPC requirement audit..." -ForegroundColor Yellow
Push-Location $repoRoot
try {
  python scripts/verify-live-npc-requirements.py --seats NPC1 NPC2 NPC3
}
finally {
  Pop-Location
}

Write-Host ""
Write-Host "Running live NPC bridge audit..." -ForegroundColor Yellow
Push-Location $repoRoot
try {
  python scripts/verify-live-npc-bridges.py --seats NPC1 NPC2 NPC3
}
finally {
  Pop-Location
}
