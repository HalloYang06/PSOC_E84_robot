# Front C NPC Sync And Skill Closure Handoff

AI identity: Codex GPT-5
Role: AI collaboration platform runner/NPC workbench continuation
Date: 2026-06-01
Workspace root: `D:\ai合作产品`
Branch: `ai/game-loop-core`

## Current Status

- Cloud project validated: `fe9bd342-f5ef-4afe-9c73-e7caa2ed17dd`
- Cloud web/API: `http://106.55.62.122:3001` and `http://106.55.62.122:8011`
- Latest deployed commit: `370979d4c2b6`
- Previous real desktop sync remains the active contract:
  - runner: `runner-front-c-local`
  - computer node: `front-c-local-pc`
  - NPC seats: `front-c-7` / `前端 C 7号`, `front-c-8` / `前端 C 8号`
  - bound Codex Desktop threads:
    - `019e8121-ee19-77d2-b391-200ffbc6dad5`
    - `019e8122-6868-7222-9a71-c2eab2483dd7`
  - default delivery path must stay non-interrupting desktop automation, not click/copy/sendkeys.

## Completed In This Pass

- Preserved the previous NPC workbench and Skill Forge UX work:
  - NPC tiles expose a visible collaboration loop: outgoing needs, accepted tasks, pending confirmations, collaboration entry, capability/knowledge status, completion receipts.
  - Skill Forge exposes an NPC capability closure check for selected NPCs and links from the workbench `补能力知识` action.
- Fixed cloud build instability in `apps/web/scripts/build.cjs`:
  - runs Next build in a child Node process with `graceful-fs` preloaded
  - keeps the Codex runtime home isolation variables
  - retries once only for the observed Next manifest/static `ENOENT` race
  - does not hide normal TypeScript, lint, or compile failures
- Deployed cloud successfully after build and restart.

## Verification

- Local build:
  - `npm --workspace apps/web run build`
  - Passed with existing React hook warnings only.
- Cloud deployment:
  - `git pull --ff-only origin ai/game-loop-core`
  - `npm install`
  - `npm run build:web`
  - `RESTART=1 scripts/start-cloud-prod.sh`
  - Passed; API on `8011`, web on `3001`.
- Cloud alignment:
  - `python scripts/check_web_api_alignment.py --web-base http://106.55.62.122:3001 --api-base http://106.55.62.122:8011 --project-id fe9bd342-f5ef-4afe-9c73-e7caa2ed17dd`
  - Passed at `370979d4c2b6`.
- User-view QA:
  - report: `D:\ai合作产品\artifacts\npc-skill-closure-qa\npc-skill-closure-qa-report-20260601-125022.json`
  - screenshots:
    - `D:\ai合作产品\artifacts\npc-skill-closure-qa\skill-desktop-20260601-125022.png`
    - `D:\ai合作产品\artifacts\npc-skill-closure-qa\skill-mobile-20260601-125022.png`
    - `D:\ai合作产品\artifacts\npc-skill-closure-qa\workbench-desktop-20260601-125022.png`
  - Passed: no horizontal overflow and no user-facing internal terms such as adapter, bridge, source_thread, raw UUID.

## Risks And Notes

- Local working tree still has unrelated/unowned changes that were not staged:
  - `BACKEND_INVENTORY.md`
  - `docs/platform-agent-operating-architecture.md`
  - `apps/web/app/projects/[id]/skill-forge/skill-forge.module.css`
  - `scripts/build-soft-copyright-docs.py`
- The CSS change in `skill-forge.module.css` appears UX-related but was not authored in this pass; review before staging.
- Cloud server still has untracked runtime files such as database copies and `.codex-backups/`; do not commit or delete casually.
- Existing npm audit warnings remain: 2 moderate and 4 high.
- Existing React hook warnings remain in `2d-upgrade`, `project-playable-shell`, and `npc-tile`.

## Recommended Next Slice

- Add a visible NPC-to-NPC collaboration ledger page or drawer that groups by Need -> Task -> Dispatch -> Receipt -> Artifact, so cooperation is auditable outside each NPC tile.
- Feed Skill/Knowledge closure results into routing quality: when an NPC asks another NPC for help, show why that recipient is recommended based on role skills, knowledge, and recent receipts.
- Keep all NPC collaboration UI user-facing: avoid adapter, bridge, source_thread, JSONL, raw UUID, or local path language.
