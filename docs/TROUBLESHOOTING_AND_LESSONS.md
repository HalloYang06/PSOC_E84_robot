# Troubleshooting and Lessons

## 2026-06-17

- Lesson: for a first-pass vision stack, two RGB cameras are enough for coarse stereo + YOLO perception, but not for trustworthy depth or motion authority.
- Lesson: keep the stereo output as a dedicated perception record (`stereo_vision_context`) instead of overloading single camera keyframes.
- Lesson: the platform should prefer stereo vision context for VLA vision input, but must still stop at high-level suggestions.
- Validation note: the stereo context path passed backend tests after adding a new request schema and dashboard wiring.
- Lesson: the command-center human muscle view must not hand-draw an anatomy model. Keep it as a GLB/GLTF asset slot with documented open-source sources and let EMG/action-prediction data render as overlays/cards.
- QA note: local visual QA requires both web `:3000` and API `:8011`; without the API the login flow stays on `/login`, and with the wrong project id it correctly shows "项目不存在或无权限".
