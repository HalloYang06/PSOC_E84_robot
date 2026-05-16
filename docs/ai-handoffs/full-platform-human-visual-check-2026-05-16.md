# Handoff - Full Platform Human Visual Check - 2026-05-16

Identity: Codex acting as user2 / human platform evaluator.

Role: full-platform black-box verifier and visual UX reviewer.

## What Was Done

Created and used real account `codex.user2.20260516@example.com` as user2.

Created full-check project:

- Project name: `全盘验证项目 20260516-191457`
- Project ID: `2426f4f9-cdd5-4c84-bcee-9507cf59b704`

Ran real black-box validation against `http://106.55.62.122:3001`:

- auth/session/workspace
- project create/read/config/members/presence
- invitation create/receive/accept
- outsider permission rejection
- collaboration provider/computer node/thread workstation
- workstation occupancy/adapter token/inbox
- logical workstations and lead assignment
- task/create/dispatch
- requirement/minimal receipt/final reply
- approval/create/message/approve
- knowledge document, project skill, seat skill assignment
- Boss Plan create/read
- collaboration message create/read
- Runner pairing token, registration, heartbeat, workspace, claim, log, result
- lab/git/scorecard/audit/health read-only endpoints
- logged-in page routes

Ran visual screenshot pass at desktop `1440x1000` and mobile `390x844`.

## Main Report

Detailed report:

`docs/acceptance/full-platform-human-visual-check-2026-05-16.md`

Screenshot directory:

`artifacts/visual-check`

Important screenshots:

- `artifacts/visual-check/projects-1440x1000.png`
- `artifacts/visual-check/projects-mobile-390x844.png`
- `artifacts/visual-check/project-2d-1440x1000.png`
- `artifacts/visual-check/workbench-1440x1000.png`
- `artifacts/visual-check/workbench-mobile-390x844.png`
- `artifacts/visual-check/observability-mobile-390x844.png`
- `artifacts/visual-check/ai-lab-1440x1000.png`
- `artifacts/visual-check/visual-results.json`

## Current Truth

The platform is no longer just a demo path. Desktop black-box flows mostly work end to end with real records.

Desktop UX is usable for an engineering maintainer. Project list is the cleanest page. Project control and workbench pages are dense but functional.

Mobile UX is not production-ready for the main workbench surfaces. Project list is readable; workbench and observability have serious responsive layout failures.

Runner flow is secure and works when using the intended pairing-token flow. Runner task result must use valid task statuses such as `reviewing`; `completed` is rejected.

## Open Risks

Mobile workbench layout is broken:

- `artifacts/visual-check/workbench-mobile-390x844.png`
- title becomes vertical
- right content is clipped
- grid does not collapse to one column

Mobile observability has horizontal overflow:

- `artifacts/visual-check/observability-mobile-390x844.png`
- `visual-results.json` reports `overflowX=true`

Human review is visible but not actionable enough:

- user sees one pending review
- direct `处理人工审核` CTA is missing or not prominent

Naming is inconsistent:

- project shell
- 2D developer mode
- cockpit
- workbench
- map
- project main page

Local validation was not completed:

- `python -m pytest tests -q` timed out
- `npm run build:web` timed out

## Recommended Next Pickup

Start with mobile responsive fixes:

1. `apps/web/app/projects/[id]/workbench/page.tsx` and related CSS/modules.
2. `apps/web/app/projects/[id]/observability/page.tsx` and related CSS/modules.
3. Ensure all grids collapse under `768px`.
4. Remove fixed-width card tracks or set `minmax(0, 1fr)`.
5. Re-run screenshot script and check `visual-results.json` has no mobile `overflowX=true`.

Then improve human action clarity:

1. Add prominent `处理人工审核` CTA on `/projects` and project control surfaces.
2. Normalize naming to `项目列表` / `项目控制台` / `NPC 工作台` / `观测台` / `AI 实验室`.
3. Add new-project guided setup order.

Then complete engineering validation:

1. Re-run backend tests with longer timeout or split test suites.
2. Re-run `npm run build:web` with longer timeout and inspect output.
