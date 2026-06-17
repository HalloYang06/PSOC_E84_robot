# Project Progress

## 2026-06-17

- Added a perception-only stereo RGB + pretrained YOLO framework for rehab-arm VLA intake.
- Added `POST /api/rehab-arm/v1/devices/{device_id}/vision/stereo-context`.
- The platform now stores `stereo_vision_context` as latest device telemetry and uses it when building `vla_vision_context`.
- Added backend coverage for stereo context upload, dashboard visibility, and model relay preference.
- Validated with `python -m pytest tests/test_rehab_arm_sync.py -q` in `apps/api`.
- Reworked the rehab-arm command center upper-limb/EMG section for presentation use: it now reserves an open-source GLB upper-limb muscle model slot, overlays EMG/fatigue channels, and exposes action prediction cards from `motion_prediction` / `action_prediction` / `model_outputs`.
- Added user-view QA screenshots for the authenticated local path `/projects/proj_rehab_arm/rehab-arm-control` under `docs/screenshots/rehab-arm-muscle-prediction-qa/`.
- Validated the frontend change with `npx --workspace apps/web tsc --noEmit` and browser screenshots at desktop and mobile sizes.
