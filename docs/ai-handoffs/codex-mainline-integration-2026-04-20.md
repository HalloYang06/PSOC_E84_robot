# Codex Mainline Integration Pass - 2026-04-20

## Scope
- Keep the imported open-source farm game as the only mainline world.
- Pull validated building flavor back into `projects/[id]` instead of growing `/dashboard`.
- Reduce HUD clutter so the map reads like a game world again.
- Keep the project buildable and future handoff-safe.

## Files changed
- `D:\aiåˆä½œäº§å“\apps\web\app\projects\[id]\project-playable-shell.tsx`
- `D:\aiåˆä½œäº§å“\apps\web\app\projects\[id]\project-playable-shell.module.css`
- `D:\aiåˆä½œäº§å“\apps\web\app\login\page.tsx`
- `D:\aiåˆä½œäº§å“\apps\web\tsconfig.json`

## What changed
0. Mainline priority changed.
   - The current priority is no longer â€œpolish the map firstâ€.
   - The current priority is â€œmake this farm map able to run real AI collaboration first, then use that platform loop to improve the project itselfâ€.

1. Mainline HUD was cut back to one persistent resource strip plus one bottom pressure card.
   - Removed the always-on conflict rail, district rail, zone prompt, world status, and legend from the mainline shell.
   - Kept the right drawer as the only heavy interaction layer.

2. Map building markers were compacted into anchored building tags.
   - Marker widths and footprints were reduced.
   - Non-active hotspot labels are hidden until hover/active.
   - Marker cards now read more like building anchors than floating dashboard tiles.

3. Headquarters drawer was tightened.
   - Reframed the project zone into a `Town command deck`.
   - Replaced the heavier overview wording with a short 3-step cycle summary.

4. Login page was rebuilt from scratch.
   - The previous file had broken encoding and unterminated strings and blocked the build.
   - It now uses the existing auth actions `ç™»å½•ç”¨æˆ·` and `æ³¨å†Œç”¨æˆ·` with clean Chinese copy.

5. Build was unblocked for Tiled resource files.
   - `apps/web/tsconfig.json` now excludes `public/**/*.tsx` so the Tiled `.tsx` asset in the imported game no longer breaks TypeScript checking.

6. The headquarters and chat zones now carry real collaboration actions.
   - `Headquarters` now exposes:
     - base broadcast form
     - task seed creation form
     - AI request ticket creation form
   - `Chat Yard` now exposes:
     - collaboration update form
     - recent collaboration message list
   - This is the first real â€œAI cooperation on the map itselfâ€ pass instead of just linking outward to tool pages.

## Validation performed
- Production build:
  - `npm run build:web` âœ…

- Mainline screenshots captured against real `projects/[id]` routes:
  - `D:\aiåˆä½œäº§å“\artifacts\project-mainline-after-hud-pass.png`
  - `D:\aiåˆä½œäº§å“\artifacts\project-mainline-after-marker-pass.png`
  - `D:\aiåˆä½œäº§å“\artifacts\project-mainline-after-compact-markers.png`
  - `D:\aiåˆä½œäº§å“\artifacts\project-mainline-after-topbar-pass.png`
  - `D:\aiåˆä½œäº§å“\artifacts\project-collab-chat.png`
  - `D:\aiåˆä½œäº§å“\artifacts\project-collab-hq-v3.png`

## Hard visual verdict
- Better:
  - The map is visible again.
  - The building flavor is finally on the `projects/[id]` mainline instead of only living in `/dashboard`.
  - The marker layer is no longer the worst offender.
  - The top bar is lighter and stops stealing as much first-screen map space.
  - Headquarters finally exposes collaboration actions in the first screen instead of hiding them below economy cards.

- Still not fully passed:
  - The map markers still feel like overlay cards rather than buildings that truly grow out of the world.
  - The right drawer is still visually stronger than the farm itself.
  - `requirements / tasks / ai` are closer to working, but the overall scene is still in a stitched state rather than a single mature game presentation.
  - The first usable collaboration loop exists, but it still needs deeper data unification with discussions / handoffs / approvals so the whole platform feels like one system.

