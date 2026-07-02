# Troubleshooting and Lessons

## 2026-06-17

- Lesson: for a first-pass vision stack, two RGB cameras are enough for coarse stereo + YOLO perception, but not for trustworthy depth or motion authority.
- Lesson: keep the stereo output as a dedicated perception record (`stereo_vision_context`) instead of overloading single camera keyframes.
- Lesson: the platform should prefer stereo vision context for VLA vision input, but must still stop at high-level suggestions.
- Validation note: the stereo context path passed backend tests after adding a new request schema and dashboard wiring.
- Lesson: the command-center human muscle view must not hand-draw an anatomy model. Keep it as a GLB/GLTF asset slot with documented open-source sources and let EMG/action-prediction data render as overlays/cards.
- QA note: local visual QA requires both web `:3000` and API `:8011`; without the API the login flow stays on `/login`, and with the wrong project id it correctly shows "项目不存在或无权限".

## 2026-06-27

- Symptom: local rehab-arm screenshot QA against `127.0.0.1:3000` redirected to `/login` even after cloud `/api/auth/session` returned a valid `farm_access_token`.
- Environment: local Next dev server, cloud API `http://106.55.62.122:8011`, rehab-arm route `/projects/e201f41c-25a6-46e1-baf8-be6dcb83284c/rehab-arm-control`.
- Lesson: authenticated screenshot helpers that inject cookies after browser startup may not satisfy Next SSR route guards on the first document request. Use the production cloud page after deployment, or run local API/auth with matching environment, before claiming user-view QA.
- Status: QA limitation recorded; backend contract and frontend build still passed for the visual-lock-meter slice.
- Correction: the cloud test account password is `1234`, not the previously used `password`. Cloud `/api/auth/session` succeeds with `3245056131@qq.com` / `1234`, and the production rehab-arm page can be opened through the normal login form.
- Deployment note: cloud HTTP health was OK, but non-interactive SSH push/deploy was blocked by `Permission denied (publickey,password)`. Use an interactive SSH session or restore key-based auth before claiming the latest web build is deployed.
- Fix: the working cloud SSH path is `ssh -i .codex-cloud-ssh/tencent_lighthouse_ed25519 -o UserKnownHostsFile=.codex-cloud-ssh/known_hosts ubuntu@106.55.62.122`; root login is not the expected deploy path.

## 2026-07-01

- Lesson: when the camera cannot see the real target and end effector in the same frame, use a short visual memory state instead of blocking the whole VLA-lite demo. Keep the TTL small; the current platform UI treats 5 seconds as usable for dry-run evidence only.
- Safety boundary: visual memory is not a hand-eye calibration, not a 3D robot-frame coordinate, and not motion permission. It can explain why A continues observing or prepares a dry-run candidate, but real motion still requires fresh perception, calibration, simulation/human review, and M33 authority.
- Symptom: the rehab-arm human muscle panel created a Three.js canvas but still showed a GLB placeholder, even though `/assets/human/*.glb` returned HTTP 200 on the cloud host.
- Root cause: the open anatomy GLB files use `KHR_draco_mesh_compression`; the cloud host did not serve `/assets/draco/gltf/draco_decoder.wasm` and `draco_wasm_wrapper.js`, so `GLTFLoader` failed after fetching the GLB.
- Fix: deploy `apps/web/public/assets/draco/gltf/*` with the web static assets and verify the decoder URLs return 200 before judging the GLB viewer. The loader should also use partial-success semantics so one failed model layer does not hide all successfully loaded layers.
- Lesson: if a GLB canvas is present but the model is invisible, check dependent decoders/textures and then fit the camera from the loaded model bounds. Do not assume a fixed camera works for anatomy assets, because their long axis may be Y rather than the expected Z-up display orientation.

## 2026-07-02

