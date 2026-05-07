# Codex English Path Migration - 2026-04-21

## Goal

Move the live collaboration project away from the Chinese workspace path and make the runtime use the English alias path:

- `D:/ai-collab-product`

## What changed

### 1. English workspace alias confirmed

The junction is available and valid:

- `D:\ai-collab-product` -> `D:\ai合作产品`

### 2. Project Git root updated

Project:

- `ai合作平台`
- `10f6a858-f3e4-467c-87f5-726caa3cc2be`

Live `projects.local_git_url` now points to:

- `D:/ai-collab-product`

### 3. Computer node paths updated

For project computer node:

- `local-dev-pc`

The following values now use the English path:

- `workspace_root`
- `git_root`
- `read_paths`
- `write_paths`

All are now:

- `D:/ai-collab-product`

### 4. Real scanned thread workspaces updated

For the real scanned Codex thread workstations in this project, the stored `cwd` path was migrated from:

- `D:\ai合作产品`

to:

- `D:\ai-collab-product`

This applies to the scanned thread workstations that come from the local Codex session index sync.

### 5. Human-facing doc hint updated

Updated:

- `D:\ai合作产品\apps\api\tests\README.md`

to reference:

- `D:\ai-collab-product\apps\api`

## Verification

Verified directly from the live SQLite database:

- `D:\ai-collab-product\apps\api\ai_collab.db`

Confirmed:

- `projects.local_git_url = D:/ai-collab-product`
- `project_computer_nodes.extra_data.workspace_root = D:/ai-collab-product`
- `project_computer_nodes.extra_data.git_root = D:/ai-collab-product`
- `project_thread_workstations.extra_data.cwd = D:\ai-collab-product`

## Notes

- Some old generated artifacts under `.next/` and old handoff docs still contain the Chinese path in compiled text or historical content. They are not the live runtime source of truth.
- Runtime collaboration pathing for the active platform project is now on the English alias path.
