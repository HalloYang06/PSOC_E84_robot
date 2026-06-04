#!/usr/bin/env bash
# Read-only NanoPi/M33 live telemetry acceptance check.
#
# This script validates the formal telemetry path after power-on or M33 flashing:
#   NanoPi can0 -> M33 0x322 status -> M33 0x330~0x337 motor telemetry -> ROS topics
#
# Safety boundary:
# - Sends only NanoPi heartbeat 0x321.
# - Optionally toggles a private motor active-report telemetry switch for a short time.
# - Starts the ROS bridge with enable_target_tx=false, or reuses the product
#   read-only bridge when USE_EXISTING_BRIDGE=1.
# - Never publishes JointTrajectory and never sends 0x320 target frames.

set -euo pipefail

IFACE="${IFACE:-can0}"
WORKSPACE="${WORKSPACE:-/home/pi/rehab_arm_ros2_ws}"
ACTIVE_REPORT_MOTOR="${ACTIVE_REPORT_MOTOR:-7}"
SNAPSHOT_SECONDS="${SNAPSHOT_SECONDS:-5}"
ECHO_TIMEOUT_SECONDS="${ECHO_TIMEOUT_SECONDS:-10}"
BUILD_WORKSPACE="${BUILD_WORKSPACE:-0}"
TMP_DIR="${TMP_DIR:-/tmp/rehab_arm_live_check}"
USE_EXISTING_BRIDGE="${USE_EXISTING_BRIDGE:-0}"
CHECK_SIM_SHADOW="${CHECK_SIM_SHADOW:-0}"
SIM_JOINT_STATE_TOPIC="${SIM_JOINT_STATE_TOPIC:-/sim/medical_arm/joint_states}"
ROS_NETWORK_ENV="${ROS_NETWORK_ENV:-$HOME/.rehab_arm_ros2_network}"

mkdir -p "$TMP_DIR"

HB_LOG="$TMP_DIR/heartbeat.log"
BRIDGE_LOG="$TMP_DIR/bridge.log"
SNAPSHOT_LOG="$TMP_DIR/snapshot.json"
MOTOR_STATE_LOG="$TMP_DIR/motor_state.txt"
JOINT_STATE_LOG="$TMP_DIR/joint_states.txt"
SAFETY_STATE_LOG="$TMP_DIR/safety_state.txt"
SIM_JOINT_STATE_LOG="$TMP_DIR/sim_joint_states.txt"
TOPICS_LOG="$TMP_DIR/topics.txt"
TARGET_FRAME_LOG="$TMP_DIR/target_0x320.log"

need_cmd() {
    if ! command -v "$1" >/dev/null 2>&1; then
        echo "FAIL: missing command: $1" >&2
        exit 2
    fi
}

wait_for_topic() {
    local topic="$1"
    local timeout_seconds="$2"
    local start_ts now_ts
    start_ts="$(date +%s)"
    while true; do
        if ros2 topic list 2>/dev/null | grep -Fxq "$topic"; then
            return 0
        fi
        now_ts="$(date +%s)"
        if [ "$((now_ts - start_ts))" -ge "$timeout_seconds" ]; then
            return 1
        fi
        sleep 0.5
    done
}

capture_topic_once() {
    local topic="$1"
    local msg_type="$2"
    local output_log="$3"
    local expect_pattern="$4"
    local timeout_seconds="$5"
    local attempts="${6:-3}"
    local attempt

    : > "$output_log"
    if ! wait_for_topic "$topic" "$timeout_seconds"; then
        echo "topic not discovered within ${timeout_seconds}s: $topic" >> "$output_log"
        return 1
    fi

    for attempt in $(seq 1 "$attempts"); do
        {
            echo "# attempt $attempt/$attempts topic=$topic type=$msg_type"
            timeout "$timeout_seconds" ros2 topic echo --once "$topic" "$msg_type"
        } >> "$output_log" 2>&1 || true
        if grep -q "$expect_pattern" "$output_log"; then
            return 0
        fi
        sleep 1.0
    done

    return 1
}

cleanup() {
    if [ "${BRIDGE_PID:-}" ]; then
        kill "$BRIDGE_PID" 2>/dev/null || true
        wait "$BRIDGE_PID" 2>/dev/null || true
    fi
}
trap cleanup EXIT

need_cmd ip
need_cmd candump
need_cmd cansend
need_cmd timeout
need_cmd python3
need_cmd date

