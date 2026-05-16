---
name: ai-collab-architecture-executor
description: Continue the AI collaboration platform according to docs/platform-agent-operating-architecture.md. Use when Codex is asked to keep improving, refactor, validate, deploy, or debug the platform, especially for cloud runner dispatch, NPC/Need/Task workflows, IDE-like workbenches, screenshots, React Bits-inspired interactions, cross-platform Linux/Windows compatibility, and frequent Git commits.
---

# AI Collab Architecture Executor

## Operating Rule

Treat `docs/platform-agent-operating-architecture.md` as the product contract, not background reading. Start every substantial pass by checking the relevant section and translating it into a thin vertical slice.

Use this order unless the user explicitly changes priority:

1. P0 runner and dispatch reality: Linux/Windows onboarding, thread scan, NPC binding, no-steal multi-computer queues, accurate online/offline/reconnect states, cloud-to-desktop dispatch.
2. NPC work model: each NPC remains an independent tile with tabs for dialogue, my needs, and my tasks. User manual dispatch is first-class. NPC-created Needs must be structured, not inferred from keywords alone.
3. Shared object model: Project, Member, Workstation, NPC Seat, Computer Node, Runner, Thread Binding, Need, Task, Dispatch, Message, Review, Receipt, Artifact, Skill, Knowledge.
4. Non-NPC workbenches: reshape into IDE/control-station layout: left object index, middle real workspace, right actions/properties/evidence, bottom compact log.
5. UI polish: use restrained React Bits-style click feedback and micro-interactions where they improve clarity.

## Required Start

Run the platform alignment check before modifying or claiming current cloud behavior:

```powershell
python scripts/check_web_api_alignment.py --web-base http://106.55.62.122:3001 --api-base http://106.55.62.122:8011 --project-id 72a1cb1d-d8a8-422f-8d87-4ed071f71dbe
```

If cloud and local behavior diverge after backend changes, restart the cloud API/web with the repo script before judging the UI.

## Architecture Discipline

Do not create isolated page-specific concepts when the shared objects already exist. Prefer adapting existing models:

- `ProjectWorkstation` means logical department/workstation.
- `ProjectThreadWorkstation` means NPC employee seat.
- `ProjectComputerNode` means a real computer/cloud server/device.
- `Requirement` means Need: what an NPC lacks or asks from others.
- `Task` means work accepted by a human or NPC.
- `TaskDispatch` means a concrete delivery/execution attempt.
- `CollaborationMessage` means visible dialogue/event history.

Need and Task are opposites:

- Need belongs to the requester.
- Task belongs to the assignee.
- Dispatch is not Task.
- Message is not a queue.

## NPC Workbench Boundaries

Protect the NPC workbench unless the user explicitly approves a structural change:

- Keep the multi-NPC tiles, dialogue box, input box, role colors, structured cards, review controls, and long text drawer.
- Thread binding belongs to the main page or NPC management. The user chooses scanned thread names; do not ask users to type thread IDs in the NPC workbench.
- User messages must not require the user to approve their own message.
- NPC-to-NPC review cards appear only after an NPC creates a structured Need that names the requested capability/output and route preview says review is required.
- Never expose internal terms in user-facing UI: adapter, bridge, session JSONL, local path, source_thread, canonical, requested id, source/root/delegation, raw UUID.

## Workbench Layout Rule

For every workbench except NPC:

```text
left: actor/NPC index and selected object list
center: one active tool surface
right: tool buttons plus properties/actions/evidence drawers
bottom: compact colored log/receipt/event line
```

Do not make long scroll pages. Do not dump every function in the center. Tool buttons on the right open a focused operation page/panel. The center top bar may contain compact parameters, debug controls, filters, and mode switches.

## User-View Validation

After UI changes, validate like a user:

1. Open the real cloud page when possible.
2. Capture screenshots with the existing Playwright/CDP validation scripts or add a focused validation script.
3. Check desktop and narrow widths when layout changed.
4. Confirm no horizontal overflow.
5. Confirm NPC workbench structure contract still passes if any adjacent routing/workbench code changed.

Prefer existing scripts:

- `scripts/validate-five-workbench-click-chain-cdp.py`
- `scripts/validate-cloud-runner-workstation-isolation.py`
- `scripts/validate-cloud-npc-thread-dispatch-flow.py`
- `scripts/validate-cross-platform-runner-onboarding.py`
- `scripts/validate-professional-surfaces-fullchain-cdp.py`
- `scripts/validate-platform-dispatch-evidence-cdp.py`

## React Bits Usage

React Bits means DavidHDev/react-bits, an open-source collection of animated, customizable React components. Use it as interaction inspiration or direct dependency only after checking project fit.

Good uses:

- Button press feedback.
- Toggle/segmented-control motion.
- Drawer/tool launcher transitions.
- Status chip hover/click affordances.
- Empty-state micro-interactions.

Avoid:

- Turning operational workbenches into decorative landing pages.
- Heavy full-screen effects that hide the work.
- Purple/blue gradient dominance.
- Components that break SSR, accessibility, or mobile layout.

If importing code, prefer small copied/adapted components with clear attribution comments or a package dependency reviewed against license and bundle impact.

## Commit Discipline

Commit frequently after a verified slice. Do not leave many unrelated changes loose.

Suggested slice boundaries:

- Runner/onboarding/backend dispatch.
- Need/Task/route-preview backend.
- NPC workbench queue tabs.
- One professional workbench layout.
- Validation scripts and docs.
- Visual polish.

Before committing:

1. Run targeted tests/build.
2. Check `git status --short`.
3. Exclude secrets, SSH keys, cloud temp archives, local service binaries, databases, and runtime logs.
4. Use a concrete commit message.

## Cloud Deployment Discipline

For features the user expects on the server:

1. Build locally.
2. Sync only required files or pull the committed branch on cloud.
3. Run `npm run build:web` on cloud when frontend changed.
4. Restart with `RESTART=1 ./scripts/start-cloud-prod.sh`.
5. Re-run cloud alignment and the relevant user-flow validation.

Do not validate only with local scripts when the user is asking about cloud behavior.
