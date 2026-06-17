# Project Progress

## 2026-06-17

- Added a perception-only stereo RGB + pretrained YOLO framework for rehab-arm VLA intake.
- Added `POST /api/rehab-arm/v1/devices/{device_id}/vision/stereo-context`.
- The platform now stores `stereo_vision_context` as latest device telemetry and uses it when building `vla_vision_context`.
- Added backend coverage for stereo context upload, dashboard visibility, and model relay preference.
- Validated with `python -m pytest tests/test_rehab_arm_sync.py -q` in `apps/api`.

