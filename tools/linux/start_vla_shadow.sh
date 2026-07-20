#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT=${REHAB_ARM_REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}
ROS_DISTRO_NAME=${ROS_DISTRO:-jazzy}
API_BASE=${REHAB_API_BASE:-http://106.55.62.122:8011}
DEVICE_ID=${REHAB_DEVICE_ID:-nanopi-m5}
PROJECT_ID=${REHAB_PROJECT_ID:-e201f41c-25a6-46e1-baf8-be6dcb83284c}
WORKSPACE="$REPO_ROOT/ros/rehab_arm_ws"

source "/opt/ros/$ROS_DISTRO_NAME/setup.bash"
source "$WORKSPACE/install/setup.bash"

ros2 launch rehab_arm_sim_mujoco medical_arm_visual_zero_3motor_shadow.launch.py enable_viewer:=true &
LAUNCH_PID=$!
trap 'kill "$LAUNCH_PID" 2>/dev/null || true' EXIT INT TERM

for _ in $(seq 1 50); do
  if ros2 topic list | grep -qx '/sim/medical_arm/joint_states'; then
    break
  fi
  sleep 0.1
done
if ! ros2 topic list | grep -qx '/sim/medical_arm/joint_states'; then
  echo "MuJoCo shadow topic did not appear" >&2
  exit 5
fi

python3 "$REPO_ROOT/tools/linux/vla_mujoco_execution_agent.py" \
  --api-base "$API_BASE" \
  --device-id "$DEVICE_ID" \
  --project-id "$PROJECT_ID"
