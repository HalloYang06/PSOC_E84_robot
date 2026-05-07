# Education 2D Planning Handoff - 2026-04-30

## Scope

Created planning docs for the new education 2D RPG entry. No app code or existing development-board entry files were modified.

## New Docs

- `docs/ai-requirements/education-2d-overall-plan-2026-04-30.md`
- `docs/ai-requirements/education-2d-balance-car-script-2026-04-30.md`
- `docs/ai-requirements/education-2d-commercial-asset-prompts-2026-04-30.md`

## Product Decisions Captured

- Education 2D must be an independent entrance and must not touch the current development-board entrance.
- Pre-game setup requires AI provider/model selection and API Key configuration.
- First main quest is the balance car project.
- Core loop: NPC task assignment -> module logic minigames -> simulation wiring -> PID tuning -> compile -> human-confirmed flashing -> rewards.
- Commercial asset prompts require original, non-branded, transparent-background assets with licensing review.
- Poster reference added: A Agent dual-entry homepage, black Linux box, green education panel, blue developer panel, isometric voxel RPG map, engineer NPC stations.
- Education entry can share the A Agent brand homepage with developer entry, but its route/module implementation should stay isolated.

## Recommended Next Step

Freeze route/module boundaries before implementation:

```text
/education-2d
/education-2d/setup
/education-2d/world
/education-2d/projects/balance-car
```

Then implement a thin vertical slice: model setup page -> small Phaser map -> 3 NPC interactions -> one code quiz -> task reward.
