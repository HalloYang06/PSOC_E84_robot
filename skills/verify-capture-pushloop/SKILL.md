---
name: verify-capture-pushloop
description: Use when continuously building this workspace and you must self-verify changes, capture fresh screenshots, compare the visible result against the intended gameplay or product behavior, and leave git traces without waiting for repeated user confirmation.
---

# Verify Capture Pushloop

Use this skill when pushing the playable AI collaboration platform forward in nonstop mode.

## Goal

Keep every implementation pass grounded in three things:
- what the user can actually see
- what the current code actually does
- what evidence is left behind

## Loop

1. Make a thin product change.
2. Run the smallest validation that proves it works.
3. Capture fresh screenshots of the changed area.
4. Inspect the screenshots yourself before claiming success.
5. Record the next gap immediately and keep moving.
6. When a milestone is real, leave git history.

## Screenshot Rules

- Prefer the local preset capture script when the work is on the farm game:
  - `D:\ai合作产品\scripts\capture-farm-presets.ps1`
- Capture before and after meaningful map or overlay changes.
- Inspect at least:
  - one changed gameplay zone
  - one unchanged control zone
  - one interior or edge-case zone if the change can affect scene transitions
- If the screenshot shows the wrong area, adjust travel coordinates and capture again.

## Validation Rules

- Do not trust code edits alone.
- For static game-shell work, verify:
  - page loads
  - expected zone is visible
  - keyboard prompt or interaction state matches the intended area
- For product behavior, verify:
  - the action changes visible state, drawer content, or world entities
  - the result survives refresh if persistence is expected

## Git Trace Rules

- Leave commits only when the slice is coherent enough to explain in one line.
- Commit message should describe a user-visible capability, not a vague refactor.
- If the change is not yet coherent, keep working instead of pushing noise.

## Cleanup Rules

- Validation-only demos, temporary buttons, fake shortcuts, and one-off debug helpers must be removed after they stop being useful.
- Keep artifacts that serve as acceptance evidence.
- Delete stale demo remnants before closing a milestone.

## Requirement Anchor

When the platform direction is unclear, re-open these docs first:
- `D:\ai合作产品\AI协作平台开发文档.md`
- `D:\ai合作产品\AI协作平台需求详细设计与未来规划.md`
- `D:\ai合作产品\AI协作平台游戏化研发基地前端详细设计.md`
- `D:\ai合作产品\项目页游戏玩法接手交接文档-2026-04-20.md`

Prefer:
- developer convenience first
- gameplay as a clearer and more enjoyable way to perform real work
- embedded robotics safety boundaries enforced by human approval

## Output Style

When reporting progress, include only:
- what changed
- what you verified
- what still looks wrong

Keep moving unless the next step is genuinely risky.
