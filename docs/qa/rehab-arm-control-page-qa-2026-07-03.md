# Rehab Arm Control Page QA - 2026-07-03

Scope: local authenticated visual QA for `http://localhost:3000/projects/proj_rehab_arm/rehab-arm-control`.

Environment:
- Web: `npm run dev -- -p 3000` from `apps/web`
- API: `uvicorn app.main:app --host 127.0.0.1 --port 8011` from `apps/api`
- Auth: `lead@example.com / password`
- Project: `proj_rehab_arm`

Results:
- Login redirect works for an unauthenticated visit.
- Authenticated access reaches the rehab arm control page without a project permission blocker when `farm_access_token` and `farm_user` cookies are present.
- Web page compiled and returned HTTP 200.
- API proxy calls returned HTTP 200 for model relay config and device dashboard.
- No page runtime errors were captured.
- Browser console warning observed: Tailwind CDN should not be used in production.

Artifacts:
- `docs/screenshots/rehab-arm-backend-qa-20260703/01-login-redirect-mobile.png`
- `docs/screenshots/rehab-arm-backend-qa-20260703/03-control-mobile-auth-fixed-cookie.png`
- `docs/screenshots/rehab-arm-backend-qa-20260703/04-control-desktop-auth.png`
- `docs/screenshots/rehab-arm-backend-qa-20260703/qa-result.json`
- `docs/screenshots/rehab-arm-backend-qa-20260703/desktop-qa-result.json`

Frontend follow-up for Stitch:
- At 390px mobile width, the control-room page renders but is heavily cropped around a desktop-style command console. It needs a phone-first home/workflow surface for patient/operator use.
- DOM automation reports no readable `innerText` or interactive `button/a` elements even though text is visible in screenshots. Accessibility/semantic markup should be restored for QA, screen readers, and reliable App automation.
- Keep the backend evidence/action boundaries: frontend should render guide actions, not invent hardware commands or motion permissions.
