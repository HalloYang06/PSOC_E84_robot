#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT=${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}
ROS_DISTRO_NAME=${ROS_DISTRO:-jazzy}
WORKSPACE="$REPO_ROOT/ros/rehab_arm_ws"

if [ ! -f "/opt/ros/$ROS_DISTRO_NAME/setup.bash" ]; then
  echo "missing ROS setup: /opt/ros/$ROS_DISTRO_NAME/setup.bash" >&2
  exit 2
fi
if ! python3 -c 'import mujoco' >/dev/null 2>&1; then
  echo "Python mujoco package is missing; install it in the Linux host environment first." >&2
  exit 3
fi
if [ ! -f "$WORKSPACE/src/rehab_arm_sim_mujoco/package.xml" ]; then
  echo "missing rehab_arm_sim_mujoco package under $WORKSPACE" >&2
  exit 4
fi

source "/opt/ros/$ROS_DISTRO_NAME/setup.bash"
cd "$WORKSPACE"
colcon build --packages-select rehab_arm_sim_mujoco --symlink-install

mkdir -p "$HOME/rehab_arm_vla"
cp "$REPO_ROOT/tools/linux/vla_mujoco_execution_agent.py" "$HOME/rehab_arm_vla/"
cp "$REPO_ROOT/tools/linux/three_motor_visual_zero_ik.py" "$HOME/rehab_arm_vla/"
chmod +x "$HOME/rehab_arm_vla/vla_mujoco_execution_agent.py"

cat > "$HOME/rehab_arm_vla/environment.example" <<'EOF'
REHAB_API_BASE=http://106.55.62.122:8011
REHAB_DEVICE_ID=nanopi-m5
REHAB_PROJECT_ID=e201f41c-25a6-46e1-baf8-be6dcb83284c
EOF

echo "installed shadow prerequisites under $WORKSPACE/install and $HOME/rehab_arm_vla"
echo "no hardware transmission was enabled"
