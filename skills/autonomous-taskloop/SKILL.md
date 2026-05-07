---
name: autonomous-taskloop
description: Use when working on this workspace and you should keep moving without repeated user confirmation by reading the core project docs, choosing the next in-scope task slice, respecting role boundaries, updating docs/ai-handoffs/<role>.md, and continuing in a Git-and-document driven loop.
---

# Autonomous Taskloop

Use this skill when an AI in this repository should continue autonomously inside its assigned scope instead of stopping after each small step.

## Goal

Turn a role-based AI into a self-propelling worker that:

1. reads the core project intent first
2. finds the next smallest useful slice in its own scope
3. leaves handoff evidence in the repo
4. continues until blocked by real risk, missing facts, or cross-scope conflict

## Required Read Order

Before substantial work, read in this order:

1. `多AI并行开发分工说明-2026-04-20.md`
2. `AI协作平台开发文档.md`
3. the role-specific skill being used
4. your own `docs/ai-handoffs/<role>.md` if it exists
5. the most relevant neighboring handoff docs for upstream or downstream dependencies

## Execution Loop

Repeat this loop inside the current role boundary:

1. Reconfirm your owned scope and forbidden scope.
2. Inspect the current repo state instead of trusting prior claims.
3. Pick the next smallest real slice that advances the role goal.
4. Implement or document that slice.
5. Run the smallest honest verification available.
6. Update `docs/ai-handoffs/<role>.md`.
7. Decide the next step:
   - continue immediately if the next step is still in scope and low risk
   - hand off if another role now owns the critical path
   - stop only for real blockers, missing facts, or risky decisions

## Task Selection Rules

Choose work in this priority order:

1. unblock the main workflow
2. replace fake or placeholder behavior with real structure
3. strengthen Git-and-doc handoff quality
4. tighten safety boundaries and approval gates
5. improve secondary polish only after the core path is clearer

Prefer:

- thin vertical slices
- existing files over new systems
- repo truth over chat memory
- config or docs when implementation is not yet your scope

Avoid:

- rewriting another role's area
- starting broad refactors without a direct blocker
- demo-only shortcuts that survive task closeout
- waiting for confirmation after every tiny step

## When To Stop And Escalate

Stop and surface the issue only when one of these is true:

1. the next step would cross role boundaries
2. the repo contains conflicting edits you cannot safely integrate
3. the next step is a high-risk action requiring human approval
4. required facts are missing and cannot be discovered from local context
5. continuing would produce fake progress instead of real progress

## Handoff Discipline

You must maintain `docs/ai-handoffs/<role>.md`.

Keep it updated with:

- identity
- current responsibility scope
- completed work
- files changed
- verification status
- next recommended step
- blockers and risks

When another role should take over, write that explicitly in the handoff doc before stopping.

## Final Response Rule

When you finish a pass, report only:

1. what became true
2. what was verified
3. what should happen next
4. the handoff document path

Do not close with vague status language like "analysis complete" if a real next step was available and still in scope.

## Works Well With

- `role-claim`
- `ai-boss`
- role-specific implementation skills
- `handoff-path-output`
- verification skills such as screenshot or build validation
