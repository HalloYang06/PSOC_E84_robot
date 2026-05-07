# Codex Platform Autonomy Full Handoff

Date: 2026-04-22
Workspace root: `D:\ai合作产品`
Runtime mirror path used by scanned threads: `D:\ai-collab-product`
Current strategic goal: make the platform capable of using real scanned Codex threads and NPC seats to keep developing and maintaining the platform itself, while the platform UI only emphasizes final replies and recommended actions.

## Product purpose

This project is not just “another AI collaboration dashboard”.

The real purpose is:
- let the user manage AI collaboration as if they were playing inside a living platform / game world
- reduce the user’s need to manually relay work between AI threads
- make the platform capable of using real computers, real Codex threads, real NPC seats, and Git-based collaboration to keep improving the platform itself
- keep the platform UI focused on:
  - final replies
  - current responsible owner
  - current recommended action
- keep full execution detail in local Codex / local thread process rather than flooding the platform UI

In short:

> The long-term goal is “平台开发平台 / 以战养战”: the platform should increasingly use its own real AI/NPC/thread/computer structure to maintain and evolve itself, while the human mainly supervises at the product level.

## Skills currently used on this line

These are the most relevant skills for continuing this work:

### 1. `ai-collab-productizer`
Path:
- `C:\Users\18312\.codex\skills\ai-collab-productizer\SKILL.md`

Use this for:
- continuing the AI collaboration platform as a real product rather than a throwaway demo
- prioritizing unfinished core workflow links
- validating frontend and backend after each increment
- keeping focus on real platform behavior instead of decorative UI-only work

### 2. `continuous-orchestrator`
Path:
- `C:\Users\18312\.codex\skills\continuous-orchestrator\SKILL.md`

Use this for:
- keeping implementation pressure high
- continuing without repeated user confirmation
- coordinating parallel subagent investigation when it materially speeds up closure
- focusing on next blocking gap instead of repeatedly restating status

### 3. `browser-game-ui-architect`
Path:
- `C:\Users\18312\.codex\skills\browser-game-ui-architect\SKILL.md`

Use this for:
- the game-like browser shell
- the backpack-style collaboration panel
- NPC / map / HUD / in-game operation entry layout
- reducing dashboard feel and preserving a playable world feeling

### 4. `utf8-guardrail`
Local project skill path:
- `D:\ai合作产品\skills\utf8-guardrail\SKILL.md`

Use this for:
- keeping Chinese source files in clean UTF-8
- avoiding shell-written mojibake regressions
- enforcing `apply_patch`-style source edits where possible
- validating build / parse after text-heavy changes

### 5. `ai-game-backpack-collab`
Local project skill path:
- `D:\ai合作产品\skills\ai-game-backpack-collab\SKILL.md`

Use this for:
- maintaining the “背包式协作面板” structure
- keeping the platform split into:
  - 电脑接入
  - NPC 创建
  - 机房
  - 信息交流
  - Git 合作
  - Skill 库
- preserving the product requirement that AI collaboration management happens inside the game/platform, not in scattered admin pages

## Working process used on this line

The current working process is important because the platform goal is not just “build features”, but “build a platform that can increasingly develop itself”.

### Step 1: prefer real platform behavior over demo behavior
- prefer real API writes over local fake state
- prefer real scanned threads over manually invented threads
- prefer real project data over static mock cards

### Step 2: keep platform UI minimal at the top level
The first screen should increasingly show only:
- `当前推荐动作`
- `当前负责人`
- `最终回复池`

Process-heavy material should be folded or moved down.

### Step 3: validate after every meaningful increment
Normal validation loop on this line:
1. patch code
2. run frontend build
3. run backend tests
4. restart relevant service if needed
5. capture page / HTML / JSON evidence when possible
6. write or refresh handoff notes

### Step 4: use subagents surgically, not for fake parallelism
Subagents are used only when they materially help:
- one may inspect DB truth
- one may inspect visible UI state
- one may inspect product structure / UX priority

Main implementation remains integrated on the main thread.

### Step 5: platform sees outcome, local Codex sees process
Product rule:
- platform UI should emphasize final outcome and next action
- local Codex / local thread can contain the detailed implementation trail

### Step 6: temporary verification data must be removed unless it becomes real platform usage data
- transient users, transient requirement rows, transient messages should be cleaned up after validation
- but if the platform is now truly using a data path as part of self-hosting, persistent project data is acceptable and should not be treated as disposable demo state

## Source of truth
Use this document as the primary handoff.

Older handoff files under `docs/ai-handoffs/` still contain encoding pollution and partial intermediate states. Do not trust those files over this one when they conflict.

## Current platform / project facts

### Main self-hosting project
- Project name: `ai合作平台`
- Project id: `10f6a858-f3e4-467c-87f5-726caa3cc2be`

### Real thread / NPC model
- The platform now distinguishes:
  - real scanned Codex threads
  - managed NPC seats
- Real scanned threads are not hand-entered fake rows.
- Current expected real scan count is around `12`.
- Managed NPC seats are around `4`.

