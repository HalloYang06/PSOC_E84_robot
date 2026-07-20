# VLA closed-loop rollout

Date: 2026-07-21

## Current external state

- NanoPi `10.101.106.82` runs the calibrated-context-capable vision uploader.
- `/home/pi/rehab_arm_calibration/base_from_camera.json` is not present yet.
- Cloud dashboard at `http://106.55.62.122:8011` is healthy.
- Cloud plural POST `/api/rehab-arm/v1/devices/{device_id}/ik-candidates`
  exists in the historical platform source.
- Cloud latest GET was HTTP 404 during this check. The Linux agent supports
  both latest GET aliases. If neither exists, it consumes calibrated dashboard
  evidence and computes `three_motor_visual_zero_v1` locally. It rejects legacy
  generic six-axis candidates.
- SSH is documented as `ubuntu@106.55.62.122:/home/ubuntu/apps/ai-collab`, but
  the current workstation key is not authorized. Do not guess credentials.

## Before calibration day

```bash
python tools/qa/vla_closed_loop_offline_qa.py
python -m pytest tools/nanopi/vision/test_eye_to_hand_calibration.py \
  tools/nanopi/vision/test_post_calibration_preflight.py \
  tools/linux/test_vla_mujoco_execution_agent.py -q
```

## Immediately after pose capture

```bash
/home/pi/rehab_arm_calibration/activate_hand_eye_and_preflight.sh \
  /home/pi/rehab_arm_calibration/session_3motor_20260721.json
```

Do not manually rename a rejected candidate to `base_from_camera.json`.

## Linux host rollout

```bash
bash tools/linux/install_vla_mujoco_prerequisites.sh /path/to/PSOC_E84_robot
bash tools/linux/start_vla_shadow.sh
```

Run without hardware flags until the MuJoCo window reaches a fresh platform
candidate and simulation readiness is uploaded.

## Cloud API rollout boundary (optional for shadow startup)

The historical cloud source contains changes newer than the platform snapshot
in the unified repository. Never upload or overwrite the complete unified
`service.py`, `router.py`, or `schemas.py` on the server. Prepare a minimal patch
against the current cloud checkout, preserve existing plural routes and
shadow-step features, run its API tests, then use the documented
`RESTART=1 scripts/start-cloud-prod.sh` workflow.

Do not block the first Linux shadow test on this optional cloud patch. The
dashboard fallback is sufficient when L mode, accepted calibration provenance,
robot-frame target, gripper evidence, and visual lock are all present.

Required post-deploy checks:

```text
GET /health -> 200
GET /api/rehab-arm/v1/devices/dashboard?... -> 200
POST /api/rehab-arm/v1/devices/nanopi-m5/ik-candidates -> candidate evidence
GET /api/rehab-arm/v1/devices/nanopi-m5/ik-candidates/latest -> latest candidate
```

Frontend, XiaoZhi/L WebSocket, App, authentication, and unrelated runner files
are out of scope for this rollout.
