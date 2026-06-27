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
