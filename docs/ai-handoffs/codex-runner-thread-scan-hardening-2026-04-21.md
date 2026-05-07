# Codex Runner / Thread Scan Hardening - 2026-04-21

## Scope
- Backend / sync chain only.
- Files touched only under:
  - `apps/api`
  - `scripts`
  - `apps/web/app/actions.ts`

## Goal
Stabilize the real computer onboarding and thread scan chain so the platform can rely on:
- real `runner`
- real `computer node`
- real `session scan`

while keeping `thread_count`, thread names, and node status consistent and reducing stale/dirty snapshots.

## What changed

### 1. Split real scanned threads from manual NPC seats
- Added workstation source exposure in runner workspace output.
- `RunnerWorkspaceWorkstationRead` now includes `source`.
- `runners.service._runner_workstation_rows()` now returns:
  - `config_id` as `workstation_id` instead of DB primary key
  - `source` from workstation metadata

This fixes the mismatch where different APIs returned different ids for the same workstation.

### 2. Keep sync replacement scoped to scan-sourced threads only
- `sync_runner_thread_workstations()` now only replaces workstation rows on the same computer node when:
  - `metadata.source == "runner_thread_scan"`
- Manual seats on the same node are preserved instead of being deleted during runner sync.

### 3. Make computer node `thread_scan` count only real scanned threads
- `collaboration.service._enrich_computer_nodes_with_thread_scan()` now groups only scan-sourced workstations.
- `thread_scan.thread_count` and `thread_scan.threads` no longer get polluted by manually created NPC seats.
- If a scan record exists but no current scan-sourced workstations remain, the node snapshot now collapses back to:
  - `thread_count = 0`
  - `threads = []`

### 4. Tighten frontend scan refresh behavior
- `apps/web/app/actions.ts`
- `请求扫描电脑线程()` now filters runner workspace rows to:
  - same `computer_node_id`
  - `source === "runner_thread_scan"`
- Removed the fallback that reused `previousThreads` when no fresh discovery was found.

This reduces stale UI scan snapshots.

### 5. Harden the local session sync script
- `scripts/sync-codex-session-threads.ps1`
- Added:
  - `MaxAgeDays` (default `14`)
  - session id dedupe
  - UTF-8 console output setup
  - `WorkspaceRoot` override
  - default preference for English path `D:\ai-collab-product`
- Synced thread metadata now includes:
  - `synced_at`
  - `cwd = D:\ai-collab-product`

## Files changed
- `D:\ai合作产品\apps\api\app\modules\runners\schemas.py`
- `D:\ai合作产品\apps\api\app\modules\runners\service.py`
- `D:\ai合作产品\apps\api\app\modules\collaboration\service.py`
- `D:\ai合作产品\apps\api\tests\test_runner_binding.py`
- `D:\ai合作产品\apps\web\app\actions.ts`
- `D:\ai合作产品\scripts\sync-codex-session-threads.ps1`

## Validation

### Automated
- `python -m pytest tests -q`
  - result: `75 passed`
- `python -m pytest D:\ai合作产品\apps\api\tests\test_runner_binding.py -q`
  - result: `5 passed`
- `npm run build:web`
  - result: passed

### Real sync chain
- Restarted API on `127.0.0.1:8000`
- Re-ran:
  - `scripts/sync-codex-session-threads.ps1`
  - with:
    - `RunnerId = runner-7e6c7eef`
    - `ProjectId = 10f6a858-f3e4-467c-87f5-726caa3cc2be`
    - `ComputerNodeId = local-dev-pc`
    - `WorkspaceRoot = D:\ai-collab-product`

### Captured verification artifact
- `D:\ai-collab-product\artifacts\runner-thread-scan-verify-2026-04-21.json`

Current verified summary from artifact:
- `thread_count = 12`
- `scanned_threads = 12`
- `managed_seats = 0` for `local-dev-pc` in this project snapshot

## Notes
- The shell output from PowerShell still visually mojibakes some Chinese thread titles in this terminal, but the backend sync logic and DB state are using UTF-8 payloads and the English workspace path.
- The important structural fix is that real scan rows and manual seats are now separated by `source`.

## Remaining risks
- `session_index.jsonl` only exposes:
  - `id`
  - `thread_name`
  - `updated_at`
  so the local sync script still cannot filter by real per-thread cwd; it can only filter by recency and dedupe by session id.
- If a future client wants “only threads for this repo”, the Codex local index format or a companion registry will need to expose repo/cwd.
- There are still historical mojibake strings elsewhere in the product, but they were intentionally left untouched because this pass was limited to runner/computer/thread-scan scope.

## Recommended next step
- Keep the platform using:
  - `computer_nodes.metadata.thread_scan`
  - scan-sourced workstations
  as the only source of truth for “real scanned threads”.
- Do not derive `thread_count` from all workstations on a node.
