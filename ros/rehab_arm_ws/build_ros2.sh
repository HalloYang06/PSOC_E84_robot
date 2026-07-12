#!/usr/bin/env bash
set -eo pipefail

cd "$(dirname "$0")"

if [ -f /opt/ros/jazzy/setup.bash ]; then
  source /opt/ros/jazzy/setup.bash
elif [ -f /opt/ros/humble/setup.bash ]; then
  source /opt/ros/humble/setup.bash
else
  echo "ROS 2 setup.bash not found" >&2
  exit 1
fi

if [ -n "${ROS_DISTRO:-}" ]; then
  ROS_PYTHON_SITE="/opt/ros/${ROS_DISTRO}/lib/python$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')/site-packages"
  if [ -d "$ROS_PYTHON_SITE" ]; then
    export PYTHONPATH="$ROS_PYTHON_SITE:${PYTHONPATH:-}"
  fi
fi

set -u
colcon build --symlink-install "$@"
