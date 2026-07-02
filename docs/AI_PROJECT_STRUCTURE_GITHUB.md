# AI Project Structure GitHub

## Rehab Arm Mobile App Slice

Branch: `app/rehab-arm-mobile-stitch`

Stitch project: `projects/9733571660387876930` (`灵动康复 ArmControl`)

Phone target:

- First runnable target is a mobile Web/PWA at `apps/web/public/rehab-arm-mobile/index.html`.
- The phone App is not Python. Python/FastAPI owns the backend API only.
- A later Android package can wrap the same PWA surface with Capacitor or a native shell.

Frontend ownership:

- Stitch owns visual layout and screen language.
- Codex owns integration, backend contracts, safety boundaries, offline/PWA wiring, and QA.
- Local Stitch-derived pages live in `apps/web/public/rehab-arm-mobile/`.
- `mobile-bridge.js` may add navigation, data binding, and safe action handlers, but should not redesign the screens.

Backend ownership:

- Mobile-facing API namespace: `/api/rehab-arm/app/v1`.
- Router/service/schema files:
  - `apps/api/app/modules/rehab_arm/app_router.py`
  - `apps/api/app/modules/rehab_arm/app_service.py`
  - `apps/api/app/modules/rehab_arm/app_schemas.py`
- Database models: `apps/api/app/db/models/rehab_arm_app.py`.
- Tests: `apps/api/tests/test_rehab_arm_app_backend.py`.

Safety boundary:

- App profile, device binding, training library, plan sync, sessions, EMG summaries, and M55 intent summaries are evidence/service data.
- Training-plan sync means a structured plan was submitted to M33 review. It is not motion permission.
- The App and API must not expose CAN frames, raw motor setpoints, torque/current commands, raw motor position/velocity commands, M33 overrides, or emergency-stop release commands.
- M33 remains the final safety authority before any real motion.

Current validation:

- `python -m pytest tests/test_rehab_arm_app_backend.py -q` passes from `apps/api`.
- Mobile PWA preview runs from `apps/web/public` with `python -m http.server 4177 --bind 127.0.0.1`, then open `http://127.0.0.1:4177/rehab-arm-mobile/index.html`.

Closed-loop backend contract:

- `GET /api/rehab-arm/app/v1/me` returns the phone bootstrap payload: profile, devices, plans, active session, latest EMG, platform sync status, and a control boundary.
- `GET /api/rehab-arm/app/v1/devices/{device_id}/status` returns M33-facing state for the bound device.
- `POST /api/rehab-arm/app/v1/devices/{device_id}/m33-status` records M33 sync decisions (`sent`, `m33_accepted`, `m33_rejected`, `failed`) and reasons. It records safety authority evidence; it does not expose override controls.
- Training-plan edits increment `version`. `sync-to-device` captures `plan_version`, and `training-sessions/start` requires an `m33_accepted` sync for the current plan version on the selected device.
- AI training draft endpoints are draft-only: generate, read, accept-to-plan. Accepted drafts become normal training plans and still require M33 sync and acceptance before a training session record can start.
- Platform sync endpoints are evidence/review only and must not be interpreted as motion permission.
- Diagnostic upload endpoints store M33/mobile snapshots for review: `POST /devices/{device_id}/diagnostic-upload` and `GET /devices/{device_id}/diagnostics`.
- Offline queue endpoints (`POST/GET /offline-queue`, `POST /offline-queue/replay`) are evidence-only. The replay whitelist is limited to diagnostic upload, training-session progress, EMG summary, M55 intent summary, and platform sync; motor or CAN-like operations are rejected.
- `GET /safety-audit` returns rehab-arm App audit events for the user and bound M33 device identities so M33 accept/reject decisions are visible to the phone workflow.
