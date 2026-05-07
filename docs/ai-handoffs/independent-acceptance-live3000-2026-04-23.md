# Live 3000 Independent Acceptance - 2026-04-23

## Scope
- Workspace: `D:\ai合作产品`
- Writer role: independent acceptance line only
- Write scope respected: `scripts/**` and `docs/ai-handoffs/**`
- Product UI/API files untouched in this run

## Goal
Independently verify live `3000`:
- project page entry shell
- direct farm page
- farm base rendering
- NPC overlay presence
- project entry path usability

## Files Changed
- `D:\ai合作产品\scripts\capture-auth-screenshot.mjs`
- `D:\ai合作产品\docs\ai-handoffs\independent-acceptance-live3000-2026-04-23.md`

## Script Improvements
Updated `scripts/capture-auth-screenshot.mjs` only:
1. Added `--no-auth true` mode so public/live pages can be captured through the same CDP flow without stale cookie dependency.
2. Fixed numeric arg parsing so `0` is preserved for waits/scroll values instead of falling back.
3. Made `--text-dump` always write when requested, not only on marker failure.

## URLs Tested
1. `http://127.0.0.1:3000/`
2. `http://127.0.0.1:3000/projects/10f6a858-f3e4-467c-87f5-726caa3cc2be`
3. `http://127.0.0.1:3000/harvest-moon-phaser3-game/index.html?project=10f6a858-f3e4-467c-87f5-726caa3cc2be`

## Commands Run
```powershell
Get-ChildItem -Path D:\ai合作产品\scripts | Select-Object Name,Length,LastWriteTime | Format-Table -AutoSize
Get-Content -Path D:\ai合作产品\scripts\capture-auth-screenshot.mjs -TotalCount 260
Get-Content -Path D:\ai合作产品\scripts\capture-auth-screenshot.mjs -Tail 220
Get-Content -Path D:\ai合作产品\apps\web\package.json
Get-Content -Path D:\ai合作产品\package.json
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:3000/
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:3000/projects/10f6a858-f3e4-467c-87f5-726caa3cc2be
Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:3000/harvest-moon-phaser3-game/index.html?project=10f6a858-f3e4-467c-87f5-726caa3cc2be"
node D:\ai合作产品\scripts\capture-edge-screenshot.mjs --url "http://127.0.0.1:3000/projects/10f6a858-f3e4-467c-87f5-726caa3cc2be" --output "D:\ai合作产品\artifacts\project-live-3000-independent-2026-04-23-v1.png" --html-dump "D:\ai合作产品\artifacts\project-live-3000-independent-2026-04-23-v1.html" --text-dump "D:\ai合作产品\artifacts\project-live-3000-independent-2026-04-23-v1.txt" --markers "研发基地庄园|最终回复池|harvest-moon-phaser3-game" --viewport-width 1680 --viewport-height 1260 --virtual-time-budget 14000
node D:\ai合作产品\scripts\capture-edge-screenshot.mjs --url "http://127.0.0.1:3000/harvest-moon-phaser3-game/index.html?project=10f6a858-f3e4-467c-87f5-726caa3cc2be" --output "D:\ai合作产品\artifacts\harvest-direct-3000-independent-2026-04-23-v1.png" --html-dump "D:\ai合作产品\artifacts\harvest-direct-3000-independent-2026-04-23-v1.html" --text-dump "D:\ai合作产品\artifacts\harvest-direct-3000-independent-2026-04-23-v1.txt" --markers "Harvest Moon Phaser 3 Game|NPC 属性|最近任务|最小回执|最终回复" --viewport-width 1680 --viewport-height 1260 --virtual-time-budget 14000
node D:\ai合作产品\scripts\capture-auth-screenshot.mjs --no-auth true --url "http://127.0.0.1:3000/projects/10f6a858-f3e4-467c-87f5-726caa3cc2be" --output "D:\ai合作产品\artifacts\project-live-3000-independent-2026-04-23-v4.png" --html-dump "D:\ai合作产品\artifacts\project-live-3000-independent-2026-04-23-v4.html" --text-dump "D:\ai合作产品\artifacts\project-live-3000-independent-2026-04-23-v4.txt" --viewport-width 1680 --viewport-height 1260 --wait-ms 3500
node D:\ai合作产品\scripts\capture-auth-screenshot.mjs --no-auth true --prime-url "http://127.0.0.1:3000/projects/10f6a858-f3e4-467c-87f5-726caa3cc2be" --url "http://127.0.0.1:3000/harvest-moon-phaser3-game/index.html?project=10f6a858-f3e4-467c-87f5-726caa3cc2be" --output "D:\ai合作产品\artifacts\harvest-direct-3000-independent-2026-04-23-v4.png" --html-dump "D:\ai合作产品\artifacts\harvest-direct-3000-independent-2026-04-23-v4.html" --text-dump "D:\ai合作产品\artifacts\harvest-direct-3000-independent-2026-04-23-v4.txt" --viewport-width 1680 --viewport-height 1260 --prime-wait-ms 2500 --wait-ms 4500
```