- Stitch MCP connection note: the configured Stitch MCP is available through `mcp__stitch`. The owned project titled `灵动康复 ArmControl` resolves to `projects/9733571660387876930`; shared projects returned empty during this check.
- Lesson: do not assume the requested `docs/AI_PROJECT_STRUCTURE_GITHUB.md` exists in the AI collaboration platform repo. When missing, use the current rehab-arm architecture sources (`medical-rehab-arm-platform-development-plan.md`, `platform-agent-operating-architecture.md`, `rehab-arm-nanopi-vla-mujoco-integration.md`, and the app backend prompt) and record the substitution.
- Safety lesson: Stitch mobile screens may contain control-like UX, but backend APIs must phrase all action-adjacent flows as plan sync, M33 decision status, or evidence upload. Syncing a training plan means M33 received structured data; it is not motion authorization.
- Mobile delivery lesson: do not describe the phone APP as Python. The Python/FastAPI code is a backend API. The phone-facing target should be a PWA/mobile Web shell first, then optionally an Android wrapper or Kotlin/Compose app.
- QA note: the Stitch-generated HTML uses `cdn.tailwindcss.com`, so browser QA logs Tailwind CDN production warnings. This is acceptable for design/PWA preview, but a production/offline phone package should localize or compile the CSS instead of depending on the CDN.
- Existing regression note: `python -m pytest tests/test_rehab_arm_sync.py -q` currently fails in `test_rehab_arm_model_relay_a_semantic_routes_all_reserved_modes`, where the prompt `进入安全审核，确认仿真和急停状态` routes to `diagnostics` instead of expected `safety_review`. This appears unrelated to the new mobile APP backend/PWA slice but should be fixed before claiming the whole rehab-arm backend suite is green.
- Symptom: after the control-room stage refactor, local Playwright QA stayed on `/login` even with the right account form values, while the cloud CDP helper opened the authenticated page successfully.
- Root cause: the platform auth cookie names are `farm_access_token` and `farm_user`; guessing generic cookie names such as `codex_access_token` does not satisfy route guards. Local web without a matching local API/session also stays on the login page.
- Fix: for cloud user-view QA, use `scripts/capture-auth-screenshot-cdp.py --api-base http://106.55.62.122:8011 --login-email 3245056131@qq.com --login-password 1234`; it injects the correct `farm_*` cookies before navigation.
- Symptom: the first muscle-focus screenshot showed only the Three.js grid and dim labels, then a later 30-second capture showed the GLB model correctly.
- Lesson: anatomy GLB plus Draco decode can be slower than the rest of the page after deploy/restart. Do not conclude the model is broken from an early screenshot alone; wait long enough or inspect loader errors.
- Lesson: when a muscle label cannot be bound to a named mesh in the current GLB, dim it as an unbound/fallback label. Hard-positioning a label to "look right" is worse for a competition demo because it implies false anatomical precision.
- Symptom: uploading `apps/web/public/previews/rehab-arm-control-room/` to the cloud initially failed because `/home/ubuntu/apps/ai-collab/apps/web/public/previews/` did not exist.
- Fix: create the remote parent first with `mkdir -p /home/ubuntu/apps/ai-collab/apps/web/public/previews`, then `scp -r` the preview directory.
- Symptom: `http://106.55.62.122:3001/previews/rehab-arm-control-room/` returned the app-level not-found page even though the static files existed.
- Root cause: this Next deployment does not serve `public` subdirectories as directory indexes after redirecting away from the trailing slash.
- Fix: use the explicit static file URL `http://106.55.62.122:3001/previews/rehab-arm-control-room/index.html` for cloud review and screenshot QA.
- Lesson: when wrapping Stitch-generated mobile screens in an iframe PWA shell, bottom-nav clicks inside the iframe do not automatically update the outer shell. Use a small bridge script plus `postMessage` so each Stitch page remains visually intact while navigation stays phone-runnable.
- Lesson: keep the mobile bridge action-adjacent but not authority-adjacent. Buttons such as start, sync, calibrate, and stop should route, record intent, or submit evidence only; they must keep explaining that M33 is required before motion and the App cannot release emergency stop.
