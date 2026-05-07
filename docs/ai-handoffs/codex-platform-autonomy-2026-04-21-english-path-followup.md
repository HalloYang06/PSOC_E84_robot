# Codex Platform Autonomy Follow-up - 2026-04-21

## Context

This follow-up continues the `ai合作平台` autonomy line after the English-path migration. The active live project is:

- project name: `ai合作平台`
- project id: `10f6a858-f3e4-467c-87f5-726caa3cc2be`

The runtime backbone now uses the English workspace alias:

- `D:\ai-collab-product`

## What was completed

### 1. Final-reply pool is live in the platform UI

The project shell now exposes a dedicated `最终回复池` in both:

- `信息交流`
- `Git 合作`

Each tab separately summarizes:

- `AI/NPC 最终回复`
- `人工最终回复`
- `未知来源回复`

This keeps the platform surface focused on minimal/final outcomes instead of flooding the user with step-by-step process logs.

### 2. English-path runtime migration is active

The live SQLite data was updated so the main runtime path points at the English alias:

- `projects.local_git_url = D:/ai-collab-product`
- `project_computer_nodes.extra_data.workspace_root = D:/ai-collab-product`
- `project_computer_nodes.extra_data.git_root = D:/ai-collab-product`
- `project_thread_workstations.extra_data.cwd = D:\ai-collab-product`

Related migration handoff:

- `D:\ai合作产品\docs\ai-handoffs\codex-english-path-migration-2026-04-21.md`

### 3. Platform maintenance skill slugs now render as readable labels

The frontend default Skill library was expanded so the platform’s self-maintenance NPC seats no longer show raw slugs or historical mojibake.

Covered mappings:

- `mainline-integration` -> `主线整合`
- `platform-dispatch` -> `平台派单`
- `requirement-routing` -> `需求分流`
- `git-collab` -> `Git 协作`
- `requirement-triage` -> `需求分诊`
- `result-relay` -> `结果回传`
- `computer-onboarding` -> `电脑接入`
- `thread-scan` -> `线程扫描`
- `ack-followup` -> `回执跟进`
- `skill-maintenance` -> `技能维护`
- `npc-loadout` -> `NPC 装配`
- `git-boundary` -> `Git 边界`

This change was made in:

- `D:\ai合作产品\apps\web\app\projects\[id]\project-playable-shell.tsx`

## Validation

### Frontend

Executed from `D:\ai-collab-product`:

- `npm run build:web`

Result: passed.

### Backend

Executed from `D:\ai-collab-product\apps\api`:

- `python -m pytest tests -q`

Result: `72 passed`.

### Page-level verification

Saved live page HTML snapshots:

- `D:\ai-collab-product\artifacts\platform-machine-room-verify-2026-04-21.html`
- `D:\ai-collab-product\artifacts\platform-skills-verify-2026-04-21.html`

Verified those rendered pages contain the new readable labels, including:

- `主线整合`
- `平台派单`
- `需求分流`
- `Git 协作`
- `线程扫描`
- `NPC 装配`
- `Git 边界`
- `最终回复池`

## Current state

The platform is now closer to the intended operating model:

- real scanned threads remain the execution backbone
- NPC seats act as platform-facing identities
- the platform UI is gradually being reduced to:
  - final replies
  - current owners
  - current recommended action
- the local Codex client remains the place for full process logs

## Remaining follow-up

1. Continue cleaning historical stored metadata/messages that still carry old mojibake from earlier rounds.
2. Keep shrinking the player-facing platform view so only:
   - final replies
   - current owners
   - current recommended action
   stay prominent.
3. Continue the autonomy line so the platform can:
   - dispatch to real scanned threads
   - receive minimal/final agent replies
   - maintain and improve itself through those NPC/thread lanes.

## Latest progress in this round

### Real thread scan hardening

The real computer/thread lane was tightened so only scanned runner threads count toward the platform thread total:

- `thread_count = 12`
- `scanned_threads = 12`
- all scanned threads carry `source = runner_thread_scan`
- `cwd` now stabilizes on `D:\ai-collab-product`

Reference handoff:

- `D:\ai合作产品\docs\ai-handoffs\codex-runner-thread-scan-hardening-2026-04-21.md`

### Requirement dispatch/final-reply APIs are now the canonical backend path

Backend added:

- `POST /api/requirements/{requirement_id}/dispatch`
- `POST /api/requirements/{requirement_id}/final-reply`

Those APIs now own the stable requirement lifecycle for:

- queued
- in_progress
- done

Reference handoff:

- `D:\ai合作产品\docs\ai-handoffs\codex-api-autonomy-dispatch-2026-04-21.md`

### Frontend action wiring updated

The player-facing `登记已接单 / 登记已完成` flow in:

- `D:\ai合作产品\apps\web\app\actions.ts`

was moved off the old direct message write path and now uses the requirement APIs above, so platform state and final replies follow the same backend rules.

### Visual verification added

Fresh screenshot verification was captured from the live 3086 service:

- `D:\ai-collab-product\artifacts\login-page-verify-2026-04-21.png`
- `D:\ai-collab-product\artifacts\team-page-verify-2026-04-21-c.png`

The latest team-page screenshot confirms:

- the duplicate in-panel navigation row is gone
- the panel still opens on `信息交流`
- the top action bar remains:
  - `回前置页`
  - `收起背包`
  - `单独打开地图`

## Current known gaps

1. The unauthenticated screenshot still shows `NPC 席位 = 0`; this is expected for the public page and still needs a clean logged-in visual verification path.
2. The source shell file still contains many historical mojibake literals outside the specific blocks repaired this round; runtime output is partially stabilized, but source cleanup is still incomplete.
3. The self-maintenance platform still needs one more tightening pass so the main view privileges:
   - final replies
   - current owners
   - current recommended action
   over all other operational detail.

## Latest UI tightening pass

Scope of this pass was limited to:

- `D:\ai合作产品\apps\web\app\projects\[id]\project-playable-shell.tsx`

Goal:

- tighten `信息交流`
- tighten `Git 合作`
- keep the main visible layer focused on:
  - final replies
  - current owners
  - current recommended action

What changed:

- Removed the duplicated top summary card grids from both `信息交流` and `Git 合作` that repeated:
  - pending counts
  - ack counts
  - active target counts
- Kept only three top-level blocks in both tabs:
  - `当前推荐动作`
  - `当前负责人`
  - `最终回复池`
- Moved noisy process-heavy sections into folded details:
  - maintenance board
  - ownership breakdown
  - dispatch/ack detail
  - dispatch maintenance operations

Validation:

- `npx tsc --noEmit --pretty false --project D:\ai合作产品\apps\web\tsconfig.json` passed
- `npm run build:web` passed
- live 3086 service was restarted
- fresh screenshots captured:
  - `D:\ai合作产品\artifacts\team-exchange-mainview-tightened-2026-04-21.png`
  - `D:\ai合作产品\artifacts\team-git-mainview-tightened-2026-04-21.png`

Visual result:

- `信息交流` now opens with:
  - final reply center intro
  - current recommended action
  - current owner cards
  - final reply pool
  - process details folded
- `Git 合作` now opens with:
  - Git middle-layer intro
  - current recommended action
  - current owner cards
  - final reply pool
  - dispatch and maintenance process folded

Suggested next thread follow-up:

- Clean the remaining historical mojibake literals in untouched sections of `project-playable-shell.tsx` with small section-by-section patches.
- Add one logged-in/member-state screenshot path so the tightened view is also verified with non-empty real project data, not only the public/empty state.