## Artifacts
Final acceptance set:
- `D:\ai合作产品\artifacts\project-live-3000-independent-2026-04-23-v4.png`
- `D:\ai合作产品\artifacts\project-live-3000-independent-2026-04-23-v4.html`
- `D:\ai合作产品\artifacts\project-live-3000-independent-2026-04-23-v4.txt`
- `D:\ai合作产品\artifacts\harvest-direct-3000-independent-2026-04-23-v4.png`
- `D:\ai合作产品\artifacts\harvest-direct-3000-independent-2026-04-23-v4.html`
- `D:\ai合作产品\artifacts\harvest-direct-3000-independent-2026-04-23-v4.txt`

Intermediate/debug artifacts kept because they document the failure mode that motivated the script fix:
- `D:\ai合作产品\artifacts\project-live-3000-independent-2026-04-23-v1.png`
- `D:\ai合作产品\artifacts\harvest-direct-3000-independent-2026-04-23-v1.html`
- `D:\ai合作产品\artifacts\harvest-direct-3000-independent-2026-04-23-v1.txt`
- `D:\ai合作产品\artifacts\project-live-3000-independent-2026-04-23-v2.txt`
- `D:\ai合作产品\artifacts\harvest-direct-3000-independent-2026-04-23-v2.txt`
- `D:\ai合作产品\artifacts\project-live-3000-independent-2026-04-23-v3.png`
- `D:\ai合作产品\artifacts\harvest-direct-3000-independent-2026-04-23-v3.png`

## Acceptance Result
### Project Page
Verified from `project-live-3000-independent-2026-04-23-v4.png`:
- Project entry shell is live on `3000`.
- Farm base is embedded under the entry shell.
- Right-side action rail is present.
- Bottom project tabs / NPC tabs render.
- Entry CTA `单独打开农场地图视图` is present.

### Direct Farm Page
Verified from `harvest-direct-3000-independent-2026-04-23-v4.png`:
- Direct farm route opens and renders the farm base normally.
- Main avatar is visible.
- Pink NPC/interaction overlay boxes are visible.
- Top-left interaction instruction stack is visible.
- Prime-from-project flow works; the direct page no longer depends on the old timeout-prone Edge screenshot path.

## Remaining Inconsistencies
1. Public/live acceptance currently lands in an unauthenticated state.
   - Project page still shows `待登录` and the login recovery task card.
   - Protected collaboration data is not visible in this acceptance pass.
2. Direct farm page shows base + overlay, but not a named NPC panel in the captured viewport.
   - The screenshot proves map rendering and interaction zones.
   - It does not yet prove that `Enter` opened a specific NPC detail panel in this independent run.
3. CDP `document.body.innerText` still contains mojibake for Chinese strings in dumps.
   - Visual PNG output is normal.
   - DOM-text markers in Chinese are not reliable enough for gating.
4. The older `capture-edge-screenshot.mjs` path is not reliable for Phaser-like live pages.
   - It succeeded for the project page once.
   - It hung on the direct farm page because the page never became a clean exiting target for that flow.

## Recommendation For Next Acceptance Run
- Reuse `scripts/capture-auth-screenshot.mjs` only.
- Prefer `--no-auth true` for public route smoke checks.
- If a fresh valid login is available, reuse the same script with auth and add one more pass for protected collaboration data.
- If the next acceptance needs proof of NPC panel opening, extend the script with a controlled keypress/click step instead of going back to the older Edge screenshot flow.
