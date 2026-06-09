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
echo "${executables}" | grep -q "${PACKAGE_NAME} build_command_center_sync_plan.py"
echo "${executables}" | grep -q "${PACKAGE_NAME} check_command_center_sync_plan.py"

voice_json="$(mktemp)"
session_json="$(mktemp)"
sync_json="$(mktemp)"
sync_quality_json="$(mktemp)"
trap 'rm -f "${voice_json}" "${session_json}" "${sync_json}" "${sync_quality_json}"' EXIT

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

ros2 run "${PACKAGE_NAME}" build_command_center_sync_plan.py \
  --robot-id medical_rehab_arm \
  --device-id sim_host \
  --tenant-id tenant_rehab_lab \
  --workspace-id workspace_rehab_lab \
  --user-id sim_operator \
  --patient-id patient_dry_run \
  --session-id session_sim_host_qa \
  --profile-id profile_sim_host_qa \
  --base-url http://server.example/api/rehab-arm/v1 \
  | python3 -m json.tool >"${sync_json}"

ros2 run "${PACKAGE_NAME}" check_command_center_sync_plan.py \
  --plan "${sync_json}" \
  | python3 -m json.tool >"${sync_quality_json}"

python3 - "${voice_json}" "${session_json}" "${sync_json}" "${sync_quality_json}" <<'PY'
import json
import sys

checks = [
    (sys.argv[1], 'rehab_arm_voice_pipeline_plan_v1', 'voice_pipeline_plan_only_not_motion_permission'),
    (sys.argv[2], 'rehab_session_plan_v1', 'rehab_session_plan_only_not_motion_permission'),
    (sys.argv[3], 'command_center_sync_plan_v1', 'server_sync_plan_only_not_motion_permission'),
]

for path, schema, boundary in checks:
    with open(path, encoding='utf-8') as handle:
        payload = json.load(handle)
    print(path, payload.get('schema_version'), payload.get('control_boundary'))
    if payload.get('schema_version') != schema:
        raise SystemExit(f'{path}: expected schema {schema}')
    if payload.get('control_boundary') != boundary:
        raise SystemExit(f'{path}: expected boundary {boundary}')

with open(sys.argv[3], encoding='utf-8') as handle:
    sync_plan = json.load(handle)
if not sync_plan.get('requests'):
    raise SystemExit('command center sync plan has no planned REST requests')
if sync_plan['auth_context'].get('tenant_id') != 'tenant_rehab_lab':
    raise SystemExit('command center sync plan lost tenant context')
if 'can_frame' not in sync_plan.get('forbidden_outputs', []):
    raise SystemExit('command center sync plan must explicitly forbid CAN frames')

with open(sys.argv[4], encoding='utf-8') as handle:
    quality = json.load(handle)
if quality.get('schema_version') != 'command_center_sync_quality_report_v1':
    raise SystemExit('command center sync quality report schema mismatch')
if quality.get('ok') is not True:
    raise SystemExit(f'command center sync quality gate failed: {quality}')

print('SIM_HOST_REHAB_USER_QA_OK')
PY
