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