if [ ! -d "$WORKSPACE" ]; then
    echo "FAIL: ROS workspace not found: $WORKSPACE" >&2
    exit 2
fi

echo "=== Rehab arm live telemetry check ==="
echo "iface=$IFACE workspace=$WORKSPACE active_report_motor=$ACTIVE_REPORT_MOTOR"
echo "use_existing_bridge=$USE_EXISTING_BRIDGE check_sim_shadow=$CHECK_SIM_SHADOW"
echo "ros_network_env=$ROS_NETWORK_ENV"
echo "Safety: no JointTrajectory, no 0x320, bridge enable_target_tx=false"
echo

echo "--- CAN status ---"
ip -details link show "$IFACE"
if ! ip -details link show "$IFACE" | grep -q "state ERROR-ACTIVE"; then
    echo "FAIL: $IFACE is not ERROR-ACTIVE" >&2
    exit 1
fi

echo
echo "--- M33 heartbeat/status probe ---"
rm -f "$HB_LOG"
timeout 4 candump -L "$IFACE",322:7FF,330:7F8 > "$HB_LOG" &
DUMP_PID=$!
sleep 0.3
cansend "$IFACE" 321#01
wait "$DUMP_PID" || true
cat "$HB_LOG"
if ! grep -q " 322#" "$HB_LOG"; then
    echo "FAIL: no M33 0x322 status reply after 0x321 heartbeat" >&2
    exit 1
fi

if [ "$BUILD_WORKSPACE" = "1" ]; then
    echo
    echo "--- Optional ROS workspace build ---"
    (cd "$WORKSPACE" && ./build_ros2.sh)
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
    echo "FAIL: neither /opt/ros/jazzy nor /opt/ros/humble exists" >&2
    exit 2
fi

if [ -n "${ROS_DISTRO:-}" ]; then
    ROS_PYTHON_SITE="/opt/ros/${ROS_DISTRO}/lib/python$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')/site-packages"
    if [ -d "$ROS_PYTHON_SITE" ]; then
        export PYTHONPATH="$ROS_PYTHON_SITE:${PYTHONPATH:-}"
    fi
fi

if [ -f "$ROS_NETWORK_ENV" ]; then
    set +u
    # shellcheck disable=SC1090
    source "$ROS_NETWORK_ENV"
    set -u
fi

set +u
# shellcheck disable=SC1091
source "$WORKSPACE/install/setup.bash"
set -u

echo
echo "--- ROS bridge read-only check ---"
rm -f "$BRIDGE_LOG" "$SNAPSHOT_LOG" "$MOTOR_STATE_LOG" "$JOINT_STATE_LOG" \
    "$SAFETY_STATE_LOG" "$SIM_JOINT_STATE_LOG" "$TOPICS_LOG" "$TARGET_FRAME_LOG"
timeout "$((SNAPSHOT_SECONDS + ECHO_TIMEOUT_SECONDS + 4))" candump -L "$IFACE",320:7FF > "$TARGET_FRAME_LOG" &
TARGET_DUMP_PID=$!
if [ "$USE_EXISTING_BRIDGE" = "1" ]; then
    {
        echo "Using existing read-only bridge; this script will not start another bridge."
        systemctl is-active rehab-arm-nanopi-readonly.service 2>/dev/null || true
        systemctl is-enabled rehab-arm-nanopi-readonly.service 2>/dev/null || true
    } > "$BRIDGE_LOG" 2>&1
    BRIDGE_PID=""
else
    ros2 run rehab_arm_psoc_bridge psoc_can_bridge_node.py \
        --ros-args \
        -p interface:="$IFACE" \
        -p enable_target_tx:=false \
        > "$BRIDGE_LOG" 2>&1 &
    BRIDGE_PID=$!
fi
sleep 1.0

timeout "$ECHO_TIMEOUT_SECONDS" ros2 topic echo --once \
    /rehab_arm/safety_state std_msgs/msg/String > "$SAFETY_STATE_LOG" 2>&1 &
SAFETY_ECHO_PID=$!
timeout "$ECHO_TIMEOUT_SECONDS" ros2 topic echo --once \
    /rehab_arm/motor_state std_msgs/msg/String > "$MOTOR_STATE_LOG" 2>&1 &