### Current UI target
Both `信息交流` and `Git 合作` are being reduced toward the same primary view:
- `当前推荐动作`
- `当前负责人`
- `最终回复池`

Everything else should keep moving down into folded process areas unless it is needed for first-screen decision making.

## What is already truly working

### 1. Real thread scan chain
The platform can recognize real Codex threads rather than only manual NPC seats.

Verified facts:
- real thread count is kept separate from managed NPC seats
- thread count now comes from scanned `runner_thread_scan` sources
- scanned thread `cwd` is stabilized to the English path:
  - `D:\ai-collab-product`

Relevant files:
- `D:\ai合作产品\scripts\sync-codex-session-threads.ps1`
- `D:\ai合作产品\scripts\sync-runner-threads.ps1`
- `D:\ai合作产品\apps\api\app\modules\runners\service.py`
- `D:\ai合作产品\apps\web\lib\server-data.ts`

### 2. Workstation / NPC / thread metadata parsing
Frontend now parses workstation `metadata` / `extra_data` robustly enough to surface:
- `source_workstation_id`
- `skill_loadout`
- `git_boundary`
- `scene_key`
- `sprite_key`
- `x / y`

This matters because seat cards and NPC overlays were previously losing critical workstation data.

Relevant file:
- `D:\ai合作产品\apps\web\lib\server-data.ts`

### 3. Final reply and minimal reply logic
Frontend and backend now distinguish better between:
- in-progress replies
- final replies
- AI / NPC replies
- human replies

Important frontend changes already in place:
- requirement display flow tracks:
  - `replyOwnerLabel`
  - `replyOwnerKind`
  - `hasFinalReply`
- `最终回复池` exists in both `信息交流` and `Git 合作`

Relevant file:
- `D:\ai合作产品\apps\web\app\projects\[id]\project-playable-shell.tsx`

### 4. Real autonomy sweep now creates real follow-up requirements
This is the most important “以战养战” progress from the latest round.

`autonomy-sweep` no longer only inspects active maintenance requirements. It now also considers completed maintenance requirements and can create follow-up review requirements for them.

Current maintenance template titles:
- `平台主链自检`
- `复查电脑与线程扫描`
- `人工确认平台风险点`

Follow-up suffix:
- `后续复查`

Real validated result after API restart:
- `followups = 3`
- created:
  - `平台主链自检 后续复查`
  - `复查电脑与线程扫描 后续复查`
  - `人工确认平台风险点 后续复查`

Relevant files:
- `D:\ai合作产品\apps\api\app\modules\requirements\service.py`
- `D:\ai合作产品\apps\api\tests\test_requirement_autonomy_flow.py`

### 5. Project-level autonomy summary message
Each `autonomy-sweep` now writes a project-level summary message:
- `平台自治推进摘要`

This lets the platform display that a sweep ran, even when the sweep only skipped items or only created follow-ups.

## Verified results

### Frontend / backend checks
These were passing at the latest checkpoint:
- `npm run build:web`
- `python -m pytest tests -q`

Latest backend test count:
- `77 passed`

### Real project autonomy artifacts
Use these as the strongest proof that the self-maintenance loop has started to generate real next-step work:
- `D:\ai-collab-product\artifacts\real-autonomy-followup-after-api-restart-2026-04-22.json`
- `D:\ai-collab-product\artifacts\real-autonomy-followup-clean-2026-04-22.json`
- `D:\ai-collab-product\artifacts\real-autonomy-followup-unicode-2026-04-22.json`
- `D:\ai-collab-product\artifacts\real-autonomy-sweep-2026-04-22.json`

### Real authenticated page captures
Most useful visual proofs from the latest rounds:
- `D:\ai-collab-product\artifacts\exchange-auth-cookie-fixed-2026-04-22-u.png`
- `D:\ai-collab-product\artifacts\git-auth-cookie-fixed-2026-04-22-t.png`
- `D:\ai-collab-product\artifacts\exchange-autonomy-followups-2026-04-22.png`
- `D:\ai-collab-product\artifacts\exchange-autonomy-followups-2026-04-22.html`
- `D:\ai-collab-product\artifacts\exchange-autonomy-followups-2026-04-22.txt`

### Auth token artifact used for logged-in checks
- `D:\ai-collab-product\artifacts\auth-cookie-payload-ascii.json`

This file was used to perform authenticated browser capture against the current project pages.

## Important current reality

### What is already true
- The platform can now start to create the next round of maintenance work for itself.
- The platform can identify real scanned threads.
- The platform can present a trimmed main view that is moving closer to:
  - `当前推荐动作`
  - `当前负责人`
  - `最终回复池`

### What is not fully true yet
The platform is **not yet fully autonomous**.

It is in the “can begin self-feeding” phase, not the “fully autonomous development loop is complete” phase.

Still missing:
1. stable automatic dispatch of the next step to real threads
2. stable real-thread acceptance and final reply generation without manual intervention
3. cleaner display normalization so first-screen text never falls back to historical dirty labels

