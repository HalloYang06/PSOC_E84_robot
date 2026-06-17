# Rehab Arm Command Center UI Handoff

AI identity: Codex GPT-5
Role: Rehab-arm command center frontend / user-view QA

## Latest Status - 2026-06-17

Updated the medical rehabilitation arm command center page to make the upper-limb EMG and action-prediction area presentation-ready while keeping the page read-only and safety-boundary-compliant.

## Changed Files

- `apps/web/app/projects/[id]/rehab-arm-control/rehab-arm-control-client.tsx`
- `apps/web/app/projects/[id]/rehab-arm-control/rehab-arm-control.module.css`
- `docs/PROJECT_PROGRESS.md`
- `docs/TROUBLESHOOTING_AND_LESSONS.md`
- `docs/screenshots/rehab-arm-muscle-prediction-qa/`

## UI Behavior

- The previous hand-built anatomy geometry was removed from the human muscle section.
- The section is now a Three.js GLB/GLTF asset slot for an open-source upper-limb muscle model.
- If a model is not reachable in the local QA environment, the page shows a polished "GLB asset slot" state instead of an ugly error.
- EMG/fatigue data is displayed as overlay cards, not as motion authority.
- Action prediction is displayed as cards sourced from model output fields, not as a real-motion command.

## Data Interfaces Reserved

Human model replacement:

- `sensor_state.human_model_url`
- `sensor_state.human_model_source`
- `sensor_state.human_model.model_url`
- `sensor_state.human_model.source`

EMG/fatigue display:

- `sensor_state.emg.channels[]`
- Supported channel fields include `channel`, `muscle`, `location`, `activation`, `value`, `rms`, `score`, `fatigue`, and `fatigue_score`.
- Current UI maps channels to shoulder/deltoid, upper-arm/biceps, forearm/wrist, and trapezius/shoulder-neck stabilization groups.

Action prediction:

- `sensor_state.motion_prediction.candidates[]`
- `sensor_state.action_prediction`
- `sensor_state.model_outputs`
- Recommended candidate fields: `label`, `confidence`, `score`, `probability`, `detail`, `reason`, `phase`, and `intent`.

All of these remain display/review data only. They are not motion permission.

## Open-Source Model Sources Noted In UI

- `juncrose/anatom-models` upper-limb GLB raw asset slot.
- AnatomyTOOL / Open3DModel upper limb reference page.
- Z-Anatomy open-source atlas reference.

Do not commit downloaded third-party model assets unless the license and attribution path are explicitly reviewed. For product demonstration, prefer a user-provided GLB through the data interface above.

## Verification

Commands:

```powershell
npx --workspace apps/web tsc --noEmit
```

User-view QA:

- Started local web on `http://localhost:3000`.
- Started local API on `http://127.0.0.1:8011`.
- Logged in with local seed account `lead@example.com`.
- Tested authenticated route: `http://localhost:3000/projects/proj_rehab_arm/rehab-arm-control`.
- Confirmed the page includes the upper-limb model section, action prediction cards, and two Three.js canvases.
- Console/page errors: none in final QA run.

Screenshots:

- `docs/screenshots/rehab-arm-muscle-prediction-qa/desktop-final-1600.png`
- `docs/screenshots/rehab-arm-muscle-prediction-qa/mobile-final-390.png`

## Follow-up QA - 2026-06-18

User-view QA found that the desktop WanAI-style rebuild could make the URDF/Three.js stage feel clipped: at 1600x1000, the main `primaryGrid` row was constrained to about 76px and relied on nested scrolling. The page now lets the main V/L/A stage expand to its natural height while keeping the right safety/model-relay command tower sticky and independently scrollable.

Additional screenshots:

- `docs/screenshots/rehab-arm-muscle-prediction-qa/desktop-qa-after-layout-fix-1600.png`
- `docs/screenshots/rehab-arm-muscle-prediction-qa/mobile-qa-after-layout-fix-390.png`

Additional checks:

- Desktop 1600x1000: no horizontal overflow; URDF canvas visible at about 779x620; human model canvas visible at about 777x360.
- Mobile 390x900: no horizontal overflow; both Three.js canvases have stable dimensions.
- Browser console: no application errors; only a Next.js Fast Refresh warning during local CSS editing.

## Display Redesign QA - 2026-06-18

The user reported the command-center frontend still looked poor. The latest pass treats the route as a presentation-grade clinical command center rather than a generic dashboard:

- Dark left device index, compact top status row, V/L/A signal strip, central URDF stage, and right safety/model-relay command tower.
- The V/L/A strip is now a compact signal track so the URDF stage appears sooner and remains the visual focus.
- The URDF stage keeps a dark high-contrast canvas; the safety/estop rail stays visible on desktop.
- Mobile keeps a single-column flow with no horizontal overflow and stable Three.js canvas sizes.

Additional screenshots:

- `docs/screenshots/rehab-arm-redesign-qa/final-desktop-1600.png`
- `docs/screenshots/rehab-arm-redesign-qa/final-mobile-390.png`

Additional checks:

- Desktop 1600x1000: no horizontal overflow; URDF canvas visible at about 813x600.
- Mobile 390x900: no horizontal overflow; URDF canvas visible at about 360x380.
- `npx --workspace apps/web tsc --noEmit` passes.

## Remaining UX Work

- The cloud/demo project with real device data should be re-QA'd after deploy because local `proj_rehab_arm` has no NanoPi device rows.
- A final licensed upper-limb muscle GLB should be selected or uploaded by the user for the public demo.
- If the GLB exposes named meshes, add a mesh-name-to-muscle mapping table so the model itself can be tinted per muscle instead of using overlay cards only.
