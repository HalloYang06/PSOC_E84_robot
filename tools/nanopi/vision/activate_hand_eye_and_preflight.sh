#!/usr/bin/env bash
set -euo pipefail

SESSION=${1:-/home/pi/rehab_arm_calibration/session_3motor_20260721.json}
CALIBRATION_DIR=${REHAB_ARM_CALIBRATION_DIR:-/home/pi/rehab_arm_calibration}
TOOL_DIR=${REHAB_ARM_CALIBRATION_TOOL_DIR:-/home/pi/rehab_arm_calibration}

python3 "$TOOL_DIR/eye_to_hand_calibration.py" activate-session \
  --session "$SESSION" \
  --output "$CALIBRATION_DIR/base_from_camera.json" \
  --candidate-output "$CALIBRATION_DIR/base_from_camera.candidate.json" \
  --finalized-session-output "$CALIBRATION_DIR/session_3motor_with_fk.json"

python3 "$TOOL_DIR/post_calibration_preflight.py" \
  --calibration "$CALIBRATION_DIR/base_from_camera.json" \
  --context /home/pi/rehab_vla_frames/latest_platform_context.json \
  --wait-s 8