MOTOR_ECHO_PID=$!
timeout "$ECHO_TIMEOUT_SECONDS" ros2 topic echo --once \
    /joint_states sensor_msgs/msg/JointState > "$JOINT_STATE_LOG" 2>&1 &
JOINT_ECHO_PID=$!
if [ "$CHECK_SIM_SHADOW" = "1" ]; then
    capture_topic_once "$SIM_JOINT_STATE_TOPIC" sensor_msgs/msg/JointState \
        "$SIM_JOINT_STATE_LOG" jian_xuanzhuan_joint \
        "$((ECHO_TIMEOUT_SECONDS + 5))" 4 &
    SIM_ECHO_PID=$!
fi

if [ "$ACTIVE_REPORT_MOTOR" != "none" ]; then
    (cd "$WORKSPACE" && python3 src/rehab_arm_psoc_bridge/rehab_arm_psoc_bridge/live_socketcan_motor_snapshot.py \
        --iface "$IFACE" \
        --duration "$SNAPSHOT_SECONDS" \
        --enable-active-report "$ACTIVE_REPORT_MOTOR" \
        > "$SNAPSHOT_LOG" 2>&1)
else
    sleep "$SNAPSHOT_SECONDS"
fi

wait "$SAFETY_ECHO_PID" || true
wait "$MOTOR_ECHO_PID" || true
wait "$JOINT_ECHO_PID" || true
if [ "${SIM_ECHO_PID:-}" ]; then
    wait "$SIM_ECHO_PID" || true
fi
ros2 topic list -t > "$TOPICS_LOG" 2>&1 || true
kill "$TARGET_DUMP_PID" 2>/dev/null || true
wait "$TARGET_DUMP_PID" 2>/dev/null || true

cleanup
BRIDGE_PID=""

echo "--- topics ---"
cat "$TOPICS_LOG"
echo "--- bridge log ---"
tail -80 "$BRIDGE_LOG"
echo "--- snapshot summary ---"
if [ -s "$SNAPSHOT_LOG" ]; then
    cat "$SNAPSHOT_LOG"
else
    echo "snapshot disabled or no snapshot output"
fi
echo "--- /rehab_arm/safety_state ---"
cat "$SAFETY_STATE_LOG" || true
echo "--- /rehab_arm/motor_state ---"
cat "$MOTOR_STATE_LOG" || true
echo "--- /joint_states ---"
cat "$JOINT_STATE_LOG" || true
if [ "$CHECK_SIM_SHADOW" = "1" ]; then
    echo "--- $SIM_JOINT_STATE_TOPIC ---"
    cat "$SIM_JOINT_STATE_LOG" || true
fi
echo "--- unexpected 0x320 frames ---"
cat "$TARGET_FRAME_LOG" || true

if [ -s "$TARGET_FRAME_LOG" ]; then
    echo "FAIL: observed unexpected 0x320 target frame during read-only check" >&2
    exit 1
fi
if ! grep -q "/rehab_arm/motor_state" "$TOPICS_LOG"; then
    echo "FAIL: /rehab_arm/motor_state topic not present" >&2
    exit 1
fi
if ! grep -q "data:" "$SAFETY_STATE_LOG"; then
    echo "FAIL: no /rehab_arm/safety_state message captured" >&2
    exit 1
fi
if ! grep -q "data:" "$MOTOR_STATE_LOG"; then
    echo "FAIL: no /rehab_arm/motor_state message captured" >&2
    exit 1
fi
if ! grep -q "name:" "$JOINT_STATE_LOG"; then
    echo "FAIL: no /joint_states message captured" >&2
    exit 1
fi
if [ "$CHECK_SIM_SHADOW" = "1" ]; then
    if ! grep -q "$SIM_JOINT_STATE_TOPIC" "$TOPICS_LOG"; then
        echo "FAIL: $SIM_JOINT_STATE_TOPIC topic not present" >&2
        exit 1
    fi
    if ! grep -q "jian_xuanzhuan_joint" "$SIM_JOINT_STATE_LOG"; then
        echo "FAIL: no 6DOF medical arm shadow JointState captured" >&2
        exit 1
    fi
fi
if [ "$ACTIVE_REPORT_MOTOR" != "none" ] && ! grep -q '"0x33' "$SNAPSHOT_LOG"; then
    echo "FAIL: snapshot did not observe any M33 0x330~0x337 telemetry count" >&2
    exit 1
fi

echo
echo "PASS: live telemetry path is valid and read-only."
