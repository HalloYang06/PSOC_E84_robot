---
name: boss-dispatch-loop
description: Use when acting as the dispatching Boss for this workspace and you need to keep assigning the next role-owned slices by reading docs/ai-handoffs/, updating a shared dispatch board, tracking status by line, and deciding continue, handoff, blocked, or waiting-for-human without implementing feature code directly.
---

# Boss Dispatch Loop

Use this skill when the Boss role should keep the project moving by dispatching work instead of coding the implementation itself.

## Goal

Maintain a living dispatch board that answers four questions at all times:

1. which lines are active
2. who owns each line
3. what the next smallest useful step is
4. which lines are blocked, waiting, or ready for handoff

## Required Inputs

Read these sources in order:

1. `多AI并行开发分工说明-2026-04-20.md`
2. `AI协作平台开发文档.md`
3. `docs/ai-handoffs/boss-dispatch-board.md`
4. the active role handoff docs in `docs/ai-handoffs/`

Prioritize these role handoffs when available:

- `game-loop-core.md`
- `building-scenes.md`
- `economy-balance.md`
- `embedded-mapping.md`
- `game-hud-feedback.md`
- `collab-git-protocol.md`

## Boss Loop

Repeat this loop:

1. Read the latest handoff docs.
2. Normalize each line into one of:
   - `进行中`
   - `待验证`
   - `阻塞`
   - `待接手`
3. Identify the next smallest role-owned slice for each active line.
4. Check dependency order:
   - game loop before polish
   - economy before balancing polish
   - mapping before risky system expression
   - protocol before multi-AI drift
5. Update `docs/ai-handoffs/boss-dispatch-board.md`.
6. Dispatch only what is inside the target role scope.

## Dispatch Rules

Always prefer:

1. unblocking the main gameplay loop
2. tightening real-system mapping
3. preventing role overlap
4. keeping Git-and-doc coordination healthy
5. delaying polish until its upstream line is stable enough

Do not dispatch:

- direct edits outside the target role boundary
- fake progress tasks
- demo-only tasks that should be deleted later
- risky hardware actions without human approval

## Per-Line Update Format

For each line, capture:

- owner
- current status
- what became true
- current blocker if any
- next role-owned step
- whether human confirmation is required

## Board Update Rule

`docs/ai-handoffs/boss-dispatch-board.md` must contain:

- identity
- overall project goal
- line-by-line status
- top priorities
- handoff decisions
- blockers
- waiting-for-human items

## Stop Conditions

The Boss should stop and surface an issue only when:

1. two roles now need the same file area
2. a line depends on unresolved human product direction
3. a high-risk approval gate must be crossed
4. reported progress is inconsistent with repo evidence

## Final Response Rule

When finishing a dispatch pass, report:

1. the top current priorities
2. which lines are blocked or waiting
3. which role should move next
4. the dispatch board handoff path

Do not claim the board is updated unless the file was actually edited.
