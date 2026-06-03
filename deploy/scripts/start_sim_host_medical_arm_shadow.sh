#!/usr/bin/env bash
set -euo pipefail

WORKSPACE="${WORKSPACE:-/home/cal/桌面/Medical-Rehabilitation-Manipulator/rehab_arm_ros2_ws}"
ROS_NETWORK_ENV="${ROS_NETWORK_ENV:-/home/cal/.rehab_arm_ros2_network}"

if [ -f /opt/ros/jazzy/setup.bash ]; then
  # shellcheck disable=SC1091
  source /opt/ros/jazzy/setup.bash
elif [ -f /opt/ros/humble/setup.bash ]; then
  # shellcheck disable=SC1091
  source /opt/ros/humble/setup.bash
else
  echo "No supported ROS setup.bash found under /opt/ros" >&2
  exit 2
fi

if [ -f "$ROS_NETWORK_ENV" ]; then
  # shellcheck disable=SC1090
  source "$ROS_NETWORK_ENV"
fi

if [ ! -f "$WORKSPACE/install/setup.bash" ]; then
  echo "ROS workspace install setup not found: $WORKSPACE/install/setup.bash" >&2
  exit 2
fi

# shellcheck disable=SC1090
source "$WORKSPACE/install/setup.bash"

exec ros2 launch rehab_arm_sim_mujoco medical_arm_6dof_hardware_shadow.launch.py
