#!/usr/bin/env bash
set -eo pipefail

ROS_SETUP="${ROS_SETUP:-/opt/ros/jazzy/setup.bash}"
WORKSPACE_DIR="${WORKSPACE_DIR:-rehab_arm_ros2_ws}"
PACKAGE_NAME="rehab_arm_psoc_bridge"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}/${WORKSPACE_DIR}"

if [[ ! -f "${ROS_SETUP}" ]]; then
  echo "ROS setup not found: ${ROS_SETUP}" >&2
  exit 2
fi

# shellcheck disable=SC1090
source "${ROS_SETUP}"

colcon build --packages-select "${PACKAGE_NAME}" --symlink-install

# shellcheck disable=SC1091
source install/setup.bash

executables="$(ros2 pkg executables "${PACKAGE_NAME}" | sort)"
echo "${executables}"
echo "${executables}" | grep -q "${PACKAGE_NAME} build_voice_pipeline_plan.py"
echo "${executables}" | grep -q "${PACKAGE_NAME} build_rehab_session_plan.py"

voice_json="$(mktemp)"
session_json="$(mktemp)"
trap 'rm -f "${voice_json}" "${session_json}"' EXIT

ros2 run "${PACKAGE_NAME}" build_voice_pipeline_plan.py \
  --robot-id medical_rehab_arm \
  --device-id sim_host \
  --wake-phrase xiao_yi_xiao_yi \
  --prompt-text start \
  | python3 -m json.tool >"${voice_json}"

ros2 run "${PACKAGE_NAME}" build_rehab_session_plan.py \
  --robot-id medical_rehab_arm \
  --device-id sim_host \
  --training-mode active_assist \
  | python3 -m json.tool >"${session_json}"

python3 - "${voice_json}" "${session_json}" <<'PY'
import json
import sys

checks = [
    (sys.argv[1], 'rehab_arm_voice_pipeline_plan_v1', 'voice_pipeline_plan_only_not_motion_permission'),
    (sys.argv[2], 'rehab_session_plan_v1', 'rehab_session_plan_only_not_motion_permission'),
]

for path, schema, boundary in checks:
    with open(path, encoding='utf-8') as handle:
        payload = json.load(handle)
    print(path, payload.get('schema_version'), payload.get('control_boundary'))
    if payload.get('schema_version') != schema:
        raise SystemExit(f'{path}: expected schema {schema}')
    if payload.get('control_boundary') != boundary:
        raise SystemExit(f'{path}: expected boundary {boundary}')

print('SIM_HOST_REHAB_USER_QA_OK')
PY
