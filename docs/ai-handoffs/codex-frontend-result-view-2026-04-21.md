# Codex Frontend Result View Tightening ? 2026-04-21

## Scope

Limited to:

- `D:i????pps\webpp\projects\[id]\project-playable-shell.tsx`
- `D:i????pps\webpp\projects\[id]\project-playable-shell.module.css`

No other product routes or backend files were changed in this pass.

## Goal

Keep the team backpack main view focused on:

- final replies
- current owners
- current recommended action
- status at a glance: `???? / ??? / ???`

And reduce duplicate counters and process noise.

## What changed

### 1. Added a shared top-level result summary card set

Created a shared `ownershipStatusCards` summary in `project-playable-shell.tsx` so both:

- `????`
- `Git ??`

now open with the same four result-first cards:

- `????`
- `???`
- `???`
- `?????`

Each card now shows:

- the count
- the current representative target
- a short next-action hint

This replaces the old duplicated owner/ack summary blocks.

### 2. Reduced duplicate badges in the main visible layer

Removed repeated `stateBadge` counters from the top visible sections of both tabs, including:

- `?????`
- `?????`
- folded maintenance/ownership/dispatch headings in the primary visible layer

The result-first layer is now quieter and easier to scan.

### 3. Kept process detail folded

The process-heavy sections remain under folded details instead of the top visible layer:

- maintenance board
- ownership breakdown
- dispatch/ack detail
- command/inbox block

This keeps the main surface focused on outcome, not process.

### 4. Preserved UTF-8 clean edits in this pass

All manual edits in this pass were made through patch-based updates only.
No whole-file re-save commands were used.

## Files changed

- `D:i????pps\webpp\projects\[id]\project-playable-shell.tsx`
- `D:i????pps\webpp\projects\[id]\project-playable-shell.module.css`

## Verification

### Build and tests

- `npm run build:web` ?
- `python -m pytest tests -q` ? (`75 passed`)

### Logged-in visual verification

Captured real logged-in screenshots against project:

- `ai????` (`10f6a858-f3e4-467c-87f5-726caa3cc2be`)

Artifacts:

- `D:i????rtifacts\platform-team-exchange-2026-04-21-final.png`
- `D:i????rtifacts\platform-team-git-2026-04-21-final.png`
- `D:i????rtifacts\platform-team-exchange-2026-04-21-final.html`
- `D:i????rtifacts\platform-team-git-2026-04-21-final.html`

### Cleanup after verification

Temporary verification account and membership were removed after capture.

## Remaining risks

1. The logged-in screenshots show the updated content, but the page styling is currently not rendering correctly in that capture path. The content is correct, but the shell styling appears degraded in the browser-capture result and needs a separate follow-up.
2. Historical mojibake still exists in untouched parts of the wider project. This pass only guaranteed no new mojibake in the edited scope.
3. The current result view is much tighter, but there is still more room to reduce lower folded sections once the visual styling issue is stabilized.