## Best next step
1. Keep working only in `projects/[id]`.
2. Continue shrinking the visual gap between map surface and marker overlays.
3. Move the next round from â€œoverlay cleanupâ€ to â€œworld integrationâ€:
   - make buildings feel more embedded in terrain placement
   - reduce drawer dominance
   - bring more of the economy feedback into the world itself

## Do not do next
- Do not expand `/dashboard` as a second base page.
- Do not accept placeholder/error screenshots as progress.
- Do not replace the open-source farm world with a detached card-town UI.

## Latest integration update
- The map mainline now carries more than isolated submit forms.
- `Headquarters` includes a `Boss dispatch board` with:
  - latest order
  - latest handoff
  - latest approval gate
  - latest runner relay
- `Chat Yard` includes a `Relay chain summary` with:
  - open updates
  - latest recipient
  - last handoff
- `Delivery Dock` includes a runner relay section when relay timeline data exists.
- The map now has a real `Farm Maintainer` hookup path:
  - server action `bootstrapFarmMaintainer`
  - HQ card `Farm AI maintainer`
  - AI district card `Maintainer seat`
  - one-click install path that creates a default provider + workstation for watching handoffs, approvals, and runner relays

## Latest validation
- Production build:
  - `npm run build:web` passed again after the dispatch-board and relay updates.
- Refreshed production server:
  - `http://127.0.0.1:3086`
- Latest screenshots:
  - `D:\aiåˆä½œäº§å“\artifacts\project-collab-hq-v5.png`
  - `D:\aiåˆä½œäº§å“\artifacts\project-collab-chat-v3.png`
  - `D:\aiåˆä½œäº§å“\artifacts\project-collab-delivery-v1.png`
  - `D:\aiåˆä½œäº§å“\artifacts\project-collab-maintainer-ai-tall.png`
  - `D:\aiåˆä½œäº§å“\artifacts\project-collab-maintainer-hq-full.png`

## Latest hard verdict
- Better:
  - The collaboration platform is now materially more usable inside the farm route itself.
  - Headquarters, chat, approvals, and delivery are starting to read like one operator loop.
- Still not fully passed:
  - Headless screenshots still render the farm background mostly black, so these images are reliable for validating drawer/platform content, not for final world-integration judgment.
  - The right drawer still dominates the scene more than the terrain and buildings do.
  - The maintainer hookup is real, but it is still a manual install action for the current project rather than an always-present default resident.

## 2026-04-20 21:20 lightweight shell rollback
- The local `projects/[id]` shell had diverged far beyond the Git-tracked farm page, so the route was reset into a lighter wrapper instead of trying to preserve the heavy drawer stack.
- The current route now prioritizes the open-source game itself:
  - full-screen iframe to `/harvest-moon-phaser3-game/index.html`
  - compact top bar only
  - optional manual side panel instead of auto-opening drawers
  - no default `zone`-driven takeover panel
- Cleanup choices:
  - hide zero-value HUD chips
  - switch fallback project copy back to Chinese
  - keep only `åˆ‡æ¢é¡¹ç›® / å•ç‹¬æ‰“å¼€åœ°å›¾ / æ‰“å¼€é¢æ¿`
- Validation:
  - `npm run build:web` passed after the shell rewrite
  - refreshed server target remains `http://127.0.0.1:3086/projects/1d243fb6-a146-4985-b6ab-a41ac30577a2`
  - latest cleanup screenshot: `D:\aiåˆä½œäº§å“\artifacts\project-clean-shell-v2.png`
- Remaining risk:
  - headless screenshots still show the iframe area as black, so live browser checking is the source of truth for whether the avatar/game world is visible.

## 2026-04-20 21:37 Codex bridge and team bootstrap
- The route now carries an in-game team model inspired by the `gstack` direction:
  - one visible operator team
  - Codex as the first real connected member
  - later seats reserved for dispatch and machine/runner control
- Real local bridge path added:
  - `apps/web/lib/local-agent-bridge.ts`
  - `dispatchCodexBridgeCommand` server action
  - inbox files written to `docs/ai-handoffs/inbox/project-<projectId>-codex.json`
  - mirrored markdown log written to `docs/ai-handoffs/inbox/project-<projectId>-codex.md`
