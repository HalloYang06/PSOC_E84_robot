#!/usr/bin/env bash
set -euo pipefail

WORKSPACE="${WORKSPACE:-/home/pi/rehab_arm_ros2_ws}"
IFACE="${IFACE:-can0}"
CAN_BITRATE="${CAN_BITRATE:-1000000}"
CAN_RESTART_MS="${CAN_RESTART_MS:-100}"
RECOVER_MCP251XFD="${RECOVER_MCP251XFD:-1}"
ROS_NETWORK_ENV="${ROS_NETWORK_ENV:-/home/pi/.rehab_arm_ros2_network}"
ROS_LOG_DIR="${ROS_LOG_DIR:-/home/pi/.ros/log}"
SKIP_SOCKETCAN_SETUP="${SKIP_SOCKETCAN_SETUP:-0}"
mkdir -p "$ROS_LOG_DIR"
chmod 0775 "$ROS_LOG_DIR" 2>/dev/null || true
export ROS_LOG_DIR

ensure_socketcan() {
  SUDO=""
  if [ "$(id -u)" -ne 0 ]; then
    SUDO="sudo"
  fi

  if ! ip link show "$IFACE" >/dev/null 2>&1 && [ "$RECOVER_MCP251XFD" = "1" ]; then
    $SUDO modprobe -r mcp251xfd 2>/dev/null || true
    sleep 1
    $SUDO modprobe mcp251xfd 2>/dev/null || true
    sleep 2
  fi

  if ! ip link show "$IFACE" >/dev/null 2>&1; then
    echo "SocketCAN interface not found: $IFACE" >&2
    exit 2
  fi

  $SUDO ip link set "$IFACE" down 2>/dev/null || true
  $SUDO ip link set "$IFACE" type can bitrate "$CAN_BITRATE" restart-ms "$CAN_RESTART_MS" berr-reporting on
  $SUDO ip link set "$IFACE" up
  ip -details link show "$IFACE"
}

if [ "$SKIP_SOCKETCAN_SETUP" != "1" ]; then
  ensure_socketcan
fi

if [ -f /opt/ros/jazzy/setup.bash ]; then
  set +u
  # shellcheck disable=SC1091
  source /opt/ros/jazzy/setup.bash
  set -u
elif [ -f /opt/ros/humble/setup.bash ]; then
  set +u
  # shellcheck disable=SC1091
  source /opt/ros/humble/setup.bash
  set -u
else
  echo "No supported ROS setup.bash found under /opt/ros" >&2
  exit 2
fi

if [ -f "$ROS_NETWORK_ENV" ]; then
  set +u
  # shellcheck disable=SC1090
  source "$ROS_NETWORK_ENV"
  set -u
fi

if [ ! -f "$WORKSPACE/install/setup.bash" ]; then
  echo "ROS workspace install setup not found: $WORKSPACE/install/setup.bash" >&2
  exit 2
fi

# shellcheck disable=SC1090
set +u
source "$WORKSPACE/install/setup.bash"
set -u

exec ros2 run rehab_arm_psoc_bridge psoc_can_bridge_node.py --ros-args \
  -p interface:="$IFACE" \
  -p enable_target_tx:=false \
  -p log_heartbeat:=false
