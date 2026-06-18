# Platform Full QA - 2026-06-18

Scope: login/account access, project isolation, rehab-arm command center, model assets, API health, and targeted backend tests.

## Summary

The database was not deleted. The local API is connected to `apps/api/ai_collab.db`, which exists and is about 1.0 GB. The `users` table still contains 6 active users, including:

- `lead@example.com`
- `3245056131@qq.com`

The reported "cannot log in" symptom was reproduced as a project-permission confusion:

- `3245056131@qq.com` can log in successfully.
- That user owns project `e201f41c-25a6-46e1-baf8-be6dcb83284c` named `医疗康复机械臂`.
- That user does not have permission for seed project `proj_rehab_arm`.
- Opening `/projects/proj_rehab_arm/rehab-arm-control` with that user correctly returns permission denied.
- Opening `/projects/e201f41c-25a6-46e1-baf8-be6dcb83284c/rehab-arm-control` works.

## Fix Applied

Improved the rehab-arm command-center no-permission page so it shows:

- current account label
- the blocked `project_id`
- a clear instruction to return to project list and enter the authorized `医疗康复机械臂` project

Changed file:

- `apps/web/app/projects/[id]/rehab-arm-control/page.tsx`

## Screenshots

- `docs/screenshots/platform-full-qa-2026-06-18/08-project-list-real-user.png`
- `docs/screenshots/platform-full-qa-2026-06-18/09-real-project-main.png`
- `docs/screenshots/platform-full-qa-2026-06-18/10-clear-no-permission.png`
- `docs/screenshots/platform-full-qa-2026-06-18/11-real-project-after-permission-fix.png`

## Verification

Commands:

```powershell
npx --workspace apps/web tsc --noEmit
python -m pytest apps/api/tests/test_rehab_arm_sync.py -q
python -m pytest apps/api/tests/test_runner_relay.py apps/api/tests/test_workstation_inbox.py -q
```

Results:

- web TypeScript: passed
- rehab-arm API tests: 25 passed
- runner relay / workstation inbox tests: 108 passed

## Remaining Risks

- Legacy login currently authenticates by existing email and does not validate password. This predates this QA pass and should be addressed as a separate auth-hardening task before production.
- There are two rehab-arm-like projects in local seed/user data. The platform should avoid sending users direct links to `proj_rehab_arm` unless they are members of that seed project.
- Browser QA on the real project showed no horizontal overflow and 2 visible Three.js canvases. Console warnings were WebGL `ReadPixels` performance warnings caused by screenshot capture, not app errors.
