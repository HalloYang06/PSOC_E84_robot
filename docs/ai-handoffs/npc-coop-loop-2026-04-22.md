# NPC Cooperative Loop 2026-04-22

Project: `ai合作平台`
Project id: `10f6a858-f3e4-467c-87f5-726caa3cc2be`

## Goal

Run a real three-thread cooperation experiment using:

- `Main Coordinator` (`codex-session-019db2a8-e685-79a3-a156-50f4f880de79`)
- `NPC1` (`codex-session-019db445-02a1-7160-9073-ffb97faed590`)
- `NPC2` (`codex-session-019db445-9180-75b3-96d4-12e110553ad9`)

The experiment is only considered successful if:

- the platform dispatches real work to `NPC1` and `NPC2`
- those existing Codex desktop threads wake up on their own
- they produce visible process output in Codex
- the platform page keeps the farm base layer intact
- the platform page can surface the cooperation proof without becoming a log wall

## Ownership

Main Coordinator owns:

- `apps/api/app/modules/projects/service.py`
- `apps/api/tests/test_runner_binding.py`
- this handoff file

NPC1 owns:

- `scripts/`
- `docs/ai-handoffs/npc1-*.md`

NPC2 owns:

- `apps/web/app/projects/[id]/project-playable-shell.tsx`
- `apps/web/lib/server-data.ts`
- `docs/ai-handoffs/npc2-*.md`

## Cooperation contract

NPC1 task shape:

- focus on the thread-side consumer path
- improve or prototype a safe local consumer for Codex inbox items
- avoid editing the farm shell or main project-page layout files
- leave a concise handoff note under `docs/ai-handoffs/npc1-*.md`

NPC2 task shape:

- focus on proof and observability for the cooperation experiment
- keep the farm visible
- keep the main three cards as the first focus
- improve only folded process visibility and related data shaping
- leave a concise handoff note under `docs/ai-handoffs/npc2-*.md`

Main Coordinator task shape:

- keep runner/thread sync reliable
- route real requirements to the correct desktop threads
- verify screenshot/build/tests and reconcile the outputs

## Verification checklist

- `npm run build:web`
- `python -m pytest tests -q`
- fresh screenshot with farm base layer visible
- proof that `NPC1` and `NPC2` threads received real platform work
- proof that those existing threads woke and produced new rollout activity
