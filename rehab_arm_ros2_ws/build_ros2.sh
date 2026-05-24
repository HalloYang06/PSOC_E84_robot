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

set -u
colcon build --symlink-install "$@"