## Current biggest remaining issues

### 1. Historical dirty display data still leaks into first-screen text
Backend data is much cleaner now, but historical requirements, messages, and a handful of old managed seat records still pollute display in some flows.

Subagent findings confirmed:
- one dirty historical requirement remains:
  - `b01affa4-6afa-437b-ac38-0e46a05230da`
- around `10` dirty historical collaboration messages remain
- `4` old managed workstation / seat rows were historically polluted

The frontend still needs a stronger normalization layer so first-screen labels never show old dirty names or titles even if historical rows are still present.

### 2. Final reply pool is improved but still needs to become the true primary sink
The platform is close, but not yet fully at:
- platform only shows final replies and recommended actions
- local Codex shows full process

There is still too much process material reachable too easily, and some first-screen decisions still depend on old state aggregation.

### 3. Autonomy sweep still needs the next step
Autonomy sweep now creates follow-up review requirements, which is real progress.

But the true end-state still requires:
- auto dispatch
- stable minimal reply
- stable final reply
- next requirement step

That means:
- requirement lifecycle automation is not complete yet

## Most recent subagent conclusions worth preserving

### Schrodinger
- First-screen visible dirty data is now mostly historical-data pollution, not brand new literal labels.
- Seat / requirement display normalization is the next real fix, not another large UI redesign.

### Avicenna
- Real DB data audit:
  - one clearly dirty requirement remains
  - around ten dirty historical collaboration messages remain
  - four old managed seats still had dirty historical names/descriptions

### Archimedes
- First screen should keep only:
  - `当前推荐动作`
  - `当前负责人`
  - `最终回复池`
- Demote or fold:
  - maintenance boards
  - quick dispatch
  - requirement reply detail
  - Git config / activity
  - test entry panels

### Additional latest subagent direction
- The next big step is no longer broad UI expansion.
- It is:
  - display normalization
  - stronger autonomy lifecycle
  - cleaner final-reply-first product behavior

## Exact files most likely to be touched next

### Highest priority frontend file
- `D:\ai合作产品\apps\web\app\projects\[id]\project-playable-shell.tsx`

This file currently contains:
- Exchange main view
- Git cooperation main view
- requirement aggregation / ownership / final reply logic

### Next backend autonomy file
- `D:\ai合作产品\apps\api\app\modules\requirements\service.py`

This file now contains:
- maintenance templates
- follow-up creation
- autonomy summary message
- autonomy sweep flow

### Frontend data normalization layer
- `D:\ai合作产品\apps\web\lib\server-data.ts`

## The next concrete steps

### Priority 1: harden display normalization
Patch the first-screen display flow so it does not leak dirty historical titles or seat names.

Recommended concrete work:
1. add stable frontend overrides / normalization helpers for:
   - historical dirty managed seat names
   - dirty maintenance requirement titles
2. route first-screen labels through those helpers:
   - current owner
   - requirement flow titles
   - final reply labels
   - machine-room lists if needed

### Priority 2: keep reducing the main view
Continue pushing process-oriented sections downward.

The desired first-screen state remains:
- `当前推荐动作`
- `当前负责人`
- `最终回复池`

### Priority 3: extend autonomy sweep from follow-up creation to stronger lifecycle progression
Target:
- create or dispatch next requirement step automatically
- produce stable minimal reply / final reply chain
- keep the platform focused on end-state outputs

## Safe commands to rerun during continuation

### Frontend build
From repo root:
```powershell
cd D:\ai合作产品\apps\web
npm run build:web
```

### Backend tests
From API app root:
```powershell
cd D:\ai合作产品\apps\api
python -m pytest tests -q
```

### Start API
```powershell
cd D:\ai合作产品\apps\api
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### Key authenticated screenshot entry
Use the auth cookie payload at:
- `D:\ai-collab-product\artifacts\auth-cookie-payload-ascii.json`

And current capture helper:
- `D:\ai合作产品\scripts\capture-auth-screenshot.mjs`

## Important cautions

1. Do not trust old mojibake handoff docs.
2. Do not reintroduce shell-written Chinese blobs that bypass UTF-8-safe editing.
3. Prefer `apply_patch` for source edits.
4. Keep verification artifacts, but do not create fresh demo data unless necessary.
5. If temporary requirement / user / message test data is created, remove it after verification unless the task explicitly needs persistent in-platform usage data.

## Short continuation brief
If resuming in a fresh thread, the shortest correct brief is:

> Continue from `D:\ai合作产品\docs\ai-handoffs\codex-platform-autonomy-2026-04-22-full-handoff.md`. The platform already scans real Codex threads, separates them from NPC seats, shows a trimmed main view, and autonomy-sweep now creates real follow-up maintenance requirements in the `ai合作平台` project. Next focus: clean first-screen display normalization and push the autonomy lifecycle further so the platform increasingly develops and maintains itself while the UI only emphasizes final replies, current owner, and recommended actions.