- Project route changes:
  - panel can be opened directly with `?panel=team`
  - manual `å®‰è£… Codex é©»åœºå¸­ä½`
  - manual `ç»™ Codex ä¸‹æŒ‡ä»¤`
  - visible `Codex æ”¶ä»¶ç®±`
- Stability fix:
  - added `apps/web/pages/_document.tsx` so the dev route stops failing on missing `_document`
- Validation:
  - dev route recovered on `http://127.0.0.1:3086/projects/1d243fb6-a146-4985-b6ab-a41ac30577a2?panel=team`
  - latest team screenshot: `D:\aiåˆä½œäº§å“\artifacts\project-ai-team-panel-v3.png`
## 2026-04-21 00:12 ÈıÒ³½á¹¹ÊÕÁ²
- ÒÑÉ¾³ı¾É app Â·ÓÉÄ¿Â¼£¬Ö»±£ÁôÈıÌõÖ÷Ïß£º`/login`¡¢`/projects`¡¢`/projects/[id]`¡£
- ÖØĞ´ÁËµÇÂ¼Ò³£¬È¡Ïû¾ÉµÄ¶àÈë¿ÚÌø×ª£¬Ö»±£ÁôµÇÂ¼/×¢²á²¢ÔÚ³É¹¦ºó»Øµ½ÏîÄ¿¹ÜÀíÒ³»òÖ¸¶¨ returnTo¡£
- ÖØĞ´ÁËÏîÄ¿¹ÜÀíÒ³£¬Í³Ò»³Ğ½Ó£ºÒÑÓĞÏîÄ¿ÁĞ±í¡¢½ÓÊÜÑûÇë¡¢ĞÂ½¨ÏîÄ¿¡£
- ÖØĞ´ÁËÏîÄ¿ÓÎÏ·Ò³¿Ç£¬¶¥²¿Ö»±£Áô `»ØÇ°ÖÃÒ³` ºÍ `´ò¿ª/ÊÕÆğÍÅ¶ÓÃæ°å`£¬ÓÎÏ·Ò³¼ÌĞø³Ğ½Ó AI Ï¯Î»¡¢µçÄÔÉ¨Ãè¡¢Ïß³Ì·¢Ö¸Áî¡£
- ÓÎÏ·±¾ÌåÀïÈÔ±£ÁôÓÒÉÏ½Ç `»ØÇ°ÖÃÒ³`£¬´ÓÅ©³¡ÄÚ¿ÉÖ±½Ó»Øµ½ `/projects`¡£
- `npm run build:web` ÒÑÍ¨¹ı£¬Next Â·ÓÉ±íÏÖÎª£º`/`¡¢`/_not-found`¡¢`/login`¡¢`/projects`¡¢`/projects/[id]`¡£
- ĞÂ½ØÍ¼£º
  - `artifacts/login-clean-3page.png`
  - `artifacts/projects-clean-3page.png`£¨Î´µÇÂ¼Ì¬»áÌø»ØµÇÂ¼Ò³£©
  - `artifacts/game-clean-3page.png`
- µ±Ç°ÕæÊµÊ£ÓàÎÊÌâ£º
  - `/projects` µÄÒÑµÇÂ¼¹ÜÀíÒ³»¹ĞèÒªÔÚÕæÊµµÇÂ¼Ì¬ÏÂÔÙ²¹Ò»ÕÅ½ØÍ¼ÑéÖ¤¡£
  - ÓÎÏ· iframe µÄÎŞÍ·½ØÍ¼ÈÔÈ»Æ«ºÚ£¬µ«Íâ¿ÇÓë·µ»ØÁ´ÒÑÕıÈ·¡£
  - ÏÂÒ»²½ÓÅÏÈ¼ÌĞø´òÍ¨¡°µçÄÔÔÚÏß×¢²á -> Ïß³ÌÉ¨Ãè -> Ö¸ÁîÖ¸¶¨Ïß³Ì -> »ØÖ´¡±ÕâÌõÁ´£¬²»ÔÙÀ©¾ÉÒ³Ãæ¡£
